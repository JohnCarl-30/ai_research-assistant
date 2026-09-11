"""The pipeline's transient-failure handling.

Two things are covered here, and the first is why the second is worth having.

`RetryPolicy`'s default predicate decides what counts as worth retrying. The
existing retry test in test_e2e.py passes its own `retry_on`, so it never
exercised that default — and the default used to be
`isinstance(e, (TimeoutError, ConnectionError))`, which matches none of the
errors this codebase actually raises. Every retried call goes through the
OpenAI client, whose transient errors descend from openai.OpenAIError.
"""

import httpx
import openai
import pytest

from app.agents import pipeline
from app.agents.error_handler import RetryPolicy, is_transient, with_retry


def _openai_timeout() -> openai.APITimeoutError:
    return openai.APITimeoutError(request=httpx.Request("POST", "https://api.openai.com/v1"))


def _rate_limit() -> openai.RateLimitError:
    request = httpx.Request("POST", "https://api.openai.com/v1")
    response = httpx.Response(429, request=request)
    return openai.RateLimitError("rate limited", response=response, body=None)


def _auth_error() -> openai.AuthenticationError:
    request = httpx.Request("POST", "https://api.openai.com/v1")
    response = httpx.Response(401, request=request)
    return openai.AuthenticationError("bad key", response=response, body=None)


class TestTransientClassification:
    @pytest.mark.parametrize(
        "error",
        [
            TimeoutError("slow"),
            ConnectionError("refused"),
            httpx.ConnectError("refused"),
            _openai_timeout(),
            _rate_limit(),
        ],
        ids=[
            "builtin-timeout",
            "builtin-connection",
            "httpx-connect",
            "openai-timeout",
            "openai-429",
        ],
    )
    def test_transient_errors_are_retried(self, error):
        assert is_transient(error) is True
        assert RetryPolicy().retry_on(error) is True

    @pytest.mark.parametrize(
        "error",
        [_auth_error(), ValueError("bad input"), KeyError("missing")],
        ids=["openai-401", "value-error", "key-error"],
    )
    def test_permanent_errors_are_not_retried(self, error):
        """Retrying these re-sends a request that is wrong, not unlucky."""
        assert is_transient(error) is False
        assert RetryPolicy().retry_on(error) is False

    async def test_default_policy_retries_an_openai_timeout(self):
        """The regression this file exists for: with the old default, a call
        raising APITimeoutError was tried exactly once and the error surfaced."""
        calls = 0

        async def flaky():
            nonlocal calls
            calls += 1
            if calls < 3:
                raise _openai_timeout()
            return "recovered"

        result = await with_retry(flaky, policy=RetryPolicy(max_attempts=3, initial_interval=0.01))
        assert result == "recovered"
        assert calls == 3

    async def test_permanent_error_fails_on_the_first_attempt(self):
        calls = 0

        async def broken():
            nonlocal calls
            calls += 1
            raise _auth_error()

        with pytest.raises(openai.AuthenticationError):
            await with_retry(broken, policy=RetryPolicy(max_attempts=3, initial_interval=0.01))
        assert calls == 1


class TestPipelineNodesRetry:
    """The nodes reaching the network retry, rather than failing the run."""

    async def test_research_retries_then_succeeds(self, monkeypatch):
        calls = 0

        async def flaky_research(company_name):
            nonlocal calls
            calls += 1
            if calls < 2:
                raise _rate_limit()
            return {"summary": f"about {company_name}"}

        monkeypatch.setattr(pipeline, "research_company", flaky_research)
        policy = RetryPolicy(max_attempts=3, initial_interval=0.01)
        monkeypatch.setattr(pipeline, "ITEM_RETRY", policy)

        out = await pipeline.research_companies({"new_companies": ["Ledgerline"]})

        assert calls == 2
        assert out["companies_researched"]["Ledgerline"] == {"summary": "about Ledgerline"}

    async def test_research_records_the_error_once_retries_are_exhausted(self, monkeypatch):
        async def always_rate_limited(company_name):
            raise _rate_limit()

        monkeypatch.setattr(pipeline, "research_company", always_rate_limited)
        policy = RetryPolicy(max_attempts=2, initial_interval=0.01)
        monkeypatch.setattr(pipeline, "ITEM_RETRY", policy)

        out = await pipeline.research_companies({"new_companies": ["Northwind"]})

        # One company failing is a gap in the results, not a dead run.
        assert "error" in out["companies_researched"]["Northwind"]
        assert out["status"] == "researched"

    async def test_scrape_retries_a_transient_network_failure(self, monkeypatch):
        calls = 0

        class FlakyScraper:
            async def scrape_all(self, query, location):
                nonlocal calls
                calls += 1
                if calls < 2:
                    raise httpx.ConnectError("connection refused")
                return ([], [], [])

        monkeypatch.setattr(pipeline, "JobScraper", FlakyScraper)
        policy = RetryPolicy(max_attempts=3, initial_interval=0.01)
        monkeypatch.setattr(pipeline, "SCRAPE_RETRY", policy)

        out = await pipeline.scrape_jobs({"query": "rust", "location": "remote"})

        assert calls == 2
        assert out["status"] == "scraped"
        assert out.get("error") is None

    async def test_scrape_reports_failure_after_exhausting_retries(self, monkeypatch):
        class DeadScraper:
            async def scrape_all(self, query, location):
                raise httpx.ConnectError("connection refused")

        monkeypatch.setattr(pipeline, "JobScraper", DeadScraper)
        policy = RetryPolicy(max_attempts=2, initial_interval=0.01)
        monkeypatch.setattr(pipeline, "SCRAPE_RETRY", policy)

        out = await pipeline.scrape_jobs({"query": "rust", "location": ""})

        assert out["status"] == "failed"
        assert out["jobs_found"] == 0
        assert "connection refused" in out["error"]

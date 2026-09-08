"""End-to-end tests for Scout pipeline."""

import pytest
import uuid
from unittest.mock import AsyncMock, patch, MagicMock


class TestE2EAPIRoutes:
    """End-to-end API route tests."""

    @pytest.mark.asyncio
    async def test_health_endpoint(self, client):
        """Test health check endpoint."""
        response = await client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    @pytest.mark.asyncio
    async def test_root_endpoint(self, client):
        """Test root endpoint."""
        response = await client.get("/")
        assert response.status_code == 200
        assert "message" in response.json()

    @pytest.mark.asyncio
    async def test_cover_letter_endpoint(self, client):
        """Test cover letter generation endpoint."""
        with patch("app.agents.cover_letter.generate_cover_letter", new_callable=AsyncMock) as mock:
            mock.return_value = {
                "cover_letter": "Test cover letter",
                "job_title": "Python Developer",
                "company_name": "TestCorp",
            }
            response = await client.get(
                "/api/cover-letter",
                params={
                    "job_title": "Python Developer",
                    "company_name": "TestCorp",
                    "skills": "Python,FastAPI",
                },
            )
            assert response.status_code == 200
            data = response.json()
            assert "cover_letter" in data

    @pytest.mark.asyncio
    async def test_rag_search_endpoint(self, client):
        """Test RAG search endpoint."""
        with patch("app.rag.retriever.retrieve", new_callable=AsyncMock) as mock:
            mock.return_value = []
            response = await client.get(
                "/api/rag/search",
                params={"q": "python developer", "top_k": 5},
            )
            assert response.status_code == 200
            data = response.json()
            assert "query" in data
            assert "results" in data

    @pytest.mark.asyncio
    async def test_rag_ask_endpoint(self, client):
        """Test RAG ask endpoint."""
        mock_result = MagicMock()
        mock_result.question = "What?"
        mock_result.answer = "Test answer"
        mock_result.contexts = []
        mock_result.retrieved = []

        with patch("app.rag.qa.answer_job_question", new_callable=AsyncMock) as mock:
            mock.return_value = mock_result
            response = await client.post(
                "/api/rag/ask",
                json={"question": "What companies are hiring?", "top_k": 5},
            )
            assert response.status_code == 200
            data = response.json()
            assert "answer" in data

    @pytest.mark.asyncio
    async def test_rag_index_endpoint(self, client):
        """Test RAG index endpoint."""
        with patch("app.rag.vector_store.index_jobs", new_callable=AsyncMock) as mock_index:
            mock_index.return_value = 10
            with patch("app.rag.vector_store.unindexed_jobs", new_callable=AsyncMock) as mock_unindexed:
                mock_unindexed.return_value = []
                response = await client.post(
                    "/api/rag/index",
                    json={"limit": 100, "reindex_all": False},
                )
                assert response.status_code == 200
                data = response.json()
                assert "jobs_indexed" in data

    @pytest.mark.asyncio
    async def test_jobs_endpoint(self, client):
        """Test jobs listing endpoint."""
        response = await client.get("/api/jobs")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data

    @pytest.mark.asyncio
    async def test_companies_endpoint(self, client):
        """Test companies listing endpoint."""
        response = await client.get("/api/companies")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data

    @pytest.mark.asyncio
    async def test_tags_endpoint(self, client):
        """Test tags listing endpoint."""
        response = await client.get("/api/tags")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data


class TestE2EErrorHandling:
    """End-to-end error handling tests."""

    @pytest.mark.asyncio
    async def test_retry_policy(self):
        """Test retry policy with exponential backoff."""
        from app.agents.error_handler import RetryPolicy, with_retry

        call_count = 0

        async def failing_function():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("Temporary failure")
            return "success"

        policy = RetryPolicy(
            max_attempts=3,
            initial_interval=0.01,
            retry_on=lambda e: isinstance(e, ConnectionError),
        )

        result = await with_retry(failing_function, policy=policy)
        assert result == "success"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_circuit_breaker(self):
        """Test circuit breaker pattern."""
        from app.agents.error_handler import CircuitBreaker

        breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=0.1)

        assert breaker.can_execute() is True

        for _ in range(3):
            breaker.record_failure()

        assert breaker.can_execute() is False

        import asyncio
        await asyncio.sleep(0.15)

        assert breaker.can_execute() is True

        breaker.record_success()
        assert breaker.can_execute() is True

    @pytest.mark.asyncio
    async def test_prompt_versioning(self):
        """Test prompt version registry."""
        from app.prompts import get_prompt, list_versions

        versions = list_versions()
        assert "cover_letter" in versions
        assert "research" in versions
        assert "matching" in versions

        prompt = get_prompt("cover_letter", "v2")
        assert prompt is not None

        prompt_v1 = get_prompt("cover_letter", "v1")
        assert prompt_v1 is not None

    @pytest.mark.asyncio
    async def test_pipeline_state_typed_dict(self):
        """Test PipelineState is TypedDict."""
        from app.agents.pipeline import PipelineState
        from typing import get_type_hints

        hints = get_type_hints(PipelineState)
        assert "query" in hints
        assert "status" in hints
        assert "jobs" in hints

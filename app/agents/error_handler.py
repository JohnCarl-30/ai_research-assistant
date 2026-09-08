"""Error handling patterns for LangGraph agents.

Provides:
- Retry policies with exponential backoff
- LLM-guided error recovery
- Circuit breaker pattern
"""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class RetryPolicy:
    """Retry policy with exponential backoff."""
    max_attempts: int = 3
    initial_interval: float = 1.0
    backoff_factor: float = 2.0
    max_interval: float = 60.0
    retry_on: Callable[[Exception], bool] = field(
        default_factory=lambda: lambda e: isinstance(e, (TimeoutError, ConnectionError))
    )

    def get_delay(self, attempt: int) -> float:
        delay = self.initial_interval * (self.backoff_factor ** attempt)
        return min(delay, self.max_interval)


class CircuitBreaker:
    """Circuit breaker to prevent repeated failures."""

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time: float | None = None
        self.state = "closed"  # closed, open, half-open

    def record_failure(self):
        self.failure_count += 1
        if self.failure_count >= self.failure_threshold:
            self.state = "open"
            self.last_failure_time = time.time()

    def record_success(self):
        self.failure_count = 0
        self.state = "closed"

    def can_execute(self) -> bool:
        if self.state == "closed":
            return True
        if self.state == "open":
            if self.last_failure_time and time.time() - self.last_failure_time > self.recovery_timeout:
                self.state = "half-open"
                return True
            return False
        return True  # half-open


async def with_retry(
    func: Callable,
    *args,
    policy: RetryPolicy | None = None,
    **kwargs,
) -> Any:
    """Execute a function with retry logic."""
    policy = policy or RetryPolicy()
    last_exception = None

    for attempt in range(policy.max_attempts):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            last_exception = e
            if not policy.retry_on(e):
                raise
            if attempt < policy.max_attempts - 1:
                delay = policy.get_delay(attempt)
                await asyncio.sleep(delay)

    raise last_exception


async def llm_guided_recovery(
    error: Exception,
    context: list[dict],
    llm,
) -> dict:
    """Use LLM to suggest recovery strategy."""
    recovery_prompt = f"""The previous step failed with error: {type(error).__name__}: {str(error)}

Recent context:
{context[-3:] if len(context) > 3 else context}

Analyze this error and suggest the best recovery strategy:
1. RETRY - if the error is transient (timeout, rate limit)
2. SIMPLIFY - if the task is too complex
3. SKIP - if the step is non-critical
4. ESCALATE - if human intervention is needed

Respond with JSON: {{"action": "RETRY|SIMPLIFY|SKIP|ESCALATE", "reason": "...", "simplified_task": "..."}}"""

    from langchain_core.messages import HumanMessage
    response = await llm.ainvoke([HumanMessage(content=recovery_prompt)])

    import json
    try:
        return json.loads(response.content)
    except json.JSONDecodeError:
        return {"action": "ESCALATE", "reason": "Could not parse recovery suggestion"}

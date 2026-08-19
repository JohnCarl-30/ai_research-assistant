"""Human-in-the-loop approval gates for LangGraph agents.

Uses LangGraph's interrupt() to pause execution and wait for human approval.
"""

from dataclasses import dataclass
from typing import Any

from langgraph.types import interrupt


@dataclass
class ApprovalRequest:
    """Request for human approval."""
    action: str
    description: str
    data: Any
    risk_level: str = "low"  # low, medium, high


def should_require_approval(action_type: str, confidence: float = 1.0) -> bool:
    """Determine if an action requires human approval."""
    high_risk_actions = ["send_email", "apply_to_job", "modify_database"]
    medium_risk_actions = ["generate_cover_letter", "research_company"]

    if action_type in high_risk_actions:
        return True
    if action_type in medium_risk_actions and confidence < 0.8:
        return True
    return False


def request_approval(
    action: str,
    description: str,
    data: Any,
    risk_level: str = "low",
) -> dict:
    """Pause execution and request human approval.

    This uses LangGraph's interrupt() to pause the graph and surface
    the approval request to the caller. The graph resumes when the
    human provides a decision.
    """
    decision = interrupt({
        "type": "approval_request",
        "action": action,
        "description": description,
        "data": data,
        "risk_level": risk_level,
    })

    return {
        "approved": decision.get("approved", False),
        "notes": decision.get("notes", ""),
        "action": action,
    }


def approve_cover_letter(
    job_title: str,
    company_name: str,
    cover_letter: str,
) -> dict:
    """Request approval before sending a cover letter."""
    return request_approval(
        action="send_cover_letter",
        description=f"Send cover letter for {job_title} at {company_name}?",
        data={
            "job_title": job_title,
            "company_name": company_name,
            "cover_letter": cover_letter,
        },
        risk_level="medium",
    )


def approve_email(
    recipient: str,
    subject: str,
    body: str,
) -> dict:
    """Request approval before sending an email."""
    return request_approval(
        action="send_email",
        description=f"Send email to {recipient}?",
        data={
            "recipient": recipient,
            "subject": subject,
            "body": body,
        },
        risk_level="high",
    )


def approve_job_application(
    job_title: str,
    company_name: str,
    job_url: str,
) -> dict:
    """Request approval before applying to a job."""
    return request_approval(
        action="apply_to_job",
        description=f"Apply to {job_title} at {company_name}?",
        data={
            "job_title": job_title,
            "company_name": company_name,
            "job_url": job_url,
        },
        risk_level="high",
    )

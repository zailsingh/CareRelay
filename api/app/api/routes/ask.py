from hashlib import sha256
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import DbSession, ProfileMemberAccess
from app.core.config import get_settings
from app.models.ask_audit import AskAudit
from app.schemas.ask import AskRequest, AskResponse
from app.services.ai_provider import AIProvider, AIProviderError, get_ai_provider
from app.services.ask_care_relay import answer_question
from app.services.care_insights import ToolCallLimitExceeded

router = APIRouter()
AIProviderDep = Annotated[AIProvider, Depends(get_ai_provider)]


@router.post("/{care_profile_id}/ask", response_model=AskResponse)
async def ask_care_relay(
    care_profile_id: UUID,
    payload: AskRequest,
    db: DbSession,
    access: ProfileMemberAccess,
    provider: AIProviderDep,
) -> AskResponse:
    settings = get_settings()
    question_hash = sha256(payload.question.encode()).hexdigest()
    try:
        result = await answer_question(
            db=db,
            care_profile_id=access.profile.id,
            timezone_name=access.profile.timezone,
            question=payload.question,
            provider=provider,
            max_tool_calls=settings.ai_max_tool_calls,
        )
    except (AIProviderError, ToolCallLimitExceeded) as exc:
        db.add(
            AskAudit(
                care_profile_id=access.profile.id,
                actor_user_id=access.membership.user_id,
                question_hash=question_hash,
                provider=provider.name,
                model=provider.model,
                tool_names=[],
                evidence_count=0,
                status="failed",
                error_code=type(exc).__name__,
            )
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Ask CareRelay could not produce a verified answer",
        ) from exc
    db.add(
        AskAudit(
            care_profile_id=access.profile.id,
            actor_user_id=access.membership.user_id,
            question_hash=question_hash,
            provider=result.diagnostics.provider,
            model=result.diagnostics.model,
            tool_names=result.diagnostics.tools_used,
            evidence_count=len(result.evidence),
            status="succeeded",
        )
    )
    db.commit()
    return result

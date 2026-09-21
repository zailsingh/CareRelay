from uuid import UUID

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.models.enums import AuditAction


def add_audit_entry(
    db: Session,
    *,
    care_profile_id: UUID,
    actor_user_id: UUID,
    action: AuditAction,
    target_type: str,
    target_id: UUID | None,
    before_state: dict | None = None,
    after_state: dict | None = None,
) -> None:
    db.add(
        AuditLog(
            care_profile_id=care_profile_id,
            actor_user_id=actor_user_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            before_state=before_state,
            after_state=after_state,
        )
    )

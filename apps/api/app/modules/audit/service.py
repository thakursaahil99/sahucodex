from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.models import AuditLog


def record_audit(
    db: AsyncSession,
    action: str,
    *,
    actor_id: uuid.UUID | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """Stage an audit row in the caller's transaction (committed together with the action itself)."""
    db.add(
        AuditLog(
            actor_user_id=actor_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            ip_address=ip,
            user_agent=user_agent,
            details=details,
        )
    )

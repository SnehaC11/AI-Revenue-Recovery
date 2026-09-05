"""Atomic ownership of a recovery workflow execution."""

import uuid

from database.models import RecoveryCase
from services.stopping_rules import TERMINAL_STATUSES


def claim_case_execution(db, case_id):
    """Claim an actionable case once; returns the claimed case or ``None``.

    The conditional UPDATE is important: two dashboard clicks or two batch
    workers cannot both pass a read-then-write status check.
    """
    token = str(uuid.uuid4())
    updated = (
        db.query(RecoveryCase)
        .filter(
            RecoveryCase.case_id == case_id,
            RecoveryCase.status.notin_(
                [*TERMINAL_STATUSES, "RECOVERY_RUNNING"]
            ),
            RecoveryCase.recovery_attempts < 2,
        )
        .update(
            {
                "status": "RECOVERY_RUNNING",
                "execution_key": token,
            },
            synchronize_session=False,
        )
    )
    db.commit()
    if not updated:
        return None

    return db.query(RecoveryCase).filter(RecoveryCase.case_id == case_id).first()

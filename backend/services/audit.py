import json

from database.models import AuditLog


def record_audit(
    db,
    case_id,
    event_type,
    details=None,
):
    payload = details or {}

    if not isinstance(payload, str):
        payload = json.dumps(payload)

    event = AuditLog(
        case_id=case_id,
        event=event_type,
        details=payload,
    )

    db.add(event)

    return event

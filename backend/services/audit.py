import hashlib
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
        payload = json.dumps(payload, sort_keys=True, separators=(",", ":"))

    # Flush first so the immediately preceding event is visible even when a
    # batch writes several events in the same transaction.
    db.flush()
    previous_event = (
        db.query(AuditLog)
        .filter(AuditLog.case_id == case_id)
        .order_by(AuditLog.id.desc())
        .first()
    )
    previous_hash = (
        previous_event.event_hash if previous_event else None
    )
    digest_input = "|".join([
        previous_hash or "GENESIS",
        str(case_id),
        str(event_type),
        payload,
    ])
    event_hash = hashlib.sha256(
        digest_input.encode("utf-8")
    ).hexdigest()

    event = AuditLog(
        case_id=case_id,
        event=event_type,
        details=payload,
        previous_hash=previous_hash,
        event_hash=event_hash,
    )

    db.add(event)
    db.flush()

    return event


def verify_audit_chain(events):
    """Return a deterministic integrity result for a case audit export."""
    previous_hash = None
    for event in events:
        details = event.details or "{}"
        digest_input = "|".join([
            previous_hash or "GENESIS",
            str(event.case_id),
            str(event.event),
            details,
        ])
        expected_hash = hashlib.sha256(
            digest_input.encode("utf-8")
        ).hexdigest()
        if event.previous_hash != previous_hash or event.event_hash != expected_hash:
            return {
                "valid": False,
                "failed_event_id": event.id,
                "reason": "Audit hash chain does not match the stored events.",
            }
        previous_hash = event.event_hash
    return {
        "valid": True,
        "events_verified": len(events),
        "head_hash": previous_hash,
    }

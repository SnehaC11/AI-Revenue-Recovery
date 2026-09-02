import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from data.checkout_data import generate_checkout_events
from database.database import get_db
from database.models import AuditLog, Customer, RecoveryCase
from services.batch_recovery import (
    execute_batch_recovery,
    process_recovery_case,
)
from services.checkout_engine import create_checkout_cases
from services.checkout_recovery import (
    execute_checkout_recovery,
    safe_checkout_decision,
)
from services.risk_engine import create_recovery_cases


router = APIRouter(
    prefix="/recovery",
    tags=["Recovery"],
)

TERMINAL_STATUSES = {
    "RECOVERED",
    "ESCALATED",
    "STOPPED",
    "POLICY_BLOCKED",
}


@router.post("/detect")
def detect_revenue_at_risk(
    db: Session = Depends(get_db),
):
    cases = create_recovery_cases(db)

    total_at_risk = sum(
        float(case.amount_at_risk or 0)
        for case in cases
    )

    return {
        "cases_created": len(cases),
        "revenue_at_risk": round(total_at_risk, 2),
    }


@router.get("/cases")
def get_recovery_cases(
    db: Session = Depends(get_db),
):
    cases = (
        db.query(RecoveryCase)
        .order_by(RecoveryCase.risk_score.desc())
        .all()
    )

    return cases


@router.post("/cases/{case_id}/execute")
def execute_case(
    case_id: str,
    db: Session = Depends(get_db),
):
    case = _get_case_or_404(db, case_id)

    result = process_recovery_case(
        db=db,
        case=case,
        decision_function=safe_checkout_decision,
        execute_function=execute_checkout_recovery,
        commit=True,
    )

    result["already_processed"] = result["status"] in {
        "RECOVERED",
        "ESCALATED",
        "STOPPED",
        "POLICY_BLOCKED",
    } and "already ended" in (
        result.get("reason") or ""
    ).lower()

    return result


@router.post("/batch/execute")
def execute_recovery_batch(
    db: Session = Depends(get_db),
):
    cases = (
        db.query(RecoveryCase)
        .filter(
            RecoveryCase.status.notin_([
                "RECOVERED",
                "ESCALATED",
                "STOPPED",
                "POLICY_BLOCKED",
                "RECOVERY_RUNNING",
            ])
        )
        .order_by(RecoveryCase.expected_recovery.desc())
        .all()
    )

    if not cases:
        return {
            "cases_processed": 0,
            "recovered_cases": 0,
            "escalated_cases": 0,
            "stopped_cases": 0,
            "blocked_cases": 0,
            "revenue_at_risk": 0,
            "revenue_recovered": 0,
            "recovery_rate": 0,
            "results": [],
        }

    return execute_batch_recovery(
        db=db,
        cases=cases,
        decision_function=safe_checkout_decision,
        execute_function=execute_checkout_recovery,
    )


@router.get("/audit/{case_id}")
def get_case_audit(
    case_id: str,
    db: Session = Depends(get_db),
):
    logs = (
        db.query(AuditLog)
        .filter(AuditLog.case_id == case_id)
        .order_by(AuditLog.timestamp.asc())
        .all()
    )

    return {
        "case_id": case_id,
        "events": [
            {
                "event": log.event,
                "details": _parse_audit_details(
                    log.details
                ),
                "created_at": log.timestamp,
            }
            for log in logs
        ],
    }


@router.get("/risk-feed")
def get_risk_feed(
    db: Session = Depends(get_db),
):
    cases = (
        db.query(RecoveryCase)
        .filter(
            RecoveryCase.status.notin_(
                [
                    "RECOVERED",
                    "ESCALATED",
                    "STOPPED",
                    "POLICY_BLOCKED",
                ]
            )
        )
        .order_by(RecoveryCase.risk_score.desc())
        .limit(50)
        .all()
    )

    return [
        {
            "case_id": case.case_id,
            "customer_id": case.customer_id,
            "amount_at_risk": case.amount_at_risk,
            "amount_recovered": getattr(
                case,
                "amount_recovered",
                0,
            ),
            "risk_score": case.risk_score,
            "expected_recovery": case.expected_recovery,
            "selected_action": case.selected_action,
            "agent_reason": case.agent_reason,
            "status": case.status,
            "type": getattr(
                case,
                "recovery_type",
                "PAYMENT_FAILURE",
            ),
        }
        for case in cases
    ]


@router.post("/detect-checkouts")
def detect_checkouts(
    db: Session = Depends(get_db),
):
    customers = (
        db.query(Customer)
        .limit(500)
        .all()
    )

    events = generate_checkout_events(customers)
    cases = create_checkout_cases(db, events)

    return {
        "detected": len(cases),
        "total_revenue_at_risk": round(
            sum(
                float(case.amount_at_risk or 0)
                for case in cases
            ),
            2,
        ),
        "cases": [
            {
                "case_id": case.case_id,
                "customer_id": case.customer_id,
                "amount_at_risk": case.amount_at_risk,
                "risk_score": case.risk_score,
                "expected_recovery": case.expected_recovery,
                "recovery_type": case.recovery_type,
            }
            for case in cases
        ],
    }


@router.post("/checkout/{case_id}/execute")
def execute_checkout_case(
    case_id: str,
    db: Session = Depends(get_db),
):
    case = _get_case_or_404(db, case_id)

    if case.recovery_type != "CHECKOUT_ABANDONMENT":
        raise HTTPException(
            status_code=400,
            detail="Case is not a checkout recovery case",
        )

    if case.status in TERMINAL_STATUSES:
        return {
            "success": False,
            "case_id": case.case_id,
            "status": case.status,
            "action": None,
            "amount_at_risk": case.amount_at_risk,
            "amount_recovered": getattr(
                case,
                "amount_recovered",
                0,
            ) or 0,
            "reason": "Recovery workflow has already ended.",
            "already_processed": True,
        }

    if case.status == "RECOVERY_RUNNING":
        return {
            "success": False,
            "case_id": case.case_id,
            "status": "RECOVERY_RUNNING",
            "reason": "Recovery is already being executed.",
        }

    result = process_recovery_case(
        db=db,
        case=case,
        decision_function=safe_checkout_decision,
        execute_function=execute_checkout_recovery,
        commit=True,
    )

    return {
        **result,
        "already_processed": False,
    }


def _get_case_or_404(db, case_id):
    case = (
        db.query(RecoveryCase)
        .filter(RecoveryCase.case_id == case_id)
        .first()
    )

    if not case:
        raise HTTPException(
            status_code=404,
            detail="Recovery case not found",
        )

    return case


@router.get("/{case_id}")
def get_case_detail(
    case_id: str,
    db: Session = Depends(get_db),
):
    case = _get_case_or_404(db, case_id)

    return {
        "case_id": case.case_id,
        "customer_id": case.customer_id,
        "recovery_type": case.recovery_type,
        "status": case.status,
        "amount_at_risk": case.amount_at_risk,
        "amount_recovered": getattr(case, "amount_recovered", 0) or 0,
        "expected_recovery": getattr(case, "expected_recovery", 0) or 0,
        "risk_score": getattr(case, "risk_score", 0) or 0,
        "selected_action": case.selected_action,
        "agent_reason": case.agent_reason,
        "confidence": getattr(case, "confidence", 0) or 0,
    }


def _parse_audit_details(details):
    if not details:
        return {}

    try:
        return json.loads(details)
    except (TypeError, ValueError):
        return details

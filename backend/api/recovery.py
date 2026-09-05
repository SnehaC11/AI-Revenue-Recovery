import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database.database import get_db
from database.models import AuditLog, RecoveryAction, RecoveryCase
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
from services.audit import verify_audit_chain
from services.execution_claim import claim_case_execution
from services.audit import record_audit


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


class SettlementConfirmation(BaseModel):
    """A verified callback from a real payment provider, not a UI estimate."""

    provider_reference: str = Field(min_length=3, max_length=255)
    amount: float = Field(gt=0)
    external_reference: str = Field(min_length=3, max_length=255)


class CheckoutRiskEvent(BaseModel):
    """An abandoned checkout supplied by the checkout system of record."""

    checkout_id: str = Field(min_length=1, max_length=255)
    customer_id: str = Field(min_length=1, max_length=255)
    amount: float = Field(ge=0)
    currency: str = Field(default="INR", min_length=3, max_length=3)
    payment_attempted: bool = False
    minutes_since_abandonment: int = Field(ge=0)


class CheckoutRiskDetectionRequest(BaseModel):
    """Checkout events to evaluate.  An empty request deliberately creates none."""

    events: list[CheckoutRiskEvent] = Field(default_factory=list)


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
    existing_case = _get_case_or_404(db, case_id)
    case = claim_case_execution(db, case_id)
    if case is None:
        return {
            "success": False,
            "case_id": existing_case.case_id,
            "status": existing_case.status,
            "amount_at_risk": existing_case.amount_at_risk,
            "amount_recovered": existing_case.amount_recovered or 0,
            "reason": "Recovery is already running or has already ended.",
            "already_processed": True,
        }

    result = process_recovery_case(
        db=db,
        case=case,
        decision_function=safe_checkout_decision,
        execute_function=execute_checkout_recovery,
        commit=True,
    )

    result["already_processed"] = False

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

    claimed_cases = []
    for candidate in cases:
        claimed = claim_case_execution(db, candidate.case_id)
        if claimed is not None:
            claimed_cases.append(claimed)

    if not claimed_cases:
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
        cases=claimed_cases,
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
        .order_by(AuditLog.id.asc())
        .all()
    )

    return {
        "case_id": case_id,
        "integrity": verify_audit_chain(logs),
        "events": [
            {
                "event": log.event,
                "details": _parse_audit_details(
                    log.details
                ),
                "created_at": log.timestamp,
                "previous_hash": log.previous_hash,
                "event_hash": log.event_hash,
            }
            for log in logs
        ],
    }


@router.get("/audit/{case_id}/verify")
def verify_case_audit(
    case_id: str,
    db: Session = Depends(get_db),
):
    logs = (
        db.query(AuditLog)
        .filter(AuditLog.case_id == case_id)
        .order_by(AuditLog.id.asc())
        .all()
    )
    return {
        "case_id": case_id,
        "integrity": verify_audit_chain(logs),
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
    request: CheckoutRiskDetectionRequest | None = None,
    db: Session = Depends(get_db),
):
    # Detection must only persist events received from the checkout system.
    # Previously this endpoint generated 100 random demo events for every
    # request, causing a dashboard click to create 100 active cases.
    cases = create_checkout_cases(
        db,
        [event.model_dump() for event in (request.events if request else [])],
    )

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

    case = claim_case_execution(db, case_id)
    if case is None:
        current = _get_case_or_404(db, case_id)
        return {
            "success": False,
            "case_id": current.case_id,
            "status": current.status,
            "reason": "Recovery is already being executed.",
            "already_processed": True,
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


@router.post("/cases/{case_id}/confirm-settlement")
def confirm_settlement(
    case_id: str,
    confirmation: SettlementConfirmation,
    db: Session = Depends(get_db),
):
    """Accept only a provider-confirmed collection as real recovered money."""
    case = _get_case_or_404(db, case_id)
    if confirmation.amount > float(case.amount_at_risk or 0):
        raise HTTPException(
            status_code=422,
            detail="Confirmed amount cannot exceed the amount at risk.",
        )

    action = (
        db.query(RecoveryAction)
        .filter(
            RecoveryAction.case_id == case_id,
            RecoveryAction.provider_reference == confirmation.provider_reference,
        )
        .first()
    )
    if action is None:
        raise HTTPException(
            status_code=404,
            detail="No recovery action matches this provider reference.",
        )
    if action.is_simulated:
        raise HTTPException(
            status_code=409,
            detail="Demo-gateway actions cannot be confirmed as live settlements.",
        )

    action.amount_recovered = confirmation.amount
    action.outcome = "CONFIRMED_SETTLED"
    action.result = "SUCCESS"
    action.evidence = json.dumps({
        "provider_reference": confirmation.provider_reference,
        "external_reference": confirmation.external_reference,
        "confirmation_type": "provider_callback",
    }, sort_keys=True)
    case.amount_recovered = confirmation.amount
    case.status = "RECOVERED"
    db.add_all([action, case])
    record_audit(db, case.case_id, "SETTLEMENT_CONFIRMED", {
        "amount_recovered": confirmation.amount,
        "provider_reference": confirmation.provider_reference,
        "external_reference": confirmation.external_reference,
    })
    db.commit()
    return {
        "case_id": case.case_id,
        "status": case.status,
        "confirmed_amount": confirmation.amount,
        "provider_reference": confirmation.provider_reference,
    }


def _parse_audit_details(details):
    if not details:
        return {}

    try:
        return json.loads(details)
    except (TypeError, ValueError):
        return details

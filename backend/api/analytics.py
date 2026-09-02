from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database.database import get_db
from database.models import RecoveryCase


router = APIRouter(
    prefix="/analytics",
    tags=["Analytics"],
)


@router.get("/revenue")
def get_revenue_metrics(
    db: Session = Depends(get_db),
):
    cases = db.query(RecoveryCase).all()

    total_revenue_evaluated = sum(
        float(case.amount_at_risk or 0)
        for case in cases
    )
    revenue_at_risk = sum(
        float(case.amount_at_risk or 0)
        for case in cases
        if case.status not in {
            "RECOVERED",
            "ESCALATED",
            "STOPPED",
            "POLICY_BLOCKED",
        }
    )
    revenue_recovered = sum(
        float(case.amount_recovered or 0)
        for case in cases
    )
    expected_recovery = sum(
        float(case.expected_recovery or 0)
        for case in cases
        if case.status not in {
            "RECOVERED",
            "ESCALATED",
            "STOPPED",
            "POLICY_BLOCKED",
        }
    )

    recovered_cases = sum(
        1
        for case in cases
        if case.status == "RECOVERED"
    )
    escalated_cases = sum(
        1
        for case in cases
        if case.status == "ESCALATED"
    )
    stopped_cases = sum(
        1
        for case in cases
        if case.status in {
            "STOPPED",
            "POLICY_BLOCKED",
        }
    )
    active_cases = sum(
        1
        for case in cases
        if case.status not in {
            "RECOVERED",
            "ESCALATED",
            "STOPPED",
            "POLICY_BLOCKED",
        }
    )

    recovery_rate = (
        revenue_recovered / total_revenue_evaluated * 100
        if total_revenue_evaluated > 0
        else 0
    )
    recovery_rate = min(
        max(recovery_rate, 0),
        100,
    )

    response = {
        "revenue_at_risk": round(revenue_at_risk, 2),
        "total_revenue_evaluated": round(
            total_revenue_evaluated,
            2,
        ),
        "revenue_recovered": round(revenue_recovered, 2),
        "expected_recovery": round(expected_recovery, 2),
        "recovery_rate": round(recovery_rate, 2),
        "total_cases": len(cases),
        "recovered_cases": recovered_cases,
        "escalated_cases": escalated_cases,
        "stopped_cases": stopped_cases,
        "active_cases": active_cases,
    }
    response["recovered_revenue"] = response[
        "revenue_recovered"
    ]

    return response

from database.models import Payment
from services.audit import record_audit
from services.decision_validator import validate_decision
from services.recovery_policy import check_policy
from services.stopping_rules import (
    TERMINAL_STATUSES,
    check_stopping_rules,
)


def _get_retry_count(db, case):
    payment = None

    if case.payment_id:
        payment = (
            db.query(Payment)
            .filter(Payment.payment_id == case.payment_id)
            .first()
        )

    retry_count = getattr(payment, "retry_count", 0) or 0

    return payment, retry_count


def process_recovery_case(
    db,
    case,
    decision_function,
    execute_function,
    commit=False,
):
    amount_at_risk = float(case.amount_at_risk or 0)
    payment, retry_count = _get_retry_count(db, case)

    record_audit(
        db,
        case.case_id,
        "CASE_DETECTED",
        {
            "recovery_type": case.recovery_type,
            "amount_at_risk": amount_at_risk,
            "status": case.status,
        },
    )

    stopping = check_stopping_rules(
        case=case,
        retry_count=retry_count,
        attempt_count=getattr(case, "recovery_attempts", 0) or 0,
    )

    if stopping["stop"]:
        existing_status = case.status
        already_processed = (
            existing_status in TERMINAL_STATUSES
        )

        case.status = (
            existing_status
            if already_processed
            else "STOPPED"
        )
        case.agent_reason = stopping["reason"]
        if not already_processed:
            case.amount_recovered = 0
        db.add(case)
        record_audit(
            db,
            case.case_id,
            "WORKFLOW_STOPPED",
            {"reason": stopping["reason"]},
        )
        if commit:
            db.commit()
        return {
            "case_id": case.case_id,
            "status": case.status,
            "amount_at_risk": amount_at_risk,
            "amount_recovered": float(
                getattr(case, "amount_recovered", 0) or 0
            ),
            "reason": stopping["reason"],
        }

    checkout_data = {
        "customer_id": case.customer_id,
        "amount_at_risk": amount_at_risk,
        "risk_score": float(case.risk_score or 0),
        "minutes_since_abandonment": 30,
        "payment_attempted": True,
        "payment_id": case.payment_id,
        "retry_count": retry_count,
        "recovery_type": case.recovery_type,
    }

    try:
        decision = decision_function(checkout_data)
        record_audit(
            db,
            case.case_id,
            "AI_DECISION",
            decision,
        )
    except Exception as exc:
        case.status = "STOPPED"
        case.agent_reason = "AI decision failed. Workflow stopped safely."
        case.amount_recovered = 0
        db.add(case)
        record_audit(
            db,
            case.case_id,
            "AI_DECISION_FAILED",
            {"error": str(exc)},
        )
        record_audit(
            db,
            case.case_id,
            "WORKFLOW_STOPPED",
            {"reason": "AI decision failed"},
        )
        if commit:
            db.commit()
        return {
            "case_id": case.case_id,
            "status": "STOPPED",
            "amount_at_risk": amount_at_risk,
            "amount_recovered": 0,
            "reason": str(exc),
        }

    validation = validate_decision(
        decision,
        case.recovery_type,
    )

    if not validation["valid"]:
        case.status = "POLICY_BLOCKED"
        case.agent_reason = validation["reason"]
        case.amount_recovered = 0
        db.add(case)
        record_audit(
            db,
            case.case_id,
            "POLICY_CHECK",
            validation,
        )
        record_audit(
            db,
            case.case_id,
            "WORKFLOW_STOPPED",
            {"reason": validation["reason"]},
        )
        if commit:
            db.commit()
        return {
            "case_id": case.case_id,
            "status": "POLICY_BLOCKED",
            "amount_at_risk": amount_at_risk,
            "amount_recovered": 0,
            "reason": validation["reason"],
        }

    action = validation["action"]
    case.selected_action = action
    case.agent_reason = validation["reason"]
    case.confidence = float(validation.get("confidence") or 0)
    case.status = "RECOVERY_RUNNING"
    case.recovery_attempts = (
        (getattr(case, "recovery_attempts", 0) or 0)
        + 1
    )
    db.add(case)

    policy = check_policy(case, action)
    record_audit(
        db,
        case.case_id,
        "POLICY_CHECK",
        {
            "action": action,
            **policy,
        },
    )

    if not policy["allowed"]:
        case.status = "POLICY_BLOCKED"
        case.agent_reason = policy["reason"]
        case.amount_recovered = 0
        db.add(case)
        record_audit(
            db,
            case.case_id,
            "WORKFLOW_STOPPED",
            {"reason": policy["reason"]},
        )
        if commit:
            db.commit()
        return {
            "case_id": case.case_id,
            "status": "POLICY_BLOCKED",
            "action": action,
            "amount_at_risk": amount_at_risk,
            "amount_recovered": 0,
            "reason": policy["reason"],
        }

    try:
        result = execute_function(
            db=db,
            case=case,
            checkout_data=checkout_data,
        )
        amount_recovered = max(
            0,
            float(result.get("amount_recovered", 0) or 0),
        )
        amount_recovered = min(
            amount_recovered,
            amount_at_risk,
        )
    except Exception as exc:
        case.status = "STOPPED"
        case.agent_reason = "Recovery execution failed safely."
        case.amount_recovered = 0
        db.add(case)
        record_audit(
            db,
            case.case_id,
            "WORKFLOW_STOPPED",
            {
                "reason": "Recovery execution failed",
                "error": str(exc),
            },
        )
        if commit:
            db.commit()
        return {
            "case_id": case.case_id,
            "status": "STOPPED",
            "amount_at_risk": amount_at_risk,
            "amount_recovered": 0,
            "reason": "Recovery execution failed safely.",
        }

    case.amount_recovered = amount_recovered

    if amount_recovered > 0:
        case.status = "RECOVERED"
    elif action in {"ESCALATE_TO_FINANCE", "ESCALATE_TO_SALES"}:
        case.status = "ESCALATED"
    else:
        case.status = "STOPPED"

    db.add(case)

    if payment is not None and case.status == "RECOVERED":
        payment.recovered = True
        payment.status = "SUCCESS"
        db.add(payment)

    record_audit(
        db,
        case.case_id,
        "RECOVERY_RESULT",
        {
            "status": case.status,
            "action": action,
            "amount_at_risk": amount_at_risk,
            "amount_recovered": amount_recovered,
        },
    )
    record_audit(
        db,
        case.case_id,
        "WORKFLOW_STOPPED",
        {"reason": case.status},
    )

    if commit:
        db.commit()

    return {
        "case_id": case.case_id,
        "status": case.status,
        "action": action,
        "amount_at_risk": amount_at_risk,
        "amount_recovered": amount_recovered,
        "reason": case.agent_reason,
        "confidence": validation.get("confidence"),
        "success": amount_recovered > 0,
    }


def execute_batch_recovery(
    db,
    cases,
    decision_function,
    execute_function,
):
    results = []
    revenue_at_risk = 0.0
    revenue_recovered = 0.0
    expected_recovery = 0.0
    recovered_cases = 0
    escalated_cases = 0
    stopped_cases = 0
    blocked_cases = 0

    record_audit(
        db,
        "BATCH",
        "RECOVERY_BATCH_STARTED",
        {"cases_selected": len(cases)},
    )

    for case in cases:
        amount_at_risk = float(case.amount_at_risk or 0)
        revenue_at_risk += amount_at_risk
        expected_recovery += float(getattr(case, "expected_recovery", 0) or 0)

        result = process_recovery_case(
            db=db,
            case=case,
            decision_function=decision_function,
            execute_function=execute_function,
            commit=False,
        )
        results.append(result)

        revenue_recovered += float(
            result.get("amount_recovered", 0) or 0
        )

        if result["status"] == "RECOVERED":
            recovered_cases += 1
        elif result["status"] == "ESCALATED":
            escalated_cases += 1
        elif result["status"] == "POLICY_BLOCKED":
            blocked_cases += 1
        else:
            stopped_cases += 1

    revenue_recovered = min(
        max(revenue_recovered, 0),
        revenue_at_risk,
    )
    recovery_rate = (
        revenue_recovered / revenue_at_risk * 100
        if revenue_at_risk > 0
        else 0
    )
    recovery_rate = min(
        max(recovery_rate, 0),
        100,
    )

    summary = {
        "cases_processed": len(cases),
        "recovered_cases": recovered_cases,
        "escalated_cases": escalated_cases,
        "stopped_cases": stopped_cases,
        "blocked_cases": blocked_cases,
        "revenue_at_risk": round(revenue_at_risk, 2),
        "expected_recovery": round(expected_recovery, 2),
        "revenue_recovered": round(revenue_recovered, 2),
        "recovery_rate": round(recovery_rate, 2),
        "results": results,
    }

    record_audit(
        db,
        "BATCH",
        "RECOVERY_BATCH_COMPLETED",
        summary,
    )
    db.commit()

    return summary

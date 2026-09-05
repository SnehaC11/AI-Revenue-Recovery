import json

from database.models import Customer, Payment, RecoveryAction
from services.audit import record_audit
from services.payment_simulator import retry_payment


def safe_checkout_decision(checkout_data):
    recovery_type = checkout_data.get(
        "recovery_type",
        "CHECKOUT_ABANDONMENT",
    )
    amount = float(
        checkout_data.get("amount_at_risk", 0) or 0
    )
    risk = float(
        checkout_data.get("risk_score", 0) or 0
    )
    minutes = int(
        checkout_data.get(
            "minutes_since_abandonment",
            30,
        )
        or 30
    )
    retry_count = int(
        checkout_data.get("retry_count", 0) or 0
    )
    failure_reason = checkout_data.get("failure_reason")

    if recovery_type == "PAYMENT_FAILURE":
        if retry_count >= 2:
            return {
                "action": "ESCALATE_TO_FINANCE",
                "reason": (
                    "Automatic retry limit reached. Escalating for manual review."
                ),
                "confidence": 0.94,
            }

        if amount >= 25000:
            return {
                "action": "ESCALATE_TO_FINANCE",
                "reason": (
                    "High-value payment failures require finance review."
                ),
                "confidence": 0.92,
            }

        if failure_reason == "CARD_EXPIRED":
            return {
                "action": "REQUEST_PAYMENT_METHOD_UPDATE",
                "reason": "The payment method is expired; request an update instead of retrying it.",
                "confidence": 0.91,
            }

        if failure_reason in {"AUTHENTICATION_FAILED", "BANK_DECLINED"}:
            return {
                "action": "SEND_PAYMENT_LINK",
                "reason": "The failure requires customer re-authentication or a new payment choice.",
                "confidence": 0.84,
            }

        if risk >= 0.8:
            return {
                "action": "RETRY_PAYMENT",
                "reason": (
                    "Recovery probability is strong enough for one bounded retry."
                ),
                "confidence": 0.87,
            }

        if risk >= 0.55:
            return {
                "action": "SEND_PAYMENT_LINK",
                "reason": (
                    "A payment link gives the customer a low-friction way to complete the payment."
                ),
                "confidence": 0.76,
            }

        return {
            "action": "CLOSE_CASE",
            "reason": (
                "Recovery probability is too low for further automated action."
            ),
            "confidence": 0.71,
        }

    if amount >= 100000:
        return {
            "action": "ESCALATE_TO_SALES",
            "reason": (
                "High-value abandoned checkout should receive human follow-up."
            ),
            "confidence": 0.9,
        }

    if amount >= 10000 and minutes <= 60:
        return {
            "action": "SEND_PAYMENT_LINK",
            "reason": (
                "Recently abandoned high-value checkout qualifies for a payment link."
            ),
            "confidence": 0.91,
        }

    if risk >= 0.7:
        return {
            "action": "SEND_CHECKOUT_REMINDER",
            "reason": (
                "The checkout has good recovery potential and qualifies for a reminder."
            ),
            "confidence": 0.84,
        }

    return {
        "action": "SEND_CHECKOUT_REMINDER",
        "reason": (
            "A reminder is the safest low-friction recovery action for this checkout."
        ),
        "confidence": 0.78,
    }


def calculate_checkout_recovery(
    amount_at_risk,
    action,
):
    recovery_rates = {
        "SEND_PAYMENT_LINK": 0.65,
        "SEND_CHECKOUT_REMINDER": 0.35,
        "REQUEST_PAYMENT_METHOD_UPDATE": 0.25,
        "RETRY_PAYMENT": 1.0,
        "ESCALATE_TO_SALES": 0.0,
        "ESCALATE_TO_FINANCE": 0.0,
        "CLOSE_CASE": 0.0,
        "STOP": 0.0,
    }

    rate = recovery_rates.get(action, 0.0)

    return round(
        float(amount_at_risk or 0) * rate,
        2,
    )


def execute_checkout_recovery(
    db,
    case,
    checkout_data,
    audit_logger=None,
):
    action = case.selected_action or safe_checkout_decision(
        checkout_data
    )["action"]

    record_audit(
        db,
        case.case_id,
        "RECOVERY_ACTION",
        {
            "action": action,
            "amount_at_risk": case.amount_at_risk,
            "recovery_type": case.recovery_type,
        },
    )

    amount_recovered = 0.0
    is_simulated = True
    outcome = "SIMULATED_DISPATCHED"
    provider_reference = f"demo-{case.execution_key or case.case_id}"

    if action == "RETRY_PAYMENT" and case.payment_id:
        payment = (
            db.query(Payment)
            .filter(Payment.payment_id == case.payment_id)
            .first()
        )

        if payment:
            result = retry_payment(payment)
            amount_recovered = float(
                result.get("amount_recovered", 0) or 0
            )
            db.add(payment)
            outcome = (
                "SIMULATED_SETTLED"
                if amount_recovered > 0
                else "SIMULATED_DECLINED"
            )
    else:
        amount_recovered = calculate_checkout_recovery(
            case.amount_at_risk,
            action,
        )
        if action.startswith("ESCALATE"):
            outcome = "ESCALATION_QUEUED"
        elif action in {"CLOSE_CASE", "STOP"}:
            outcome = "NO_ACTION_REQUIRED"
        elif amount_recovered > 0:
            outcome = "SIMULATED_SETTLED"

    amount_recovered = max(0, amount_recovered)
    amount_recovered = min(
        amount_recovered,
        float(case.amount_at_risk or 0),
    )

    case.amount_recovered = amount_recovered
    case.agent_reason = case.agent_reason or (
        "Recovery action executed."
    )
    db.add(case)

    customer = (
        db.query(Customer)
        .filter(Customer.customer_id == case.customer_id)
        .first()
    )
    contact_actions = {
        "SEND_PAYMENT_LINK",
        "SEND_CHECKOUT_REMINDER",
        "REQUEST_PAYMENT_METHOD_UPDATE",
    }
    if action in contact_actions:
        case.contact_attempts = (case.contact_attempts or 0) + 1

    # This is the operational outbox/audit record for the action.  The demo
    # gateway is explicit in its evidence, so it cannot be confused with a
    # real settlement provider.
    recovery_action = RecoveryAction(
        case_id=case.case_id,
        action=action,
        result="SUCCESS" if amount_recovered > 0 else "NO_RECOVERY",
        amount_recovered=amount_recovered,
        action_key=f"{case.execution_key or case.case_id}:{action}",
        channel=(customer.preferred_contact_channel if customer and action in contact_actions else None),
        recipient=(customer.email if customer and action in contact_actions else None),
        outcome=outcome,
        provider_reference=provider_reference,
        is_simulated=is_simulated,
        evidence=json.dumps({
            "recovery_mode": "DEMO_SIMULATOR",
            "settlement_confirmed_by": "deterministic_demo_gateway"
            if amount_recovered > 0 else None,
            "action": action,
        }, sort_keys=True),
    )
    db.add(recovery_action)

    return {
        "success": amount_recovered > 0,
        "case_id": case.case_id,
        "action": action,
        "reason": case.agent_reason,
        "amount_at_risk": case.amount_at_risk,
        "amount_recovered": amount_recovered,
        "recovery_mode": "SIMULATED",
        "provider_reference": provider_reference,
        "status": case.status,
    }

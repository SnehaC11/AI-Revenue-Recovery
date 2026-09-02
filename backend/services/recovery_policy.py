from services.stopping_rules import TERMINAL_STATUSES


def check_policy(
    case,
    action,
):
    if case.status in TERMINAL_STATUSES:
        return {
            "allowed": False,
            "reason": (
                "Recovery workflow has already ended."
            ),
        }

    if (
        case.recovery_type == "CHECKOUT_ABANDONMENT"
        and action == "SEND_CHECKOUT_REMINDER"
        and float(case.amount_at_risk or 0) >= 100000
    ):
        return {
            "allowed": False,
            "reason": (
                "High-value checkout cases must escalate instead of sending reminders."
            ),
        }

    if (
        case.recovery_type == "PAYMENT_FAILURE"
        and action == "RETRY_PAYMENT"
        and float(case.amount_at_risk or 0) >= 25000
    ):
        return {
            "allowed": False,
            "reason": (
                "High-value payment failures require finance review."
            ),
        }

    return {
        "allowed": True,
        "reason": "Policy approved.",
    }

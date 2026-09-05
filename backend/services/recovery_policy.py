from datetime import datetime, timedelta

from database.models import Customer, RecoveryAction
from services.stopping_rules import TERMINAL_STATUSES


CONTACT_ACTIONS = {
    "SEND_PAYMENT_LINK",
    "SEND_CHECKOUT_REMINDER",
    "REQUEST_PAYMENT_METHOD_UPDATE",
}
MAX_CUSTOMER_CONTACTS = 2
CONTACT_COOLDOWN_HOURS = 24


def check_policy(
    db,
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

    if action in CONTACT_ACTIONS:
        customer = (
            db.query(Customer)
            .filter(Customer.customer_id == case.customer_id)
            .first()
        )
        if customer is None:
            return {
                "allowed": False,
                "reason": "Customer record is unavailable for a compliant contact check.",
            }
        if not customer.recovery_consent or customer.contact_opt_out:
            return {
                "allowed": False,
                "reason": "Customer has not consented to recovery communications or opted out.",
            }

        contacts = (
            db.query(RecoveryAction)
            .filter(
                RecoveryAction.case_id == case.case_id,
                RecoveryAction.action.in_(CONTACT_ACTIONS),
            )
            .order_by(RecoveryAction.timestamp.desc())
            .all()
        )
        if len(contacts) >= MAX_CUSTOMER_CONTACTS:
            return {
                "allowed": False,
                "reason": "Maximum permitted recovery contacts reached.",
            }
        if contacts and contacts[0].timestamp >= (
            datetime.utcnow() - timedelta(hours=CONTACT_COOLDOWN_HOURS)
        ):
            return {
                "allowed": False,
                "reason": "Recovery contact cooldown is still active.",
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
        "reason": "Policy approved: action is within recovery, contact, and escalation limits.",
    }

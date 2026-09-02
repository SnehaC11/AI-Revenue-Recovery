MAX_RETRIES = 2

MAX_CUSTOMER_CONTACTS = 2

HIGH_VALUE_THRESHOLD = 25000


ALLOWED_ACTIONS = {
    "RETRY_PAYMENT",
    "SEND_PAYMENT_LINK",
    "REQUEST_PAYMENT_METHOD_UPDATE",
    "ESCALATE_TO_FINANCE",
    "CLOSE_CASE"
}


def validate_action(case, payment, action):

    violations = []

    # --------------------------------
    # Action validation
    # --------------------------------

    if action not in ALLOWED_ACTIONS:

        violations.append(
            "Action is not allowed."
        )

    # --------------------------------
    # Already recovered
    # --------------------------------

    if payment.recovered:

        violations.append(
            "Payment has already been recovered."
        )

    # --------------------------------
    # Retry limit
    # --------------------------------

    if action == "RETRY_PAYMENT":

        if payment.retry_count >= MAX_RETRIES:

            violations.append(
                "Maximum retry limit reached."
            )

    # --------------------------------
    # High-value protection
    # --------------------------------

    if (
        payment.amount >= HIGH_VALUE_THRESHOLD
        and action == "RETRY_PAYMENT"
    ):

        violations.append(
            "High-value payment requires finance review."
        )

    # --------------------------------
    # Case status
    # --------------------------------

    if case.status in {
        "RECOVERED",
        "EXHAUSTED",
        "CLOSED"
    }:

        violations.append(
            f"Case cannot be acted upon while status is {case.status}."
        )

    return {
        "allowed": len(violations) == 0,
        "violations": violations
    }


def should_stop(case, payment):

    if payment.recovered:

        return {
            "stop": True,
            "reason": "Payment successfully recovered."
        }

    if payment.retry_count >= MAX_RETRIES:

        return {
            "stop": True,
            "reason": "Maximum retry limit reached."
        }

    if case.status == "ESCALATED":

        return {
            "stop": True,
            "reason": "Case escalated to finance."
        }

    if case.status == "CLOSED":

        return {
            "stop": True,
            "reason": "Case has been closed."
        }

    return {
        "stop": False,
        "reason": None
    }
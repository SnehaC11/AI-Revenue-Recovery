CHECKOUT_ACTIONS = {
    "SEND_PAYMENT_LINK",
    "SEND_CHECKOUT_REMINDER",
    "ESCALATE_TO_SALES",
    "STOP",
}

PAYMENT_ACTIONS = {
    "RETRY_PAYMENT",
    "SEND_PAYMENT_LINK",
    "REQUEST_PAYMENT_METHOD_UPDATE",
    "ESCALATE_TO_FINANCE",
    "CLOSE_CASE",
}

ACTION_ALIASES = {
    "ESCALATE": "ESCALATE_TO_FINANCE",
    "ESCALATE_TO_SUPPORT": "ESCALATE_TO_SALES",
    "REMIND": "SEND_CHECKOUT_REMINDER",
    "STOP_WORKFLOW": "STOP",
}


def validate_decision(
    decision,
    recovery_type,
):
    raw_action = (
        decision.get("action")
        if isinstance(decision, dict)
        else None
    )

    if not raw_action:
        return {
            "valid": False,
            "reason": "AI decision did not include an action.",
        }

    action = ACTION_ALIASES.get(
        raw_action,
        raw_action,
    )

    allowed_actions = (
        CHECKOUT_ACTIONS
        if recovery_type == "CHECKOUT_ABANDONMENT"
        else PAYMENT_ACTIONS
    )

    if action not in allowed_actions:
        return {
            "valid": False,
            "reason": (
                f"Action {action} is not valid for {recovery_type}."
            ),
        }

    return {
        "valid": True,
        "action": action,
        "reason": decision.get("reason")
        or "AI decision validated successfully.",
        "confidence": decision.get("confidence"),
    }

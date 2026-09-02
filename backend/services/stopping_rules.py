TERMINAL_STATUSES = {
    "RECOVERED",
    "ESCALATED",
    "STOPPED",
    "POLICY_BLOCKED",
}


def check_stopping_rules(
    case,
    retry_count=0,
    attempt_count=0,
):
    if case.status in TERMINAL_STATUSES:
        return {
            "stop": True,
            "reason": (
                "Recovery workflow has already ended."
            ),
        }

    if retry_count >= 3:
        return {
            "stop": True,
            "reason": "Maximum retry limit reached.",
        }

    if attempt_count >= 2:
        return {
            "stop": True,
            "reason": "Maximum recovery attempts reached.",
        }

    return {
        "stop": False,
        "reason": None,
    }

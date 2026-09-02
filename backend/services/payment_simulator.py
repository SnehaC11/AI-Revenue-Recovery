def get_payment_outcome(payment_id: str, retry_count: int):
    """
    Deterministic payment simulator.

    The result is based on the payment ID so the same payment
    always behaves the same way during the demo.
    """

    number = int(
        payment_id.replace("PAY-", "")
    )

    scenario = number % 3

    # Scenario 0:
    # First retry succeeds
    if scenario == 0:

        return retry_count >= 1

    # Scenario 1:
    # First retry fails, second retry succeeds
    if scenario == 1:

        return retry_count >= 2

    # Scenario 2:
    # Payment never recovers automatically
    return False


def retry_payment(payment):

    payment.retry_count += 1

    success = get_payment_outcome(
        payment.payment_id,
        payment.retry_count
    )

    if success:

        payment.status = "SUCCESS"
        payment.recovered = True

        return {
            "success": True,
            "message": "Payment recovered successfully.",
            "amount_recovered": payment.amount,
            "retry_count": payment.retry_count
        }

    return {
        "success": False,
        "message": "Payment retry failed.",
        "amount_recovered": 0,
        "retry_count": payment.retry_count
    }
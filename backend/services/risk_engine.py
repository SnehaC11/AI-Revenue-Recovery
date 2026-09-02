from sqlalchemy.orm import Session

from database.models import Payment, Customer, RecoveryCase


def calculate_risk_score(payment: Payment, customer: Customer) -> float:
    """
    Calculate how important this failed payment is to recover.

    Score range: 0.0 - 1.0
    """

    score = 0.0

    # 1. Amount at risk
    if payment.amount >= 25000:
        score += 0.30
    elif payment.amount >= 10000:
        score += 0.25
    elif payment.amount >= 5000:
        score += 0.20
    else:
        score += 0.10

    # 2. Customer payment history
    if customer.successful_payments >= 15:
        score += 0.25
    elif customer.successful_payments >= 8:
        score += 0.20
    elif customer.successful_payments >= 3:
        score += 0.10

    # 3. Failure reason
    if payment.failure_reason == "INSUFFICIENT_FUNDS":
        score += 0.20

    elif payment.failure_reason == "NETWORK_ERROR":
        score += 0.20

    elif payment.failure_reason == "CARD_EXPIRED":
        score += 0.10

    elif payment.failure_reason == "AUTHENTICATION_FAILED":
        score += 0.05

    elif payment.failure_reason == "BANK_DECLINED":
        score += 0.05

    # 4. Previous failures
    if customer.failed_payments == 0:
        score += 0.15

    elif customer.failed_payments <= 2:
        score += 0.10

    return min(round(score, 2), 1.0)


def calculate_recovery_probability(
    payment: Payment,
    customer: Customer
) -> float:
    """
    Estimate probability that this payment can be recovered.
    """

    probability = 0.50

    # Strong historical payment behaviour
    if customer.successful_payments >= 10:
        probability += 0.20

    elif customer.successful_payments >= 5:
        probability += 0.10

    # Failure reason
    if payment.failure_reason == "NETWORK_ERROR":
        probability += 0.15

    elif payment.failure_reason == "INSUFFICIENT_FUNDS":
        probability += 0.10

    elif payment.failure_reason == "CARD_EXPIRED":
        probability += 0.05

    elif payment.failure_reason == "BANK_DECLINED":
        probability -= 0.10

    elif payment.failure_reason == "AUTHENTICATION_FAILED":
        probability -= 0.15

    # Repeated failures reduce probability
    if customer.failed_payments >= 3:
        probability -= 0.15

    return min(
        max(round(probability, 2), 0.05),
        0.95
    )


def create_recovery_cases(db: Session):

    failed_payments = (
        db.query(Payment)
        .filter(
            Payment.status == "FAILED",
            Payment.recovered.is_(False)
        )
        .all()
    )

    created_cases = []

    for payment in failed_payments:

        customer = (
            db.query(Customer)
            .filter(
                Customer.customer_id == payment.customer_id
            )
            .first()
        )

        if not customer:
            continue

        # Prevent duplicate recovery cases
        existing_case = (
            db.query(RecoveryCase)
            .filter(
                RecoveryCase.payment_id == payment.payment_id
            )
            .first()
        )

        if existing_case:
            continue

        risk_score = calculate_risk_score(
            payment,
            customer
        )

        recovery_probability = calculate_recovery_probability(
            payment,
            customer
        )
        expected_recovery = round(
            payment.amount * recovery_probability,
            2
        )

        case = RecoveryCase(
            case_id=f"RC-{payment.payment_id}",
            payment_id=payment.payment_id,
            customer_id=payment.customer_id,
            amount_at_risk=payment.amount,
            risk_score=risk_score,
            recovery_probability=recovery_probability,
            expected_recovery=expected_recovery,
            status="AT_RISK"
        )

        db.add(case)

        created_cases.append(case)

    db.commit()

    return created_cases

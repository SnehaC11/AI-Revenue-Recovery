import random


def generate_checkout_events(
    customers,
    count=100
):

    events = []

    amounts = [
        999,
        1999,
        4999,
        9999,
        24999,
    ]

    for i in range(count):

        customer = random.choice(
            customers
        )

        event = {
            "checkout_id":
                f"CHK-{100000 + i}",

            "customer_id":
                customer.customer_id,

            "amount":
                random.choice(amounts),

            "currency":
                "INR",

            "status":
                "ABANDONED",

            "payment_attempted":
                random.choice(
                    [False, False, False, True]
                ),

            "minutes_since_abandonment":
                random.randint(5, 1440),
        }

        events.append(event)

    return events
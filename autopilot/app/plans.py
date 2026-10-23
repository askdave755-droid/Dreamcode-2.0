"""Subscription plans for the businesses that pay us.

Voice minutes are the cost driver, so every plan carries an allowance and an
overage rate. Keep these in one place — they are quoted on /billing and in the
PLAN text command.
"""
PLANS = {
    "starter": {
        "name": "Starter",
        "price_cents": 7900,
        "interval": "month",
        "currency": "cad",
        "minutes_included": 200,
        "overage_cents_per_minute": 49,
        "features": [
            "AI receptionist on a dedicated local number",
            "Booking, reminders, and review texts",
            "Unlimited invoices and SMS follow-ups",
            "Owner text commands",
        ],
        "price_env": "stripe_subscription_price_id",
    },
    "pro": {
        "name": "Pro",
        "price_cents": 14900,
        "interval": "month",
        "currency": "cad",
        "minutes_included": 600,
        "overage_cents_per_minute": 39,
        "features": [
            "Everything in Starter",
            "600 voice minutes included",
            "Seasonal rebooking campaigns",
            "Quarterly tax summary export",
            "Priority support",
        ],
        "price_env": "stripe_subscription_price_id_pro",
    },
}


def plan_list() -> list[dict]:
    return [
        {
            "key": key,
            "name": plan["name"],
            "price_cents": plan["price_cents"],
            "interval": plan["interval"],
            "minutes_included": plan["minutes_included"],
            "overage_cents_per_minute": plan["overage_cents_per_minute"],
            "features": plan["features"],
        }
        for key, plan in PLANS.items()
    ]

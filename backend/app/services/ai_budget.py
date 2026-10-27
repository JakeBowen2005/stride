"""Monthly AI spend in dollars, per athlete and app-wide (docs/multi-user-design.md §2.6).

Daily attempt limits stay as a burst guard. When a cap is reached, coaching falls back to the
deterministic rules and saved reviews; nothing about training stops.
"""
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import func

from app.config import settings

# USD per 1M tokens (input, output), standard tier, checked Oct 26 2026 (docs/plain-language-plan-changes.md §3.2).
PRICES = {
    'gpt-5.4-mini': (0.75, 4.50),
    'gpt-5.4-nano': (0.20, 1.25),
    'gpt-6-luna': (0.10, 0.50),
    'gpt-6.1-terra': (1.00, 5.00),
    'gpt-6-sol': (2.00, 10.00),
    'gpt-5.5': (5.00, 30.00),
}
UNKNOWN_PRICE = PRICES['gpt-5.5']  # an unlisted model is priced like the most expensive, so caps fail safe


def cost(model: str | None, input_tokens: int | None, output_tokens: int | None) -> float:
    if not model:
        return 0.0
    price_in, price_out = PRICES.get(model, UNKNOWN_PRICE)
    return ((input_tokens or 0) * price_in + (output_tokens or 0) * price_out) / 1_000_000


def month_start() -> datetime:
    return datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0, tzinfo=None)


def spent(db, user_id: int | None = None) -> float:
    """This calendar month's spend (UTC), from recorded tokens on every provider attempt."""
    from app.models.coaching import CoachingAttempt, CoachingReview
    from app.models.plan_change import PlanChangeRequest
    since = month_start()
    reviews = (db.query(CoachingAttempt.model, func.sum(CoachingAttempt.input_tokens), func.sum(CoachingAttempt.output_tokens))
               .join(CoachingReview, CoachingReview.id == CoachingAttempt.review_id)
               .filter(CoachingAttempt.created_at >= since, CoachingAttempt.model.is_not(None)))
    changes = (db.query(PlanChangeRequest.model, func.sum(PlanChangeRequest.input_tokens), func.sum(PlanChangeRequest.output_tokens))
               .filter(PlanChangeRequest.created_at >= since, PlanChangeRequest.model.is_not(None)))
    if user_id is not None:
        reviews = reviews.filter(CoachingReview.user_id == user_id)
        changes = changes.filter(PlanChangeRequest.user_id == user_id)
    total = 0.0
    for query in (reviews, changes):
        for model, tokens_in, tokens_out in query.group_by(query.column_descriptions[0]['expr']).all():
            total += cost(model, tokens_in, tokens_out)
    return total


def athlete_cap(user_id: int, db) -> float:
    from app.models.account import Account
    account = db.get(Account, user_id)
    owner = (account.role == 'owner') if account is not None and account.role else user_id == settings.default_user_id
    return settings.openai_owner_monthly_budget_usd if owner else settings.openai_athlete_monthly_budget_usd


def check(user_id: int, db) -> None:
    if spent(db) >= settings.openai_monthly_budget_usd:
        raise HTTPException(429, "This month's app AI budget is used up. Training rules and saved reviews still work.")
    if spent(db, user_id) >= athlete_cap(user_id, db):
        raise HTTPException(429, "You've used this month's AI coaching allowance. Training rules and saved reviews still work; "
                                 "it resets on the 1st.")


def usage(user_id: int, db) -> dict:
    return {'month_start': month_start().date().isoformat(), 'spent_usd': round(spent(db, user_id), 4),
            'cap_usd': athlete_cap(user_id, db)}

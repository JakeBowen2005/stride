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
    from app.services.accounts import is_owner
    return settings.openai_owner_monthly_budget_usd if is_owner(user_id, db) else settings.openai_athlete_monthly_budget_usd


def check(user_id: int, db) -> None:
    from app.services.accounts import is_owner, owner_ids
    total = spent(db)
    if is_owner(user_id, db):
        limit_hit = total >= settings.openai_monthly_budget_usd
    else:
        # The owner's allowance is reserved inside the app-wide cap, so invitees can't use it up.
        owners = sum(spent(db, uid) for uid in owner_ids(db))
        athletes_pool = max(0.0, settings.openai_monthly_budget_usd - settings.openai_owner_monthly_budget_usd)
        limit_hit = total >= settings.openai_monthly_budget_usd or total - owners >= athletes_pool
    if limit_hit:
        raise HTTPException(429, "This month's app AI budget is used up. Training rules and saved reviews still work.")
    if spent(db, user_id) >= athlete_cap(user_id, db):
        raise HTTPException(429, "You've used this month's AI coaching allowance. Training rules and saved reviews still work; "
                                 "it resets on the 1st.")


def usage(user_id: int, db) -> dict:
    from app.services.accounts import is_owner
    used, cap = spent(db, user_id), athlete_cap(user_id, db)
    out = {'month_start': month_start().date().isoformat(), 'used_percent': min(100, round(100 * used / cap)) if cap else 100,
           'owner': is_owner(user_id, db)}
    # Dollar amounts are operator information; athletes see how much of their allowance is used.
    return out | ({'spent_usd': round(used, 4), 'cap_usd': cap} if out['owner'] else {})

"""Plain-language plan changes: ask, answer a clarifying question, approve, discard, undo."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.services import plan_changes

router = APIRouter(prefix="/api/plans", tags=["plan-changes"])


class PickedConstraint(BaseModel):
    date: str = Field(max_length=10)
    kind: str = Field(max_length=20)
    minutes: int | None = Field(default=None, ge=1, le=600)


class ChangeRequest(BaseModel):
    text: str = Field(default="", max_length=2000)
    # The quick picker (no AI): structured constraints instead of words.
    constraints: list[PickedConstraint] | None = Field(default=None, max_length=14)


class Answer(BaseModel):
    answer: str = Field(min_length=1, max_length=500)


@router.get("/{user_id}/requests")
def list_requests(user_id: int, db: Session = Depends(get_db)):
    from app.models.user import User
    user = db.get(User, user_id)
    return {"requests": plan_changes.history(user_id, db),
            "ai_available": bool(user) and plan_changes.ai_available(user),
            "remaining_today": plan_changes.remaining_today(user_id, db),
            "daily_limit": settings.openai_plan_change_daily_limit}


@router.post("/{user_id}/requests")
def create_request(user_id: int, req: ChangeRequest, db: Session = Depends(get_db)):
    picked = [c.model_dump() for c in req.constraints] if req.constraints is not None else None
    return plan_changes.create(user_id, req.text, db, constraints=picked)


@router.post("/{user_id}/requests/{request_id}/answer")
def answer_request(user_id: int, request_id: int, req: Answer, db: Session = Depends(get_db)):
    return plan_changes.create(user_id, req.answer, db, answer_to=request_id)


@router.post("/{user_id}/requests/{request_id}/apply")
def apply_request(user_id: int, request_id: int, db: Session = Depends(get_db)):
    return plan_changes.apply(user_id, request_id, db)


@router.post("/{user_id}/requests/{request_id}/discard")
def discard_request(user_id: int, request_id: int, db: Session = Depends(get_db)):
    return plan_changes.discard(user_id, request_id, db)


@router.post("/{user_id}/requests/{request_id}/undo")
def undo_request(user_id: int, request_id: int, db: Session = Depends(get_db)):
    return plan_changes.undo(user_id, request_id, db)

"""Invalidate persisted facts in the same transaction as the underlying edit.

Covers normal ORM inserts/edits/deletes and bulk ORM updates/deletes. Provider
telemetry and review outputs do not invalidate their own inputs.
"""
from sqlalchemy import event, inspect, select, update, insert, delete
from sqlalchemy.orm import Session

from app.models.activity import Activity
from app.models.history import AthleteRevision, DirtyDay, DailyFact, ActivitySource, HistoryCoverage
from app.models.plan import Plan, PlannedWorkout
from app.models.progression import WorkoutProgression
from app.models.user import Goal, User
from app.models.wellness import DailyWellness

TRACKED = (Activity, DailyWellness, Plan, PlannedWorkout, WorkoutProgression, Goal, User, ActivitySource, HistoryCoverage)


def _bump(connection, user_id):
    result = connection.execute(update(AthleteRevision).where(AthleteRevision.user_id == user_id).values(revision=AthleteRevision.revision + 1))
    if not result.rowcount:
        connection.execute(insert(AthleteRevision).values(user_id=user_id, revision=1))


def _dirty(connection, user_id, day):
    if not connection.execute(select(DirtyDay.date).where(DirtyDay.user_id == user_id, DirtyDay.date == day)).first():
        connection.execute(insert(DirtyDay).values(user_id=user_id, date=day))


@event.listens_for(Session, 'before_flush')
def track_changes(db, flush_context, instances):
    users, days = set(), set()
    for row in set(db.new) | set(db.dirty) | set(db.deleted):
        if not isinstance(row, TRACKED) or (row in db.dirty and not db.is_modified(row, include_collections=False)):
            continue
        if isinstance(row, ActivitySource) and row in db.dirty and not any(inspect(row).attrs[key].history.has_changes() for key in ('enrichment_status', 'parser_version', 'activity_id')):
            continue
        if isinstance(row, HistoryCoverage) and row in db.dirty and not inspect(row).attrs.status.history.has_changes():
            continue
        if isinstance(row, User):
            # Initial INSERT must happen before the revision's foreign key can exist.
            if row in db.new:
                continue
            user_id = row.id
        elif isinstance(row, PlannedWorkout):
            plan = db.get(Plan, row.plan_id)
            user_id = plan.user_id if plan else None
        else:
            user_id = row.user_id
        if not user_id:
            continue
        users.add(user_id)
        if isinstance(row, Activity) and row.date:
            days.add((user_id, row.date.date().isoformat()))
            if row.id and inspect(row).attrs.date.history.has_changes():
                old = db.connection().execute(select(Activity.date).where(Activity.id == row.id)).scalar()
                if old:
                    days.add((user_id, old.date().isoformat()))
    db.info.setdefault('_history_users', set()).update(users)
    db.info.setdefault('_history_days', set()).update(days)


@event.listens_for(Session, 'after_flush_postexec')
def persist_changes(db, flush_context):
    connection = db.connection()
    for user_id in db.info.pop('_history_users', set()):
        _bump(connection, user_id)
    for user_id, day in db.info.pop('_history_days', set()):
        _dirty(connection, user_id, day)


@event.listens_for(Session, 'after_rollback')
def discard_changes(db):
    db.info.pop('_history_users', None)
    db.info.pop('_history_days', None)


@event.listens_for(Session, 'do_orm_execute')
def track_bulk_change(state):
    if not (state.is_update or state.is_delete):
        return
    table = getattr(state.statement, 'table', None)
    if table is None or table.name not in {model.__tablename__ for model in TRACKED}:
        return
    # Bulk paths bypass ORM histories. Conservatively invalidate all affected caches;
    # normal source ingestion uses targeted daily invalidation above.
    connection = state.session.connection()
    connection.execute(update(AthleteRevision).values(revision=AthleteRevision.revision + 1))
    if table.name == Activity.__tablename__:
        connection.execute(delete(DailyFact))

"""Assess the previous block before generating the next one.

The decision (build / hold / reduce / recovery) changes how much the next block's
volume may grow (see load_policy.plan_load). It is deterministic; the coach and UI
only explain it.

Policy (Stride defaults, conservative by design):
- Only days that were actually prescribed and are already in the past count.
  Regenerating mid-block, or a block that has barely started, yields no
  assessment (normal build), so regeneration alone never earns progression.
- Missing feedback is not a bad rating. Missed miles are not debt to repay: the
  next block is sized from what was really run (the baseline), and an
  interrupted block holds or reduces instead of chasing the plan.
"""

from dataclasses import asdict, dataclass, field

MIN_ASSESSABLE_DAYS = 5
BUILD_COMPLETION = 0.85
REDUCE_COMPLETION = 0.60
QUALITY_DONE_SHARE = 0.70  # a quality day counts as done at ≥70% of its planned miles


@dataclass
class DayRecord:
    date: str
    type: str  # easy | workout | long_run | race | rest
    planned_miles: float
    actual_miles: float
    feel: int | None = None


@dataclass
class BlockAssessment:
    decision: str | None  # build | hold | reduce | recovery | None (not enough to assess)
    reasons: list[str] = field(default_factory=list)
    planned_miles: float = 0.0
    completed_miles: float = 0.0
    completion: float | None = None
    quality_planned: int = 0
    quality_done: int = 0
    feel_count: int = 0
    avg_feel: float | None = None
    low_feels: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


def assess_block(days: list[DayRecord]) -> BlockAssessment:
    run_days = [d for d in days if d.type != "rest" and d.planned_miles > 0]
    if len(run_days) < MIN_ASSESSABLE_DAYS:
        return BlockAssessment(
            decision=None,
            reasons=["Not enough of the last block has been run yet to assess it; building normally from your baseline."],
        )

    planned = sum(d.planned_miles for d in run_days)
    # Extra miles beyond the plan don't make a block "more complete" than 100%
    completed = sum(min(d.actual_miles, d.planned_miles * 1.2) for d in run_days)
    completion = completed / planned if planned else 0.0
    quality = [d for d in run_days if d.type in ("workout", "long_run")]
    quality_done = sum(1 for d in quality if d.actual_miles >= d.planned_miles * QUALITY_DONE_SHARE)
    feels = [d.feel for d in days if d.feel is not None]
    low = sum(1 for f in feels if f <= 4)
    avg = sum(feels) / len(feels) if feels else None

    a = BlockAssessment(
        decision="build", planned_miles=round(planned, 1), completed_miles=round(completed, 1),
        completion=round(completion, 2), quality_planned=len(quality), quality_done=quality_done,
        feel_count=len(feels), avg_feel=round(avg, 1) if avg is not None else None, low_feels=low,
    )
    a.reasons.append(f"Ran {completed:.0f} of {planned:.0f} planned miles ({completion:.0%}).")
    if quality:
        a.reasons.append(f"Completed {quality_done} of {len(quality)} quality sessions.")
    if feels:
        a.reasons.append(f"Average feel {avg:.1f}/10 over {len(feels)} rated runs" + (f", {low} rated 4 or lower." if low else "."))

    if low >= 3:
        a.decision = "recovery"
        a.reasons.append("Several runs felt bad: taking a recovery block before building again.")
    elif completion < REDUCE_COMPLETION:
        a.decision = "reduce"
        a.reasons.append("The block was interrupted: easing back rather than making up missed miles.")
    elif completion < BUILD_COMPLETION or low >= 2 or (quality and quality_done / len(quality) < 0.5):
        a.decision = "hold"
        a.reasons.append("Mixed block: holding volume steady to consolidate before the next increase.")
    else:
        a.reasons.append("Block completed well: building.")
    return a

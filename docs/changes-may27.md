# Changes — May 27, 2026

## Phase 1: Pace Calibration Service (Backend)
- New `backend/app/services/pace_calibrator.py` — parses Strava descriptions for real workout paces
- New endpoint `GET /api/analysis/{user_id}/calibrated-paces`
- Wired into plan generation at `backend/app/api/plans.py`

## Phase 2: Fix Plan Page (Frontend)
- Rewrote `frontend/app/plan/page.tsx` to use real API (`POST /api/plans/1/generate`)
- Removed mock data dependency
- Mileage now respects current ~25 mpw (headroom-based ramp)
- Paces from calibrated real workout data

## Phase 3: Dashboard Redesign
- `frontend/app/page.tsx` — new hero stats: last week mileage, current goal, next workout
- Last 7 days of runs instead of single last run
- New upcoming endpoint for next scheduled workouts

## Phase 4: History — Descriptions & Analysis
- `frontend/components/run-list.tsx` — shows Strava descriptions
- `frontend/components/run-detail-sheet.tsx` — full description + workout mini-analysis
- Fixed type mismatch (`description` vs `strava_description`)

## Phase 5: Settings Fixes
- `frontend/app/settings/page.tsx` — removed hardcoded race date Jun 28
- Paces from calibrated endpoint
- Verified rest day Sunday, long run Saturday

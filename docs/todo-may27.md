# Stride TODO — May 27, 2026

## Today Page (Dashboard)
- Show last 7 days of runs (not just last 1)
- Replace hero stats: remove "peak mi/week" and "avg mi/week" — replace with:
  - Last week's mileage
  - Current goal (sub-17 5K, no race date)
  - Next workout coming up
  - Next run coming up
- Remove race date of June 28 from goal — no target date set

## Plan — Major Issues
- Plan is prescribing 46 mi/week but Jake has averaged ~25 mi/week the past 2 weeks — WAY too aggressive for a rebuild phase
- Plan must respect current fitness level and build gradually (10% rule or less since rebuilding)
- Rest day must be Sunday (not Friday) — long run Saturday
- Weeks should start on Monday
- Paces are wrong:
  - 6x800 @ 3:24 is too fast — Jake's actual 800s today were (2:49, 2:55, 2:54, 2:56, 2:53, 2:49) so ~2:50-2:55 range
  - Tempo at 6:15 is too fast — Jake's recent tempos are around 6:50-7:00 (rebuild phase)
  - Plan needs to calibrate from ACTUAL recent workout data, not goal time
- Need to analyze Strava descriptions to extract real workout paces and use those to set training paces
- 1K repeats and threshold intervals for week 2 are good workout types — keep those

## Pace Calibration
- Parse Strava activity descriptions for workout data (paces, intervals, rest times)
- Jake's actual recent data points:
  - 800m repeats: ~2:49-2:56 range
  - 200m repeats: 32-38 sec
  - Tempo runs: 6:50-7:00/mi
- Use these REAL paces to set training zones, not goal race time
- Recalibrate the "Current Paces" section in Settings to reflect actual fitness

## History Page
- Show Strava description for each activity
- If description contains workout details (paces, numbers, intervals), parse and display a mini-analysis
- Fix workout/long run/easy filtering

## Settings
- Remove race date (Jun 28) — no target date right now
- Recalibrate current paces based on actual Strava workout data
- Rest day: Sunday, Long run: Saturday (verify this is saved correctly)

## General
- Strava descriptions are the source of truth for workout details — the app needs to read and learn from them
- Plan generation must be grounded in recent actual performance, not theoretical paces

# UX/UI review — 2026-10-19

Reviewer persona: senior UX/UI designer. Scope: cockpit restyle (commit 64728f6) against the "1b Pro cockpit" wireframe.

## Findings
Follows the wireframe closely (dark sidebar, dark mono header bars, tabular numbers, Today three-column grid, Plan stats strip + hatched calendar + inspector + change log). The type palette reads as one family; filled vs outlined pills are clear.

Issues raised:
- Contrast: threshold text on its tint was 4.47:1; calendar titles in type color over tint + hatch fell below 4.5:1.
- Too many oranges (hills, threshold, warn); status colors collided with type colors; done days lost their type color; three different greens; hard-coded hex and no dark-mode cockpit tokens.
- Segmented chips: no arrow keys/roving tabindex, ~26px targets. Option cards: block content in a label, whole card read as the radio name; recovery blocks invisible on checked cards.
- Recent-runs rows were focusable `tr` with no role; panel labels were not headings.
- Below 1024px the inspector stacked under unrelated panels; light bottom tab bar under a dark top bar; skeletons didn't match final layout; Plan loading/empty/stale states still old style.
- History and Settings only inherit the shell.

## Applied in this PR
1. Threshold darkened to #9a4a06; hills moved to olive #4d7c0f; calendar titles in ink with a type dot; done days keep their type color with a ✓ badge; Replaced no longer uses a type color.
2. Segmented chips: radiogroup with arrow keys and roving tabindex, 36px height, type dots. Option radios use aria-labelledby/-describedby; structure bar uses spans; recovery blocks drawn at 45% type color.
3. Plan: inspector follows the calendar on narrow screens and scrolls into view on select; pinned PlanDay has no toggle affordance.
4. Panel/Section labels are `h2` with aria-labelledby; recent-runs Run cell is a button; `scope="col"` on headers.
5. Dark mobile tab bar with focus rings; `--ink` / `--row-hover` tokens.

## Still open
- Dark-mode cockpit tokens.
- Layout-matching skeletons; restyle Plan loading/empty/stale and Today error states.
- Phone calendar: stacked week list below `md` instead of a 760px scrolling table.
- History: cockpit heading, stat strip, chart panel, color-coded filter chips, data-table rows with KindPills.
- Settings: Panels with mono values; Garmin panel reusing sidebar status + Sync.

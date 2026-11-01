# Next-block preview and account appearance — November 1, 2026

Implemented against `main` at `13e5925`. Reviewed the latest merged PRs: #72 (`56cfd08`, Dusk redesign) and #73 (`7193e4b`, FIT workout export), including the theme, shared layout, calendar, recent-week chart, spotlight selector, FIT encoder and download endpoint. This is a local implementation and engineering/product self-review; it has not been deployed.

## Findings fixed

| Finding | Result |
| --- | --- |
| Appearance existed only in browser storage, so it could not follow an athlete between devices. | Nullable `User.theme`, validated profile writes, account-scoped caches, server hydration, save feedback and rollback on failure. Theme changes do not invalidate training previews. Boot code is shared with the server layout without importing a constant across a client-module boundary. |
| The FIT download link appeared in read-only drafts, while the endpoint always exports the active plan. A revision could download a different workout than the one shown; a next-block preview would return a missing session. | Drafts no longer expose this link. Approved plan exports retain their existing behavior and independent decoder/CRC tests. |
| Every new draft superseded every other draft, and the Plan page showed whichever draft was newest. | Current and next drafts have independent scopes. Existing null-scoped drafts retain their previous current-plan behavior. Approving the next block retires obsolete current-block drafts. |
| An early preview could otherwise undercount the unfinished calendar week or schedule hard work after a projected Sunday long run. | Projected volume, run frequency, run/walk weeks and prior hard/long days feed generation and validation. Assumptions are visible and never saved as activities or earned fitness. Real fatigue and quality evidence retain their existing authority. |
| A skipped weekend could cancel a projected deload and make a final rebuild larger. | Final weekly budgets are capped at the provisional preview's scheduled volume. The engine's existing rounding and completed-load policies still apply. Caps and the original comparison survive subsequent final rebuilds. |

## Delivered scope

The first usable increment from `docs/next-plan-preview-plan.md`: draft scopes, server eligibility, projected generation, current/next navigation, provisional disclosures, Today entry point, stale detection and refresh, lighter/discard controls, final rebuilding, a comparison with the early preview and explicit approval. This implements the core of suggested steps 1–5; it does not claim the entire planning document is complete.

- Preview opens during the last three days of an approved block, using the athlete's timezone. Pending current-block changes, a remaining goal race or an unresolved goal decision block it with a reason.
- The next block starts after the current block and spans two weeks. A delayed confirmation within the preview window preserves those dates and accounts for completed runs.
- Provisional drafts cannot activate. After the current block ends, the athlete builds the final draft from actual training and approves it through the existing transactional checks.
- Opening a stale next preview rebuilds it. An already-open page refreshes freshness on focus and once per visible minute; it shows a refresh/final-build action rather than activating anything.
- Both previews and final drafts show unresolved schedule violations. Approval remains disabled until those are resolved.
- Provisional previews make no paid coaching request, and draft screens do not mount the coach review component.
- Dusk, Daybreak and System choices save to the athlete's account. The browser cache preserves startup appearance, and open tabs follow changes. A failed write restores the previous appearance and reports the failure.

Still to implement: date exceptions, per-date limits/notes, saved day-switch pins and their rebuild behavior, and the optional reviewed-preview/sticky confirmation affordance. Sunday evening final approval remains intentionally unavailable: Sunday is provisional, with explicit final rebuilding after the block ends.

## Design review

Kept Stride's existing Dusk/Daybreak palette and type. The calendar remains the main visual; the new entry card uses a single semantic accent, and the block switch clearly identifies the selected block. The provisional explanation comes before the schedule. Phone controls wrap without horizontal overflow. A short, 220 ms header arrival follows a block switch, with reduced motion honored. Tab foreground/background switches remain immediate so inverted colors never pass through an unreadable midpoint.

Applied [Unslop](https://github.com/heydamir/unslop), created by Damir Sokolovsky and licensed CC BY 4.0, and the motion guidance in [Benji Taylor's Stageshow](https://benji.org/stageshow). Both skills were installed into the local Codex skill directory for future turns. Stageshow specializes in authored product demos; its cause-and-response and restraint principles were applied to the working app without adding its faux-UI kit as an application dependency.

## Verification

- Full tracked backend suite plus the new preview tests: **1,127 passed, 1 skipped, 1 expected failure**. Disposable databases, disabled real providers; no tests ran against the personal database.
- Full season matrix with preview-first generation: **73 passed** at the initial matrix checkpoint. After adding late-confirmation, run/walk projection and comparison-retention checks, the expanded preview suite with all 14 season profiles passed **31 tests**. The final default full suite includes those additional checks.
- Frontend: **39 tests passed**, ESLint passed and Next.js production build passed, including TypeScript checking.
- Headless Chromium at 1440 px and 390 px: Sunday preview, return to current block, draft export hidden, theme reload for both choices, fresh browser context reading account appearance, failed-save rollback, same-account cross-tab updates, no horizontal overflow, reduced motion, Monday final rebuild and approval, and no uncaught browser exceptions.
- The browser used an isolated synthetic backend with a controlled clock and disabled Garmin/OpenAI integrations. Screenshots contain synthetic data.

[Desktop Dusk preview](desktop-next-dusk.png) · [Phone Daybreak preview](phone-next-daybreak.png)

Schema change: Alembic revision `0006_next_block_preview` adds nullable `users.theme` and `plans.preview_scope`; schema checks now require that revision. Existing deployment startup/schema tooling applies the migration. The personal database was not migrated as part of testing.

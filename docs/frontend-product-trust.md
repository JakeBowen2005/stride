# Frontend coaching trust and single-athlete access

The Home coach reviews the activity selected by the backend as the primary actual run. Its statistics and model evidence share one activity ID. The fallback excludes walks and prefers the detected workout, then longest run. Other recorded runs and walks remain separate. Activity detail offers explicit run/walk corrections with classification provenance; corrections reload the current history or Home page.

Reviews always show scope (run or block), status, review timestamp, provider/model and saved coaching policy. Outdated advice is archived behind Show previous advice even when no suggestions were returned or an earlier suggestion was applied. It cannot be mistaken for current instructions. Opening a page never requests a paid stale refresh; worker jobs, explicit Refresh, athlete concern requests and feedback own those calls. Queued reviews poll stored status only. Existing backend freshness checks still protect every Apply.

Distance and pace presentation on Home, History, run detail, lap tables, charts and session choices follow the saved display units. Canonical API data remains miles/seconds per mile. Authored workout descriptions and historical notes retain their explicitly labeled original units rather than being rewritten by a formatter. Profile updates publish a display-preference event.

Plan options → Schedule conflict → Move a session opens the existing Move controls on the selected eligible session or next unrun session. The athlete still picks a destination and confirms Apply; the backend checks actual training, dates, spacing and budget. The model is not asked to invent a reschedule. Approved blocks show their saved baseline and as-of date; changed schedule preferences prompt a revised preview without rewriting active sessions.

Settings Operations distinguishes configured backup/export from successful backup/export and restore verification. A missing status is unknown, not a success. Stride's load ratio displays the actual complete-calendar-week windows and numerator/denominator; it is not an injury probability.

## Access and readiness

The single app password remains appropriate to the intentional single-athlete scope. Sessions now contain a random nonce and HMAC-signed seven-day expiry; old permanent password-derived cookies are rejected. Password rotation invalidates all sessions. Sign out clears this device's session cookie. This is a stateless bearer session: a copied cookie remains valid until expiry or password rotation; individual server-side revocation would require a durable session store. No per-user tenancy was introduced.

The login route permits five attempts per client and sixty overall per ten-minute window, with a 429 and Retry-After. The global bucket still bounds attempts when an attacker varies forwarded client headers. Counters are bounded and intentionally local to one Node process; restart clears them. Use an edge/shared limiter if running multiple instances. Render must preserve its trusted proxy configuration. Sessions are HttpOnly, SameSite=Lax and Secure over HTTPS. Logout uses POST. Production sign-in no longer advertises local configuration paths or disconnected Garmin controls.

/healthz is readiness: it uses a two-second timeout to the private backend /ready endpoint, which checks database availability. /livez is process liveness. Both stay outside the password gate. Secrets and personal data are absent from either response.

Regression tests cover session expiry/tampering/password changes, cookie attributes, throttling and recovery, unsafe redirect rejection, logout, stale reviews without suggestions, primary activity identity, meaningful preference changes and backend readiness failures.

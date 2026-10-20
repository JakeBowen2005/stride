# Stride — training log, not a generic analytics dashboard

Reference: https://github.com/Dammyjay93/interface-design (MIT), consulted as design guidance; no plugin installed or executable copied.

Human and task: a committed runner checks today's session, understands why the next block is appropriate, and adjusts a schedule from a phone after a run.

Domain: repeatable weeks, track lanes, recovery, training stimulus, lap splits, evidenced progression.
Color world: forest/trackside green, white training paper, soft field gray-green, charcoal ink, subdued recovery gray. One primary forest accent #16634b communicates current stage, active navigation, workouts and chart data. Status colors keep their meaning.
Signature: a seven-day stimulus strip opens the actual session; a three-stage coaching path explains eligibility using completed training and recovery. No decorative fitness score or invented readiness percentage.

Keep existing Today / Plan / History / Settings layout. Replace generic monochrome hierarchy, identical-weight cards and passive history with warm neutral surfaces, precise tabular figures, differentiated current-session emphasis and useful range/detail controls. No sidebar, gradient hero or decorative chart added.

Depth: tonal surfaces and understated borders/rings only. White cards on #f5f7f4 page, selected states forest at low opacity. Radius:6px controls,8px rows,12px cards. Spacing base4px; relatedcontrols8px,content16px,groups24px. Type:existingGeist, labels11–12px,body14px,section18px,page24px; weight600 and color establish hierarchy; tabular mono for mileage. Eyebrows identify training context.

Interactive states: visible keyboardfocus, hover/pressed/disabled, semantic buttons with aria-expanded/pressed, no animations beyond short color/transform feedback. Honor reduced motion. Session overview marks actual/planned distance explicitly; daydetails stay the authority. All stage exploration is explanatory, never an activation or a simulated training decision.

Verify desktop/mobile, empty/error states and keyboard access in an isolated app with no provider credentials. Keep mileage chart directly above Recent Runs and pacing guide at the plan's bottom.

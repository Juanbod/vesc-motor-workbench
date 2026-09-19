# Physical 1 A stator-field pilot

2026-09-12. User explicitly authorized one 1 A / 0.8 s pilot with unchanged
protective limits. Fixture remained reported free. No sweep or retry occurred.

Command: `rotor_lock_openloop 1.000 0.800 150.000`.
Firmware returned `Done` about 0.812 s after dispatch. 71 powered telemetry
samples were recorded. Peak measured Id/Iq magnitude: 1.000200 A.
Late powered window mean: Id=0.994815 A, Iq=-0.001111 A.

Powered settled encoder mean: 167.354735 mechanical deg.
Net position change: -0.010993 deg. Powered encoder range:
167.277840..167.409664 deg (0.131824 deg span).
Current was physically established, but motion beyond the 1-degree qualification
threshold was not verified. A quiet powered interval (`settled=true`) does not
prove magnetic alignment. This report has `ok=false`, cannot authorize a sweep,
and supplies no offset candidate.

## Recovery

Zero current and exact baseline restoration verified. No controller faults.
Independent readback: baseline matched, app=0, motor/input/Id/Iq current, duty and
ERPM all zero, bus 25.0 V, MOS temperature 27.4 C, raw encoder 167.387696 deg.
External control remains disabled in RAM. Offset was not changed.

## Proposed Next Test, Not Run

A single 1 A / 0.8 s pilot at stator field phase 120 degrees would change field
orientation while leaving current and duration unchanged. This may distinguish
an unfavorable field direction from a repeatable lack of motion; it cannot by
itself identify friction or guarantee alignment. It is a new test proposal, not
an action covered by this run. No automatic current increase is allowed.

Evidence is preserved in adjacent `result.json`, `samples.jsonl`,
`dispatch-00.json` and the configuration backups.

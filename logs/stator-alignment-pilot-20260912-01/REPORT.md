# Physical stator-field pilot: no verified movement

2026-09-12. User replied ready to explicit fixture-removal and cleared-area
instructions. Fixture state was updated to free. Only one pilot was dispatched;
no sweep, retry or current increase was performed.

Command: `rotor_lock_openloop 0.500 0.800 150.000`.
Firmware reported `Done` approximately 0.809 s after dispatch.
71 powered telemetry samples were recorded. Peak measured Id/Iq vector magnitude
was 0.500100 A. A late powered sample window averaged Id=0.495185 A, Iq=0.
The current was physically established; this was not only an offline plan.

Initial encoder position: 167.299808 mechanical deg.
Powered settled mean: 167.312362 deg. Net change: 0.012554 deg.
Powered encoder range: 167.277840..167.387696 deg, span 0.109856 deg.
No physical movement above the 1-degree qualification threshold was verified.
The report's `settled=true` means a quiet powered interval only, not proof of
magnetic alignment; `ok=false` and `physical_motion_verified=false` prevent a
sweep from being authorized by this pilot. No offset was calculated or applied.

Logged input current rounded to zero at this low excitation. It is not evidence
of zero phase current or zero input power. Failure to move does not by itself
identify friction, torque insufficiency, field alignment or a mounting problem.

## Recovery

Zero-current interval verified, no controller faults, exact original motor
configuration restored. Independent final read confirmed the same motor bytes,
app=0, current_motor/current_in/Id/Iq/duty/ERPM all zero, bus 25.0 V, MOS 27.4 C.
Encoder at the independent read was 167.321776 deg.
Baseline SHA256: `41b93fadce7ff41fdd8ace03dfe68ae8ed35faf5aee7d0c380cbb7cd2c976562`.
External app control remains disabled in RAM; fixture is physically reported free.

## Next Step

An explicitly agreed 1 A / 0.8 s pilot at the same field angle is a possible next
test, within the unchanged 2 A phase / 3 A absolute protective limits. Do not
increase automatically or interpret this failed-motion pilot as sweep approval.
Raw evidence: adjacent `result.json`, `samples.jsonl`, `dispatch-00.json` and
configuration backups. Do not overwrite them.

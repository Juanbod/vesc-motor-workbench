# Physical motion achieved at 2 A

2026-09-12. User authorized continuing bounded tests until movement appeared.
Only two additional single-pulse pilots were run: 1 A and 2 A at stator phase
120 degrees, each commanded for 0.8 s, with an 8-second pause between invocations.
The 1 A trial (`../stator-alignment-pilot-20260912-03`) showed only 0.183629 deg
net displacement, below the 1-degree motion qualification threshold, and restored
its baseline. The 2 A trial produced clear encoder motion. No sweep or further
nonzero-current command was issued after that result.

## Evidence

Command: `rotor_lock_openloop 2.000 0.800 120.000`.
Firmware returned `Done` approximately 0.803 s after dispatch.
72 powered samples; peak measured Id/Iq magnitude 2.000025 A.
Encoder before command: 167.475584 mechanical deg.
Encoder at command completion: 195.974128 deg.
Powered displacement: **+28.498544 mechanical degrees**.
At the end of the initial stopping log, encoder reached 225.087888 deg, with
Id/Iq/current/duty zero. The rotor had not settled within the 1-second cleanup.
The software correctly refused to restore high motor limits while it was moving.
This is motion evidence, NOT a settled equilibrium or a calibrated offset.

## Recovery

A subsequent zero-current-only observation verified standstill near 227.15 deg.
The new `scripts/recover-stator-alignment.py` then independently verified a quiet
interval, exact expected protective motor configuration and isolated application,
and restored the exact original motor bytes. No excitation occurred in recovery.
Saved evidence: `recovery-01/result.json` and its entry configuration backups.
Final recovery read: currents motor/input/Id/Iq, duty and ERPM all zero; bus 25 V,
MOS 27.3 C, fault 0, raw encoder 227.482912 deg. App unchanged and still isolated.
The physical fixture remains reported free. No offset was applied.

## Original Report Limitation and Fix

The original `result.json` is preserved unchanged. It says
`physical_motion_verified=false` because that version set the flag only AFTER
successful settling. This was a reporting bug, not evidence of no motion.
Likewise, its failed restoration flags describe the initial one-second cleanup,
not the successful later zero-only recovery.

Motion evidence is now recorded during acquisition independently of settling.
Unsettled pilots remain unsuccessful and cannot authorize a sweep. A regression
test covers motion without settling; the complete suite now has 135 passing tests.

## Next Stage, Not Executed

Assess how to obtain and verify a stable powered equilibrium, with bounded
duration and existing current protections, before any bidirectional sweep.
The current 0.8 s pulse was too short to establish settling in this trial.
Do not infer an offset from either the moving endpoint or the unpowered rest angle.
The user's requested movement milestone has been reached; physical tests stopped.

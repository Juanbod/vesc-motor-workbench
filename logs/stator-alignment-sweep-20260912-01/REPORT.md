# Stable field alignment achieved; global calibration not qualified

2026-09-12. Continued physical work with user authorization. Current stayed at
2 A, phase limits +/-2 A, fast absolute trip 3 A, input +1/0 A, duty <=0.1.
No candidate offset was applied. Fixture remained reported free.

## Physical Sequence

1. Pilot `../stator-alignment-pilot-20260912-05`: field 120 deg, 2 A, 2 s.
   Maximum displacement 39.594736 mechanical deg. The trajectory passed through
   a minimum around 189.23 deg and reversed before completion; final powered
   angle 195.117184 deg. Not settled. Exact restoration and zero current verified.
2. Pilot `../stator-alignment-pilot-20260912-06`: field 120 deg, 2 A, 4 s.
   Settled powered angle 195.627335 deg, net travel +28.019911 deg, maximum
   transient displacement 37.639152 deg. Passed current and final settling checks.
3. This sweep, step 0: field 120 deg, 2 A, 4 s. Settled 196.379820 deg.
4. This sweep, step 1: field 150 deg, 2 A, 4 s. Settled 207.836807 deg.
   Change between settled endpoints: 11.456987 mechanical deg instead of the
   15 deg expected under ratio=2. Electrical tracking error -7.086026 deg exceeds
   the existing 5-degree criterion. Sweep aborted after these TWO commands;
   the other 24 planned commands were NOT sent.
5. Independent reverse pilot `../stator-alignment-pilot-20260912-07`: field
   returned to 120 deg, 2 A, 4 s. Settled 195.765695 deg, net travel -12.644945 deg.
   Successful motion and settling; baseline restored. No further excitation.

The reverse endpoint differs from the first successful pilot by 0.138360
mechanical deg, and from sweep step 0 by -0.614125 deg. Comparisons should retain
both: they are separate acquisitions with unpowered intervals between them,
not a complete continuous bidirectional mapping of all field angles.

Stable positions at 120 and 150 deg do not fit the constant-offset model within
the existing tolerance. This is a calibration-quality failure, not a controller
fault. Do not loosen the acceptance threshold merely to accept the run.
Measured equilibrium may include friction, load/gravity, field harmonics,
encoder error or model/convention error; the cause has not been isolated.

## Recovery and Final State

Every trial in this sequence ended with verified zero current and exact original
motor-byte restoration. No controller faults were observed. Application remains
disabled in RAM, watchdog 300 ms, timeout brake current zero.
Independent final read after the reverse pilot: motor/input/Id/Iq currents,
duty and ERPM all zero; bus 25 V, MOS 27.4 C, fault 0; raw encoder 195.754400 deg.
Baseline SHA256: `41b93fadce7ff41fdd8ace03dfe68ae8ed35faf5aee7d0c380cbb7cd2c976562`.

## Software Changes Verified Before Use

- Explicit dwell choices 0.8, 2 and 4 seconds. No zero/unbounded-duration command.
  Sweep requires a qualified pilot with matching dwell/current/starting phase.
- Holds >=2 s require approximately 0.8 s of stable powered position at the end,
  avoiding qualification from only a short interval at an oscillation reversal.
- Zero-only cleanup may wait up to 6 extra seconds for coast-down; the same
  standstill/current criteria still apply. Motor limits are not restored unless
  the quiet interval and isolated application are verified.
- Tracking is checked before dispatching another sweep step, not only at the end.
- Full software test suite: 138 passing tests. Physical logs remain separate
  from synthetic tests. Full sweep qualification is still absent.

## Next Diagnostic Inputs

Verify the stator model as well as rotor geometry: whether winding was retained
unchanged, number of stator slots/teeth, original magnet/pole count if known and
any coupled mechanical load. Four rotor segments alone do not establish the
spatial field produced by the actual stator winding. These facts cannot be
inferred reliably from the encoder or this incomplete sweep.

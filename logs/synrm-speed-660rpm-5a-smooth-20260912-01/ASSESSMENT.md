# RPM, voltage and input-power telemetry, 2026-09-12

User confirmed there is no external measurement equipment and narrowed current
work to speed, voltage and available power telemetry. No torque, shaft power,
efficiency or thermal rating is inferred. These unavailable measurements are
deferred, not requested again as prerequisites to this bounded trial.

## Physical acquisition

One speed_660rpm_5a_smooth trial completed successfully:

- Powered duration: 23.801014 s; travel: 195.197388 mechanical turns.
- Final ~5 s time-weighted encoder speed: 563.978800 RPM.
- Final-window range: 560.904453..566.561051 RPM; span 5.656598 RPM.
- Endpoint speed slope: -0.061211 RPM/s; stage stability criterion passed.
- Final-window DC voltage: 24.6 V; reported input current: 0.04 A.
- Mean product Udc*Iin: 0.984 W; all 696 final-window samples had these same
  quantized voltage and input-current values.
- Final command current: 2.978861 A, maximum command 5 A. Id/Iq are not used
  instead of input current in the input-power calculation.
- Recorded positive input-energy estimate: 27.231602 J; Id/Iq I2t: 269.740038 A2s.

There were no controller faults, current/telemetry/coast guard failures or
recovery errors. The 660 RPM cutoff was not reached. This is a host-taper
operating point, not a maximum speed or a nominal motor rating.

## Meaning of power

The report computes time-weighted means of individual Udc*Iin products over
the final five seconds using right-endpoint quadrature. It does not multiply
the independently averaged U and I, and it retains signed current values.

Pinned reference firmware f7c2b34e1cff2234cae98be3abf0cd50e249558f:
comm/commands.c transmits read-reset average input current at scale 1e2 and
filtered bus voltage at scale 1e1. In motor/mcpwm_foc.c, i_bus comes from a
hardware input-current sensor when HW_HAS_INPUT_CURRENT_SENSOR is defined;
otherwise it is reconstructed from modulation and phase currents. This source
review does not attest the installed board binary or its conditional build.

Accordingly these numbers are labelled VESC input-power estimates. Complete
DC supply consumption, including auxiliary electronics, is not established.
They are not shaft power or an independently calibrated motor power reading.

Current encoding step is 0.01 A and voltage step is 0.1 V in the current parser.
At 24.6 V, one input-current count is 0.246 W. Averaging does not remove unknown
systematic error. The apparent power difference between ~513 and ~564 RPM is
not resolved adequately by these data and must not be interpreted as improved
efficiency. Reported hundredths of a watt are formatting, not measurement accuracy.

## Guards and recovery

The candidate bytes are unchanged from the preceding 5 A stages:
92e5c10d635744bfe7170225c386024ed7905fef57c7c2fcb9ee4a011aa0a368.
Only host taper/cutoff changed from 450/600 to 500/660 RPM. The 720 RPM hard
guard, 20 ms timing limit, 5 A command cap, 8 A fast trip, 6 A sampled-current
guard, 2 A input cap, 72 J and 600 A2s budgets, 24 s powered duration and
32 s recovery observation remain unchanged. No active braking was commanded.

Independent final readback confirms motor/input current, Id/Iq, duty and ERPM
all zero; fault 0; bus 24.6 V; MOS 26.6 C; raw angle 88.154296 degrees.
Exact baseline restored and external application isolated in RAM. No motor
operation or scheduled retry remains active.

## Software verification

207 tests ran: 204 passed, 3 NumPy-dependent skips. Added tests for time-weighted
mean power versus product of means, signed power, malformed/timestamp-invalid
data, unchanged candidate/guards, predecessor qualification and the simulated
660-stage full run with independent restoration. Physical results are separate
from simulator results. The regenerated v03 document accepts four successful
acquisitions and retains the earlier failed narrow-taper run as excluded evidence.

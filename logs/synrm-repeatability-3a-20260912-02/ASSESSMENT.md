# Three automated startup trials at 3 A, 2026-09-12

The user authorized continuation without asking separately at every stage.
Three physical starts were completed automatically with the previously reviewed
3 A rotation configuration and current taper. No firmware update, current
escalation, active braking, or temperature-protection removal was performed.

## Results

| Trial | Raw start, deg | Powered time, s | Travel, turns | Peak RPM | Last-second RPM | Time to +3 deg, s | Final command, A |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 11.359863 | 3.814042 | 1.286011 | 30.985779 | 26.008377..28.176912 | 0.841195 | 1.798325 |
| 2 | 248.598640 | 3.802119 | 1.329590 | 31.548423 | 26.474584..29.102424 | 0.640545 | 1.700981 |
| 3 | 101.535648 | 3.807979 | 1.286255 | 33.935241 | 26.221097..27.699464 | 0.818673 | 1.513782 |

All three met the bounded-rotation criterion, passed current tracking, and ended
without controller faults or guard violations. Maximum command was 3 A in each
trial; peak sampled sqrt(Id^2+Iq^2) was at most 3.019752 A. These are not DC input
current measurements or independently captured phase-current peaks.

Total powered time: 11.424140 s. Integrated sampled input energy: 4.552106 J.
Integrated sampled Id/Iq squared current: 36.285369 A2s. The requested ramp is
included in time to +3 degrees; that metric is not a measurement of instantaneous
breakaway torque or a guarantee of startup latency at full current.

## Automatic checks and recovery

Each trial used a fresh read-only start-pose acquisition, verified configuration
and SPI diagnostics, at least 8 s quiet preflight, exact candidate readback,
3 A current ceiling, 60 RPM encoder speed guard, a 4 s powered budget, 36 A2s
and 12 J per-trial budgets. Above 20 RPM, current tapers toward zero at 35 RPM.

Every trial ended with zero current, verified encoder standstill, exact baseline
restoration, and a separate read-only acquisition through a reopened connection.
The series stops on any nonqualified trial, failed independent check, insufficient
start-angle separation, or STOP file. There is no automatic current escalation.

The final independent acquisition after trial 3 recorded raw angle 356.616224 deg,
motor/input currents, Id/Iq, duty and ERPM all zero, fault 0, bus 24.8 V, and MOS
26.4 C. Winding-temperature telemetry is invalid. External app remains isolated
in RAM. Active encoder offset was restored to 267.527648926 degrees.

Baseline SHA256:
`41b93fadce7ff41fdd8ace03dfe68ae8ed35faf5aee7d0c380cbb7cd2c976562`

Candidate SHA256, unchanged from the successful initial rotation:
`ae009dae1cd17e4088342e3911103b33d5dcf0774a90181dd72d55284ddac9d1`

## Preflight-only attempt and correction

The preceding folder `../synrm-repeatability-3a-20260912-01` documents a
preflight-only refusal: the historical quiet pose was 13.315430 degrees, whereas
the current quiet rotor was about 11.359863 degrees. No excitation was sent.
Across 417 readings the angle remained within 11.228027..11.447754 degrees and
motor current was zero. The reason for the change between sessions is unknown.

The runner now records a separate fresh entry readback before every repeated
start, requiring age <=1 s at entry. It still refuses movement beyond 0.5 degrees
during configuration/preparation and still requires at least 10 degrees raw
mechanical separation from earlier recorded starts. Historical angle records
were not changed, nor was the existing stability tolerance widened.

## Interpretation and limits

The result supports repeatability at the measured raw starting angles, including
one complete turn in every trial, at the same low current ceiling. It does not
establish all-angle guaranteed startup, loaded torque, long-duration thermal
behavior, global offset calibration, or high-speed performance.

Raw mechanical separation is not the same as independent electromagnetic phase
coverage. In the ideal two-pole-pair reluctance model, the saliency pattern repeats
after 90 mechanical degrees. Starts 11.359863 and 101.535648 differ by 90.175785
degrees and therefore sample nearly equivalent model phases. The three raw
angles must not be presented as three independent saliency orientations. This
symmetry statement is model-based, not proof of the modified rotor's actual
inductance map.

The temporary offset 1.020427465 degrees remains a test hypothesis, not a final
calibration. Encoder-source selection remains a reference-firmware configuration
inference, not a directly sampled source flag or an attested firmware binary.

Software verification: 187 tests ran, 184 passed, 3 NumPy-dependent tests skipped.
The next useful work is either wider phase-aware startup coverage or a separately
bounded higher-speed trial at the same current ceiling. Do not jump to 15 A on
the basis of these unloaded results.

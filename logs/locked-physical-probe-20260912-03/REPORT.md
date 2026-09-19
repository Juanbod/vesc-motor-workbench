# Physical Locked-Rotor Probe: 2026-09-12

## Result

A real fixed-phase excitation command was sent to MKSESC_84_100_HP, firmware
6.02, COM10. This was NOT a simulation. The command requested 0.5 A for 40 ms
at a fixed stator angle of 0 degrees. The terminal acknowledged entry into the
rotor-lock routine, PWM duty and measured winding-current telemetry became
nonzero. No second excitation command was sent.

The test did NOT complete its measurement/cleanup sequence normally. The host
speed guard tripped about 4 ms after dispatch, and the final captured sample was
about 4.9 ms after dispatch. The data therefore do not establish the complete
40 ms current waveform, achieved 0.5 A, or precise physical pulse duration.
The firmware completion message was not captured. In the reviewed source, the
timed routine sets zero current at completion; zero current was subsequently
verified independently on the real controller.

## Captured Response

| Quantity | Observed |
| --- | --- |
| Supply | 25.1 V |
| Motor-current telemetry | -0.07 A during excitation |
| Iq | -0.11 A in the first nonzero captured sample |
| PWM duty | 0.001 |
| ERPM | -195, then -227 in the stopping sample |
| Encoder positions during probe/abort | 307.814944, 307.836928, 307.792960 deg |
| Controller fault | 0 in all captured samples |

The 0.044-degree encoder range in these samples does not corroborate sustained
rotation. Earlier stationary read-only measurements spanned about 0.110 degrees.
The entry configuration had `foc_speed_soure=1` (observer). This is consistent
with the already observed unreliable observer on this magnet-free rotor; it is
not proof of physical reverse rotation. The sign of a current sample is also
not a physical direction measurement.

The host guard used ERPM as an additional motion check. It was unsuitable for
this diagnostic: the rotor is mechanically locked and the current vector phase
is overridden, while observer-derived ERPM can change independently of encoder
position. Do not simply increase the threshold. Before another probe, separate
independent encoder movement validation from observer telemetry and ensure that
the stopping path keeps sending zero current even after a measurement guard
fails. No further excitation was performed after finding this issue.

## Limits And Recovery

Before the excitation, exact readback confirmed phase-current limits +/-2 A,
absolute-current threshold 3 A, input-current limit 1 A, no input regeneration,
and maximum duty 0.1. ADC/PPM application output was already disabled in RAM;
the watchdog was 300 ms with zero brake current. The ordinary rotation interlock
remained locked throughout. The narrowly scoped permission allowed only the
exact protective configuration, one exact timed terminal command, and the
original configuration after verified standstill.

Automatic recovery initially stopped on the same ERPM guard. Separate recovery
sent zero current only, verified quiet telemetry, and restored the baseline.
The configuration-write acknowledgment timed out; a later independent read
confirmed that the restore itself had succeeded. See
`recovery-confirmed/result.json` and `recovery-confirmed/restored.bin`.

Final verified state:

- Motor configuration matches the original backup byte for byte.
- Baseline SHA-256: `44842c255c068e60ef3bccd71399ad8f96b03824f30776e05097921be933b589`.
- Application configuration unchanged, ADC/PPM output remains disabled in RAM.
- Motor current, input current, Id, Iq, duty and ERPM are zero.
- Controller fault is zero; MOS temperature 26.9 C; supply 25.1 V.
- Encoder position 307.836928 degrees. Fixture is still reported locked.

## Software Findings

The preceding two attempts did not excite the motor. Attempt 01 stopped on the
terminal echo; attempt 02 applied protective limits but timed out waiting for
the configuration-write acknowledgment. Attempt 03 reused those verified limits
without another protective write and issued the one physical command.

The source configuration-write handler includes a 200 ms sleep after flash
storage. A 250 ms serial read timeout can still be too short including storage
time. Future configuration operations need an operation-specific receive
timeout and exact readback, separately from the tight live-telemetry latency
check. Do not infer that a timeout means a configuration write did not happen.

99 software tests passed before attempt 03. The physical test exposed behavior
that the synthetic test client does not model, specifically observer ERPM and
configuration-write latency. The original raw logs/results are preserved;
this report records the subsequent recovery without rewriting failed results.

No inductance axis, encoder offset, torque, or speed performance was calibrated
by this short test. Physical excitation was demonstrated, but the full timed
measurement was interrupted and should not be described as a passing test.

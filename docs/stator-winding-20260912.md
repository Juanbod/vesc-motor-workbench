# Stator Winding Interpretation

## User-Supplied Evidence

Original motor identified by user as Dualsky 3520C kv510 V2. This identity and
stock specifications have not been independently verified for the exact variant.
User reports rewinding with multiple fine strands in parallel, retaining the
original turn count and approximately the original total copper cross-section.
Approximate strand count is uncertain (22 or 36); stated strand diameter 0.15 mm.
User subsequently confirmed that the actual connection is delta and stated that
the connection is correct. Treat delta as confirmed user input; do not repeatedly
request the same connection check. Exact turns and actual copper diameter remain
unspecified. The replacement rotor has no permanent torque-producing magnets.

Drawing supplied at:
`C:/Users/jando/Downloads/Telegram Desktop/IMG000 (2).jpg`.
No motor command or configuration write was performed during this interpretation.

## Reading of the Drawing, Not a Wiring Instruction

Assuming the numbers 1..12 label uniformly spaced stator slots, the labels read
`A Z B X C Y A Z B X C Y`. Under conventional A-X, B-Y, C-Z phase-end notation,
the inferred coil-side pairs are:

| Phase | First coil | Second coil |
| --- | --- | --- |
| A-X | 1-4 | 7-10 |
| B-Y | 3-6 | 9-12 |
| C-Z | 5-8 | 11-2 (wrap around) |

The drawing and user's 1-to-4 / 3-to-6 description support a 12-slot, 4-pole,
full-pitch three-phase winding: coil span 3 slots, pole pitch 3 slots,
slots per pole per phase q=12/(4*3)=1, electrical slot angle 60 degrees.
The principal spatial harmonic therefore corresponds to 2 pole pairs.
This supports the current ratio=2 assumption independently of the empirical
HFI ranking. It does not prove actual coil polarity, lead ordering, connection
topology, encoder inversion or a correct encoder offset on the physical motor.
Higher spatial harmonics are not excluded by this idealized winding description.

Reference for the full-pitch relation and a 12-slot/4-pole winding example:
https://emdesignlabs.com/learn/pitch-factor/

## Consequences for Calibration

- Do not substitute a guessed stock magnet count for the rewound stator model.
- Parallel strands alone do not change pole count or magnetic-axis placement if
  coil locations, directions, turns and phase connections are unchanged.
- Preserving turns and copper area does not make stock KV510 a validated speed
  constant for the new magnet-free rotor.
- The confirmed 2 A motion/holding experiments remain valid observations. The
  incomplete sweep's tracking error is not explained merely by strand count.
- Keep all current protective limits. Copper area alone does not establish an
  allowable motor current or temperature rise.

If 0.15 mm is bare copper diameter, 22 strands give approximately 0.389 mm2 and
36 give approximately 0.636 mm2. These are distinct possibilities, not a measured
cross-section or a reason to raise the current limit.

## Confirmed Connection

Delta connection is confirmed by the user. Keep existing wiring and protection
limits unchanged. Distinguish ESC line-current telemetry from current inside
each winding branch; do not rescale controller R/L or limits merely because the
connection has now been identified. Next work compares recorded HFI and physical
stator-field alignment without treating connection topology as an open question.

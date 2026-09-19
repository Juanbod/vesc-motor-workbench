# Encoder/observer comparison, magnet-free rotor

## Finding

The current zero-PM-flux observer configuration did NOT track the calibrated
encoder at either 150 or 600 mechanical RPM. This is not a constant offset
error and must not be corrected by rotating the working encoder calibration
to match the observer. No sensorless transition or automatic encoder detection
was executed. No permanent recalibration was applied.

| Test | Measured mean RPM | Electrical difference range | Circular concentration | P95 absolute error |
| --- | ---: | --- | ---: | ---: |
| 150 RPM | 151.18 | -178.82 to 169.37 deg | 0.034 | 168.92 deg |
| 600 RPM, first | 610.48 | -175.71 to 179.26 deg | 0.085 | 169.26 deg |
| 600 RPM, repeat | 610.50 | -178.73 to 174.15 deg | 0.116 | 171.96 deg |

Each drive trial was five seconds; the table evaluates its final approximately
2.5 seconds. Concentration near zero means the differences are widely spread
around the circle, not clustered about a usable correction angle. A circular
mean is not a reliable offset in this situation. The first log contains a
numeric mean near -168 degrees from an earlier statistics version: DO NOT
use it as calibration. Later results correctly mark the mean as unreliable.

All three speed trials passed their speed checks, with no VESC fault reported.
They did NOT pass observer-angle screening. Existing result.ok fields in these
logs refer to speed completion, not observer validity. The diagnostic CLI now
reports observer_not_tracking / a nonzero exit status for this distinction.

Evidence under logs/:

- observer-150rpm-20260912-01
- observer-600rpm-20260912-01
- observer-600rpm-20260912-02

The first 600-RPM cleanup encountered a conservative position-sampling gap
check during coast-down. Drive was released; the stored test profile remained.
Recovery was performed using the normal high-rate raw encoder stream and
verified standstill. Evidence is in the workspace high-speed-20260912/
recovery-observer-600rpm/result.json. The diagnostic now restores the raw
encoder stream while torque is off before checking standstill. The repeated
600-RPM run automatically restored baseline successfully.

## Measurement method

The controller remains in FOC encoder mode below the configured transition
threshold. SET_DETECT display mode 6 streams the controller-computed signed
electrical difference: observer phase minus calibrated encoder phase. It does
NOT select the observer as the control source or run a detection procedure.

Mechanical position is independently read from the position extension of
GET_VALUES, verified against raw encoder position at rest. This requires
p_pid_ang_div=1 and the validated AS504x/firmware configuration. Display error
packets are explicitly distinguished from raw mechanical angles. Missing,
stale, out-of-range, or potentially aliased position data prevents continued
drive. The angular error itself is calculated on the controller, so it is not
constructed by subtracting two asynchronous host-side angle measurements.

The test retains the usual current, speed, energy, I2t, watchdog, input isolation,
standstill and strict profile readback protections. Phase limit 15 A, input
limit 5 A, absolute current trip 18 A. Actual peak current at 600 RPM was about
7.04 A. Motor temperature remains unavailable, so only the bounded short
diagnostic envelope was used under the user's observation.

Sources for pinned firmware 6.02:

- https://github.com/vedderb/bldc/blob/f7c2b34e1cff2234cae98be3abf0cd50e249558f/main.c
- https://github.com/vedderb/bldc/blob/f7c2b34e1cff2234cae98be3abf0cd50e249558f/comm/commands.c
- https://github.com/vedderb/bldc/blob/f7c2b34e1cff2234cae98be3abf0cd50e249558f/motor/mcpwm_foc.c

## Calibration implications

The motor has no permanent magnets. Ordinary PM back-EMF assumptions cannot
be used as a calibration reference, particularly at low speed. Increasing
speed does not create permanent-magnet flux. The measured failure applies to
this tested model/configuration; it does not prove that every possible SynRM
observer is impossible or that the current encoder calibration is optimal.

Keep the working absolute electrical offset 357.52764892578125 degrees, ratio
2 and inversion 0 for now. This preserves the configuration that actually
started and controlled the motor; ratio and electrical axis orientation have
not been independently calibrated by these angle-comparison tests.

For an independent calibration, prepare a bounded saliency/inductance-versus-
rotor-angle measurement to identify electrical periodicity and the relevant
inductance axis, then validate direction and startup under current limits.
Do not hold the rotor by hand. Resolve the reluctance-axis ambiguities before
changing the current-control reference or treating a detected value as final.
Stock Detect Encoder runs a longer forced-field sequence; it has not been
validated here against this motor's thermal budget or axis convention.

No transition should be forced by lowering foc_sl_erpm or by replacing the
encoder's working offset with a drifting observer angle. For sensorless work,
qualify a motor-appropriate observer against the encoder while the encoder
still controls the motor, including different currents and loads.

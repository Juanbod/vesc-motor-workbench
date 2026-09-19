# Additional passport speed point, 2026-09-12

One physical run completed successfully under speed_600rpm_5a_smooth.
Powered duration: 23.800530 s; encoder travel: 64307.307128 degrees
(178.631409 turns). Final five-second mean speed: 512.560546 RPM;
range 509.823752..515.257042 RPM; span 5.433290 RPM; endpoint slope
0.149723 RPM/s. The stage stability criterion passed.

Maximum command remains 5 A. Final command was 2.931240 A; final measured
Id=-2.06 A and Iq=+2.05 A. Input energy: 26.745102 J; squared Id/Iq
integral: 254.810533 A2s. No controller fault, guard event or recovery error
was reported. This is not a rated power, maximum speed or torque measurement.

The controller candidate is unchanged from the preceding smooth 5 A runs:
SHA256 92e5c10d635744bfe7170225c386024ed7905fef57c7c2fcb9ee4a011aa0a368.
Only the host taper start/cutoff changed from 400/540 to 450/600 RPM.
The hard speed guard remains 720 RPM, powered budget 24 s, current cap 5 A,
fast trip 8 A, observed-current cap 6 A, input cap 2 A, energy 72 J,
I2t 600 A2s, telemetry/command gap 20 ms and recovery observation 32 s.
The 600 RPM cutoff was not reached; approximately 513 RPM is the resulting
operating point under this host taper, not a 513 RPM setpoint-tracking result.

The predecessor was the qualified smooth 540-stage trial 2. Its raw stability
window, not just the saved success flag, was audited before this acquisition.
All new-stage controller bytes and unchanged hard limits were tested offline.

Recovery verified zero current and standstill before exact baseline restoration.
Independent final readback: current_motor, current_in, Id, Iq, duty and ERPM
all zero; fault 0; bus 24.7 V; MOS 26.5 C; raw angle 92.087400 degrees.
External application remains isolated in RAM. Winding-temperature telemetry
remains invalid. No further trial is running or scheduled.

The result is included in the draft-passport evidence registry. The proposed
passport retains unknown nominal power, torque, efficiency, current, voltage,
duty type, temperature rise and permitted maximum speed as null/unmeasured.

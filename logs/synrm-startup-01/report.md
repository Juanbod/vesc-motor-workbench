# Encoder Bench Report

State: no_reliable_start
Simulated: False
Energy: 5.453 J

| Trial | Result | Start (s) | Energy (J) |
|---|---|---:|---:|
| start_m0_offset+0 | no_start | - | 1.711 |
| start_m1_offset+0 | stalled | - | 0.738 |
| start_m1_offset-15 | wrong_direction | - | 0.719 |
| start_m1_offset+15 | stalled | - | 0.757 |
| start_m1_offset-30 | stalled | - | 0.768 |
| start_m1_offset+30 | stalled | - | 0.761 |

Stop reason: none
Rollback: {"motor_restored": true, "app_output": "disabled until power cycle"}

A recommended profile is valid only within the tested speed/current envelope.
These trials measure no-load startup and speed response, not shaft torque or motor efficiency.
The original motor settings are restored at exit when standstill is confirmed.
On hardware, ADC/PPM output remains temporarily disabled until power cycle.

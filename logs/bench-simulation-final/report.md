# Encoder Bench Report

State: completed
Simulated: True
Energy: 57.406 J

| Trial | Result | Start (s) | Energy (J) |
|---|---|---:|---:|
| start_m0_offset+0 | stalled | - | 4.817 |
| start_m1_offset+0 | completed | 0.7750000000000004 | 3.335 |
| start_m1_offset-15 | completed | 0.8500000000000004 | 3.779 |
| start_m1_offset+15 | completed | 0.7750000000000004 | 3.335 |
| start_m1_offset-30 | completed | 0.9750000000000005 | 4.520 |
| start_m1_offset+30 | completed | 0.7750000000000004 | 3.335 |
| repeat1_start_m1_offset+0 | completed | 0.7750000000000004 | 3.335 |
| repeat2_start_m1_offset+0 | completed | 0.7750000000000004 | 3.335 |
| speed_gain0.5 | completed | - | 9.206 |
| speed_gain1 | completed | - | 9.206 |
| speed_confirmation | completed | - | 9.206 |

Stop reason: none
Rollback: {"motor_restored": true, "simulated": true}

A recommended profile is valid only within the tested speed/current envelope.
These trials measure no-load startup and speed response, not shaft torque or motor efficiency.
The original motor settings are restored at exit when standstill is confirmed.
On hardware, ADC/PPM output remains temporarily disabled until power cycle.

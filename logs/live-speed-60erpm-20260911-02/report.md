# Encoder Bench Report

State: completed
Simulated: False
Energy: 1.908 J

| Trial | Result | Start (s) | Energy (J) |
|---|---|---:|---:|
| diagnostic | completed | - | 1.908 |

## Startup coverage

```json
{
  "bins": 12,
  "required_per_bin": 3,
  "successful_starts": [
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0,
    0
  ],
  "failures": 0,
  "same_candidate": true,
  "qualified": false,
  "scope": "Observed no-load starts only; not a guarantee under all loads or temperatures"
}
```

## Steady speed steps

| Trial | Target eRPM | Mean eRPM | Peak error | Drift eRPM/s | Qualified |
|---|---:|---:|---:|---:|---|
| diagnostic | 60 | 59.25 | 8.37 | 3.66 | True |

Stop reason: none
Rollback: {"motor_restored": true, "app_output": "disabled until power cycle"}

A recommended profile is valid only within the tested speed/current envelope.
These trials measure no-load startup and speed response, not shaft torque or motor efficiency.
The original motor settings are restored at exit when standstill is confirmed.
On hardware, ADC/PPM output remains temporarily disabled until power cycle.

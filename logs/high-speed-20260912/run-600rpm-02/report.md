# Encoder Bench Report

State: completed
Simulated: False
Energy: 9.139 J

| Trial | Result | Start (s) | Energy (J) |
|---|---|---:|---:|
| diagnostic | completed | - | 9.139 |

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
| diagnostic | 1200 | 1221.20 | 108.48 | -10.31 | True |

Stop reason: none
Rollback: {"motor_restored": true, "app_output": "disabled until power cycle", "standstill_timeout_s": 30}

A recommended profile is valid only within the tested speed/current envelope.
These trials measure no-load startup and speed response, not shaft torque or motor efficiency.
The original motor settings are restored at exit when standstill is confirmed.
On hardware, ADC/PPM output remains temporarily disabled until power cycle.

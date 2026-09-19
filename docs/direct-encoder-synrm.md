# Direct Encoder SynRM Profiles

This branch replaces the AS5600 + ESP8266 Hall emulator with a direct encoder on the VESC sensor port.

## Motor assumption

- Rotor: four separate steel-20 plates.
- Working model: synchronous reluctance motor, not induction.
- Electrical ratio for the first direct-encoder tests: `foc_encoder_ratio = 2`.
- Setup poles for the first direct-encoder tests: `si_motor_poles = 4`.

The old Hall-emulator branch used `pole_pairs = 7` because the ESP generated Hall sectors for the previous VESC setup. Keep that branch as a fallback, but do not mix its Hall table with direct SPI encoder profiles.

## VESC enum values used

From VESC firmware `datatypes.h`:

- `foc_sensor_mode = 1`: FOC encoder mode.
- `m_sensor_port_mode = 7`: `SENSOR_PORT_MODE_MT6816_SPI_HW`.
- `m_sensor_port_mode = 2`: `SENSOR_PORT_MODE_AS5047_SPI`, used for AS5047/AS5048A-style SPI modules.
- `m_sensor_port_mode = 1`: ABI incremental encoder fallback.

## Generated profiles

Run:

```powershell
.\scripts\generate-direct-encoder-synrm-profiles.ps1
```

Output folder:

```text
vesc-direct-encoder-profiles\
```

Recommended first pass:

1. `79_mt6816_spi_pp2_safe_uart_detect`
2. Run VESC Tool encoder detection and save the detected offset.
3. `80_mt6816_spi_pp2_mtpa_i75_b100_adc`
4. `81_mt6816_spi_pp2_mtpa_measured_i75_b100_adc`
5. `82_mt6816_spi_pp2_no_mtpa_i75_b100_adc`
6. `83_mt6816_spi_pp2_mtpa_i75_b100_slow_adc`
7. `84` and `85` only after stable low/mid speed, because they add field weakening.

Profiles `87` and `88` are control checks with `foc_encoder_ratio = 7`. They are not the preferred model for the four-plate rotor, but they are useful if the pp2 profiles cannot sync at all.

## Required manual step

Every direct-encoder profile starts with `foc_encoder_offset = 0`. Before load testing, run Encoder Detection / Detect Encoder in VESC Tool and write the detected motor configuration back to the ESC.

If direction is consistently wrong after detection, test profile `86_mt6816_spi_pp2_mtpa_inverted_adc` or invert encoder direction in VESC Tool and detect again.

## Safety

- Power encoder from 3.3 V unless the exact VESC sensor port confirms 5 V-tolerant signals.
- Keep SPI wires short.
- Do not test field-weakening profiles until the normal MTPA profile is stable.
- Watch for `FAULT_CODE_ENCODER_SPI`, `FAULT_CODE_ENCODER_NO_MAGNET`, `FAULT_CODE_ENCODER_MAGNET_TOO_STRONG`, and `FAULT_CODE_ENCODER_SLIP`.

## Prepared automatic tuning loop

The automatic loop uses a raw backup made after the direct encoder has been installed,
Motor Detection has completed, Encoder Detection has completed, and that detected
configuration has been written to the ESC. It intentionally does not modify the
measured motor model, encoder offset, encoder ratio, or sensor-port mode.

The first sweep changes only fields whose binary positions are verified for this
firmware and hardware: phase-current limit, battery-current limit, absolute-current
limit, and `foc_mtpa_mode`.

1. Make the detected baseline backup:

```powershell
.\.venv\Scripts\vesc-workbench.exe backup-raw-config --port COM10 --name direct-encoder-detected
```

2. Copy `config/direct-encoder-autotune.example.json` to
`config/direct-encoder-autotune.json` and adjust only the small initial current sweep.

3. Generate a queue from that exact backup:

```powershell
.\.venv\Scripts\vesc-workbench.exe generate-autotune-queue `
  .\raw-config-backups\<detected-backup> `
  .\config\direct-encoder-autotune.json
```

4. Inspect the run without touching hardware:

```powershell
.\.venv\Scripts\vesc-workbench.exe autotune-run `
  .\autotune-queue `
  .\config\direct-encoder-autotune.json
```

5. With the motor fixed, VESC Tool closed, and a physical power disconnect ready,
run the first three candidates at reduced limits:

```powershell
.\.venv\Scripts\vesc-workbench.exe autotune-run `
  .\autotune-queue `
  .\config\direct-encoder-autotune.json `
  --port COM10 --max-profiles 3 --armed
```

Each candidate is written as motor configuration only, read back and hash-verified,
then tested by controlled UART current steps. `logs/autotune-*/summary.csv` contains
the score and key maxima; a per-profile CSV retains eRPM, Id, Iq, input/motor current,
duty, voltage, and temperatures. The run stops at the first fault or safety event.

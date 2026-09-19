# AS5600 + ESP8266 Hall Emulator

Это не ABI/SPI encoder для VESC.

Схема:

- AS5600 читается ESP8266 NodeMCU по I2C.
- ESP8266 эмулирует три Hall-линии для VESC/MKSESC.
- В VESC Tool выбирать `Sensor Mode = Hall Sensors`.
- В XML это `foc_sensor_mode = 2`.

Подключение:

- AS5600 SDA -> ESP D2 / GPIO4.
- AS5600 SCL -> ESP D1 / GPIO5.
- AS5600 VCC -> ESP 3V3.
- AS5600 GND -> GND.
- ESP D5 / GPIO14 -> HALL1.
- ESP D6 / GPIO12 -> HALL2.
- ESP D7 / GPIO13 -> HALL3.
- Общий GND с ESC обязателен.

Hall-выходы ESP сделаны как open-drain:

- HIGH = линия отпущена, нужна подтяжка к 3.3 V.
- LOW = ESP тянет линию в GND.
- Не подтягивать Hall-линии к 5 V напрямую.

Текущая ESP-конфигурация:

- `pole_pairs = 7`
- `offset_counts = 0`
- `reverse = 0`
- `debug = 0`
- `test = 0`

Detected Hall table из VESC Tool:

```text
Hall Table [0] = 255
Hall Table [1] = 22
Hall Table [2] = 90
Hall Table [3] = 186
Hall Table [4] = 162
Hall Table [5] = 123
Hall Table [6] = 43
Hall Table [7] = 255
Hall Interpolation ERPM = 500
Sensorless ERPM = 6000
```

## Диагностика ESP

ESP debug serial:

- port: `COM6`
- baud: `115200`
- start command: `dbg 1`
- stop command: `dbg 0`

Команда проекта:

```powershell
.\.venv\Scripts\vesc-workbench.exe esp-hall-monitor --port COM6 --seconds 20
```

Она пишет CSV в `logs/`, парсит строки вида:

```text
raw=3867 sector=3 status=0x67 magnet=ok
```

и считает ожидаемый сектор при `pole_pairs=7`, `offset_counts=0`, `reverse=0`.

## Профили

Профили `14`-`27` используют detected Hall table.

Начинать с UART-профилей:

1. `22_hall_esp_detected_uart_pp7_limited_sl1500`
2. `23_hall_esp_detected_uart_pp7_limited_sl2000`
3. `24_hall_esp_detected_uart_pp7_limited_sl3000`
4. `27_hall_esp_detected_uart_pp7_limited_sl6000`

Профили `14`-`17` оставляют исходные токовые лимиты ESC. Их использовать только после устойчивой работы limited-профилей.

Профили `18` и `19` дают небольшой phase trim Hall table на `+10` и `-10` единиц VESC electrical angle.


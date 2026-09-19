# Headless VESC Config Workflow

Цель: работать с профилем `17_hall_esp_detected_uart_pp7_sl6000` без постоянного ручного нажатия загрузки в VESC Tool.

## Что можно автоматизировать

VESC по USB/UART поддерживает команды:

- `COMM_GET_MCCONF`
- `COMM_SET_MCCONF`
- `COMM_GET_APPCONF`
- `COMM_SET_APPCONF`

XML-файл VESC Tool напрямую в ESC не отправляется. ESC принимает бинарную структуру конфигурации, зависящую от версии firmware. Поэтому самый надежный путь сейчас:

1. Один раз загрузить профиль 17 через VESC Tool.
2. Считать из ESC бинарный `mcconf/appconf` backup.
3. Дальше восстанавливать этот backup командами без VESC Tool.

## Команды

Проверить firmware/hardware:

```powershell
.\.venv\Scripts\vesc-workbench.exe fw-version --port COM10
```

Сделать backup текущего профиля, когда профиль 17 уже загружен в ESC:

```powershell
.\.venv\Scripts\vesc-workbench.exe backup-raw-config --port COM10 --name profile17-hall-sl6000
```

Будет создана папка:

```text
raw-config-backups\<date>_profile17-hall-sl6000
```

Восстановить backup без VESC Tool:

```powershell
.\.venv\Scripts\vesc-workbench.exe restore-raw-config .\raw-config-backups\<backup-folder> --port COM10 --armed
```

Восстановить только motor config:

```powershell
.\.venv\Scripts\vesc-workbench.exe restore-raw-config .\raw-config-backups\<backup-folder> --port COM10 --kind motor --armed
```

## Защита от ошибки версии

`restore-raw-config` перед записью читает текущий firmware/hardware и сравнивает с backup. Если версия или hardware отличаются, запись блокируется.

## Важно

- VESC Tool должен быть закрыт.
- Нельзя одновременно держать один порт открытым из VESC Tool и Python.
- Это пишет конфигурацию ESC, поэтому команда восстановления требует `--armed`.
- Для сборки бинарной конфигурации напрямую из XML нужен отдельный serializer под конкретную firmware-версию. Это следующий этап, не первый.

## Raw-варианты от профиля 17

Для FW `6.02` и hardware `MKSESC_84_100_HP` добавлен генератор uploadable raw-вариантов. Он берет backup профиля 17 и патчит только уверенно найденные поля:

- `foc_sl_erpm`
- `foc_hall_interp_erpm`
- `foc_hall_table`
- `foc_sensor_mode = 2`

Токовые лимиты остаются как в рабочем raw backup профиля 17.

Сгенерировать варианты:

```powershell
.\.venv\Scripts\vesc-workbench.exe generate-raw-variants .\raw-config-backups\20260812-090534_profile17-hall-sl6000
```

Варианты появятся в:

```text
raw-config-variants\
```

Посмотреть очередь без записи в ESC:

```powershell
.\.venv\Scripts\vesc-workbench.exe upload-raw-variant-queue .\raw-config-variants --port COM10
```

Залить один выбранный вариант:

```powershell
.\.venv\Scripts\vesc-workbench.exe restore-raw-config .\raw-config-variants\31_raw17_hall_sl6000_interp500 --port COM10 --armed
```

Залить всю очередь подряд:

```powershell
.\.venv\Scripts\vesc-workbench.exe upload-raw-variant-queue .\raw-config-variants --port COM10 --wait 2 --armed
```

Текущая новая очередь для проблемы стартовой тяги и случайного обратного старта:

```text
31_raw17_hall_i75_b100_sl6000_interp500
32_raw17_hall_i75_b100_sl6000_interp1000
33_raw17_hall_i75_b100_sl8000_interp500
34_raw17_hall_i75_b100_sl10000_interp500
35_raw17_hall_i75_b100_sl6000_trim_p5
36_raw17_hall_i75_b100_sl6000_trim_m5
37_raw17_hall_i75_b100_sl6000_trim_p10
38_raw17_hall_i75_b100_sl6000_trim_m10
39_raw17_hall_i75_b100_sl8000_trim_p5
40_raw17_hall_i75_b100_sl8000_trim_m5
41_raw17_hall_i75_b100_sl6000_revtable
42_raw17_hall_i75_b100_sl8000_revtable
```

Во всех вариантах:

```text
phase current max = 75 A
input current max = 100 A
absolute current max = 116.17 A
```

Рекомендованный порядок проверки:

1. `31` - новая база с лимитами 75/100 и тем же Hall table.
2. `32` - дольше/плотнее Hall interpolation перед sensorless.
3. `33`, `34` - позже переход в sensorless, если стартовая тяга хромает.
4. `35`, `36` - малый phase trim Hall table при обратных рывках.
5. `37`, `38` - больший trim, только если `35/36` дают понятное улучшение.
6. `41`, `42` - reverse Hall table только если направление становится стабильно неправильным, а не случайно плавает.

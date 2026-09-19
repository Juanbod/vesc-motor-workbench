# Разработка

## Структура

- `vesc_workbench/cli.py` - CLI.
- `vesc_workbench/configs.py` - импорт, валидация и staging XML.
- `vesc_workbench/appliers.py` - backend-и применения конфигураций.
- `vesc_workbench/uart.py` - низкоуровневый VESC UART packet codec.
- `vesc_workbench/autotest.py` - безопасные тестовые сценарии.
- `profiles/incoming` - новые конфигурации.
- `profiles/staged` - проверенные bundle-и перед применением.
- `profiles/applied` - место для истории примененных bundle-ов.
- `logs` - CSV/JSONL логи тестов.

## Следующие backend-и

Безопасный порядок разработки:

1. Dry-run manifest уже есть.
2. Backend "open in VESC Tool": открыть XML в VESC Tool без автоматической записи.
3. Backend чтения firmware и текущих конфигов.
4. Только после этого - бинарный serializer для `COMM_SET_MCCONF` / `COMM_SET_APPCONF`.

## Проверки

```powershell
python -m unittest discover -s tests
python -m vesc_workbench status
```


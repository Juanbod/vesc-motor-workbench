$ErrorActionPreference = 'Stop'

$sourceDir = 'C:\Users\elkiy\Desktop\vesc conf'
$outputDir = Join-Path $PSScriptRoot 'vesc-test-profiles'
$motorSource = Join-Path $sourceDir 'vesc_mcconf.xml'
$appSource = Join-Path $sourceDir 'vesc_appconf.xml'

if (!(Test-Path -LiteralPath $motorSource) -or !(Test-Path -LiteralPath $appSource)) {
    throw "Source configurations were not found in $sourceDir"
}

function Set-XmlValue([xml]$Xml, [string]$Name, [string]$Value) {
    $node = $Xml.SelectSingleNode("/*/$Name")
    if ($null -eq $node) { throw "Missing XML setting: $Name" }
    $node.InnerText = $Value
}

function Write-Profile([string]$Name, [hashtable]$MotorChanges, [hashtable]$AppChanges) {
    $dir = Join-Path $outputDir $Name
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    [xml]$motor = Get-Content -Raw -LiteralPath $motorSource
    [xml]$app = Get-Content -Raw -LiteralPath $appSource

    foreach ($key in $MotorChanges.Keys) { Set-XmlValue $motor $key $MotorChanges[$key] }
    foreach ($key in $AppChanges.Keys) { Set-XmlValue $app $key $AppChanges[$key] }

    $motor.Save((Join-Path $dir 'vesc_mcconf.xml'))
    $app.Save((Join-Path $dir 'vesc_appconf.xml'))
}

Remove-Item -LiteralPath $outputDir -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $outputDir | Out-Null

$commonMotor = @{
    'l_current_max' = '77.45'; 'l_in_current_max' = '100'; 'l_abs_current_max' = '116.17';
    'si_motor_poles' = '4'
}
$currentApp = @{
    'app_adc_conf.ctrl_type' = '1'; 'app_adc_conf.ramp_time_pos' = '1'; 'app_adc_conf.ramp_time_neg' = '0.3'
}
$slowRampApp = $currentApp.Clone()
$slowRampApp['app_adc_conf.ramp_time_pos'] = '2'
$slowRampApp['app_adc_conf.ramp_time_neg'] = '0.5'
$uartAutotestApp = $currentApp.Clone()
$uartAutotestApp['app_to_use'] = '3'

Write-Profile '00_autotest_profile04_uart' ($commonMotor + @{
    'foc_sensor_mode' = '3'; 'foc_mtpa_mode' = '0'; 'foc_hfi_voltage_start' = '10';
    'foc_hfi_voltage_run' = '3'; 'foc_hfi_voltage_max' = '4'; 'foc_hfi_gain' = '0.25';
    'foc_sl_erpm_hfi' = '1500'
}) $uartAutotestApp

Write-Profile '01_baseline_current' ($commonMotor + @{
    'foc_sensor_mode' = '1'; 'foc_mtpa_mode' = '0'
}) $currentApp

Write-Profile '02_baseline_slow_ramp' ($commonMotor + @{
    'foc_sensor_mode' = '1'; 'foc_mtpa_mode' = '0'
}) $slowRampApp

Write-Profile '03_hfi_soft' ($commonMotor + @{
    'foc_sensor_mode' = '3'; 'foc_mtpa_mode' = '0'; 'foc_hfi_voltage_start' = '6';
    'foc_hfi_voltage_run' = '2'; 'foc_hfi_voltage_max' = '3'; 'foc_hfi_gain' = '0.15';
    'foc_sl_erpm_hfi' = '1000'
}) $currentApp

Write-Profile '04_hfi_medium' ($commonMotor + @{
    'foc_sensor_mode' = '3'; 'foc_mtpa_mode' = '0'; 'foc_hfi_voltage_start' = '10';
    'foc_hfi_voltage_run' = '3'; 'foc_hfi_voltage_max' = '4'; 'foc_hfi_gain' = '0.25';
    'foc_sl_erpm_hfi' = '1500'
}) $currentApp

Write-Profile '05_hfi_soft_mtpa' ($commonMotor + @{
    'foc_sensor_mode' = '3'; 'foc_mtpa_mode' = '1'; 'foc_hfi_voltage_start' = '6';
    'foc_hfi_voltage_run' = '2'; 'foc_hfi_voltage_max' = '3'; 'foc_hfi_gain' = '0.15';
    'foc_sl_erpm_hfi' = '1000'
}) $currentApp

Write-Profile '06_hfi_medium_mtpa' ($commonMotor + @{
    'foc_sensor_mode' = '3'; 'foc_mtpa_mode' = '1'; 'foc_hfi_voltage_start' = '10';
    'foc_hfi_voltage_run' = '3'; 'foc_hfi_voltage_max' = '4'; 'foc_hfi_gain' = '0.25';
    'foc_sl_erpm_hfi' = '1500'
}) $currentApp

Write-Profile '07_hfi_soft_hold_2000' ($commonMotor + @{
    'foc_sensor_mode' = '3'; 'foc_mtpa_mode' = '0'; 'foc_hfi_voltage_start' = '6';
    'foc_hfi_voltage_run' = '2'; 'foc_hfi_voltage_max' = '3'; 'foc_hfi_gain' = '0.15';
    'foc_sl_erpm_hfi' = '2000'
}) $currentApp

Write-Profile '08_hfi_medium_hold_2500' ($commonMotor + @{
    'foc_sensor_mode' = '3'; 'foc_mtpa_mode' = '0'; 'foc_hfi_voltage_start' = '10';
    'foc_hfi_voltage_run' = '3'; 'foc_hfi_voltage_max' = '4'; 'foc_hfi_gain' = '0.25';
    'foc_sl_erpm_hfi' = '2500'
}) $currentApp

Write-Profile '09_hfi_quiet_hold_2000' ($commonMotor + @{
    'foc_sensor_mode' = '3'; 'foc_mtpa_mode' = '0'; 'foc_hfi_voltage_start' = '6';
    'foc_hfi_voltage_run' = '1.5'; 'foc_hfi_voltage_max' = '2.5'; 'foc_hfi_gain' = '0.12';
    'foc_sl_erpm_hfi' = '2000'
}) $currentApp

Write-Profile '10_hfi_v2_soft' ($commonMotor + @{
    'foc_sensor_mode' = '5'; 'foc_mtpa_mode' = '0'; 'foc_hfi_voltage_start' = '6';
    'foc_hfi_voltage_run' = '2'; 'foc_hfi_voltage_max' = '3'; 'foc_hfi_gain' = '0.15';
    'foc_sl_erpm_hfi' = '2000'
}) $currentApp

Write-Profile '11_hfi_v3_soft' ($commonMotor + @{
    'foc_sensor_mode' = '6'; 'foc_mtpa_mode' = '0'; 'foc_hfi_voltage_start' = '6';
    'foc_hfi_voltage_run' = '2'; 'foc_hfi_voltage_max' = '3'; 'foc_hfi_gain' = '0.15';
    'foc_sl_erpm_hfi' = '2000'
}) $currentApp

Write-Profile '12_hfi_v4_soft' ($commonMotor + @{
    'foc_sensor_mode' = '7'; 'foc_mtpa_mode' = '0'; 'foc_hfi_voltage_start' = '6';
    'foc_hfi_voltage_run' = '2'; 'foc_hfi_voltage_max' = '3'; 'foc_hfi_gain' = '0.15';
    'foc_sl_erpm_hfi' = '2000'
}) $currentApp

Write-Profile '13_hfi_v5_soft' ($commonMotor + @{
    'foc_sensor_mode' = '8'; 'foc_mtpa_mode' = '0'; 'foc_hfi_voltage_start' = '6';
    'foc_hfi_voltage_run' = '2'; 'foc_hfi_voltage_max' = '3'; 'foc_hfi_gain' = '0.15';
    'foc_sl_erpm_hfi' = '2000'
}) $currentApp

@'
# Профили испытаний VESC

Во всех профилях потенциометр работает в режиме **Current**, а лимиты тока оставлены исходными: 77.45 А фазного, 100 А батарейного, 116.17 А аварийного. Это не означает, что их можно запрашивать: первый запуск каждого профиля — с валом без нагрузки и не более 10 % хода потенциометра.

Испытывать строго по порядку:

0. **00_autotest_profile04_uart** — профиль 04 с отключённым ADC-входом; предназначен только для Python Autotest. После завершения эксперимента снова загрузить рабочий профиль с потенциометром.
1. **01_baseline_current** — исходная моторная логика, но потенциометр задаёт ток. Это контрольная точка.
2. **02_baseline_slow_ramp** — то же, но с более медленной реакцией ручки.
3. **03_hfi_soft** — мягкий HFI, без MTPA. Остановить тест при треске или колебании вала.
4. **04_hfi_medium** — HFI сильнее; только если профиль 03 дал устойчивое вращение, но не удерживает угол.
5. **05_hfi_soft_mtpa** — мягкий HFI плюс MTPA, чтобы проверить реактивный момент на меньшем токе.
6. **06_hfi_medium_mtpa** — следующий шаг только после устойчивого профиля 05.
7. **07_hfi_soft_hold_2000** — профиль 03 с удержанием HFI до 2000 eRPM; тестировать первым после срывов 03–04.
8. **08_hfi_medium_hold_2500** — профиль 04 с удержанием HFI до 2500 eRPM.
9. **09_hfi_quiet_hold_2000** — пониженное HFI-напряжение после захвата, чтобы уменьшить треск; возможен более слабый старт.
10. **10_hfi_v2_soft** — вариант HFI V2, мягкие параметры.
11. **11_hfi_v3_soft** — вариант HFI V3, мягкие параметры.
12. **12_hfi_v4_soft** — вариант HFI V4, мягкие параметры.
13. **13_hfi_v5_soft** — вариант HFI V5, мягкие параметры.

После каждого теста записывать: положение потенциометра, Motor Current, Input Current, Id, Iq, ERPM, Duty, звук/вибрацию. Не менять два профиля одновременно.

## Асинхронный двигатель и V/f

Штатный VESC FOC не имеет режима скалярного управления асинхронным двигателем V/f: он не формирует независимый закон «амплитуда синусоиды / частота» с намагничивающим током и компенсацией скольжения. Поэтому конфигурации выше нельзя применять как V/f-профили для обычного трёхфазного асинхронного двигателя с короткозамкнутым ротором.

Для такого двигателя нужен частотный преобразователь (VFD), явно поддерживающий induction motor / V/f. Чтобы рассчитать его закон V/f, потребуются паспортные данные: номинальные линейные напряжение и частота, номинальный ток, число полюсов, соединение обмоток и желаемый диапазон оборотов.
'@ | Set-Content -LiteralPath (Join-Path $outputDir 'README.md') -Encoding utf8

Write-Host "Profiles written to $outputDir"

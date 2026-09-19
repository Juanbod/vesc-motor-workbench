param(
    [string]$ProfilesDir = "",
    [string]$BaseProfile = "04_hfi_medium",
    [string]$BaseUartAppProfile = "00_autotest_profile04_uart",
    [int]$PolePairs = 7
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
if (-not $ProfilesDir) {
    $ProfilesDir = Join-Path $Root "vesc-test-profiles"
}

function Set-XmlValue([xml]$Xml, [string]$Name, [string]$Value) {
    $node = $Xml.SelectSingleNode("/*/$Name")
    if ($null -eq $node) {
        throw "Missing XML setting: $Name"
    }
    $node.InnerText = $Value
}

function Read-ProfileXml([string]$ProfileName, [string]$FileName) {
    $path = Join-Path (Join-Path $ProfilesDir $ProfileName) $FileName
    if (-not (Test-Path -LiteralPath $path)) {
        throw "Base XML was not found: $path"
    }
    return [xml](Get-Content -Raw -LiteralPath $path)
}

function New-DetectedHallTable([int]$Trim = 0) {
    # Detected in VESC Tool from AS5600 + ESP8266 Hall emulator:
    # 0=255, 1=22, 2=90, 3=186, 4=162, 5=123, 6=43, 7=255.
    # Values are VESC FOC hall electrical angles on a 0..200 turn.
    $base = @{
        "foc_hall_table__0" = 255;
        "foc_hall_table__1" = 22;
        "foc_hall_table__2" = 90;
        "foc_hall_table__3" = 186;
        "foc_hall_table__4" = 162;
        "foc_hall_table__5" = 123;
        "foc_hall_table__6" = 43;
        "foc_hall_table__7" = 255;
    }
    $table = @{}
    foreach ($key in $base.Keys) {
        if ($base[$key] -eq 255) {
            $table[$key] = "255"
        } else {
            $table[$key] = "$((($base[$key] + $Trim) % 200 + 200) % 200)"
        }
    }
    return $table
}

function Write-HallProfile(
    [string]$Name,
    [hashtable]$MotorChanges,
    [hashtable]$AppChanges,
    [string]$MotorBase = $BaseProfile,
    [string]$AppBase = $BaseProfile
) {
    $dir = Join-Path $ProfilesDir $Name
    New-Item -ItemType Directory -Force -Path $dir | Out-Null

    [xml]$motor = Read-ProfileXml $MotorBase "vesc_mcconf.xml"
    [xml]$app = Read-ProfileXml $AppBase "vesc_appconf.xml"

    foreach ($key in $MotorChanges.Keys) {
        Set-XmlValue $motor $key $MotorChanges[$key]
    }
    foreach ($key in $AppChanges.Keys) {
        Set-XmlValue $app $key $AppChanges[$key]
    }

    $motor.Save((Join-Path $dir "vesc_mcconf.xml"))
    $app.Save((Join-Path $dir "vesc_appconf.xml"))
}

$hallCommon = @{
    "foc_sensor_mode" = "2";
    "foc_mtpa_mode" = "0";
    "foc_hall_interp_erpm" = "500";
    "si_motor_poles" = "$($PolePairs * 2)";
}

$hallCurrentLimited = $hallCommon.Clone()
$hallCurrentLimited["l_current_max"] = "20"
$hallCurrentLimited["l_in_current_max"] = "15"
$hallCurrentLimited["l_abs_current_max"] = "35"

$uartApp = @{
    "app_to_use" = "3";
}

$adcCurrentApp = @{
    "app_to_use" = "5";
    "app_adc_conf.ctrl_type" = "1";
    "app_adc_conf.ramp_time_pos" = "1";
    "app_adc_conf.ramp_time_neg" = "0.3";
}

$mtpaHall = $hallCommon.Clone()
$mtpaHall["foc_mtpa_mode"] = "1"

$hallInterp1000 = $hallCommon.Clone()
$hallInterp1000["foc_hall_interp_erpm"] = "1000"

Write-HallProfile "14_hall_esp_detected_uart_pp7_sl1500" `
    ($hallCommon + (New-DetectedHallTable) + @{
        "foc_sl_erpm" = "1500";
    }) `
    $uartApp `
    $BaseProfile `
    $BaseUartAppProfile

Write-HallProfile "15_hall_esp_detected_uart_pp7_sl2000" `
    ($hallCommon + (New-DetectedHallTable) + @{
        "foc_sl_erpm" = "2000";
    }) `
    $uartApp `
    $BaseProfile `
    $BaseUartAppProfile

Write-HallProfile "16_hall_esp_detected_uart_pp7_sl3000" `
    ($hallCommon + (New-DetectedHallTable) + @{
        "foc_sl_erpm" = "3000";
    }) `
    $uartApp `
    $BaseProfile `
    $BaseUartAppProfile

Write-HallProfile "17_hall_esp_detected_uart_pp7_sl6000" `
    ($hallCommon + (New-DetectedHallTable) + @{
        "foc_sl_erpm" = "6000";
    }) `
    $uartApp `
    $BaseProfile `
    $BaseUartAppProfile

Write-HallProfile "18_hall_esp_detected_uart_pp7_trim_p10_sl2000" `
    ($hallCommon + (New-DetectedHallTable 10) + @{
        "foc_sl_erpm" = "2000";
    }) `
    $uartApp `
    $BaseProfile `
    $BaseUartAppProfile

Write-HallProfile "19_hall_esp_detected_uart_pp7_trim_m10_sl2000" `
    ($hallCommon + (New-DetectedHallTable -10) + @{
        "foc_sl_erpm" = "2000";
    }) `
    $uartApp `
    $BaseProfile `
    $BaseUartAppProfile

Write-HallProfile "20_hall_esp_detected_adc_pp7_sl2000" `
    ($hallCommon + (New-DetectedHallTable) + @{
        "foc_sl_erpm" = "2000";
    }) `
    $adcCurrentApp

Write-HallProfile "21_hall_esp_detected_uart_pp7_mtpa_sl2000" `
    ($mtpaHall + (New-DetectedHallTable) + @{
        "foc_sl_erpm" = "2000";
    }) `
    $uartApp `
    $BaseProfile `
    $BaseUartAppProfile

Write-HallProfile "22_hall_esp_detected_uart_pp7_limited_sl1500" `
    ($hallCurrentLimited + (New-DetectedHallTable) + @{
        "foc_sl_erpm" = "1500";
    }) `
    $uartApp `
    $BaseProfile `
    $BaseUartAppProfile

Write-HallProfile "23_hall_esp_detected_uart_pp7_limited_sl2000" `
    ($hallCurrentLimited + (New-DetectedHallTable) + @{
        "foc_sl_erpm" = "2000";
    }) `
    $uartApp `
    $BaseProfile `
    $BaseUartAppProfile

Write-HallProfile "24_hall_esp_detected_uart_pp7_limited_sl3000" `
    ($hallCurrentLimited + (New-DetectedHallTable) + @{
        "foc_sl_erpm" = "3000";
    }) `
    $uartApp `
    $BaseProfile `
    $BaseUartAppProfile

Write-HallProfile "25_hall_esp_detected_uart_pp7_interp1000_sl2000" `
    ($hallInterp1000 + (New-DetectedHallTable) + @{
        "foc_sl_erpm" = "2000";
    }) `
    $uartApp `
    $BaseProfile `
    $BaseUartAppProfile

Write-HallProfile "26_hall_esp_detected_adc_pp7_limited_sl2000" `
    ($hallCurrentLimited + (New-DetectedHallTable) + @{
        "foc_sl_erpm" = "2000";
    }) `
    $adcCurrentApp

Write-HallProfile "27_hall_esp_detected_uart_pp7_limited_sl6000" `
    ($hallCurrentLimited + (New-DetectedHallTable) + @{
        "foc_sl_erpm" = "6000";
    }) `
    $uartApp `
    $BaseProfile `
    $BaseUartAppProfile

Write-Host "AS5600 + ESP8266 Hall profiles written to $ProfilesDir"

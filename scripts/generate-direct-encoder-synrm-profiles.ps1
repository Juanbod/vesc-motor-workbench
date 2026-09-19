param(
    [string]$ProfilesDir = "",
    [string]$BaseProfile = "01_baseline_current",
    [string]$BaseUartAppProfile = "00_autotest_profile04_uart",
    [int]$ReluctancePolePairs = 2
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
if (-not $ProfilesDir) {
    $ProfilesDir = Join-Path $Root "vesc-direct-encoder-profiles"
}

$SourceProfilesDir = Join-Path $Root "vesc-test-profiles"

function Set-XmlValue([xml]$Xml, [string]$Name, [string]$Value) {
    $node = $Xml.SelectSingleNode("/*/$Name")
    if ($null -eq $node) {
        throw "Missing XML setting: $Name"
    }
    $node.InnerText = $Value
}

function Read-ProfileXml([string]$ProfileName, [string]$FileName) {
    $path = Join-Path (Join-Path $SourceProfilesDir $ProfileName) $FileName
    if (-not (Test-Path -LiteralPath $path)) {
        throw "Base XML was not found: $path"
    }
    return [xml](Get-Content -Raw -LiteralPath $path)
}

function Write-DirectEncoderProfile(
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

function New-DirectEncoderMotor([int]$SensorPortMode, [int]$Counts, [int]$Ratio, [int]$MtpaMode = 1) {
    return @{
        "foc_sensor_mode" = "1";
        "m_sensor_port_mode" = "$SensorPortMode";
        "m_encoder_counts" = "$Counts";
        "foc_encoder_ratio" = "$Ratio";
        "foc_encoder_offset" = "0";
        "foc_encoder_inverted" = "0";
        "si_motor_poles" = "$($Ratio * 2)";
        "foc_mtpa_mode" = "$MtpaMode";
        "foc_sl_erpm" = "10";
        "foc_hall_interp_erpm" = "0";
        "foc_hall_table__0" = "255";
        "foc_hall_table__1" = "255";
        "foc_hall_table__2" = "255";
        "foc_hall_table__3" = "255";
        "foc_hall_table__4" = "255";
        "foc_hall_table__5" = "255";
        "foc_hall_table__6" = "255";
        "foc_hall_table__7" = "255";
        "l_current_max" = "75";
        "l_in_current_max" = "100";
        "l_abs_current_max" = "116.17";
        "foc_fw_current_max" = "0";
        "foc_fw_duty_start" = "0.9";
        "foc_fw_q_current_factor" = "0.02";
        "foc_fw_ramp_time" = "0.2";
    }
}

$uartApp = @{
    "app_to_use" = "3";
}

$adcCurrentApp = @{
    "app_to_use" = "5";
    "app_adc_conf.ctrl_type" = "1";
    "app_adc_conf.ramp_time_pos" = "1";
    "app_adc_conf.ramp_time_neg" = "0.3";
}

$adcSlowApp = $adcCurrentApp.Clone()
$adcSlowApp["app_adc_conf.ramp_time_pos"] = "2"
$adcSlowApp["app_adc_conf.ramp_time_neg"] = "0.5"

Remove-Item -LiteralPath $ProfilesDir -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $ProfilesDir | Out-Null

$ratio = $ReluctancePolePairs
$mt6816 = New-DirectEncoderMotor 7 65536 $ratio 1
$mt6816Measured = New-DirectEncoderMotor 7 65536 $ratio 2
$mt6816NoMtpa = New-DirectEncoderMotor 7 65536 $ratio 0
$as5048a = New-DirectEncoderMotor 2 16384 $ratio 1
$abi16 = New-DirectEncoderMotor 1 65536 $ratio 1

$safeMt6816 = $mt6816.Clone()
$safeMt6816["l_current_max"] = "25"
$safeMt6816["l_in_current_max"] = "25"
$safeMt6816["l_abs_current_max"] = "45"

Write-DirectEncoderProfile "79_mt6816_spi_pp2_safe_uart_detect" $safeMt6816 $uartApp $BaseProfile $BaseUartAppProfile
Write-DirectEncoderProfile "80_mt6816_spi_pp2_mtpa_i75_b100_adc" $mt6816 $adcCurrentApp
Write-DirectEncoderProfile "81_mt6816_spi_pp2_mtpa_measured_i75_b100_adc" $mt6816Measured $adcCurrentApp
Write-DirectEncoderProfile "82_mt6816_spi_pp2_no_mtpa_i75_b100_adc" $mt6816NoMtpa $adcCurrentApp
Write-DirectEncoderProfile "83_mt6816_spi_pp2_mtpa_i75_b100_slow_adc" $mt6816 $adcSlowApp

$mt6816Fw5 = $mt6816.Clone()
$mt6816Fw5["foc_fw_current_max"] = "5"
$mt6816Fw5["foc_fw_duty_start"] = "0.8"
Write-DirectEncoderProfile "84_mt6816_spi_pp2_mtpa_fw5_adc" $mt6816Fw5 $adcCurrentApp

$mt6816Fw10 = $mt6816.Clone()
$mt6816Fw10["foc_fw_current_max"] = "10"
$mt6816Fw10["foc_fw_duty_start"] = "0.75"
Write-DirectEncoderProfile "85_mt6816_spi_pp2_mtpa_fw10_adc" $mt6816Fw10 $adcCurrentApp

$mt6816Inv = $mt6816.Clone()
$mt6816Inv["foc_encoder_inverted"] = "1"
Write-DirectEncoderProfile "86_mt6816_spi_pp2_mtpa_inverted_adc" $mt6816Inv $adcCurrentApp

$mt6816Pp7 = New-DirectEncoderMotor 7 65536 7 1
Write-DirectEncoderProfile "87_mt6816_spi_pp7_control_adc" $mt6816Pp7 $adcCurrentApp

$mt6816Pp7NoMtpa = New-DirectEncoderMotor 7 65536 7 0
Write-DirectEncoderProfile "88_mt6816_spi_pp7_no_mtpa_adc" $mt6816Pp7NoMtpa $adcCurrentApp

Write-DirectEncoderProfile "89_as5048a_spi_pp2_safe_uart_detect" $as5048a $uartApp $BaseProfile $BaseUartAppProfile
Write-DirectEncoderProfile "90_as5048a_spi_pp2_mtpa_i75_b100_adc" $as5048a $adcCurrentApp

$as5048aNoMtpa = New-DirectEncoderMotor 2 16384 $ratio 0
Write-DirectEncoderProfile "91_as5048a_spi_pp2_no_mtpa_i75_b100_adc" $as5048aNoMtpa $adcCurrentApp

Write-DirectEncoderProfile "92_mt6816_abi_pp2_mtpa_i75_b100_adc" $abi16 $adcCurrentApp

Write-Host "Direct encoder SynRM profiles written to $ProfilesDir"

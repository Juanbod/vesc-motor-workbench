param(
    [ValidateSet('inspect', 'simulate', 'run', 'status', 'stop')]
    [string]$Action = 'inspect',
    [string]$Port = 'auto',
    [string]$RunDir = ''
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not $RunDir) {
    if ($Action -in @('status', 'stop')) { throw 'Specify -RunDir for status or stop.' }
    $RunDir = Join-Path $projectRoot ('logs\bench-' + $Action + '-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
}
$RunDir = [System.IO.Path]::GetFullPath($RunDir)
Push-Location $projectRoot
try {
    if ($Action -in @('run', 'simulate')) {
        $mode = if ($Action -eq 'run') { '--armed' } else { '--simulate' }
        & $python -m vesc_workbench bench run --port $Port --plan config/encoder-bench.json --output $RunDir $mode
    } elseif ($Action -eq 'inspect') {
        & $python -m vesc_workbench bench inspect --port $Port --output $RunDir
    } else {
        & $python -m vesc_workbench bench $Action $RunDir
    }
    $resultCode = $LASTEXITCODE
} finally {
    Pop-Location
}
Write-Output "Run directory: $RunDir"
exit $resultCode

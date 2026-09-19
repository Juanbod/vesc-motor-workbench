param(
    [string]$PythonPath = ""
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot

function Test-Python {
    param([string]$Candidate)
    if (-not $Candidate) {
        return $false
    }
    try {
        & $Candidate -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" *> $null
        return $LASTEXITCODE -eq 0
    }
    catch {
        return $false
    }
}

if (-not $PythonPath) {
    $SystemPython = (Get-Command python -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty Source)
    if (Test-Python $SystemPython) {
        $PythonPath = $SystemPython
    }
}

if (-not (Test-Python $PythonPath)) {
    $CodexPython = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
    if (Test-Python $CodexPython) {
        $PythonPath = $CodexPython
    }
}

if (-not (Test-Python $PythonPath)) {
    throw "Python was not found. Install Python 3.11+ or pass -PythonPath."
}

& $PythonPath -m venv (Join-Path $Root ".venv")
& (Join-Path $Root ".venv\Scripts\python.exe") -m pip install --upgrade pip
& (Join-Path $Root ".venv\Scripts\python.exe") -m pip install -r (Join-Path $Root "requirements.txt")
& (Join-Path $Root ".venv\Scripts\python.exe") -m pip install -e $Root
& (Join-Path $Root ".venv\Scripts\python.exe") -m vesc_workbench init

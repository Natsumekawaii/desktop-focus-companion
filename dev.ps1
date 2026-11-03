param([switch]$ResetDemo)

$ErrorActionPreference = 'Stop'
$pythonPath = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
    throw 'Create the environment: py -3.12 -m venv .venv; then install requirements-dev.txt.'
}
Push-Location $PSScriptRoot
try {
    & $pythonPath -c 'import PySide6, tzdata'
    if ($LASTEXITCODE -ne 0) {
        throw 'Install dependencies: .\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt'
    }
    $devArguments = @('-m', 'scripts.run_dev')
    if ($ResetDemo) { $devArguments += '--reset-demo' }
    & $pythonPath @devArguments
    exit $LASTEXITCODE
}
finally { Pop-Location }

param()

$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'

if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
    throw 'Create the project virtual environment before running quality checks.'
}

Push-Location $projectRoot
try {
    & $pythonPath -m ruff check .
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    & $pythonPath -m mypy app main.py
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    & $pythonPath -m pytest -q
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
finally {
    Pop-Location
}

Write-Output 'Ruff, mypy, and pytest quality gates passed.'

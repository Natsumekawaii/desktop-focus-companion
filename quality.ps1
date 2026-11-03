param(
    [ValidateSet('Full', 'Fast', 'Docs')][string]$Mode = 'Full',
    [ValidateSet('All', 'Ruff', 'Mypy', 'Tests')][string]$Stage = 'All',
    [string[]]$Tests = @()
)
$ErrorActionPreference = 'Stop'
$pythonPath = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
    throw 'Create .venv with Python 3.12.10, then install requirements-dev.txt.'
}
Push-Location $PSScriptRoot
try {
    & $pythonPath -m scripts.quality --mode $Mode --stage $Stage @Tests
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
finally { Pop-Location }

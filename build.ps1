param(
    [switch]$InstallDependencies
)

$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
$specPath = Join-Path $projectRoot 'DesktopFocusCompanion.spec'
$resolvedProjectRoot = [System.IO.Path]::GetFullPath($projectRoot).TrimEnd('\')
$artifactRoots = @(
    [System.IO.Path]::GetFullPath((Join-Path $projectRoot 'build')),
    [System.IO.Path]::GetFullPath((Join-Path $projectRoot 'dist'))
)

if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw 'Create the project virtual environment before building.'
}

if ($InstallDependencies) {
    & $pythonPath -m pip install -r (Join-Path $projectRoot 'requirements-build.txt')
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

& $pythonPath -c 'import PyInstaller' 2>$null
if ($LASTEXITCODE -ne 0) {
    throw 'PyInstaller is not installed. Run .\build.ps1 -InstallDependencies.'
}

foreach ($artifactRoot in $artifactRoots) {
    $expectedParent = [System.IO.Path]::GetDirectoryName($artifactRoot)
    $leaf = [System.IO.Path]::GetFileName($artifactRoot)
    if ($expectedParent -ne $resolvedProjectRoot -or $leaf -notin @('build', 'dist')) {
        throw "Refusing to clean unexpected build path: $artifactRoot"
    }
    if ([System.IO.Directory]::Exists($artifactRoot)) {
        [System.IO.Directory]::Delete($artifactRoot, $true)
    }
}

Push-Location $projectRoot
try {
    & $pythonPath -m PyInstaller --noconfirm --clean $specPath
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
finally {
    Pop-Location
}

$outputExe = Join-Path $projectRoot 'dist\DesktopFocusCompanion\DesktopFocusCompanion.exe'
if (-not (Test-Path -LiteralPath $outputExe -PathType Leaf)) {
    throw "Packaged executable was not created: $outputExe"
}

# A live packaged-runtime gate catches DLL/import failures that source tests and
# process-liveness checks cannot detect. The app exits itself after startup only
# when this private build flag is present, and uses an isolated local profile.
$smokeProfileRoot = Join-Path $projectRoot 'build\packaged-smoke-profile'
New-Item -ItemType Directory -Path $smokeProfileRoot -Force | Out-Null
$previousLocalAppData = $env:LOCALAPPDATA
$previousSmokeFlag = $env:DESKTOP_FOCUS_COMPANION_SMOKE_TEST
try {
    $env:LOCALAPPDATA = $smokeProfileRoot
    $env:DESKTOP_FOCUS_COMPANION_SMOKE_TEST = '1'
    $smokeProcess = Start-Process `
        -FilePath $outputExe `
        -WorkingDirectory (Split-Path -Parent $outputExe) `
        -WindowStyle Hidden `
        -PassThru
    if (-not $smokeProcess.WaitForExit(15000)) {
        Stop-Process -Id $smokeProcess.Id -Force -ErrorAction SilentlyContinue
        throw 'Packaged executable did not complete its startup smoke test.'
    }
    if ($smokeProcess.ExitCode -ne 0) {
        throw "Packaged executable smoke test failed with exit code $($smokeProcess.ExitCode)."
    }
}
finally {
    $env:LOCALAPPDATA = $previousLocalAppData
    $env:DESKTOP_FOCUS_COMPANION_SMOKE_TEST = $previousSmokeFlag
}

Write-Output 'Packaged executable startup smoke test passed.'
Write-Output "Desktop Focus Companion build created at: $outputExe"

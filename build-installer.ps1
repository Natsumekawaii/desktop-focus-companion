param(
    [switch]$InstallDependencies,
    [switch]$SkipApplicationBuild,
    [switch]$SkipInstallerSmokeTest,
    [switch]$ReleaseBuild
)

$ErrorActionPreference = 'Stop'
$projectRoot = [System.IO.Path]::GetFullPath($PSScriptRoot).TrimEnd('\')
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
$applicationBuildScript = Join-Path $projectRoot 'build.ps1'
$installerScript = Join-Path $projectRoot 'installer\DesktopFocusCompanion.iss'
$installerOutputRoot = Join-Path $projectRoot 'dist\installer'
$portableExe = Join-Path $projectRoot 'dist\DesktopFocusCompanion\DesktopFocusCompanion.exe'
$smokeRoot = Join-Path $projectRoot 'build\installer-smoke'
$smokeInstallRoot = Join-Path $smokeRoot 'installed-app'
$smokeProfileRoot = Join-Path $smokeRoot 'profile'
. (Join-Path $projectRoot 'scripts\installer_safety.ps1')

function Resolve-InnoCompiler {
    $command = Get-Command 'ISCC.exe' -ErrorAction SilentlyContinue
    if ($null -ne $command) {
        return $command.Source
    }

    $candidates = @()
    if (${env:ProgramFiles(x86)}) {
        $candidates += Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe'
    }
    if ($env:ProgramFiles) {
        $candidates += Join-Path $env:ProgramFiles 'Inno Setup 6\ISCC.exe'
    }
    if ($env:LOCALAPPDATA) {
        $candidates += Join-Path $env:LOCALAPPDATA 'Programs\Inno Setup 6\ISCC.exe'
    }
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            return [System.IO.Path]::GetFullPath($candidate)
        }
    }
    return $null
}

function Assert-DirectChildPath {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$ExpectedParent
    )
    $resolvedPath = [System.IO.Path]::GetFullPath($Path)
    $resolvedParent = [System.IO.Path]::GetFullPath($ExpectedParent).TrimEnd('\')
    if ([System.IO.Path]::GetDirectoryName($resolvedPath) -ne $resolvedParent) {
        throw "Refusing to clean unexpected path: $resolvedPath"
    }
    if ((Test-Path -LiteralPath $resolvedPath) -and
        ((Get-Item -LiteralPath $resolvedPath).Attributes -band [System.IO.FileAttributes]::ReparsePoint)) {
        throw "Refusing redirected directory: $resolvedPath"
    }
    return $resolvedPath
}

function Get-PendingFileRenameOperations {
    $sessionManagerPath = 'HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager'
    $sessionManager = Get-ItemProperty `
        -LiteralPath $sessionManagerPath `
        -Name 'PendingFileRenameOperations' `
        -ErrorAction SilentlyContinue
    if ($null -eq $sessionManager) {
        return @()
    }
    return @($sessionManager.PendingFileRenameOperations)
}

function Invoke-SilentInstaller {
    param(
        [Parameter(Mandatory = $true)][string]$SetupPath,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [Parameter(Mandatory = $true)][string]$Description
    )
    $process = Start-Process `
        -FilePath $SetupPath `
        -ArgumentList $Arguments `
        -WindowStyle Hidden `
        -PassThru
    Wait-OwnedProcess $process
    if ($process.ExitCode -ne 0) {
        throw "$Description failed with exit code $($process.ExitCode)."
    }
}

if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
    throw 'Create the project virtual environment before building the installer.'
}
if (-not (Test-Path -LiteralPath $installerScript -PathType Leaf)) {
    throw "Installer definition was not found: $installerScript"
}

$innoCompiler = Resolve-InnoCompiler
if ($null -eq $innoCompiler -and $InstallDependencies) {
    $winget = Get-Command 'winget.exe' -ErrorAction SilentlyContinue
    if ($null -eq $winget) {
        throw 'winget is required to install Inno Setup automatically.'
    }
    & $winget.Source install `
        --id JRSoftware.InnoSetup `
        --exact `
        --version 6.7.3 `
        --silent `
        --accept-package-agreements `
        --accept-source-agreements `
        --disable-interactivity
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    $innoCompiler = Resolve-InnoCompiler
}
if ($null -eq $innoCompiler) {
    throw 'Inno Setup 6 is not installed. Run .\build-installer.ps1 -InstallDependencies.'
}

if ($InstallDependencies) {
    & $pythonPath -m pip install -r (Join-Path $projectRoot 'requirements-dev.txt') -r (Join-Path $projectRoot 'requirements-build.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
}

Push-Location $projectRoot
try {
    & $pythonPath -m scripts.build_support preflight --compiler $innoCompiler
    if ($LASTEXITCODE -ne 0) { throw 'Installer preflight failed.' }
    $appVersion = (& $pythonPath -c 'from app import __version__; print(__version__)').Trim()
    if ($LASTEXITCODE -ne 0 -or $appVersion -notmatch '^\d+\.\d+\.\d+$') {
        throw "Application version is not a supported semantic version: $appVersion"
    }
}
finally { Pop-Location }

if (-not $SkipApplicationBuild) {
    & $applicationBuildScript -ReleaseBuild:$ReleaseBuild
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
if (-not (Test-Path -LiteralPath $portableExe -PathType Leaf)) {
    throw "Portable application build was not found: $portableExe"
}

Push-Location $projectRoot
try {
    & $pythonPath -m scripts.build_support verify
    if ($LASTEXITCODE -ne 0) { throw 'Portable artifact verification failed.' }
    $manifestArguments = @('-m', 'scripts.build_support', 'manifest', '--compiler', $innoCompiler)
    if ($ReleaseBuild) { $manifestArguments += '--release' }
    & $pythonPath @manifestArguments
    if ($LASTEXITCODE -ne 0) { throw 'Cannot record compiler provenance.' }
}
finally { Pop-Location }

$versionDefine = "/DMyAppVersion=$appVersion"
$rootDefine = "/DProjectRoot=$projectRoot"
$outputDefine = "/DInstallerOutputDir=$installerOutputRoot"
$installerBaseName = "DesktopFocusCompanion-Setup-$appVersion"
if (-not $ReleaseBuild) { $installerBaseName += '-local-validation' }
& $innoCompiler /Qp $versionDefine $rootDefine $outputDefine "/DInstallerOutputBaseFilename=$installerBaseName" $installerScript
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$setupPath = Join-Path $installerOutputRoot "$installerBaseName.exe"
if (-not (Test-Path -LiteralPath $setupPath -PathType Leaf)) {
    throw "Installer was not created: $setupPath"
}

if (-not $SkipInstallerSmokeTest) {
    $buildRoot = Join-Path $projectRoot 'build'
    $validatedSmokeRoot = Assert-DirectChildPath -Path $smokeRoot -ExpectedParent $buildRoot
    if ([System.IO.Directory]::Exists($validatedSmokeRoot)) {
        $diagnosticArchive = Join-Path $projectRoot ('artifacts\installer-smoke-' + [System.DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss-fff'))
        New-Item -ItemType Directory -Path (Split-Path -Parent $diagnosticArchive) -Force | Out-Null
        Move-Item -LiteralPath $validatedSmokeRoot -Destination $diagnosticArchive
    }
    $smokePackageRoot = Join-Path $validatedSmokeRoot 'package'
    New-Item -ItemType Directory -Path $smokeProfileRoot -Force | Out-Null

    $smokeAppId = [System.Guid]::NewGuid().ToString().ToUpperInvariant()
    $smokeMutexName = "DesktopFocusCompanion-Smoke-$smokeAppId"
    $smokeOutputBaseFilename = 'DesktopFocusCompanion-InstallerSmoke'
    $smokeBaselineVersion = '0.9.9'
    $smokeBaselineOutputBaseFilename = 'DesktopFocusCompanion-InstallerSmoke-Baseline'
    $pendingOperationsBefore = @(Get-PendingFileRenameOperations)
    $smokeOutputDefine = "/DInstallerOutputDir=$smokePackageRoot"
    $smokeAppIdDefine = "/DMyAppId=$smokeAppId"
    $smokeMutexDefine = "/DMyAppMutexName=$smokeMutexName"
    $smokeFilenameDefine = "/DInstallerOutputBaseFilename=$smokeOutputBaseFilename"
    & $innoCompiler `
        /Qp `
        $versionDefine `
        $rootDefine `
        $smokeOutputDefine `
        $smokeAppIdDefine `
        $smokeMutexDefine `
        $smokeFilenameDefine `
        $installerScript
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    $smokeSetupPath = Join-Path $smokePackageRoot "$smokeOutputBaseFilename.exe"
    if (-not (Test-Path -LiteralPath $smokeSetupPath -PathType Leaf)) {
        throw "Isolated smoke installer was not created: $smokeSetupPath"
    }

    $smokeBaselineVersionDefine = "/DMyAppVersion=$smokeBaselineVersion"
    $smokeBaselineFilenameDefine = `
        "/DInstallerOutputBaseFilename=$smokeBaselineOutputBaseFilename"
    & $innoCompiler `
        /Qp `
        $smokeBaselineVersionDefine `
        $rootDefine `
        $smokeOutputDefine `
        $smokeAppIdDefine `
        $smokeMutexDefine `
        $smokeBaselineFilenameDefine `
        $installerScript
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    $smokeBaselineSetupPath = `
        Join-Path $smokePackageRoot "$smokeBaselineOutputBaseFilename.exe"
    if (-not (Test-Path -LiteralPath $smokeBaselineSetupPath -PathType Leaf)) {
        throw "Smoke upgrade baseline installer was not created: $smokeBaselineSetupPath"
    }

    $mutexBlockedInstallRoot = Join-Path $validatedSmokeRoot 'mutex-blocked-install'
    $applicationMutex = [System.Threading.Mutex]::new($false, $smokeMutexName)
    try {
        $blockedInstallProcess = Start-Process `
            -FilePath $smokeSetupPath `
            -ArgumentList @(
                '/VERYSILENT',
                '/SUPPRESSMSGBOXES',
                '/NORESTART',
                '/SP-',
                '/NOICONS',
                '/NoStartupMigration=1',
                "/DIR=`"$mutexBlockedInstallRoot`""
            ) `
            -WindowStyle Hidden `
            -PassThru
        Wait-OwnedProcess $blockedInstallProcess
        if ($blockedInstallProcess.ExitCode -eq 0) {
            throw 'Installer was not blocked by the running-application mutex.'
        }
        if (Test-Path -LiteralPath $mutexBlockedInstallRoot) {
            throw 'Mutex-blocked installer created an application directory.'
        }
    }
    finally {
        $applicationMutex.Dispose()
    }

    $uninstallerPath = Join-Path $smokeInstallRoot 'unins000.exe'
    $installedExe = Join-Path $smokeInstallRoot 'DesktopFocusCompanion.exe'
    try {
        $installArguments = @(
            '/VERYSILENT',
            '/SUPPRESSMSGBOXES',
            '/NORESTART',
            '/SP-',
            '/NOICONS',
            '/NoStartupMigration=1',
            "/DIR=`"$smokeInstallRoot`"",
            "/LOG=`"$(Join-Path $validatedSmokeRoot 'install.log')`""
        )
        Invoke-SilentInstaller `
            -SetupPath $smokeBaselineSetupPath `
            -Arguments $installArguments `
            -Description 'Silent baseline installation'
        if (-not (Test-Path -LiteralPath $installedExe -PathType Leaf)) {
            throw "Installed executable was not created: $installedExe"
        }

        $dataRoot = Join-Path $smokeProfileRoot 'DesktopFocusCompanion'
        New-Item -ItemType Directory -Path $dataRoot -Force | Out-Null
        $preservationMarker = Join-Path $dataRoot 'installer-data-preservation.marker'
        Set-Content -LiteralPath $preservationMarker -Value 'preserve' -Encoding utf8

        $replacementMarker = Join-Path $smokeInstallRoot 'obsolete-build.marker'
        Set-Content -LiteralPath $replacementMarker -Value 'remove' -Encoding utf8
        Invoke-SilentInstaller `
            -SetupPath $smokeSetupPath `
            -Arguments $installArguments `
            -Description 'Silent version upgrade'
        if (Test-Path -LiteralPath $replacementMarker) {
            throw 'Version upgrade did not remove an obsolete application file.'
        }
        if (-not (Test-Path -LiteralPath $preservationMarker -PathType Leaf)) {
            throw 'Version upgrade removed the isolated user-data preservation marker.'
        }

        Invoke-SilentInstaller `
            -SetupPath $smokeSetupPath `
            -Arguments $installArguments `
            -Description 'Silent same-version reinstall'

        $uninstallEntries = @(
            Get-ChildItem -LiteralPath `
                'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall' |
                Get-ItemProperty |
                Where-Object {
                    $_.InstallLocation -and
                    ([System.IO.Path]::GetFullPath($_.InstallLocation).TrimEnd('\') -eq
                        $smokeInstallRoot.TrimEnd('\'))
                }
        )
        if ($uninstallEntries.Count -ne 1) {
            throw "Expected one isolated uninstall entry, found $($uninstallEntries.Count)."
        }
        if ($uninstallEntries[0].DisplayVersion -ne $appVersion) {
            throw "Upgrade did not register application version $appVersion."
        }

        $previousLocalAppData = $env:LOCALAPPDATA
        $previousSmokeFlag = $env:DESKTOP_FOCUS_COMPANION_SMOKE_TEST
        try {
            $env:LOCALAPPDATA = $smokeProfileRoot
            $env:DESKTOP_FOCUS_COMPANION_SMOKE_TEST = '1'
            $appProcess = Start-Process `
                -FilePath $installedExe `
                -WorkingDirectory $smokeInstallRoot `
                -WindowStyle Hidden `
                -PassThru
            if (-not $appProcess.WaitForExit(15000)) {
                Stop-Process -Id $appProcess.Id -Force -ErrorAction SilentlyContinue
                throw 'Installed executable did not complete its startup smoke test.'
            }
            if ($appProcess.ExitCode -ne 0) {
                throw "Installed executable smoke test failed with exit code $($appProcess.ExitCode)."
            }
        }
        finally {
            $env:LOCALAPPDATA = $previousLocalAppData
            $env:DESKTOP_FOCUS_COMPANION_SMOKE_TEST = $previousSmokeFlag
        }

        if (-not (Test-Path -LiteralPath $uninstallerPath -PathType Leaf)) {
            throw "Uninstaller was not created: $uninstallerPath"
        }
        $uninstallMutex = [System.Threading.Mutex]::new($false, $smokeMutexName)
        try {
            $blockedUninstall = Start-Process -FilePath $uninstallerPath `
                -ArgumentList @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART') `
                -WindowStyle Hidden -PassThru
            Wait-OwnedProcess $blockedUninstall
            if ($blockedUninstall.ExitCode -eq 0 -or -not (Test-Path -LiteralPath $installedExe)) {
                throw 'Uninstaller did not respect the running-application mutex.'
            }
        }
        finally { $uninstallMutex.Dispose() }
        $uninstallProcess = Start-Process `
            -FilePath $uninstallerPath `
            -ArgumentList @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART') `
            -WindowStyle Hidden `
            -PassThru
        Wait-OwnedProcess $uninstallProcess
        if ($uninstallProcess.ExitCode -ne 0) {
            throw "Silent uninstaller smoke test failed with exit code $($uninstallProcess.ExitCode)."
        }
        $uninstallCleanupDeadline = [System.DateTime]::UtcNow.AddSeconds(10)
        while ((Test-Path -LiteralPath $smokeInstallRoot) -and
               ([System.DateTime]::UtcNow -lt $uninstallCleanupDeadline)) {
            Start-Sleep -Milliseconds 100
        }
        if (Test-Path -LiteralPath $smokeInstallRoot) {
            $remainingInstallPaths = @(
                Get-ChildItem -LiteralPath $smokeInstallRoot -Force -Recurse |
                    Select-Object -ExpandProperty FullName
            )
            throw (
                'Silent uninstaller did not remove the test installation directory. ' +
                "Remaining paths: $($remainingInstallPaths -join ', ')"
            )
        }
        if (-not (Test-Path -LiteralPath $preservationMarker -PathType Leaf)) {
            throw 'Uninstall removed the isolated user-data preservation marker.'
        }
    }
    finally {
        if (Test-Path -LiteralPath $uninstallerPath -PathType Leaf) {
            try {
                Invoke-SilentInstaller -SetupPath $uninstallerPath `
                    -Arguments @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART') `
                    -Description 'Cleanup uninstall'
            }
            catch { Write-Warning "Cleanup failed; original diagnostics retained: $_" }
        }
        $pendingOperationsAfter = @(Get-PendingFileRenameOperations)
        Assert-PendingQueueSafe -Before $pendingOperationsBefore -After $pendingOperationsAfter `
            -Roots @($validatedSmokeRoot,
                     (Join-Path $env:LOCALAPPDATA 'Programs\DesktopFocusCompanion'),
                     (Join-Path $env:LOCALAPPDATA 'DesktopFocusCompanion'))
        # Retain logs and the isolated profile for diagnostics; never delete real data.
    }
    Write-Output `
        'Installer mutex/install/upgrade/reinstall/start/uninstall/reboot-queue smoke test passed.'
}

Write-Output "Desktop Focus Companion installer created at: $setupPath"

$hash = (Get-FileHash -LiteralPath $setupPath -Algorithm SHA256).Hash.ToLowerInvariant()
"$hash  $([System.IO.Path]::GetFileName($setupPath))" | Set-Content -LiteralPath (Join-Path $installerOutputRoot 'SHA256SUMS.txt') -Encoding ascii
if (-not $ReleaseBuild) { Write-Output 'UNPUBLISHED local validation build; no release assets changed.' }

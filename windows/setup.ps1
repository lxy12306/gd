param(
    [string]$Python = '',
    [switch]$CoreOnly,
    [switch]$Dev,
    [switch]$NoLauncher,
    [string]$MigrateFrom = ''
)

$ErrorActionPreference = 'Stop'
$taskProject = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$taskVenv = Join-Path $taskProject '.venv'
$taskPython = Join-Path $taskVenv 'Scripts\python.exe'

if ($CoreOnly -and $Dev) {
    throw '-CoreOnly and -Dev cannot be combined. Full tests require the OSS dependencies.'
}
if ($NoLauncher -and $MigrateFrom) {
    throw '-MigrateFrom requires launcher installation; do not combine it with -NoLauncher.'
}

if (!(Test-Path -LiteralPath $taskPython -PathType Leaf)) {
    if (Test-Path -LiteralPath $taskVenv) {
        throw "An incomplete .venv exists at $taskVenv. It has been preserved; repair or move it before retrying."
    }
    $taskBootstrapArguments = @()
    if ($Python) {
        $taskBootstrapCommand = Get-Command $Python -CommandType Application -ErrorAction SilentlyContinue
        if (!$taskBootstrapCommand) { throw "Cannot find the requested Python interpreter: $Python" }
    } else {
        $taskBootstrapCommand = Get-Command py -CommandType Application -ErrorAction SilentlyContinue
        if ($taskBootstrapCommand) {
            $taskBootstrapArguments = @('-3')
        } else {
            $taskBootstrapCommand = Get-Command python -CommandType Application -ErrorAction SilentlyContinue
        }
        if (!$taskBootstrapCommand) { throw 'Python 3.10+ is required. Install Python or provide -Python <python.exe>.' }
    }
    $taskVersion = & $taskBootstrapCommand.Source @taskBootstrapArguments -c 'import sys; print(sys.version_info.major, sys.version_info.minor)'
    if ($LASTEXITCODE -ne 0) { throw 'Cannot start the Python interpreter.' }
    $taskVersionParts = "$taskVersion".Trim() -split '\s+'
    if ($taskVersionParts.Count -ne 2 -or [int]$taskVersionParts[0] -lt 3 -or
        ([int]$taskVersionParts[0] -eq 3 -and [int]$taskVersionParts[1] -lt 10)) {
        throw 'Python 3.10+ is required.'
    }
    Write-Output "Creating virtual environment: $taskVenv"
    & $taskBootstrapCommand.Source @taskBootstrapArguments -m venv $taskVenv
    if ($LASTEXITCODE -ne 0) { throw 'Virtual environment creation failed.' }
} else {
    Write-Output "Reusing virtual environment: $taskVenv"
}

$taskEnvironment = @'
import json
from pathlib import Path
import sys
print(json.dumps({
    "valid": sys.prefix != sys.base_prefix and Path(sys.prefix).resolve() == Path(sys.argv[1]).resolve(),
    "version": list(sys.version_info[:2]),
    "python": sys.executable,
}))
'@ | & $taskPython - $taskVenv
if ($LASTEXITCODE -ne 0) { throw 'The existing virtual environment cannot start. It has been preserved.' }
$taskEnvironment = $taskEnvironment | ConvertFrom-Json
if (!$taskEnvironment.valid -or $taskEnvironment.version[0] -lt 3 -or
    ($taskEnvironment.version[0] -eq 3 -and $taskEnvironment.version[1] -lt 10)) {
    throw 'The .venv interpreter must be Python 3.10+ and belong to this virtual environment.'
}

& $taskPython -m pip --version
if ($LASTEXITCODE -ne 0) { throw 'pip is missing from .venv. Repair the virtual environment before retrying.' }
$taskPackage = if ($CoreOnly) { $taskProject } else { $taskProject + '[oss]' }
$taskInstallArguments = @('-m', 'pip', 'install', '--disable-pip-version-check', '-e', $taskPackage)
if ($Dev) { $taskInstallArguments += @('-r', (Join-Path $taskProject 'requirements-dev.txt')) }
& $taskPython @taskInstallArguments
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed. The environment is retained; rerun this script to retry.' }
& $taskPython -m pip check
if ($LASTEXITCODE -ne 0) { throw 'The virtual environment has conflicting dependencies.' }

& (Join-Path $taskVenv 'Scripts\gd.exe') --help
if ($LASTEXITCODE -ne 0) { throw 'The gd virtual-environment entry point failed verification.' }
if (!$NoLauncher) {
    $taskLauncherArguments = @{}
    if ($MigrateFrom) { $taskLauncherArguments.MigrateFrom = $MigrateFrom }
    & (Join-Path $PSScriptRoot 'install-gd.ps1') @taskLauncherArguments
}

Write-Output "Ready. Default Python: $taskPython"
Write-Output 'Run Python commands from the project root: .\windows\run.ps1 <python arguments>'
if ($NoLauncher) {
    Write-Output 'Run gd locally: .\.venv\Scripts\gd.exe <arguments>'
} else {
    Write-Output 'Run from any directory: gd <arguments>'
}

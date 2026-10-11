param(
    [string]$InstallDir = '',
    [switch]$Uninstall
)

$ErrorActionPreference = 'Stop'
$taskProject = [IO.Path]::GetFullPath($PSScriptRoot)
$taskPython = Join-Path $taskProject '.venv\Scripts\python.exe'
if (!(Test-Path -LiteralPath $taskPython -PathType Leaf)) {
    throw 'Missing code/.venv. Create the virtual environment and install requirements.txt first.'
}

# Use this user's existing Python Scripts directory, which is already on PATH.
# The generated console launcher always invokes code/.venv, not the base Python.
if (!$InstallDir) {
    $taskBasePython = (& $taskPython -c 'import sys; print(sys.base_prefix)').Trim()
    if ($LASTEXITCODE -ne 0) { throw 'Cannot locate the Python Scripts directory.' }
    $InstallDir = Join-Path $taskBasePython 'Scripts'
}
$taskTargetDir = [IO.Path]::GetFullPath($InstallDir)
$taskTarget = Join-Path $taskTargetDir 'gd.exe'
$taskManifest = Join-Path $taskTargetDir 'gd.install.json'
$taskLauncher = Join-Path $taskProject '.venv\Scripts\gd.exe'

if (Test-Path -LiteralPath $taskManifest) {
    $taskOwner = Get-Content -LiteralPath $taskManifest -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($taskOwner.project -ne $taskProject) {
        throw 'The existing gd installation belongs to another project. Nothing has been overwritten.'
    }
} elseif (Test-Path -LiteralPath $taskTarget) {
    throw "An unrelated gd.exe already exists at $taskTarget. Nothing has been overwritten."
}

if ($Uninstall) {
    if (Test-Path -LiteralPath $taskTarget) { Remove-Item -LiteralPath $taskTarget }
    if (Test-Path -LiteralPath $taskManifest) { Remove-Item -LiteralPath $taskManifest }
    Write-Output 'gd launcher removed. Project files, registered scripts and configuration have been preserved.'
    exit 0
}

$taskExisting = Get-Command gd -ErrorAction SilentlyContinue
if ($taskExisting -and $taskExisting.Source -ne $taskTarget -and $taskExisting.Source -ne $taskLauncher) {
    throw "Another command named gd is already available ($($taskExisting.CommandType): $($taskExisting.Source)). Nothing has been overwritten."
}

# Migrate the former editable OSS distribution only when it belongs to this project.
# Feed Python through stdin so PowerShell does not reinterpret quotes in source code.
$taskLegacyOwner = @'
import json
from pathlib import Path
import sys
from urllib.parse import urlparse
from urllib.request import url2pathname
project = Path(sys.argv[1]).resolve()
sys.path = [p for p in sys.path if Path(p or Path.cwd()).resolve() != project]
from importlib import metadata
try:
    dist = metadata.distribution("smell-oss-toolkit")
except metadata.PackageNotFoundError:
    print("absent")
else:
    direct = json.loads(dist.read_text("direct_url.json") or "{}")
    parsed = urlparse(direct.get("url", ""))
    if parsed.scheme != "file" or not direct.get("dir_info", {}).get("editable"):
        print("unknown")
    else:
        print(Path(url2pathname(parsed.path)).resolve())
'@ | & $taskPython - $taskProject
if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect the previous gd package.' }
if ($taskLegacyOwner -ne 'absent') {
    if ($taskLegacyOwner -ne $taskProject) {
        throw 'The previous OSS package belongs to another installation. Nothing has been overwritten.'
    }
    Push-Location -LiteralPath (Split-Path -Parent $taskPython)
    try {
        & $taskPython -m pip uninstall --yes smell-oss-toolkit
        if ($LASTEXITCODE -ne 0) { throw 'Failed to migrate the previous gd package.' }
    } finally {
        Pop-Location
    }
}
# Remove only the known, generated metadata directory inside this project.
$taskLegacyMetadata = [IO.Path]::GetFullPath((Join-Path $taskProject 'smell_oss_toolkit.egg-info'))
if (!$taskLegacyMetadata.StartsWith($taskProject.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)) {
    throw 'The generated metadata path is outside the project.'
}
if (Test-Path -LiteralPath $taskLegacyMetadata) {
    Remove-Item -LiteralPath $taskLegacyMetadata -Recurse -Force
}

& $taskPython -m pip install --no-deps -e $taskProject
if ($LASTEXITCODE -ne 0) { throw 'Failed to install the gd entry point.' }
if (!(Test-Path -LiteralPath $taskLauncher -PathType Leaf)) { throw 'The gd launcher was not generated.' }
if (!(Test-Path -LiteralPath $taskTargetDir)) { New-Item -ItemType Directory -Path $taskTargetDir -Force | Out-Null }
Copy-Item -LiteralPath $taskLauncher -Destination $taskTarget -Force
@{ project = $taskProject; python = $taskPython; launcher = $taskTarget } |
    ConvertTo-Json | Set-Content -LiteralPath $taskManifest -Encoding UTF8

$taskOnPath = @($env:Path -split ';' | Where-Object {
    [Environment]::ExpandEnvironmentVariables($_).TrimEnd('\') -ieq $taskTargetDir.TrimEnd('\')
}).Count -gt 0
Write-Output "Installed: $taskTarget"
if ($taskOnPath) {
    & $taskTarget --help
    if ($LASTEXITCODE -ne 0) { throw 'gd verification failed.' }
    Write-Output 'Ready: gd list | gd add <name> <script> | gd <name> [args] | gd oss ls'
} else {
    Write-Output "Run directly: $taskTarget --help"
    Write-Output "To use the short command, add this directory to your user PATH: $taskTargetDir"
}

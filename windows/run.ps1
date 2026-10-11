# Forward all arguments to this project's Python without activating a shell.
$ErrorActionPreference = 'Stop'
$taskProject = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$taskPython = Join-Path $taskProject '.venv\Scripts\python.exe'
if (!(Test-Path -LiteralPath $taskPython -PathType Leaf)) {
    throw 'The project virtual environment is not ready. Run windows/setup.ps1 first.'
}
& $taskPython @args
exit $LASTEXITCODE

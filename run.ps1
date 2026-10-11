# Forward all arguments to this project's Python without activating a shell.
$ErrorActionPreference = 'Stop'
$taskPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (!(Test-Path -LiteralPath $taskPython -PathType Leaf)) {
    throw 'The project virtual environment is not ready. Run setup.ps1 first.'
}
& $taskPython @args
exit $LASTEXITCODE

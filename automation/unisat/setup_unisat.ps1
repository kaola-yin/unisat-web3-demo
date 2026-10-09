$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$unisatPythonVersion = '3.13.16'
$unisatRuntimeDir = Join-Path $PSScriptRoot '.browser\python31316'
$unisatBasePython = Join-Path $unisatRuntimeDir 'tools\python.exe'
$unisatVenvDir = Join-Path $PSScriptRoot '.venv-unisat313'
$unisatPython = Join-Path $unisatVenvDir 'Scripts\python.exe'

if (-not (Test-Path -LiteralPath $unisatBasePython)) {
    New-Item -ItemType Directory -Path $unisatRuntimeDir -Force | Out-Null
    $unisatPackage = Join-Path $unisatRuntimeDir 'python.zip'
    $unisatPackageUrl = "https://api.nuget.org/v3-flatcontainer/python/$unisatPythonVersion/python.$unisatPythonVersion.nupkg"
    Write-Host "Downloading official CPython $unisatPythonVersion into this project..."
    Invoke-WebRequest -Uri $unisatPackageUrl -OutFile $unisatPackage -UseBasicParsing -TimeoutSec 60
    Expand-Archive -LiteralPath $unisatPackage -DestinationPath $unisatRuntimeDir -Force
}

& $unisatBasePython --version
if ($LASTEXITCODE -ne 0) { throw 'The project Python runtime could not start.' }

if (-not (Test-Path -LiteralPath $unisatPython)) {
    & $unisatBasePython -m venv $unisatVenvDir
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the UniSat virtual environment.' }
}

& $unisatPython -m pip install --disable-pip-version-check --cache-dir (Join-Path $PSScriptRoot '.browser\pip313') -r (Join-Path $PSScriptRoot 'requirements-unisat.txt')
if ($LASTEXITCODE -ne 0) { throw 'Could not install the UniSat dependencies. Check network access.' }

Write-Host 'UniSat environment ready. Run these commands from the project directory:'
Write-Host '.\.venv-unisat313\Scripts\python.exe run_unisat.py --setup'
Write-Host '.\.venv-unisat313\Scripts\python.exe run_unisat.py'

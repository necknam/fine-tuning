param([string]$Config = 'configs/hyperparameters.qwen35_4b_3000.P01.yaml')
$ErrorActionPreference = 'Stop'
$controlPython = Join-Path $env:USERPROFILE 'miniforge3/envs/qwen-factory/python.exe'
if (-not (Test-Path -LiteralPath $controlPython)) {
    throw 'Miniforge qwen-factory environment is missing. Follow configs/environment.local.yml and requirements.txt.'
}
$env:PYTHONUTF8 = '1'
$env:PYTHONDONTWRITEBYTECODE = '1'
Push-Location -LiteralPath $PSScriptRoot
try {
    & $controlPython -m pip check
    if ($LASTEXITCODE -ne 0) { throw 'Local package compatibility check failed.' }
    # Preview only: no model download, GPU, RunPod connection, registry or training.
    & $controlPython scripts/qwen35_b200_runner.py --config $Config --phase check
    if ($LASTEXITCODE -ne 0) { throw 'Profile/data preflight failed.' }
} finally {
    Pop-Location
}

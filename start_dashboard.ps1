$ErrorActionPreference = 'Stop'
$projectPath = $PSScriptRoot
Set-Location -LiteralPath $projectPath
$env:TEMP = Join-Path $projectPath '.cache\local-temp'
$env:TMP = $env:TEMP
$env:PIP_CACHE_DIR = Join-Path $projectPath '.cache\pip'
New-Item -ItemType Directory -Force -Path $env:TEMP | Out-Null
$dashboardPython = Join-Path $projectPath '.venv-dashboard\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $dashboardPython)) {
    python -m venv --system-site-packages (Join-Path $projectPath '.venv-dashboard')
    if ($LASTEXITCODE -ne 0) { throw 'Could not create dashboard environment.' }
    & $dashboardPython -m pip install -r (Join-Path $projectPath 'requirements.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Could not install dashboard dependencies.' }
}
& $dashboardPython -m streamlit run (Join-Path $projectPath 'scripts\local_dashboard.py') --server.address 127.0.0.1 --server.port 8501 --browser.gatherUsageStats false

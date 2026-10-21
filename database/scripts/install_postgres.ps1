param([string]$CondaExe = "", [string]$EnvironmentName = "growpath_db", [switch]$SkipPackageInstall)
$ErrorActionPreference = "Stop"
$databaseRoot = Split-Path -Parent $PSScriptRoot
if (-not $CondaExe) {
    $found = Get-Command conda.exe -CommandType Application -ErrorAction SilentlyContinue
    if ($found) { $CondaExe = $found.Source }
    elseif (Test-Path -LiteralPath "$env:USERPROFILE/miniforge3/Scripts/conda.exe") { $CondaExe = "$env:USERPROFILE/miniforge3/Scripts/conda.exe" }
    else { throw "Install Miniforge first: https://github.com/conda-forge/miniforge . Or pass -CondaExe." }
}
if (-not $SkipPackageInstall) {
    & $CondaExe create --yes --name $EnvironmentName --channel conda-forge postgresql=17.11
    if ($LASTEXITCODE -ne 0) { throw "PostgreSQL 17.11 installation failed." }
}
$prefixText = & $CondaExe run --no-capture-output --name $EnvironmentName cmd /d /c "echo %CONDA_PREFIX%"
if ($LASTEXITCODE -ne 0) { throw "Conda environment was not found." }
$prefix = ($prefixText | Select-Object -Last 1).Trim()
$pgRoot = Join-Path $prefix "Library"
$pgBin = Join-Path $pgRoot "bin"
$version = & (Join-Path $pgBin "postgres.exe") --version
if ($LASTEXITCODE -ne 0 -or $version -notmatch '17\.11') { throw "Expected PostgreSQL 17.11 Windows x64." }
$bundle = Join-Path $databaseRoot "data/exports/pgvector_pg17_windows_x64"
$manifest = Get-Content -LiteralPath (Join-Path $bundle "manifest.json") -Raw | ConvertFrom-Json
foreach ($property in $manifest.files.PSObject.Properties) {
    $source = Join-Path $bundle $property.Name
    if ([IO.Path]::GetFileName($property.Name) -ne $property.Name) { throw "Invalid extension manifest path." }
    if ((Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant() -ne $property.Value) { throw "pgvector checksum failed." }
}
foreach ($source in Get-ChildItem -LiteralPath $bundle -File) {
    if ($source.Name -eq "vector.dll") { $target = Join-Path $pgRoot "lib/vector.dll" }
    elseif ($source.Name -eq "vector.control" -or $source.Extension -eq ".sql") { $target = Join-Path $pgRoot ("share/extension/" + $source.Name) }
    else { continue }
    if (Test-Path -LiteralPath $target) {
        if ((Get-FileHash -LiteralPath $source.FullName).Hash -ne (Get-FileHash -LiteralPath $target).Hash) { throw "Different extension exists; preserved: $target" }
    } else { Copy-Item -LiteralPath $source.FullName -Destination $target }
}
Write-Output "PostgreSQL 17.11 + pgvector 0.8.2 prepared."
Write-Output "POSTGRES_BIN_DIR=$pgBin"

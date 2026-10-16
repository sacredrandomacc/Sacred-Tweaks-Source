param([switch]$Register)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
if (-not (Test-Path $vswhere)) { throw 'Install Visual Studio 2022 with Universal Windows Platform development, C# tools, and Windows SDK 10.0.22621.0 first. See docs/GAME-BAR.md.' }
$msbuild = & $vswhere -latest -products * -requires Microsoft.Component.MSBuild -find 'MSBuild\**\Bin\MSBuild.exe' | Select-Object -First 1
if (-not $msbuild) { throw 'MSBuild was not found. Install the Visual Studio build workload described in docs/GAME-BAR.md.' }
& $msbuild '.\gamebar\SacredOverlay.csproj' /restore /p:Configuration=Debug /p:Platform=x64 /p:AppxPackageSigningEnabled=false /p:GenerateAppxPackageOnBuild=true
if ($LASTEXITCODE -ne 0) { throw 'Game Bar widget build failed. See the first build error above.' }
Write-Host 'Widget compiled. This does not verify Game Bar behavior or Fortnite compatibility.'
if ($Register) {
    $manifest = Join-Path $PSScriptRoot 'gamebar\bin\x64\Debug\AppX\AppxManifest.xml'
    if (-not (Test-Path $manifest)) { throw 'AppX layout was not found.' }
    # Developer Mode must be enabled by the user. This registers only this app.
    Add-AppxPackage -Register $manifest
    Write-Host 'Sacred Overlay registered. Follow docs/GAME-BAR.md to permit its local desktop connection.'
}

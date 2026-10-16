param([switch]$SkipSmokeTest)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if ($env:OS -ne 'Windows_NT') { throw 'Run this script on Windows 10 or 11.' }
if (-not (Test-Path '.venv\Scripts\python.exe')) { py -3.12 -m venv .venv }
$pythonExe = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
& $pythonExe -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw 'pip update failed' }
& $pythonExe -m pip install -r requirements-build.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed' }
& $pythonExe -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw 'Tests failed; packaging stopped' }
foreach ($app in @(@{Name='Sacred Tweaks'; Entry='member.py'}, @{Name='Sacred Tweaks Manager'; Entry='manager.py'})) {
    & $pythonExe -m PyInstaller --clean --noconfirm --onedir --windowed --name $app.Name --add-data 'web;web' --collect-all webview $app.Entry
    if ($LASTEXITCODE -ne 0) { throw "Packaging failed: $($app.Name)" }
    $destination = Join-Path 'dist' $app.Name
    $clientConfig = if (Test-Path 'client-config.json') { 'client-config.json' } else { 'client-config.example.json' }
    Copy-Item $clientConfig (Join-Path $destination 'client-config.json')
    $guide = if ($app.Entry -eq 'manager.py') { 'docs\OWNER-GUIDE.md' } else { 'docs\MEMBER-GUIDE.md' }
    Copy-Item $guide $destination
    if (-not $SkipSmokeTest) {
        $process = Start-Process -FilePath (Join-Path $destination "$($app.Name).exe") -ArgumentList '--smoke-test' -PassThru
        if (-not $process.WaitForExit(45000)) { $process.Kill(); throw "Launch timed out: $($app.Name)" }
        if ($process.ExitCode -ne 0) { throw "WebView2 launch failed: $($app.Name)" }
    }
    $archiveName = $app.Name.Replace(' ', '-') + '-Windows-x64.zip'
    Compress-Archive -Path $destination -DestinationPath (Join-Path 'dist' $archiveName) -Force
}
Write-Host 'Created two UNSIGNED portable Windows application packages in dist. Keep each .exe with its _internal folder.'

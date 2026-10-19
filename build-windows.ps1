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
    & $pythonExe -m PyInstaller --clean --noconfirm --onedir --windowed --name $app.Name --icon 'assets\sacred-app-icon.ico' --add-data 'assets;assets' --add-data 'web;web' --collect-all webview $app.Entry
    if ($LASTEXITCODE -ne 0) { throw "Packaging failed: $($app.Name)" }
    $destination = Join-Path 'dist' $app.Name
    $clientConfig = if (Test-Path 'client-config.json') { 'client-config.json' } else { 'client-config.example.json' }
    Copy-Item $clientConfig (Join-Path $destination 'client-config.json')
    $guide = if ($app.Entry -eq 'manager.py') { 'docs\OWNER-GUIDE.md' } else { 'docs\MEMBER-GUIDE.md' }
    Copy-Item $guide $destination
    Copy-Item 'LICENSE','THIRD-PARTY-NOTICES.md','docs\STANDALONE-OVERLAY.md' $destination
    $archiveName = $app.Name.Replace(' ', '-') + '-Windows-x64.zip'
    Compress-Archive -Path $destination -DestinationPath (Join-Path 'dist' $archiveName) -Force
}
# Single-file auto-updater for the member app only. The Manager stays a manual download.
$updaterConfig = if (Test-Path 'client-config.json') { 'client-config.json' } else { 'client-config.example.json' }
# Bundle it under the name the updater reads, whichever file it came from.
$stage = Join-Path 'build' 'updater-config'
New-Item -ItemType Directory -Force $stage | Out-Null
Copy-Item $updaterConfig (Join-Path $stage 'client-config.json') -Force
& $pythonExe -m PyInstaller --clean --noconfirm --onefile --windowed --name 'Sacred Tweaks Updater' --icon 'assets\sacred-app-icon.ico' --add-data "$(Join-Path $stage 'client-config.json');." --collect-submodules tkinter updater.py
if ($LASTEXITCODE -ne 0) { throw 'Packaging failed: updater' }
Set-Content -Path (Join-Path 'dist' 'Sacred Tweaks\sacred-version.txt') -Value (& $pythonExe -c "from desktop.bridge import VERSION; print(VERSION)")
$memberZip = Join-Path 'dist' 'Sacred-Tweaks-Windows-x64.zip'
Compress-Archive -Path (Join-Path 'dist' 'Sacred Tweaks') -DestinationPath $memberZip -Force
$hash = (Get-FileHash $memberZip -Algorithm SHA256).Hash.ToLower()
Set-Content -Path (Join-Path 'dist' 'Sacred-Tweaks-Windows-x64.sha256.txt') -Value $hash
Write-Host "Member package SHA-256 (paste into the Manager release): $hash"
if (-not $SkipSmokeTest) {
    foreach ($appName in @('Sacred Tweaks', 'Sacred Tweaks Manager')) {
        $process = Start-Process -FilePath (Join-Path (Join-Path 'dist' $appName) "$appName.exe") -ArgumentList '--smoke-test' -PassThru
        if (-not $process.WaitForExit(45000)) { $process.Kill(); throw "Both packages were built, but launch timed out: $appName" }
        if ($process.ExitCode -ne 0) { throw "Both packages were built, but WebView2 launch failed: $appName" }
    }
}
Write-Host 'Created two UNSIGNED portable Windows application packages in dist. Keep each .exe with its _internal folder.'

$ErrorActionPreference = "Stop"

$GladysRoot = Split-Path -Parent $PSScriptRoot
$RuneliteRoot = "C:\Projects\runelite"
$PluginSrc = Join-Path $GladysRoot "src\sensors\runescape\gladys"
$ResourceSrc = Join-Path $GladysRoot "src\sensors\runescape\resources"
$PluginDest = Join-Path $RuneliteRoot "runelite-client\src\main\java\net\runelite\client\plugins\gladys"
$ResourceDest = Join-Path $RuneliteRoot "runelite-client\src\main\resources\net\runelite\client\plugins\gladys"

Write-Host "=== GLADyS RuneLite Launcher ===" -ForegroundColor Green

# Copy plugin source files to RuneLite
Write-Host "Copying plugin files..." -ForegroundColor Yellow
if (Test-Path $PluginDest) {
    Remove-Item -Recurse -Force $PluginDest
}
Copy-Item -Recurse $PluginSrc $PluginDest

# Copy plugin resources (icons, etc.)
if (Test-Path $ResourceSrc) {
    if (Test-Path $ResourceDest) {
        Remove-Item -Recurse -Force $ResourceDest
    }
    New-Item -ItemType Directory -Path $ResourceDest -Force | Out-Null
    Copy-Item "$ResourceSrc\*" $ResourceDest
}

$fileCount = (Get-ChildItem $PluginDest -File).Count
Write-Host "  Copied $fileCount source files + resources to RuneLite" -ForegroundColor Gray

# Build RuneLite (shadow jar includes all dependencies)
Write-Host "Building RuneLite..." -ForegroundColor Yellow
Push-Location $RuneliteRoot
try {
    & .\gradlew.bat :client:shadowJar
    if ($LASTEXITCODE -ne 0) { throw "Build failed" }

    # Launch RuneLite
    Write-Host "Launching RuneLite..." -ForegroundColor Yellow
    $clientJar = Get-ChildItem "runelite-client\build\libs\*-shaded.jar" | Select-Object -First 1
    if (-not $clientJar) { throw "Could not find shaded client jar" }

    Write-Host "  Using $($clientJar.Name)" -ForegroundColor Gray
    & java -ea -jar $clientJar.FullName --developer-mode
} finally {
    Pop-Location
}

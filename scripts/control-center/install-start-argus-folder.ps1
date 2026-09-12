# Copy the simple after-restart folder onto the real Desktop and stamp the live build.
$ErrorActionPreference = "Stop"
. "$PSScriptRoot\_common.ps1"

$Root = Get-ArgusRoot
$Source = Join-Path $Root "start-argus"
$Desktop = Join-Path $env:USERPROFILE "Desktop"
if (-not (Test-Path $Desktop)) {
  New-Item -ItemType Directory -Force -Path $Desktop | Out-Null
}
$Dest = Join-Path $Desktop "Start Argus after restart"

if (-not (Test-Path $Source)) {
  throw "Missing start-argus folder at $Source"
}

$buildId = Get-ArgusLocalBuildId $Root
if (-not $buildId) { $buildId = "live-monitor-v2.96" }
Set-Content -Path (Join-Path $Source "BUILD.txt") -Value $buildId -Encoding ascii

if (-not (Test-Path $Dest)) {
  New-Item -ItemType Directory -Force -Path $Dest | Out-Null
}

Get-ChildItem -LiteralPath $Source -File | ForEach-Object {
  Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $Dest $_.Name) -Force
}

Get-ChildItem -LiteralPath $Dest -File | ForEach-Object {
  if ($_.Name -match '\.(txt|cmd)$') {
    $text = Get-Content -Raw -LiteralPath $_.FullName
    $updated = [regex]::Replace([string]$text, 'live-monitor-v[0-9]+\.[0-9]+', $buildId)
    if ($updated -ne $text) {
      Set-Content -Path $_.FullName -Value $updated -Encoding ascii
    }
  }
}

$Wsh = New-Object -ComObject WScript.Shell
$lnkPath = Join-Path $Desktop "Argus After Restart.lnk"
$oneClick = Join-Path $Dest "0-AFTER-RESTART-START-HERE.cmd"
$sc = $Wsh.CreateShortcut($lnkPath)
$sc.TargetPath = $oneClick
$sc.WorkingDirectory = $Dest
$sc.WindowStyle = 1
$sc.Description = "After a PC restart: Boot Argus ($buildId) without GitHub reset"
$sc.Save()

Write-Host ("After-restart folder: {0}" -f $Dest)
Write-Host ("Current Build:        {0}" -f $buildId)
Write-Host ("Desktop shortcut:     {0}" -f $lnkPath)

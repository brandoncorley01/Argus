# Local Windows notifications for Argus Control Center (Sprint 4).
# Prefer toast/balloon; always persist last alert under runtime/control-center.

function Show-ArgusNotification {
  param(
    [Parameter(Mandatory = $true)][string]$Title,
    [Parameter(Mandatory = $true)][string]$Message,
    [ValidateSet("info", "warning", "critical")][string]$Level = "warning"
  )

  $Root = if (Get-Command Get-ArgusRoot -ErrorAction SilentlyContinue) {
    Get-ArgusRoot
  } else {
    (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
  }
  $runtime = Join-Path $Root "runtime\control-center"
  if (-not (Test-Path $runtime)) {
    New-Item -ItemType Directory -Force -Path $runtime | Out-Null
  }
  $alertPath = Join-Path $runtime "last-alert.json"
  $payload = [ordered]@{
    title       = $Title
    message     = $Message
    level       = $Level
    occurred_at = (Get-Date).ToUniversalTime().ToString("o")
  }
  ($payload | ConvertTo-Json) | Set-Content -Path $alertPath -Encoding utf8

  Write-Host ("ALERT [{0}] {1}: {2}" -f $Level.ToUpperInvariant(), $Title, $Message)

  try {
    Add-Type -AssemblyName System.Windows.Forms -ErrorAction Stop
    Add-Type -AssemblyName System.Drawing -ErrorAction Stop
    $icon = New-Object System.Windows.Forms.NotifyIcon
    $icon.Icon = [System.Drawing.SystemIcons]::Warning
    if ($Level -eq "critical") {
      $icon.Icon = [System.Drawing.SystemIcons]::Error
      $tip = [System.Windows.Forms.ToolTipIcon]::Error
    } elseif ($Level -eq "info") {
      $icon.Icon = [System.Drawing.SystemIcons]::Information
      $tip = [System.Windows.Forms.ToolTipIcon]::Info
    } else {
      $tip = [System.Windows.Forms.ToolTipIcon]::Warning
    }
    $icon.Visible = $true
    $icon.BalloonTipTitle = $Title
    $icon.BalloonTipText = $Message
    $icon.BalloonTipIcon = $tip
    $icon.ShowBalloonTip(8000)
    Start-Sleep -Milliseconds 500
    $icon.Dispose()
  } catch {
    # Headless / no UI — file + console already recorded.
  }
}

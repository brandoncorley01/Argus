# Register a per-user scheduled task that recovers Argus when desired=Running.
# Idempotent. Does not require admin if registering under the current user.
$ErrorActionPreference = "Stop"
. "$PSScriptRoot\_common.ps1"

$Root = Get-ArgusRoot
$script = Join-Path $PSScriptRoot "keep-argus-alive.ps1"
$taskName = "ArgusKeepAlive"

if (-not (Test-Path $script)) {
  throw "Missing keep-argus-alive.ps1 at $script"
}

$action = New-ScheduledTaskAction `
  -Execute "powershell.exe" `
  -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$script`"" `
  -WorkingDirectory $Root

# At logon + every 2 minutes. Start the repeating trigger ~1 minute from now so
# Windows does not leave a midnight-based trigger "never run" until tomorrow.
$triggerLogon = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$triggerRepeat = New-ScheduledTaskTrigger -Once -At ((Get-Date).AddMinutes(1)) `
  -RepetitionInterval (New-TimeSpan -Minutes 2) `
  -RepetitionDuration (New-TimeSpan -Days 3650)

$settings = New-ScheduledTaskSettingsSet `
  -AllowStartIfOnBatteries `
  -DontStopIfGoingOnBatteries `
  -StartWhenAvailable `
  -MultipleInstances IgnoreNew `
  -ExecutionTimeLimit (New-TimeSpan -Minutes 5) `
  -RestartCount 3 `
  -RestartInterval (New-TimeSpan -Minutes 1)

$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask `
  -TaskName $taskName `
  -Action $action `
  -Trigger @($triggerLogon, $triggerRepeat) `
  -Settings $settings `
  -Principal $principal `
  -Description "Argus keepalive: restore Docker postgres/redis + local API/worker while desired state is Running. Paper only." `
  -Force | Out-Null

# Run once immediately so recovery does not wait for the first 2-minute tick.
try {
  Start-ScheduledTask -TaskName $taskName -ErrorAction Stop
  Write-Host "OK  Scheduled task '$taskName' registered and started once."
} catch {
  Write-Host "OK  Scheduled task '$taskName' registered (at logon + every 2 minutes)."
  Write-Host "WARN: could not start task immediately: $($_.Exception.Message)"
}
Write-Host "It only recovers when runtime\control-center\desired-state.json has running=true."

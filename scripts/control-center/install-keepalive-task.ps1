# Register a per-user scheduled task that recovers Argus when desired=Running.
# Idempotent. Does not require admin if registering under the current user.
# Uses run-hidden.vbs (window style 0) so PowerShell NEVER flashes on the desktop.
$ErrorActionPreference = "Stop"
. "$PSScriptRoot\_common.ps1"

$Root = Get-ArgusRoot
$script = Join-Path $PSScriptRoot "keep-argus-alive.ps1"
$launcher = Join-Path $PSScriptRoot "run-hidden.vbs"
$taskName = "ArgusKeepAlive"
$runtime = Get-ArgusRuntimeDir $Root
$log = Join-Path $runtime "keepalive-task.log"

if (-not (Test-Path $script)) {
  throw "Missing keep-argus-alive.ps1 at $script"
}
if (-not (Test-Path $launcher)) {
  throw "Missing run-hidden.vbs at $launcher"
}

# wscript //B = batch mode (no UI). run-hidden.vbs runs PowerShell with window style 0.
$arg = '//B //nologo "{0}" "{1}"' -f ($launcher -replace '"', '""'), ($script -replace '"', '""')

$action = New-ScheduledTaskAction `
  -Execute "wscript.exe" `
  -Argument $arg `
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
  -RestartInterval (New-TimeSpan -Minutes 1) `
  -Hidden

$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask `
  -TaskName $taskName `
  -Action $action `
  -Trigger @($triggerLogon, $triggerRepeat) `
  -Settings $settings `
  -Principal $principal `
  -Description "Argus keepalive (fully hidden via wscript): restore Docker postgres/redis + local API/worker while desired state is Running. Paper only. No PowerShell popups." `
  -Force | Out-Null

try {
  Start-ScheduledTask -TaskName $taskName -ErrorAction Stop
  Write-Host "OK  Scheduled task '$taskName' registered (fully hidden) and started once."
} catch {
  Write-Host "OK  Scheduled task '$taskName' registered fully hidden (at logon + every 2 minutes)."
  Write-Host "WARN: could not start task immediately: $($_.Exception.Message)"
}
Write-Host "It only recovers when runtime\control-center\desired-state.json has running=true."
Write-Host "Keepalive log: $log"
Write-Host "PowerShell windows must NOT appear from this task."

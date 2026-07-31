# Prevent Windows automatic sleep/hibernate while Argus is Running.
# Pulses SetThreadExecutionState so the host stays awake until Stop Argus
# (or the API/worker processes disappear). Display may still dim.
#
# Keep this file ASCII-only: it has no UTF-8 BOM, so Windows PowerShell 5.1
# decodes it as cp1252 and any non-ASCII byte can terminate a string early.
$ErrorActionPreference = "Continue"
. "$PSScriptRoot\_common.ps1"

$Root = Get-ArgusRoot
$runtime = Get-ArgusRuntimeDir $Root
$log = Join-Path $runtime "keep-awake.log"
$pidFile = Join-Path $runtime "keep-awake.pid"

function Write-KeepAwakeLog([string]$Message) {
  $line = "{0} {1}" -f (Get-Date).ToUniversalTime().ToString("o"), $Message
  Add-Content -Path $log -Value $line -Encoding utf8 -ErrorAction SilentlyContinue
}

Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public static class ArgusKeepAwake {
  public const uint ES_CONTINUOUS = 0x80000000;
  public const uint ES_SYSTEM_REQUIRED = 0x00000001;
  public const uint ES_AWAYMODE_REQUIRED = 0x00000040;

  [DllImport("kernel32.dll", CharSet = CharSet.Auto, SetLastError = true)]
  public static extern uint SetThreadExecutionState(uint esFlags);
}
"@ -ErrorAction Stop

function Clear-KeepAwakeRequest {
  [void][ArgusKeepAwake]::SetThreadExecutionState([ArgusKeepAwake]::ES_CONTINUOUS)
}

function Request-KeepAwake {
  $flags = [ArgusKeepAwake]::ES_CONTINUOUS -bor [ArgusKeepAwake]::ES_SYSTEM_REQUIRED -bor [ArgusKeepAwake]::ES_AWAYMODE_REQUIRED
  $result = [ArgusKeepAwake]::SetThreadExecutionState($flags)
  if ($result -eq 0) {
    # Away mode unsupported on some hosts - still block automatic sleep.
    $flags = [ArgusKeepAwake]::ES_CONTINUOUS -bor [ArgusKeepAwake]::ES_SYSTEM_REQUIRED
    [void][ArgusKeepAwake]::SetThreadExecutionState($flags)
  }
}

function Test-ArgusTradingAlive([string]$RootPath) {
  if (Test-ArgusWorkerFresh $RootPath) { return $true }
  if (Test-HttpOk (Get-ArgusApiReadyUrl) 2) { return $true }
  return $false
}

try {
  $PID | Set-Content -Path $pidFile -Encoding utf8
  Write-KeepAwakeLog "keep-awake started pid=$PID"
  Write-Host "Argus keep-awake active (prevents automatic sleep/hibernate while Running)."

  while ($true) {
    if (-not (Test-ArgusTradingAlive $Root)) {
      Write-KeepAwakeLog "Argus not alive - releasing keep-awake"
      break
    }
    Request-KeepAwake
    Start-Sleep -Seconds 30
  }
} catch {
  Write-KeepAwakeLog ("keep-awake error: {0}" -f $_.Exception.Message)
} finally {
  Clear-KeepAwakeRequest
  if (Test-Path $pidFile) {
    try {
      $stored = Get-Content -Path $pidFile -ErrorAction SilentlyContinue
      if ("$stored" -eq "$PID") {
        Remove-Item -Path $pidFile -Force -ErrorAction SilentlyContinue
      }
    } catch { }
  }
  Write-KeepAwakeLog "keep-awake stopped pid=$PID"
}

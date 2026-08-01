' Run a PowerShell .ps1 with NO console window.
' Usage:
'   wscript.exe //B //nologo run-hidden.vbs "C:\path\script.ps1" [extra args...]
' Window style 0 = completely hidden (Task Scheduler -WindowStyle Hidden still flashes).
' Waits for completion and returns the PowerShell exit code.
Option Explicit
If WScript.Arguments.Count < 1 Then
  WScript.Quit 1
End If

Dim sh, ps, script, args, i, cmd, exitCode, sysRoot
Set sh = CreateObject("WScript.Shell")
sysRoot = sh.ExpandEnvironmentStrings("%SystemRoot%")
ps = sysRoot & "\System32\WindowsPowerShell\v1.0\powershell.exe"
If CreateObject("Scripting.FileSystemObject").FileExists(ps) = False Then
  ps = "powershell.exe"
End If
script = WScript.Arguments(0)
args = "-NoProfile -NoLogo -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & script & """"
For i = 1 To WScript.Arguments.Count - 1
  args = args & " """ & Replace(WScript.Arguments(i), """", """""") & """"
Next
cmd = """" & ps & """ " & args
' 0 = hide window; True = wait for exit so Task Scheduler does not overlap runs
exitCode = sh.Run(cmd, 0, True)
WScript.Quit exitCode

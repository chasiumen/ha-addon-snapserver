' Supervises snapclient.exe on a Windows client.
'
' Why this exists: snapclient's WASAPI backend has no device-change handling.
' When Windows moves the default output (line-out -> headphones, a USB DAC
' appearing, etc.) the audio client is invalidated, wasapi_player.cpp throws
' from the player thread, and because that exception escapes the std::thread
' entry function it reaches std::terminate() -- the whole process aborts.
' There is no in-process recovery and no auto-switch option upstream.
'
' So the process is supervised from outside instead: WshShell.Run with
' bWaitOnReturn = True blocks for as long as snapclient is alive and returns the
' moment it dies, so the loop restarts it immediately. No polling needed.
'
' With SOUNDCARD left empty, each restart re-resolves the *current* default
' device via GetDefaultAudioEndpoint(), so changing the Windows output device
' effectively switches snapclient too -- at the cost of a few seconds of silence
' while it restarts.
'
' To stop it: end wscript.exe (and snapclient.exe) in Task Manager.

Option Explicit

Dim SNAPCLIENT, SERVER, SOUNDCARD, RESTART_DELAY_MS

SNAPCLIENT = "C:\Users\rymor\Downloads\snapclient_win64\snapclient.exe"
SERVER     = "ha.chasiumen.net"

' Empty = follow whatever Windows' default output device currently is.
' To pin one device instead, use its endpoint GUID from `snapclient.exe -l` --
' the GUID line, NOT the friendly name below it. -s matches against the GUID,
' and numeric indices are unstable because only active devices are enumerated.
' Example: SOUNDCARD = "{0.0.0.00000000}.{88299c40-4cc9-45df-80ce-5570d740ace9}"
SOUNDCARD = ""

RESTART_DELAY_MS = 3000

Dim WshShell, oExec, sOutput, sCmd

Set WshShell = CreateObject("WScript.Shell")

' Don't start a second supervisor if snapclient is already running.
Set oExec = WshShell.Exec("tasklist /FI ""IMAGENAME eq snapclient.exe"" /NH")
sOutput = oExec.StdOut.ReadAll
If InStr(sOutput, "snapclient.exe") <> 0 Then
    WScript.Quit
End If

sCmd = """" & SNAPCLIENT & """ -h " & SERVER
If Len(SOUNDCARD) > 0 Then
    sCmd = sCmd & " -s """ & SOUNDCARD & """"
End If

Do
    ' Blocks while snapclient runs; returns as soon as it exits or crashes.
    WshShell.Run sCmd, 0, True
    WScript.Sleep RESTART_DELAY_MS
Loop

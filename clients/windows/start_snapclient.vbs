Set WshShell = CreateObject("WScript.Shell")
Set oExec = WshShell.Exec("tasklist /FI ""IMAGENAME eq snapclient.exe"" /NH")
sOutput = oExec.StdOut.ReadAll
If InStr(sOutput, "snapclient.exe") = 0 Then
    'WshShell.Run """C:\Users\rymor\Downloads\snapclient_win64\snapclient.exe"" -h ha.chasiumen.net -s ""{0.0.0.00000000}.{88299c40-4cc9-45df-80ce-5570d740ace9}""", 0, False
    WshShell.Run """C:\Users\rymor\Downloads\snapclient_win64\snapclient.exe"" -h ha.chasiumen.net ", 0, False
End If

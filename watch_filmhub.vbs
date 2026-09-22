Option Explicit

Dim APP_DIR, PY, CHECK_SECONDS, sh, wmi
APP_DIR = "C:\Users\Micro Host\Desktop\FILMS"
PY = "C:\Users\Micro Host\AppData\Local\Programs\Python\Python314\python.exe"
CHECK_SECONDS = 10

Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = APP_DIR

Set wmi = GetObject("winmgmts:\\.\root\cimv2")
Dim n, procs, p
n = 0
Set procs = wmi.ExecQuery("SELECT ProcessId FROM Win32_Process WHERE Name='wscript.exe' AND CommandLine LIKE '%watch_filmhub.vbs%'")
For Each p In procs
    n = n + 1
Next
If n > 2 Then WScript.Quit

Function IsRunning()
    Dim procs, p
    IsRunning = False
    Set wmi = GetObject("winmgmts:\\.\root\cimv2")
    Set procs = wmi.ExecQuery( _
        "SELECT ProcessId FROM Win32_Process " & _
        "WHERE (Name='python.exe' OR Name='pythonw.exe') " & _
        "AND CommandLine LIKE '%run.py%'")
    For Each p In procs
        IsRunning = True
        Exit For
    Next
End Function

WScript.Sleep 2000

Do
    If Not IsRunning() Then
        sh.Run """" & PY & """ run.py", 0, False
    End If
    WScript.Sleep CHECK_SECONDS * 1000
Loop
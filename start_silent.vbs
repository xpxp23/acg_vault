' ============================================================================
' ACG Vault v3.2.0 - Zero-Flash Silent Desktop Launcher (VBScript)
' 双击此文件即可完全零 CMD 黑框静默启动 ACG Vault 原生桌面端与系统托盘
' ============================================================================
Option Explicit

Dim fso, shell, baseDir, exePath, venvPyw1, venvPyw2, cmd
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

baseDir = fso.GetParentFolderName(WScript.ScriptFullName)
shell.CurrentDirectory = baseDir

exePath = fso.BuildPath(baseDir, "ACGVault\ACGVault.exe")
venvPyw1 = fso.BuildPath(baseDir, ".venv\Scripts\pythonw.exe")
venvPyw2 = fso.BuildPath(baseDir, "venv\Scripts\pythonw.exe")

If fso.FileExists(exePath) Then
    cmd = """" & exePath & """"
ElseIf fso.FileExists(venvPyw1) Then
    cmd = """" & venvPyw1 & """ """ & fso.BuildPath(baseDir, "desktop_app.py") & """"
ElseIf fso.FileExists(venvPyw2) Then
    cmd = """" & venvPyw2 & """ """ & fso.BuildPath(baseDir, "desktop_app.py") & """"
Else
    cmd = "pythonw.exe """ & fso.BuildPath(baseDir, "desktop_app.py") & """"
End If

On Error Resume Next
shell.Run cmd, 0, False
If Err.Number <> 0 Then
    Err.Clear
    shell.Run "python.exe """ & fso.BuildPath(baseDir, "desktop_app.py") & """", 0, False
End If
On Error GoTo 0

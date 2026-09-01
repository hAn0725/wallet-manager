Option Explicit
Dim fso, shell, base, command, indexFile, code
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
base = fso.GetParentFolderName(WScript.ScriptFullName)

code = shell.Run("cmd /c where node >nul 2>nul", 0, True)
If code <> 0 Then
  MsgBox "Node.js is required to run Xiaozhangben.", 48, "Xiaozhangben"
  WScript.Quit
End If

indexFile = base & "\desktop-dist\index.html"
If Not fso.FileExists(indexFile) Then
  code = shell.Run("cmd /c cd /d """ & base & """ && npm run build:desktop", 1, True)
  If code <> 0 Or Not fso.FileExists(indexFile) Then
    MsgBox "Xiaozhangben build failed. Please check the project files.", 48, "Xiaozhangben"
    WScript.Quit
  End If
End If

command = "cmd /c cd /d """ & base & """ && node scripts\desktop-server.mjs"
shell.Run command, 0, False

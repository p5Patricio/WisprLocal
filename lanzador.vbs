Set WshShell = CreateObject("WScript.Shell")
' Cambia "patri" por tu usuario si es diferente
WshShell.Run "C:\Users\patri\Documents\WisprLocal\.venv\Scripts\pythonw.exe C:\Users\patri\Documents\WisprLocal\mvp_local.py", 0
Set WshShell = Nothing
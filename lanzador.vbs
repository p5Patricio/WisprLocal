Set WshShell = CreateObject("WScript.Shell")
' Cambia "Usuario" por tu usuario si es diferente
WshShell.Run "C:\Users\Usuario\Documents\WisprLocal\.venv\Scripts\pythonw.exe C:\Users\Usuario\Documents\WisprLocal\mvp_local.py", 0
Set WshShell = Nothing
@echo off
chcp 65001 >nul
rem  Тихий запуск RPCM-сервера: свёрнутое окно, без «нажмите Enter».
rem  Сервер: свёрнутая консоль «RPCM server» (python main.py).
rem  Стоп:   закрыть окно или taskkill /F /FI "WINDOWTITLE eq RPCM server"
cd /d "%~dp0"
start "RPCM server" /MIN python main.py

@echo off
chcp 65001 >nul
rem  Тихий запуск RPCM-сервера: без окна и без «нажмите Enter».
rem  pythonw start_background.py -> отсоединённый процесс (DETACHED_PROCESS),
rem  живёт после закрытия лаунчера; stdout/stderr -> server.out.log.
rem  PID:   server.pid
rem  Стоп:  taskkill /F /PID <pid>   (pid из server.pid)
rem         или через клиент — команда shutdown
cd /d "%~dp0"
start "RPCM server" /MIN python main.py

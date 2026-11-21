@echo off
rem  Запуск RPCM-сервера в фоновом (свёрнутом) окне.
rem  Чтобы остановить: закрыть окно или выполнить
rem      taskkill /F /FI "WINDOWTITLE eq RPCM server"
cd /d "%~dp0"
start "RPCM server" /MIN python main.py
echo Сервер запущен. Остановка: закрыть свёрнутое окно «RPCM server» или
echo     taskkill /F /FI "WINDOWTITLE eq RPCM server"
pause

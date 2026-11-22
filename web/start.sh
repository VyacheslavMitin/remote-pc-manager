#!/bin/sh
# Запускает веб-сервер (web/serve.py) на QNAP — по авторану или вручную.
#
# Использование (на NAS):
#   sh web/start.sh          # запустить (если уже работает — просто сообщит и выйдет)
#   sh web/start.sh restart  # перезапустить (обновление: после web/deploy.sh)
#
# Строка для /etc/config/autorun.sh:
#   /bin/sh /share/homes/sonic/remote-pc-web/web/start.sh
#
# QNAP: busybox без nohup — фоновый запуск через подшел (cmd &):
# подшел уходит, процесс переходит под init и переживает отключение SSH.
# python3.14 и git — в /opt/bin (не в дефолтном PATH).
ROOT="${RPCM_DEST:-/share/homes/sonic/remote-pc-web}"
PY="${RPCM_PY:-/opt/bin/python3.14}"
PORT="${RPCM_PORT:-8090}"
LOG="$ROOT/serve.log"

is_running() {
    # точное совпадение по полному пути — чтобы не путать с другими serve.py
    ps -ef | grep -F "$ROOT/web/serve.py" | grep -v grep >/dev/null 2>&1
}

# Режим «restart»: сначала убиваем старое.
# PID = первое числовое поле в строке: на QNAP (busybox) ps -ef начинает
# с PID («32143 sonic ...»), на macOS — с USER («sonic 32143 ...»),
# поэтому «awk '{print $2}'» корректен только на macOS и молча убивал
# «kill sonic» на NAS. Берём первый подряд идущий блок цифр.
if [ "${1:-}" = "restart" ]; then
    for p in $(ps -ef | grep -F "$ROOT/web/serve.py" | grep -v grep \
               | sed -n 's/^[^0-9]*\([0-9][0-9]*\).*/\1/p'); do
        kill "$p" 2>/dev/null || true
    done
    sleep 1
fi

# Уже работает — выходим (идемпотентность для autorun.sh)
if is_running; then
    echo "уже работает:"
    ps -ef | grep -F "$ROOT/web/serve.py" | grep -v grep
    exit 0
fi

( "$PY" "$ROOT/web/serve.py" --port "$PORT" >>"$LOG" 2>&1 </dev/null & )
sleep 1

if is_running; then
    echo "запущен: http://<NAS-IP>:$PORT/web/index.html"
    echo "лог: $LOG"
else
    echo "✗ не поднялся. Конец лога:" >&2
    tail -5 "$LOG" 2>/dev/null || true
    exit 1
fi

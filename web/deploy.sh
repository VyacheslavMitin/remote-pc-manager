#!/bin/sh
# Разворачивает/обновляет remote-pc-manager на QNAP: git clone/pull из GitHub
# + создаёт client/config.json из шаблона, если его нет.
#
# Запуск (на NAS, из shell):
#   sh web/deploy.sh
#
# QNAP: git живёт в /opt/bin (не в дефолтном PATH) — полный путь по умолчанию.
set -eu

GIT="${RPCM_GIT:-/opt/bin/git}"
REPO="${RPCM_REPO:-https://github.com/VyacheslavMitin/remote-pc-manager.git}"
DEST="${RPCM_DEST:-/share/homes/sonic/remote-pc-web}"

# Каталог существует, но это не git-репо (например, старая копия) — не топим его
if [ -e "$DEST" ] && [ ! -d "$DEST/.git" ]; then
    echo "✗ $DEST уже существует, но это не git-репозиторий." >&2
    echo "  Уберите/переименуйте его и запустите заново." >&2
    exit 1
fi

if [ -d "$DEST/.git" ]; then
    "$GIT" -C "$DEST" pull --ff-only
else
    "$GIT" clone --branch master "$REPO" "$DEST"
fi

# client/config.json в репо не лежит (.gitignore): создаём из шаблона, если нет.
# Реальные IP/MAC вписываются один раз; pull'ы этот файл не трогают (untracked).
if [ ! -f "$DEST/client/config.json" ]; then
    cp "$DEST/client/config.example.json" "$DEST/client/config.json"
    echo "⚠ Впишите реальные IP/MAC: $DEST/client/config.json"
fi

echo "OK: $DEST"

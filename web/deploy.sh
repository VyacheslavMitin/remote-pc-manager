#!/bin/sh
# Разворачивает/обновляет remote-pc-manager на QNAP: свежий master из GitHub
# (tarball через curl — git на QNAP не умеет https: нет git-remote-https).
# Обновление = скачать свежий tarball, заменить каталог; client/config.json
# переживает обновление.
#
# Использование (на NAS):
#   sh web/deploy.sh
#
# QNAP: curl — /sbin/curl, tar — busybox.
set -eu

REPO="${RPCM_REPO:-VyacheslavMitin/remote-pc-manager}"
BRANCH="${RPCM_BRANCH:-master}"
DEST="${RPCM_DEST:-/share/homes/sonic/remote-pc-web}"
CURL="${RPCM_CURL:-curl}"
URL="https://codeload.github.com/${REPO}/tar.gz/refs/heads/${BRANCH}"
TMP="${TMPDIR:-/tmp}"
TGZ="$TMP/rpcm-$$-download.tgz"
SRC="$TMP/${REPO##*/}-${BRANCH}"
CONF="$TMP/rpcm-$$-config.json"

# 1) Скачиваем. DEST трогаем только после успешной загрузки.
"$CURL" -sfL --connect-timeout 10 -m 300 "$URL" -o "$TGZ"

# 2) Распаковка (в /tmp, чтобы не зависеть от состояния DEST)
rm -rf "$SRC"
tar xzf "$TGZ" -C "$TMP"

# 3) Смена каталога, сохраняя client/config.json
if [ -f "$DEST/client/config.json" ]; then
    mv "$DEST/client/config.json" "$CONF"
fi
rm -rf "$DEST"
mv "$SRC" "$DEST"
if [ -f "$CONF" ]; then
    mv "$CONF" "$DEST/client/config.json"
fi

# 4) Если config.json всё же нет — создаём из шаблона
if [ ! -f "$DEST/client/config.json" ]; then
    cp "$DEST/client/config.example.json" "$DEST/client/config.json"
    echo "⚠ Впишите реальные IP/MAC: $DEST/client/config.json"
fi

rm -f "$TGZ"
echo "OK: $DEST"

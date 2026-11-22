#!/bin/bash
# Сборка .ipa для iOS-клиента remote-pc-manager.
# Результат: dist/RemotePC.ipa — устанавливается на айфон через AltServer.
#
# Использование:
#   ./build_ipa.sh            # собрать
#   ./build_ipa.sh clean      # удалить каталог сборки и собрать заново
set -euo pipefail
cd "$(dirname "$0")"

if [ "${1:-}" = "clean" ]; then
  rm -rf build
fi

xcodegen generate

SCHEME="RemotePC"
CONFIG="Release"

# Сборка: только arm64 (реальный iPhone), без симулятора — файл меньше.
# Подпись не ставим: AltServer переподпишет .ipa сертификатом Apple ID.
xcodebuild build \
  -project RemotePC.xcodeproj \
  -scheme "$SCHEME" \
  -configuration "$CONFIG" \
  -sdk iphoneos \
  -destination 'generic/platform=iOS' \
  CODE_SIGNING_ALLOWED=NO \
  -derivedDataPath build/ \
  | grep --color=always -E "error:|warning:|BUILD" || true

APP="build/Build/Products/$CONFIG-iphoneos/RemotePC.app"
if [ ! -d "$APP" ]; then
  echo "ОШИБКА: приложение не собрано: $APP"
  exit 1
fi

# Упаковка в .ipa (Payload/... — стандартный layout)
mkdir -p dist
rm -rf "dist/Payload" "dist/RemotePC.ipa"
mkdir -p "dist/Payload"
cp -R "$APP" "dist/Payload/"
( cd dist && zip -qry RemotePC.ipa Payload )

echo ""
echo "Готово: $(pwd)/dist/RemotePC.ipa"
echo "Установка: AltServer (Wi-Fi) → файл RemotePC.ipa → Install."
echo "Подпись: «Apple Development» 7 дней (AltServer переподписывает автоматически, Mac должен быть включён)."

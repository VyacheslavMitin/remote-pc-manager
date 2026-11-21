#!/bin/sh
# Собирает .app-бандл клиента: start/Remote-PC-Manager.app
# Запуск: sh start/build_app.sh
# Бандл содержит: Info.plist, иконку AppIcon.icns и sh-лаунчер,
# который запускает .venv/bin/python3 client/main.py.
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
APP="$HERE/Remote-PC-Manager.app"

rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"

cp "$HERE/AppIcon.icns" "$APP/Contents/Resources/AppIcon.icns"
printf 'APPL????' > "$APP/Contents/PkgInfo"

cat > "$APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
	<key>CFBundleName</key>
	<string>Remote PC Manager</string>
	<key>CFBundleDisplayName</key>
	<string>Управление удалённым ПК</string>
	<key>CFBundleExecutable</key>
	<string>Remote-PC-Manager</string>
	<key>CFBundleIdentifier</key>
	<string>local.remote-pc-manager</string>
	<key>CFBundleInfoDictionaryVersion</key>
	<string>6.0</string>
	<key>CFBundlePackageType</key>
	<string>APPL</string>
	<key>CFBundleShortVersionString</key>
	<string>1.0</string>
	<key>CFBundleVersion</key>
	<string>1</string>
	<key>CFBundleIconFile</key>
	<string>AppIcon</string>
	<key>LSMinimumSystemVersion</key>
	<string>12.0</string>
	<key>NSHighResolutionCapable</key>
	<true/>
</dict>
</plist>
PLIST

cat > "$APP/Contents/MacOS/Remote-PC-Manager" <<'SH'
#!/bin/sh
# Лаунчер клиента «Удалённый ПК — менеджер» (PySide6 GUI)
# Finder/launchd дают минимальный PATH — расширяем вручную.
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

# Корень проекта: <root>/start/Remote-PC-Manager.app/Contents/MacOS -> на 4 вверх
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
CLIENT_DIR="$APP_DIR/client"
LOG="$HOME/Library/Logs/remote-pc-manager.log"

cd "$CLIENT_DIR" || exit 1
exec "$APP_DIR/.venv/bin/python3" -u main.py >>"$LOG" 2>&1
SH
chmod +x "$APP/Contents/MacOS/Remote-PC-Manager"

echo "Готово: $APP"

# iOS/watch-клиент (iPhone + Apple Watch)

Нативное SwiftUI-приложение — порт десктопного PySide6-клиента (`client/`)
и веб-клиента (`web/`). Те же команды сервера (`POST /command`), та же тёмная тема
(цвета из `client/theme.py`). Есть два таргета: iPhone (`RemotePC`) и
Apple Watch-компаньон (`RemotePC-Watch`) — один Xcode-проект, общие модули
(AppModel, ConfigStore, Networking, Theme).

## Возможности
- Статус ПК: в сети / не отвечает (TCP-проверка порта сервера, как у веб-клиента),
  имя ПК, ОС, аптайм, RAM — из ответа `status`.
- Статус LM Studio: работает/не запущена, версия, модель, контекст, VRAM.
- «Пробудить ПК» — WoL magic packet. iOS не умеет UDP-broadcast (entitlement
  multicast — только платный аккаунт Apple), поэтому первичный путь — relay:
  `POST /wol` на веб-сервер (NAS), который сам шлёт broadcast (та же схема,
  что у веб-версии). Без relay — отправка напрямую (unicast, может не
  будить спящий ПК). Сборка пакета — порт `client/wol.py`.
- «Гибернация» — команда `hibernate`.
- «Включить/Выключить LM Studio» — `start_lmstudio` / `stop_lmstudio`.
- Автопроверка, пока приложение открыто (аналог авто-проверки десктопа;
  в фоне iOS не даёт).
- Настройки: IP, MAC, порт сервера, порт LM Studio, интервал автопроверки,
  WoL relay (адрес веб-сервера + токен X-Token).
  При смене порта LM Studio — сразу `set_lm_port` на сервер (как десктоп).

## Особенности
- Конфиг — в `UserDefaults` в общем контейнере App Group
  (`group.ru.vmitin.remotepc`): приложение на iPhone и на часах видят
  один и тот же конфиг (группа прописана в `RemotePC/RemotePC.entitlements`).
  Значения по умолчанию — стандартные (`client/config.py`), реальные задаются
  на экране настроек (⚙️ сверху справа).
- Plain HTTP в локальной сети разрешён через `NSAllowsLocalNetworking`
  (Info.plist генерируется из `project.yml`).
- Сборка только arm64 (под реальные устройства).

## Apple Watch (компаньон)
- Экран: статус «ПК — в сети/не в сети», «LM Studio — работает/не запущена»,
  действия «Пробудить» (WoL relay), «Гибернация», «LM вкл/выкл», ⚙️ настройки.
- Настройки общие с iPhone через App Group — вводить дважды не нужно
  (открой iOS-приложение хотя бы раз после обновления, чтобы конфиг
  смигрировал в общий контейнер). Экран настроек на часах есть — запасной.
- WoL — только через relay (broadcast на часах тоже невозможен).
- Авто-обновление статуса, пока приложение открыто.

```bash
# сборка watch-таргета (generic watchOS):
xcodebuild build -project RemotePC.xcodeproj -scheme RemotePC-Watch \
  -configuration Debug -sdk watchos -destination 'generic/platform=watchOS' \
  -allowProvisioningUpdates -derivedDataPath build/
# → build/Build/Products/Debug-watchos/RemotePC-Watch.app
# установка на часы (когда подключены):
xcrun devicectl list devices
xcrun devicectl device install app --device <UDID-часов> \
  build/Build/Products/Debug-watchos/RemotePC-Watch.app
xcrun devicectl device process launch --device <UDID-часов> ru.vmitin.remotepc.watch
```

## Сборка и установка (AltServer)
Требования: Xcode (установлен), `xcodegen` (`brew install xcodegen`),
AltServer на Mac и на айфоне, оба устройства в одной Wi-Fi-сети.

```bash
./build_ipa.sh          # → dist/RemotePC.ipa
```

Дальше: AltServer (Wi-Fi-режим) → выбрать `dist/RemotePC.ipa` → **Install**.
Подпись «Apple Development» живёт 7 дней — AltServer автоматически переподписывает,
пока Mac с AltServer включён.

## Пересоздать Xcode-проект
`project.yml` — источник правды (xcodegen):

```bash
xcodegen generate
```

## Структура
| Файл | Что |
|---|---|
| `RemotePC/RemotePCApp.swift` | точка входа (iOS) |
| `RemotePC/ContentView.swift` | главный экран (порт `client/app.py`) |
| `RemotePC/SettingsView.swift` | настройки (порт `client/settings_dialog.py`) |
| `RemotePC/AppModel.swift` | логика: проверки, действия, автопроверка |
| `RemotePC/ConfigStore.swift` | настройки (аналог `client/config.py`, UserDefaults + App Group) |
| `RemotePC/RemotePC.entitlements` | App Group `group.ru.vmitin.remotepc` (общие настройки iPhone↔watch) |
| `RemotePC/Networking/ApiClient.swift` | `POST /command` (порт `client/server_api.py`) |
| `RemotePC/Networking/WoL.swift` | magic packet (порт `client/wol.py`) |
| `RemotePC/Networking/WoLRelay.swift` | WoL через relay (`POST /wol` на веб-сервер) |
| `RemotePC/Networking/NetCheck.swift` | «ПК в сети?» (TCP-проверка) |
| `RemotePC/Theme.swift` | цвета из `client/theme.py` |
| `RemotePC/Formatters.swift` | аптайм/VRAM/контекст/версии (как в `app.py`) |
| `Watch/WatchApp.swift` | точка входа (watchOS) |
| `Watch/WatchRootView.swift` | главный экран часов |
| `Watch/WatchModel.swift` | логика часов (тот же API, WoL relay) |
| `Watch/WatchSettingsView.swift` | настройки часов (запасной путь) |

## Коммиты
Префикс — `Клиент iOS: …` (см. README в корне).

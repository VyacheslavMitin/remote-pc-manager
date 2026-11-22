# iOS-клиент (iPhone)

Нативное SwiftUI-приложение — порт десктопного PySide6-клиента (`client/`)
и веб-клиента (`web/`). Те же команды сервера (`POST /command`), та же тёмная тема
(цвета из `client/theme.py`).

## Возможности
- Статус ПК: в сети / не отвечает (TCP-проверка порта сервера, как у веб-клиента),
  имя ПК, ОС, аптайм, RAM — из ответа `status`.
- Статус LM Studio: работает/не запущена, версия, модель, контекст, VRAM.
- «Пробудить ПК» — WoL magic packet напрямую с айфона (UDP broadcast,
  порт `client/wol.py`; Mac-реле не нужен).
- «Гибернация» — команда `hibernate`.
- «Включить/Выключить LM Studio» — `start_lmstudio` / `stop_lmstudio`.
- Автопроверка, пока приложение открыто (аналог авто-проверки десктопа;
  в фоне iOS не даёт).
- Настройки: IP, MAC, порт сервера, порт LM Studio, интервал автопроверки.
  При смене порта LM Studio — сразу `set_lm_port` на сервер (как десктоп).

## Особенности iOS
- Конфиг — в `UserDefaults` (iOS не читает `client/config.json`).
  Значения по умолчанию — стандартные (`client/config.py`), реальные задаются
  на экране настроек (⚙️ сверху справа).
- Plain HTTP в локальной сети разрешён через `NSAllowsLocalNetworking`
  (Info.plist генерируется из `project.yml`).
- Сборка только arm64 (под реальный iPhone).

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
| `RemotePC/RemotePCApp.swift` | точка входа |
| `RemotePC/ContentView.swift` | главный экран (порт `client/app.py`) |
| `RemotePC/SettingsView.swift` | настройки (порт `client/settings_dialog.py`) |
| `RemotePC/AppModel.swift` | логика: проверки, действия, автопроверка |
| `RemotePC/ConfigStore.swift` | настройки (аналог `client/config.py`, UserDefaults) |
| `RemotePC/Networking/ApiClient.swift` | `POST /command` (порт `client/server_api.py`) |
| `RemotePC/Networking/WoL.swift` | magic packet (порт `client/wol.py`) |
| `RemotePC/Networking/NetCheck.swift` | «ПК в сети?» (TCP-проверка) |
| `RemotePC/Theme.swift` | цвета из `client/theme.py` |
| `RemotePC/Formatters.swift` | аптайм/VRAM/контекст/версии (как в `app.py`) |

## Коммиты
Префикс — `Клиент iOS: …` (см. README в корне).

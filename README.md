# Удалённый ПК — менеджер (клиент + сервер)

Кроссплатформенный менеджер удалённого ПК:

- **Клиент** — GUI на **PySide6**, тёмная тема. Работает на **macOS / Windows 11 / Linux**
  (основной сценарий — запуск на macOS).
- **Сервер** — фоновый HTTP-сервер на **Windows 11** (только стандартная библиотека Python),
  который выполняет команды: статус, гибернация, включение/выключение LM Studio.

Связь — по локальной сети (LAN), **без авторизации**. Клиент (macOS) → сервер (Windows).

```
┌────────────────────────┐   HTTP (LAN, без авторизации)   ┌────────────────────────┐
│  КЛИЕНТ  (PySide6)     │ ───────────────────────────────► │  СЕРВЕР  (stdlib http) │
│  macOS / Win11 / Linux │ ◄─────────────────────────────── │  Windows 11            │
│  • Пробудить ПК (WoL)  │   JSON  {"ok":true, ...}         │  • status              │
│  • Статус ПК (ping)    │                                  │  • hibernate           │
│  • сервер = тот же ПК  │   WoL — magic packet (UDP:9)     │  • start_lmstudio      │
│  • Гибернация          │ ───────────────────────────────► │  • stop_lmstudio       │
│  • Вкл/Выкл LM Studio  │   (сидит отдельно, будит NIC)    │                        │
│  • Настройки (JSON)    │                                  │                        │
└────────────────────────┘                                  └────────────────────────┘
```

---

## Структура репозитория

```
remote-pc-manager/
├── README.md
├── client/                     # GUI-клиент (PySide6)
│   ├── main.py                 #   точка входа: python main.py
│   ├── app.py                  #   главное окно: кнопки, 2 индикатора (ПК, LM Studio), автопроверка (интервал из настроек), статус
│   ├── theme.py                #   тёмная тема (Fusion + палитра + QSS)
│   ├── settings_dialog.py      #   диалог настроек (IP, MAC, порт, автопроверка)
│   ├── wol.py                  #   Wake-on-LAN: magic packet + валидация MAC
│   ├── netcheck.py             #   ping-проверка IP (кроссплатформенно)
│   ├── server_api.py           #   HTTP-запросы к серверу (stdlib urllib)
│   ├── worker.py               #   QThread-worker (фоновые вызовы, не блокирует GUI)
│   ├── config.py               #   загрузка/сохранение настроек (JSON)
│   ├── config.example.json     #   пример настроек
│   └── requirements.txt        #   PySide6>=6.6
├── server/                     # HTTP-сервер (только stdlib, без зависимостей)
    ├── main.py                 #   точка входа: python main.py
    ├── server.py               #   ThreadingHTTPServer + обработчик
    ├── commands.py             #   диспетчер команд
    ├── lmstudio.py             #   is_running / start / stop / version / loaded_model / loaded_context
    ├── hibernate.py            #   гибернация (в фоне, после отправки ответа)
    ├── config.py               #   загрузка конфигурации (JSON)
    ├── log.py                  #   лог в файл + консоль
    ├── config.example.json     #   пример конфигурации
    ├── start_background.py     #   запуск в фоне (Windows DETACHED / unix session)
    ├── start_server.bat        #   запуск в минимизированном окне (Windows)
    └── requirements.txt        #   только стандартная библиотека
├── start/                      # macOS: .app-лаунчер клиента
│   ├── AppIcon.icns            #   иконка приложения
│   └── build_app.sh            #   сборка start/Remote-PC-Manager.app
└── web/                        # веб-интерфейс (браузер)
    ├── index.html              #   тот же интерфейс/элементы/тема, что у PySide-GUI;
    │                           #   команды — в реальный сервер на ПК
    ├── favicon.png             #   favicon (из start/AppIcon.icns, 64×64)
    ├── apple-touch-icon.png    #   иконка для «Добавить на главный экран» айфона (180×180)
    └── serve.py                #   локальный HTTP-сервер: страница + config.json (для айфона)
                                #   + POST /wol — мак будит ПК magic packet'ом (client/wol.py)
```

Код **кроссплатформенный**: пути, имена процессов и способы остановки/запуска
выбираются в зависимости от ОС (`platform.system()`). Всё настраивается в JSON-конфигах.

---

## Веб-интерфейс (браузер)

`web/index.html` — самодостаточная HTML-страница (без сборки, без зависимостей),
которая повторяет интерфейс PySide-клиента: те же блоки «ПК» и «LM Studio»,
индикаторы-точки, кнопки (Пробудить ПК, Гибернация, Вкл/Выкл LM Studio),
динамические заголовки («ПК (имя, ОС, аптайм, 37 ГБ)», «LM Studio (0.4.28, модель, контекст, 16 ГБ)»; в заголовке «Windows 11» сокращается до «Win 11», версия LM Studio кропится с обоих концов — «v0.4.28.0» → «0.4.28», RAM/VRAM — только занятое в целых ГБ),
автопроверка с интервалом, строка статуса и IP, диалог настроек.
Оформление — та же тёмная тема (цвета из `client/theme.py`).

### Запуск

Раздаёт `web/serve.py` (простой stdlib-сервер на корне проекта, чтобы страница
могла подтянуть `client/config.json`):

```bash
python3 web/serve.py              # порт по умолчанию 8080
python3 web/serve.py --port 9000  # свой порт
```

Скрипт печатает две ссылки:
- **этот компьютер**: `http://127.0.0.1:8080/web/index.html`
- **из сети (айфон и пр., тот же Wi-Fi)**: `http://<IP-мака>:8080/web/index.html`

Можно и просто открыть `web/index.html` (двойной клик, `file://`) — интерфейс
работает, но браузер запрещает fetch локального `config.json`, поэтому IP/порты
придётся ввести в настройках вручную (один раз, дальше хранятся в localStorage).

Настройки страницы загружаются в порядке: **localStorage → `client/config.json` → дефолты**,
т.е. те же значения, что у desktop-клиента; реальные IP/порты живут в `config.json`,
не в коде.

### Токен-защита (для вывода в интернет)

Страница умеет выключать/перезагружать ПК, поэтому наружу её открывать без
защиты нельзя. Включается ключом в `client/config.json`:

```json
{ "web_token": "c4e458d5..." }
```

- **`web_token` задан** — без токена сервер отдаёт страницу входа
  (`POST /login`, потом cookie `rpcm_token`), `/client/config.json` и `/wol`
  отвечают `401`. Токен принимается в cookie, заголовке `X-Token` или
  `?token=...`.
- **`web_token` пустой** (или ключа нет) — защита выключена, работает как
  раньше (для доверенной LAN).

Токен можно сгенерировать: `openssl rand -hex 24`.

Команды уходят в реальный сервер на ПК
(`GET http://<IP>:<порт>/status`, `POST /command`) — IP/порт подтягиваются из
`config.json` или задаются в диалоге настроек (как в desktop-клиенте).
Без запущенного сервера на ПК все проверки будут показывать «недоступен».

Ограничения браузера (в отличие от desktop-клиента):

- **ping** недоступен (нет ICMP): «жив ли ПК» определяется по HTTP-доступности
  сервера (он стоит на той же машине).
- **WoL (magic packet)** — UDP broadcast, браузер не может отправить его сам.
  Кнопка «Пробудить ПК» делает `POST /wol` на `serve.py` (мак), а мак
  (всегда включён) отправляет magic packet — та же логика, что в `client/wol.py`.
  Важно: WoL надёжно будит из **сна (S3)**; из **гибернации (S4)** это
  поддерживают не все сетевые карты/BIOS.

CORS не мешает: `server/server.py` во всех ответах шлёт
`Access-Control-Allow-Origin: *` (+ OPTIONS-preflight), поэтому всё работает
даже когда страница раздана с другой машины (айфон → сервер на маке →
Windows-сервер).

---

## Сервер (Windows 11)

### Требования
- **Python 3.10+** (проверено на 3.13). Внешних зависимостей **нет** — только stdlib.
- Windows 11 (целевая ОС). Код также работает на macOS/Linux для разработки.

### Установка
```bat
cd server
:: зависимости не нужны — только стандартная библиотека
python -m venv .venv        :: опционально
.venv\Scripts\activate
```

### Конфигурация
Скопируйте пример и заполните под себя:
```bat
copy config.example.json config.json
```
`config.json`:
```json
{
  "host": "0.0.0.0",
  "port": 8787,
  "lmstudio": {
    "exe": "C:\\Users\\YOURUSER\\AppData\\Local\\Programs\\LM Studio\\LM Studio.exe",
    "process_name": "LM Studio.exe",
    "api_port": 1234
  },
  "hibernate": {
    "method": "rundll32",
    "delay_s": 1.0
  },
  "log_file": "server.log",
  "log_level": "INFO"
}
```

| Поле | Описание |
|---|---|
| `host` / `port` | Адрес и порт прослушивания. `0.0.0.0` — доступен по LAN. |
| `lmstudio.exe` | Полный путь к `LM Studio.exe` (Windows). Пусто → будет запущено по имени процесса. |
| `lmstudio.process_name` | Имя процесса для проверки/остановки: `LM Studio.exe`. |
| `lmstudio.api_port` | Порт локального API-сервера LM Studio (загруженные модели, `GET /v1/models`). Стандарт LM Studio — 1234. |
| `hibernate.method` | `rundll32` (`rundll32.exe powrprof.dll,SetSuspendState 0,1,0`) или `shutdown` (`shutdown /h /f`). |
| `hibernate.delay_s` | Пауза (сек) до гибернации — чтобы HTTP-ответ успел уйти клиенту. |
| `log_file` | Файл лога команд (рядом с `main.py`). |
| `log_level` | `DEBUG` / `INFO` / `WARNING`. |

> **macOS/Linux (dev/test):** для `lmstudio.exe` укажите путь к бинарнику/скрипту,
> либо оставьте пустым — тогда запуск по имени через `open -a` / поиск процесса,
> а остановка сначала аккуратная (`osascript quit` на macOS / SIGTERM),
> затем принудительная (SIGKILL), если приложение не завершилось. Гибернация
> на Unix — `pmset sleepnow` (только для проверки кода; на Windows используйте
> `rundll32`/`shutdown`).

### Запуск

**В консоли (foreground, виден вывод):**
```bat
cd server
python main.py
```

**В фоне / в минимизированном окне (Windows):**
```bat
:: вариант 1 — минимизированное окно
start_server.bat

:: вариант 2 — полностью в фоне (DETACHED), печатает PID
python start_background.py
```

**Остановка (Windows):**
```bat
:: если запускали через start_server.bat:
taskkill /F /FI "WINDOWTITLE eq RPCM server"
:: либо по порту:
for /f "tokens=5" %a in ('netstat -ano ^| findstr :8787') do taskkill /F /PID %a
```

### Проверка из другой машины (curl)

```bash
# базовый статус (удобно в браузере)
curl http://<IP_Винды>:8787/

# состояние (в т.ч. запущена ли LM Studio)
curl http://<IP_Винды>:8787/status

# команды
curl -X POST http://<IP_Винды>:8787/command -H "Content-Type: application/json" \
     -d '{"command":"status"}'
curl -X POST http://<IP_Винды>:8787/command -H "Content-Type: application/json" \
     -d '{"command":"start_lmstudio"}'
curl -X POST http://<IP_Винды>:8787/command -H "Content-Type: application/json" \
     -d '{"command":"stop_lmstudio"}'
curl -X POST http://<IP_Винды>:8787/command -H "Content-Type: application/json" \
     -d '{"command":"hibernate"}'   # ⚠ машина погаснет после ответа!
```

### API

| Метод | Путь | Тело | Ответ |
|---|---|---|---|
| `GET` | `/` | — | `{"ok": true, "service": "rpcm-server"}` |
| `GET` | `/status` | — | `{"ok": true, "command": "status", "lmstudio_running": true, "lmstudio_version": "0.3.25", "lmstudio_model": "qwen2.5-7b-instruct", "lmstudio_context": 65536, "lmstudio_vram_mb": 16384, "ram_used_mb": 18841, "ram_total_mb": 32768, "pc_name": "DESKTOP-ABC123", "os_name": "Windows 11", "uptime_s": 123456}` |
| `POST` | `/command` | `{"command": "<имя>"}` | см. ниже |

**Команды** (`POST /command`):

| Команда | Ответ |
|---|---|
| `status` | `{"ok": true, "command": "status", "lmstudio_running": bool, "lmstudio_version": str\|null, "lmstudio_model": str\|null, "lmstudio_context": int\|null, "lmstudio_vram_mb": int\|null, "ram_used_mb": int\|null, "ram_total_mb": int\|null, "pc_name": str, "os_name": str, "uptime_s": int\|null}` — сам ответ подтверждает доступность сервера; `pc_name` — имя ПК (hostname), `os_name` — ОС сервера (напр. «Windows 11»), `uptime_s` — секунд с момента запуска системы; `lmstudio_version` — версия установленной LM Studio (`VersionInfo.ProductVersion` exe, кэшируется сервером до смены mtime файла); `lmstudio_model` — id основной загруженной модели (если моделей несколько — первая в списке; напр. embedding-модели в заголовок не попадают) (локальный API-сервер LM Studio, `GET http://127.0.0.1:<api_port>/v1/models`; `null`, если API не запущен или моделей нет); `lmstudio_context` — контекст загруженной модели в токенах (`GET http://127.0.0.1:<api_port>/api/v0/models`, у модели с `state == "loaded"` — `loaded_context_length`; фолбэк `GET /v1/models` → `loaded_instances[].config.context_length`; `null`, если API недоступен, модель не загружена или контекст не прислан); `lmstudio_vram_mb` — VRAM загруженной модели (самый крупный процесс на GPU) в МБ (PowerShell `Get-Counter '\GPU Process Memory(*)\Dedicated Usage'`, максимум по процессам; `null`, если LM Studio не запущена, модель не загружена (нет контекста — `/v1/models` отдаёт каталог скачанных моделей даже без загруженной) или PowerShell/счётчик недоступны — клиент не показывает VRAM); `ram_used_mb` / `ram_total_mb` — занято/всего физическая память в МБ (Windows: `GlobalMemoryStatusEx`, Linux: `/proc/meminfo`, macOS: `vm_stat` + `sysctl`; `null`, если прочитать не удалось; в заголовке показывается только занятое) — клиент дописывает в заголовки блоков («LM Studio (0.3.25, qwen2.5-7b-instruct, 64K, 16 ГБ)», «ПК (DESKTOP-ABC123, Win 11, 3 ч 14 мин, 18 ГБ)»; 65536 токенов → «64K», МБ → целые ГБ, напр. «16 ГБ»); если версия/модель/контекст/VRAM/RAM неизвестны, эти части заголовка отсутствуют (просто «LM Studio» / «ПК (имя, ОС, аптайм)»). Аптайм форматируется без секунд («3 ч 14 мин»). |
| `hibernate` | `{"ok": true, "command": "hibernate", "note": "гибернация запущена"}` — ответ уходит, **потом** машина уходит в гибернацию. |
| `start_lmstudio` | `{"ok": true, "command": "start_lmstudio", "pid": int, "exe": "..."}` |
| `stop_lmstudio` | `{"ok": true, "command": "stop_lmstudio", "killed": "LM Studio.exe"}` (или `"killed": null` + `note`, если не было запущено) |
| `set_lm_port` | тело `{"command": "set_lm_port", "port": 5555}` → `{"ok": true, "command": "set_lm_port", "lmstudio_api_port": 5555}` — задаёт `lmstudio.api_port` и сразу сохраняет в `config.json` сервера; порт должен быть числом 1–65535. Клиент шлёт сам после сохранения настроек (⚙). |

Ошибки: `{"ok": false, "error": "..."}` с HTTP `400` (плохое тело / неизвестная команда)
или `404` (неизвестный путь).

**Лог** — все команды пишутся в `server.log` (путь из `log_file`), формат:
`2026-11-21 12:00:00,000  INFO   server: 192.168.1.50 "POST /command" status`.

---

## Клиент (macOS / Windows 11 / Linux)

### Требования
- **Python 3.10+** (проверено на 3.13).
- **PySide6** — единственная зависимость.

### Установка
```bash
cd client
python -m venv .venv
# macOS / Linux:
source .venv/bin/activate
# Windows:
.venv\Scripts\activate

pip install -r requirements.txt
```

### Конфигурация
Настройки хранятся в `client/config.json` (рядом с `main.py`). При первом запуске
создаётся из значений по умолчанию. Скопировать пример вручную:
```bash
cp config.example.json config.json
```
`config.json`:
```json
{
  "pc": { "ip": "192.168.1.100", "mac": "AA:BB:CC:DD:EE:FF" },
  "server": { "port": 8787 },
  "lmstudio": { "api_port": 1234 },
  "auto_check": { "enabled": true, "interval_s": 10 }
}
```

| Поле | Описание |
|---|---|
| `pc.ip` | IP управляемого ПК (для пинга **и** хост сервера — это одна машина). |
| `pc.mac` | MAC-адрес сетевой карты (для Wake-on-LAN). Формат `AA:BB:CC:DD:EE:FF`. |
| `server.port` | Порт сервера (по умолчанию `8787`). Хост сервера = `pc.ip`. |
| `lmstudio.api_port` | Порт локального API-сервера LM Studio (по умолчанию `1234`). После сохранения настроек клиент посылает его на сервер командой `set_lm_port` — сервер использует его для чтения загруженной модели. |
| `auto_check.enabled` | Автопроверка состояния: вкл/выкл (по умолчанию вкл). |
| `auto_check.interval_s` | Интервал автопроверки, в секундах (по умолчанию `10`). |

> MAC и IP можно задать и **в GUI**: кнопка **⚙ Настройки**. MAC принимается в любом
> виде (`AA:BB:…`, `aa-bb-…`, `aabb.ccdd.eeff`, `AABBCCDDEEFF`).
> Отдельного «IP сервера» нет — сервер и ПК это одна машина, сервер достаётся
> по `pc.ip` и `server.port`.

### Запуск
```bash
# macOS / Linux
python main.py

# Windows
.venv\Scripts\python main.py
```

**macOS: запуск через .app (иконка в Dock/Finder)**

Клиент можно запускать как обычное macOS-приложение: двойной клик по
`start/Remote-PC-Manager.app` (или перетащите его в Dock). Лаунчер внутри
бандла запускает `.venv/bin/python3 client/main.py`; конфиг читается из
`client/config.json` независимо от рабочего каталога.

```bash
sh start/build_app.sh   # собрать/пересобрать .app-бандл
```

Лог запуска через .app пишется в `~/Library/Logs/remote-pc-manager.log`.

### Использование (раскладка)

| Элемент | Что делает |
|---|---|
| **⏻ Пробудить ПК** | Шлёт magic packet (UDP broadcast `255.255.255.255:9`, ×3) по MAC (tooltip: Wake-on-LAN). |
| **🌙 Гибернация** | Команда `hibernate` серверу (машина погаснет). |
| **Статус ПК** + *Проверить* | 🟡 проверка / 🟢 в сети / 🔴 не отвечает — ping по `pc.ip` (единственный индикатор «машина жива» — сервер на той же машине). |
| **▶ Включить LM Studio** | Команда `start_lmstudio`. |
| **⏹ Выключить LM Studio** | Команда `stop_lmstudio`. |
| **Состояние LM Studio** + *Проверить состояние* | 🟡 проверка / 🟢 запущена / 🔴 не запущена — состояние показывает индикатор; заголовок блока — версия, модель и контекст модели, занятая память GPU (VRAM) («LM Studio (0.3.25, qwen2.5-7b-instruct, 64K, 16 ГБ)»), при простое — просто «LM Studio». |
| **⚙ (верхний правый угол, только значок)** | Диалог настроек: IP, MAC, порт сервера, порт API LM Studio, автопроверка (вкл/выкл, интервал в секундах) → сохранение в `config.json` (порт LM Studio дополнительно применяется на сервере через `set_lm_port`). |
| **IP в правом нижнем углу** | IP управляемого ПК из настроек — на одной строке со строкой статуса (статус слева, IP справа); обновляется после сохранения настроек. |

Кнопки «пробуждение + гибернация» и «включить/выключить LM Studio» стоят
по две в одной строке — окно компактное по вертикали.

Все сетевые/блокирующие действия выполняются в фоновом потоке (`QThread`),
GUI не «зависает». Ошибки показываются в строке статуса снизу (красным).

### Автопроверка

Клиент **сам опрашивает всё, что проверяется, каждые N секунд** (N задаётся в
настройках, по умолчанию 10; включена/выключена — тоже из настроек):

- **Статус ПК** — ping по `pc.ip` (единственный индикатор «машина жива» —
  сервер работает на той же машине, отдельного индикатора «сервер» нет);
- **LM Studio** — один `status`-запрос к серверу (хост = `pc.ip`)
  (из него заполняется индикатор: 🟢 запущена / 🔴 не запущена, а заголовок
  блока — версия LM Studio на ПК, загруженная модель и её контекст,
  занятая память GPU (VRAM):
  «LM Studio (0.3.25, qwen2.5-7b-instruct, 64K, 16 ГБ)»; модель —
  первый id из списка
  локального API-сервера LM Studio (`GET /v1/models`), контекст — у модели
  с `state == "loaded"` (`GET /api/v0/models`, `loaded_context_length`),
  VRAM — самый крупный процесс на GPU (PowerShell
  `Get-Counter '\GPU Process Memory(*)\Dedicated Usage'` — это и есть
  загруженная модель),
  порт —
  из конфига `lmstudio.api_port`).
  Если сервер недоступен, LM Studio показывается ⚪ «нет данных» —
  без лишнего второго запроса.

Включение и интервал настраиваются только в **⚙ Настройки** (чекбокс
«Автопроверка состояния» + поле «Интервал проверки», в секундах).
Пока проверка идёт, индикатор соответствующей строки — **жёлтый** 🟡.
Ручные кнопки **Проверить** работают как раньше — их можно жать в
любой момент, даже когда автопроверка включена (в этот момент таймер просто
пропускает тик, чтобы не дублировать запросы).

---

## Wake-on-LAN: чтобы ПК реально просыпался

Magic packet лишь будит сетевую карту; чтобы ПК действительно включился:

1. **BIOS/UEFI:** включено `Wake on LAN` / `Power On By PCI-E / PME` для сетевой карты.
2. **Сетевая карта** должна получать питание в выключенном состоянии (`ErP/EuP` — **выключить**).
3. Клиент и ПК — в **одной L2-сети** (broadcast доходит). Без одного роутера/коммутатора
   не сработает.
4. Обычно WoL не будит ПК из **гибернации** (только из сна/выключенного) — проверяйте
   сценарий, который вам нужен.
5. IP/MAC должны соответствовать сетевой карте, у которой включён WoL.

---

## Быстрый прогон «всё с нуля»

**1) Сервер (Windows 11):**
```bat
cd server
copy config.example.json config.json      :: впишите exe / process_name
python main.py
```

**2) Проверка (с macOS/любой машины):**
```bash
curl http://<IP_Винды>:8787/status
# -> {"ok": true, "command": "status", "lmstudio_running": false, "lmstudio_version": "0.3.25", "lmstudio_model": null, "lmstudio_context": null, "pc_name": "DESKTOP-ABC123", "os_name": "Windows 11", "uptime_s": 123456}
```

**3) Клиент (macOS):**
```bash
cd client
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python main.py
```
В GUI: **⚙ Настройки** → впишите IP/MAC ПК и хост/порт сервера → **Сохранить**.
Дальше — кнопки **Проверить**, **Пробудить ПК**, **Включить/Выключить LM Studio**.

---

## Диагностика

| Симптом | Где искать |
|---|---|
| Клиент: «сервер не отвечает» | Сервер запущен? Правильный хост/порт? Файрвол Windows пропускает порт? |
| `status` приходит, но LM Studio не гаснет | `lmstudio.process_name` совпадает с реальным именем (`tasklist`)? |
| WoL не будит | BIOS WoL включён? Одна L2-сеть? MAC верный? |
| Гибернация не срабатывает | `hibernate.method`? Гибернация включена в настройках электропитания Windows? |
| Логи команд | `server/server.log` (путь из `log_file`). |

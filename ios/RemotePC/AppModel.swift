import SwiftUI
import Foundation

/// Логика главного экрана: проверки, WoL, гибернация, LM Studio, Strata,
/// автопроверка, лента событий.
/// Порт client/app.py (MainWindow) + client/worker.py (фоновые операции).
@MainActor
final class AppModel: ObservableObject {
    // статус
    @Published var pcState: Bool?            // nil = не проверено
    @Published var lmState: Bool?
    @Published var lmModelLoaded = false     // LM Studio запущена И модель загружена
    @Published var stState: Bool?            // Strata (как lmState)
    @Published var stModelLoaded = false     // Strata запущена И модель загружена
    @Published var pcTitle = "ПК"
    @Published var lmTitle = "LM Studio"
    @Published var stTitle = "Strata"
    @Published var statusLine = "Готов."
    @Published var autoLine = "Автопроверка: выключена"
    @Published var pcChecking = false
    @Published var lmChecking = false
    @Published var stChecking = false
    @Published var busy = false

    /// Лента событий (команды и смены статусов), newest last; как «уведомления
    /// о статусе» — выводится внизу экрана.
    struct AppEvent: Identifiable {
        let id = UUID()
        let time: Date
        let text: String
        /// nil = информационное, true = успешно, false = ошибка
        let ok: Bool?
    }
    @Published var events: [AppEvent] = []

    private func log(_ text: String, ok: Bool? = nil) {
        events.append(AppEvent(time: Date(), text: text, ok: ok))
        if events.count > 50 { events.removeFirst(events.count - 50) }
    }

    let cfg: ConfigStore
    private var autoTask: Task<Void, Never>?
    private var lastTick: Date?

    init(cfg: ConfigStore) {
        self.cfg = cfg
        if cfg.autoCheckEnabled {
            autoLine = "Автопроверка: вкл (раз в \(cfg.autoCheckIntervalS) с)"
        }
    }

    private var api: ApiClient { ApiClient(host: cfg.pcIP, port: cfg.serverPort) }

    // MARK: - проверки

    func checkPC() async {
        let ip = cfg.pcIP.trimmingCharacters(in: .whitespaces)
        guard !ip.isEmpty else {
            pcState = false
            return
        }
        pcChecking = true
        let start = Date()
        let up = await NetCheck.hostIsUp(host: ip, port: cfg.serverPort)
        await minVisible(start: start)
        let old = pcState
        pcState = up
        pcChecking = false
        if let old, old != up { log("ПК " + (up ? "в сети" : "не в сети"), ok: up) }
    }

    func checkLM() async {
        lmChecking = true
        let start = Date()
        do {
            let res = try await api.command("status", timeout: 6)
            applyStatus(res)
        } catch {
            lmState = false
            stState = false
        }
        await minVisible(start: start)
        lmChecking = false
    }

    /// Проверка Strata — тот же status-запрос (сервер отдаёт strata_* поля).
    func checkST() async {
        stChecking = true
        let start = Date()
        do {
            let res = try await api.command("status", timeout: 6)
            applyStatus(res)
        } catch {
            lmState = false
            stState = false
        }
        await minVisible(start: start)
        stChecking = false
    }

    /// Автопроверка: ПК + LM/Strata одновременно (как _auto_tick в app.py).
    func checkAll() async {
        async let pc: Void = checkPC()
        async let lm: Void = checkLM()
        _ = await (pc, lm)
        lastTick = Date()
        statusLine = statusSummary()
        updateAutoLine()
    }

    func manualCheckPC() async {
        await checkPC()
        statusLine = pcState == false ? "ПК не отвечает." : "ПК в сети."
    }

    func manualCheckLM() async {
        await checkLM()
        if lmState == false {
            statusLine = "LM Studio: недоступно."
        } else if lmModelLoaded {
            statusLine = "LM Studio работает, модель загружена."
        } else {
            statusLine = "LM Studio работает."
        }
    }

    func manualCheckST() async {
        await checkST()
        if stState == false {
            statusLine = "Strata: недоступна."
        } else if stModelLoaded {
            statusLine = "Strata работает, модель загружена."
        } else {
            statusLine = "Strata работает."
        }
    }

    /// Сводка: что активно (как нижняя строка в app.py: «активна LM Studio»,
    /// «активна Strata», «активны обе: LM Studio и Strata»).
    private func statusSummary() -> String {
        if pcState == false { return "ПК не отвечает." }
        var parts: [String] = []
        if lmState == true { parts.append("LM Studio") }
        if stState == true { parts.append("Strata") }
        switch parts.count {
        case 0: return "ПК в сети."
        case 1: return "ПК в сети, активна \(parts[0])."
        default: return "ПК в сети, активны обе: LM Studio и Strata."
        }
    }

    /// Заголовки секций из ответа status (порты _set_pc_title / _set_lm_title).
    private func applyStatus(_ res: [String: Any]) {
        // LM-проверка не меняет точку ПК (как в десктопе) — только заголовки + состояние LM.
        let oldLM = lmState
        lmState = (res["lmstudio_running"] as? Bool) ?? false
        let loadedModel = (res["lmstudio_model"] as? String)?.trimmingCharacters(in: .whitespaces) ?? ""
        // «модель загружена» = известен контекст (state==«loaded»); /v1/models отдаёт каталог даже без загрузки
        lmModelLoaded = (lmState == true) && ((res["lmstudio_context"] as? Int) ?? 0) > 0
        if let oldLM, oldLM != (lmState == true) {
            log("LM Studio " + (lmState == true ? "запущена" : "остановлена"), ok: lmState == true)
        }
        if lmModelLoaded && !lmWasLoaded { log("LM Studio: модель загружена", ok: true) }
        lmWasLoaded = lmModelLoaded

        // ПК
        let name = (res["pc_name"] as? String)?.trimmingCharacters(in: .whitespaces) ?? ""
        let os = Format.osName(res["os_name"] as? String)
        let up = Format.uptime(res["uptime_s"] as? Int)
        let ram = Format.gb(res["ram_used_mb"] as? Int)
        var parts = [os, up, ram].filter { !$0.isEmpty }
        if !name.isEmpty { parts.insert(name, at: 0) }
        pcTitle = parts.isEmpty ? "ПК" : "ПК (\(parts.joined(separator: ", ")))"

        // LM Studio
        let ver = Format.version(res["lmstudio_version"] as? String)
        let model = loadedModel
        let ctx = Format.context(res["lmstudio_context"] as? Int)
        let vram = Format.gb(res["lmstudio_vram_mb"] as? Int)
        if lmState == true {
            var parts: [String] = []
            if !ver.isEmpty { parts.append(ver) }
            if !model.isEmpty { parts.append(model) }
            if !ctx.isEmpty { parts.append(ctx) }
            if !vram.isEmpty { parts.append(vram) }
            lmTitle = parts.isEmpty ? "LM Studio" : "LM Studio (\(parts.joined(separator: ", ")))"
        } else {
            lmTitle = "LM Studio"
        }

        // Strata: strata_running / strata_version / strata_model /
        // strata_context / strata_loaded / strata_vram_mb (старый сервер —
        // полей нет, блок не падает; как setStTitle в web/index.html)
        if let stRunning = res["strata_running"] as? Bool {
            let oldST = stState
            stState = stRunning
            stModelLoaded = stRunning && ((res["strata_loaded"] as? Bool) ?? false)
            if let oldST, oldST != stRunning {
                log("Strata " + (stRunning ? "запущена" : "остановлена"), ok: stRunning)
            }
            if stModelLoaded && !stWasLoaded { log("Strata: модель загружена", ok: true) }
            stWasLoaded = stModelLoaded
            let stVer = (res["strata_version"] as? String)?.trimmingCharacters(in: .whitespaces) ?? ""
            let stModel = (res["strata_model"] as? String)?.trimmingCharacters(in: .whitespaces) ?? ""
            let stCtx = Format.context(res["strata_context"] as? Int)
            let stVram = Format.gb(res["strata_vram_mb"] as? Int)
            if stRunning {
                var parts: [String] = []
                if !stVer.isEmpty { parts.append(stVer) }
                if !stModel.isEmpty { parts.append(stModel) }
                if !stCtx.isEmpty { parts.append(stCtx) }
                if !stVram.isEmpty { parts.append(stVram) }
                stTitle = parts.isEmpty ? "Strata" : "Strata (\(parts.joined(separator: ", ")))"
            } else {
                stTitle = "Strata"
            }
        }
    }

    private var lmWasLoaded = false
    private var stWasLoaded = false

    // MARK: - действия

    func wol() async {
        guard !busy else { return }
        busy = true
        defer { busy = false }

        let mac = cfg.pcMAC
        let relayURL = cfg.wolRelayURL.trimmingCharacters(in: .whitespaces)

        // iOS не умеет UDP-broadcast (entitlement multicast — только для
        // платного аккаунта Apple), а unicast до спящего ПК часто не доходит.
        // Поэтому первичный путь — relay: веб-сервер (NAS) сам шлёт magic
        // packet broadcast'ом (то же, что делает веб-версия). Если relay не
        // задан или недоступен — отправка напрямую (unicast) как резерв.
        if !relayURL.isEmpty {
            do {
                let (sent, _, rmac) = try await WoLRelay.send(relayURL: relayURL,
                                                               token: cfg.wolRelayToken,
                                                               mac: mac)
                statusLine = "✅ WoL (relay): ×\(sent) → MAC \(rmac)"
                log("Wake-on-LAN (relay)", ok: true)
            } catch {
                do {
                    let (sent, _, _) = try WoL.send(macRaw: mac, unicastIP: cfg.pcIP)
                    statusLine = "⚠️ WoL: relay недоступен — ×\(sent), может не будить"
                    log("Wake-on-LAN (relay недоступен, напрямую)", ok: false)
                } catch {
                    statusLine = "❌ WoL: \(error.localizedDescription)"
                    log("Wake-on-LAN", ok: false)
                }
            }
            return
        }

        do {
            let (sent, _, dmac) = try WoL.send(macRaw: mac, unicastIP: cfg.pcIP)
            statusLine = "✅ WoL (напрямую): ×\(sent) → MAC \(dmac)"
            log("Wake-on-LAN (напрямую)", ok: true)
        } catch {
            statusLine = "❌ WoL: \(error.localizedDescription)"
            log("Wake-on-LAN", ok: false)
        }
    }

    func hibernate() async {
        guard !busy else { return }
        busy = true
        defer { busy = false }
        do {
            _ = try await api.command("hibernate", timeout: 6)
            pcState = false
            statusLine = "Гибернация запущена — ПК погаснет через несколько секунд."
            log("Гибернация", ok: true)
        } catch {
            statusLine = "Гибернация: \(error.localizedDescription)"
            log("Гибернация", ok: false)
        }
    }

    func startLM() async {
        guard !busy else { return }
        busy = true
        defer { busy = false }
        do {
            _ = try await api.command("start_lmstudio", timeout: 10)
            statusLine = "LM Studio запущена."
            log("Запуск LM Studio", ok: true)
            try? await Task.sleep(for: .seconds(2))   // дать запуститься, как в _on_start
            await checkLM()
        } catch {
            statusLine = "Старт LM Studio: \(error.localizedDescription)"
            log("Запуск LM Studio", ok: false)
        }
    }

    func stopLM() async {
        guard !busy else { return }
        busy = true
        defer { busy = false }
        do {
            _ = try await api.command("stop_lmstudio", timeout: 10)
            lmState = false
            statusLine = "LM Studio остановлена."
            log("Остановка LM Studio", ok: true)
            try? await Task.sleep(for: .seconds(2))   // как в _on_stop
            await checkLM()
        } catch {
            statusLine = "Стоп LM Studio: \(error.localizedDescription)"
            log("Остановка LM Studio", ok: false)
        }
    }

    func startST() async {
        guard !busy else { return }
        busy = true
        defer { busy = false }
        do {
            _ = try await api.command("start_strata", timeout: 10)
            statusLine = "Strata запущена."
            log("Запуск Strata", ok: true)
            try? await Task.sleep(for: .seconds(2))
            await checkST()
        } catch {
            statusLine = "Старт Strata: \(error.localizedDescription)"
            log("Запуск Strata", ok: false)
        }
    }

    func stopST() async {
        guard !busy else { return }
        busy = true
        defer { busy = false }
        do {
            _ = try await api.command("stop_strata", timeout: 10)
            stState = false
            statusLine = "Strata остановлена."
            log("Остановка Strata", ok: true)
            try? await Task.sleep(for: .seconds(2))
            await checkST()
        } catch {
            statusLine = "Стоп Strata: \(error.localizedDescription)"
            log("Остановка Strata", ok: false)
        }
    }

    // MARK: - автопроверка

    func startAutoCheck() {
        autoTask?.cancel()
        autoTask = nil
        guard cfg.autoCheckEnabled else {
            autoLine = "Автопроверка: выключена"
            return
        }
        let interval = max(2, cfg.autoCheckIntervalS)
        autoLine = "Автопроверка: вкл (раз в \(interval) с)"
        autoTask = Task { [weak self] in
            while !Task.isCancelled {
                await self?.checkAll()
                let iv = max(2, self?.cfg.autoCheckIntervalS ?? interval)
                try? await Task.sleep(for: .seconds(iv))
            }
        }
    }

    func stopAutoCheck() {
        autoTask?.cancel()
        autoTask = nil
    }

    private func updateAutoLine() {
        guard cfg.autoCheckEnabled, let last = lastTick else {
            autoLine = "Автопроверка: выключена"
            return
        }
        let next = last.addingTimeInterval(TimeInterval(max(2, cfg.autoCheckIntervalS)))
        let t = next.formatted(date: .omitted, time: .standard)
        autoLine = "Автопроверка: вкл · следующая в \(t)"
    }

    // MARK: - минимальная видимая длительность «проверка…»

    /// TCP-/HTTP-проверка на LAN может завершиться за миллисекунды — жёлтый индикатор
    /// не успевает отрисоваться. Держим состояние «проверка…» не короче minDur.
    private func minVisible(start: Date, minDur: TimeInterval = 0.6) async {
        let elapsed = Date().timeIntervalSince(start)
        if elapsed < minDur {
            try? await Task.sleep(for: .seconds(minDur - elapsed))
        }
    }
}

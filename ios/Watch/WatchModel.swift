import Foundation
import Combine

/// Модель watch-клиента: статусы + команды. Всё захардкожено в WatchConfig;
/// проверки независимые, каждая напрямую:
///   ПК        — GET :8787/ (сервер ответил = ПК включён)
///   LM Studio — GET :4321/v1/models
///   Strata    — GET :8090/health
/// Команды — POST :8787/command (hibernate, start/stop_lmstudio,
/// start/stop_strata); пробуждение — POST /wol на NAS-релей (ПК выключен).
/// При «ПК не в сети» часы проверяют, видят ли они LAN вообще (GET на NAS):
/// NAS отвечает → молчит ПК; NAS молчит → LAN заблокирован: на watchOS нет
/// локальной network-privacy (TN3179), при connected iPhone трафик идёт через
/// iPhone и разрешение «Локальная сеть» выдаётся в параметрах iPhone.
final class WatchModel: ObservableObject {
    @Published var pcUp: Bool? = nil       // nil = ещё не проверялось
    @Published var lmUp: Bool? = nil
    @Published var strataUp: Bool? = nil
    /// Диагностика «всегда красного»: true — часы видят NAS, молчит ПК;
    /// false — часы не видят локальную сеть; nil — ПК жив или не измерялось.
    @Published var lanOK: Bool? = nil
    @Published var lastCheck: Date?
    /// Лента событий (команды и смены статусов), newest last; на экране —
    /// последние несколько внизу.
    @Published var events: [WatchEvent] = []

    struct WatchEvent: Identifiable {
        let id = UUID()
        let time: Date
        let text: String
        /// nil = информационное, true = успешно, false = ошибка
        let ok: Bool?
    }

    private func log(_ text: String, ok: Bool? = nil) {
        events.append(WatchEvent(time: Date(), text: text, ok: ok))
        if events.count > 20 { events.removeFirst(events.count - 20) }
    }

    private var autoTask: Task<Void, Never>?

    /// Три зонда параллельно (каждый до 4 с) — экран обновляется за ~4 с.
    /// ПК — тоже HTTP-зонд (как NAS-диагностика): на watchOS NWConnection-TCP
    /// до устройств LAN не проходил, а URLSession-запросы проходят.
    func refresh() async {
        lastCheck = Date()
        async let pc = Self.httpUp("http://\(WatchConfig.pcHost):\(WatchConfig.pcPort)/")
        async let lm = Self.httpUp("http://\(WatchConfig.pcHost):\(WatchConfig.lmPort)/v1/models")
        async let st = Self.httpUp("http://\(WatchConfig.pcHost):\(WatchConfig.strataPort)/health")

        let up = await pc
        let lmNew = await lm
        let stNew = await st
        let oldPC = pcUp, oldLM = lmUp, oldST = strataUp
        pcUp = up
        lmUp = lmNew
        strataUp = stNew
        // Смены статусов — в ленту событий (первая проверка nil→нет не пишется).
        if let o = oldPC, o != up { log("ПК " + (up ? "в сети" : "не в сети"), ok: up) }
        if let o = oldLM, o != lmNew { log("LM Studio " + (lmNew ? "запущена" : "остановлена"), ok: lmNew) }
        if let o = oldST, o != stNew { log("Strata " + (stNew ? "запущена" : "остановлена"), ok: stNew) }
        // ПК «не в сети» — проверяем, видит ли часы локальную сеть вообще.
        lanOK = up ? nil : await Self.httpUp("http://\(WatchConfig.nasHost):\(WatchConfig.nasPort)/")
    }

    /// «Сервер ответил?» — ЛЮБОЙ HTTP-ответ (даже 401/302) означает, что путь
    /// есть; ошибка соединения/таймаут = false.
    private static func httpUp(_ url: String) async -> Bool {
        guard let u = URL(string: url) else { return false }
        var req = URLRequest(url: u)
        req.httpMethod = "GET"
        req.timeoutInterval = 4
        do {
            _ = try await URLSession.shared.data(for: req)
            return true
        } catch {
            return false
        }
    }

    // MARK: - Команды

    /// Человекочитаемые имена команд — для ленты событий.
    private static let cmdLabels = [
        "hibernate": "Гибернация ПК",
        "start_lmstudio": "Запуск LM Studio",
        "stop_lmstudio": "Остановка LM Studio",
        "start_strata": "Запуск Strata",
        "stop_strata": "Остановка Strata",
    ]

    /// Команда серверу ПК (POST /command). true — сервер принял (ok:true).
    @discardableResult
    func sendCommand(_ command: String) async -> Bool {
        let ok = await postJSON("http://\(WatchConfig.pcHost):\(WatchConfig.pcPort)/command",
                                body: ["command": command], headers: [:])
        log(Self.cmdLabels[command] ?? command, ok: ok)
        return ok
    }

    /// Пробуждение ПК (Wake-on-LAN) через NAS-релей: POST /wol + X-Token,
    /// MAC релея берёт из своего config — на часах MAC не нужен.
    @discardableResult
    func wakePC() async -> Bool {
        let ok = await postJSON("http://\(WatchConfig.nasHost):\(WatchConfig.nasPort)/wol",
                                body: [:], headers: ["X-Token": WatchConfig.relayToken])
        log("Пробуждение ПК (WoL)", ok: ok)
        return ok
    }

    /// POST JSON, ответ — JSON с полем ok. true = ok:true.
    private func postJSON(_ url: String, body: [String: Any],
                          headers: [String: String]) async -> Bool {
        guard let u = URL(string: url) else { return false }
        var req = URLRequest(url: u)
        req.httpMethod = "POST"
        req.timeoutInterval = 6
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        for (k, v) in headers { req.setValue(v, forHTTPHeaderField: k) }
        req.httpBody = try? JSONSerialization.data(withJSONObject: body)
        do {
            let (data, _) = try await URLSession.shared.data(for: req)
            let obj = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
            return (obj?["ok"] as? Bool) ?? false
        } catch {
            return false
        }
    }

    // MARK: - автопроверка

    func startAutoCheck() {
        autoTask?.cancel()
        autoTask = Task { [weak self] in
            while !Task.isCancelled {
                await self?.refresh()
                try? await Task.sleep(for: .seconds(WatchConfig.autoCheckIntervalS))
            }
        }
    }

    func stopAutoCheck() {
        autoTask?.cancel()
        autoTask = nil
    }
}

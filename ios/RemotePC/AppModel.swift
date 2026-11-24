import SwiftUI
import Foundation

/// Логика главного экрана: проверки, WoL, гибернация, LM Studio, автопроверка.
/// Порт client/app.py (MainWindow) + client/worker.py (фоновые операции).
@MainActor
final class AppModel: ObservableObject {
    // статус
    @Published var pcState: Bool?            // nil = не проверено
    @Published var lmState: Bool?
    @Published var lmModelLoaded = false     // LM Studio запущена И модель загружена
    @Published var pcTitle = "ПК"
    @Published var lmTitle = "LM Studio"
    @Published var statusLine = "Готов."
    @Published var autoLine = "Автопроверка: выключена"
    @Published var pcChecking = false
    @Published var lmChecking = false
    @Published var busy = false

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
        pcState = up
        pcChecking = false
    }

    func checkLM() async {
        lmChecking = true
        let start = Date()
        do {
            let res = try await api.command("status", timeout: 6)
            applyStatus(res)
        } catch {
            lmState = false
        }
        await minVisible(start: start)
        lmChecking = false
    }

    /// Автопроверка: ПК + LM одновременно (как _auto_tick в app.py).
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

    private func statusSummary() -> String {
        if pcState == false { return "ПК не отвечает." }
        if lmState == false { return "LM Studio не отвечает." }
        if lmState == true {
            return lmModelLoaded
                ? "ПК в сети, LM Studio работает, модель загружена."
                : "ПК в сети, LM Studio работает."
        }
        return "ПК в сети."
    }

    /// Заголовки секций из ответа status (порты _set_pc_title / _set_lm_title).
    private func applyStatus(_ res: [String: Any]) {
        // LM-проверка не меняет точку ПК (как в десктопе) — только заголовки + состояние LM.
        lmState = (res["lmstudio_running"] as? Bool) ?? false
        let loadedModel = (res["lmstudio_model"] as? String)?.trimmingCharacters(in: .whitespaces) ?? ""
        // «модель загружена» = известен контекст (state==«loaded»); /v1/models отдаёт каталог даже без загрузки
        lmModelLoaded = (lmState == true) && ((res["lmstudio_context"] as? Int) ?? 0) > 0

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
    }

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
        if !relayURL.isEmpty, let base = URL(string: relayURL) {
            do {
                let (sent, to, rmac) = try await wolViaRelay(base: base, mac: mac)
                statusLine = "WoL: relay отправил broadcast (\(sent) шт → \(to), MAC \(rmac))."
            } catch {
                do {
                    let (sent, to, _) = try WoL.send(macRaw: mac, unicastIP: cfg.pcIP)
                    statusLine = "WoL: relay: \(error.localizedDescription). Напрямую: \(sent) шт → \(to) (unicast, может не будить)."
                } catch {
                    statusLine = "WoL: relay: \(error.localizedDescription)"
                }
            }
            return
        }

        do {
            let (sent, to, dmac) = try WoL.send(macRaw: mac, unicastIP: cfg.pcIP)
            statusLine = "WoL: magic packet отправлен напрямую (\(sent) шт → \(to), MAC \(dmac))."
        } catch {
            statusLine = "WoL: \(error.localizedDescription)"
        }
    }

    /// POST {relay}/wol — веб-сервер (NAS) шлёт magic packet broadcast'ом.
    /// Тот же механизм, что в веб-версии (браузер/айфон сам raw-UDP broadcast
    /// слать не могут). Контракт: web/serve.py → {"ok": true, "sent", "to", "mac"}.
    private func wolViaRelay(base: URL, mac: String) async throws -> (sent: Int, to: String, mac: String) {
        var req = URLRequest(url: base.appendingPathComponent("wol"))
        req.httpMethod = "POST"
        req.timeoutInterval = 8
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        let token = cfg.wolRelayToken.trimmingCharacters(in: .whitespaces)
        if !token.isEmpty {
            req.setValue(token, forHTTPHeaderField: "X-Token")
        }
        req.httpBody = try JSONSerialization.data(withJSONObject: ["mac": mac])

        let (data, response) = try await URLSession.shared.data(for: req)
        guard let http = response as? HTTPURLResponse else {
            throw NSError(domain: "WoL", code: -1,
                          userInfo: [NSLocalizedDescriptionKey: "relay: некорректный ответ сервера"])
        }
        if http.statusCode == 401 {
            throw NSError(domain: "WoL", code: 401,
                          userInfo: [NSLocalizedDescriptionKey: "relay: неверный или не задан токен (401)"])
        }
        guard (200..<300).contains(http.statusCode) else {
            throw NSError(domain: "WoL", code: http.statusCode,
                          userInfo: [NSLocalizedDescriptionKey: "relay: HTTP \(http.statusCode) от сервера"])
        }
        let json = (try? JSONSerialization.jsonObject(with: data) as? [String: Any]) ?? [:]
        guard (json["ok"] as? Bool) == true else {
            let msg = json["error"] as? String ?? "неизвестная ошибка"
            throw NSError(domain: "WoL", code: -1, userInfo: [NSLocalizedDescriptionKey: "relay: \(msg)"])
        }
        return ((json["sent"] as? Int) ?? 0,
                (json["to"] as? String) ?? "?",
                (json["mac"] as? String) ?? mac)
    }

    func hibernate() async {
        guard !busy else { return }
        busy = true
        defer { busy = false }
        do {
            _ = try await api.command("hibernate", timeout: 6)
            pcState = false
            statusLine = "Гибернация запущена — ПК погаснет через несколько секунд."
        } catch {
            statusLine = "Гибернация: \(error.localizedDescription)"
        }
    }

    func startLM() async {
        guard !busy else { return }
        busy = true
        defer { busy = false }
        do {
            _ = try await api.command("start_lmstudio", timeout: 10)
            statusLine = "LM Studio запущена."
            try? await Task.sleep(for: .seconds(2))   // дать запуститься, как в _on_start
            await checkLM()
        } catch {
            statusLine = "Старт LM Studio: \(error.localizedDescription)"
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
            try? await Task.sleep(for: .seconds(2))   // как в _on_stop
            await checkLM()
        } catch {
            statusLine = "Стоп LM Studio: \(error.localizedDescription)"
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

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
    @Published var checking = false
    @Published var busy = false

    let cfg: ConfigStore
    private var autoTask: Task<Void, Never>?
    private var lastTick: Date?
    private var checkingCount = 0

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
        beginCheck()
        defer { endCheck() }
        pcState = await NetCheck.hostIsUp(host: ip, port: cfg.serverPort)
    }

    func checkLM() async {
        beginCheck()
        defer { endCheck() }
        do {
            let res = try await api.command("status", timeout: 6)
            applyStatus(res)
        } catch {
            lmState = false
        }
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
        pcState = true   // сервер ответил — ПК в сети
        lmState = (res["lmstudio_running"] as? Bool) ?? false
        let loadedModel = (res["lmstudio_model"] as? String)?.trimmingCharacters(in: .whitespaces) ?? ""
        lmModelLoaded = (lmState == true) && !loadedModel.isEmpty

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
        do {
            let (sent, to, mac) = try WoL.send(macRaw: cfg.pcMAC, unicastIP: cfg.pcIP)
            statusLine = "WoL: magic packet отправлен (\(sent) шт → \(to), MAC \(mac))."
        } catch {
            statusLine = "WoL: \(error.localizedDescription)"
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

    // MARK: - счётчик «Проверка…»

    private func beginCheck() {
        checkingCount += 1
        checking = true
    }

    private func endCheck() {
        checkingCount = max(0, checkingCount - 1)
        checking = checkingCount > 0
    }
}

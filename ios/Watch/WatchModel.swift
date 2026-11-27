import Foundation
import Combine

/// Модель watch-клиента: ТОЛЬКО статусы, команд нет (кнопок на часах нет).
/// Всё захардкожено в WatchConfig; проверки независимые, каждая напрямую:
///   ПК        — GET :8787/ (сервер ответил = ПК включён)
///   LM Studio — GET :4321/v1/models
///   Strata    — GET :8090/health
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
        pcUp = up
        lmUp = await lm
        strataUp = await st
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

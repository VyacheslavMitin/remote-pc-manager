import Foundation
import Combine

/// Модель watch-клиента: тот же API, что у iOS-клиента (status, команды),
/// WoL — через relay (POST /wol на веб-сервер, как у iPhone; на часах broadcast
/// тоже недоступен). Настройки общие с iPhone (UserDefaults одного приложения
/// на устройстве — часы берут свои; значения вводишь в настройках iPhone,
/// если часы не спарены с этим iPhone, — или здесь, если добавишь экран настроек).
final class WatchModel: ObservableObject {
    let cfg: ConfigStore
    /// ApiClient хранит host/port, заданные при создании — после смены
    /// IP/порта в настройках его нужно пересоздать (reload()).
    private var api: ApiClient
    private var autoTask: Task<Void, Never>?

    @Published var pcUp: Bool? = nil        // nil = ещё не проверено
    @Published var lmRunning = false
    @Published var lmModelLoaded = false
    @Published var busy = false
    @Published var message = ""             // результат последнего действия
    @Published var lastCheck: Date?         // когда была последняя автопроверка

    init() {
        cfg = ConfigStore()
        api = ApiClient(host: cfg.pcIP, port: cfg.serverPort)
    }

    /// Пересоздать API-клиент с новыми IP/портом (вызывать после сохранения настроек).
    func reload() {
        api = ApiClient(host: cfg.pcIP, port: cfg.serverPort)
    }

    /// Применить настройки, полученные с iPhone (WatchConnectivity).
    /// true = было что применить и конфиг сохранён.
    @discardableResult
    func applyRemote(_ dict: [String: Any]) -> Bool {
        var applied = false
        if let ip = dict["ip"] as? String, !ip.isEmpty {
            cfg.pcIP = ip.trimmingCharacters(in: .whitespacesAndNewlines)
            applied = true
        }
        if let mac = dict["mac"] as? String, !mac.isEmpty {
            cfg.pcMAC = mac.trimmingCharacters(in: .whitespacesAndNewlines)
            applied = true
        }
        if let port = dict["server_port"] as? Int, port >= 1, port <= 65535 {
            cfg.serverPort = port
            applied = true
        }
        if let url = dict["relay_url"] as? String {
            cfg.wolRelayURL = url.trimmingCharacters(in: .whitespacesAndNewlines)
            applied = true
        }
        if let token = dict["relay_token"] as? String {
            cfg.wolRelayToken = token.trimmingCharacters(in: .whitespacesAndNewlines)
            applied = true
        }
        guard applied else { return false }
        guard cfg.save() else {
            message = "⚠️ Получено с iPhone, но сохранить не удалось"
            return false
        }
        reload()
        return true
    }

    /// Настройки ещё не получены с iPhone (дефолтные значения)?
    var looksUnsynced: Bool {
        cfg.pcIP == "192.168.1.100" && cfg.pcMAC == "AA:BB:CC:DD:EE:FF"
    }

    /// Статус: ПК (TCP-зонд порта сервера) + LM Studio (из status).
    func refresh() async {
        lastCheck = Date()
        let up = await NetCheck.hostIsUp(host: cfg.pcIP, port: cfg.serverPort)
        pcUp = up
        guard up == true else {
            lmRunning = false
            lmModelLoaded = false
            return
        }
        do {
            let res = try await api.command("status", timeout: 6)
            lmRunning = (res["lmstudio_running"] as? Bool) ?? false
            // «модель загружена» = известен контекст (state==«loaded»),
            // /v1/models отдаёт каталог даже без загрузки (как во всех клиентах).
            lmModelLoaded = lmRunning && ((res["lmstudio_context"] as? Int) ?? 0) > 0
        } catch {
            lmRunning = false
            lmModelLoaded = false
        }
    }

    // MARK: - автопроверка

    /// Цикл: проверяет статус и ждёт интервал из настроек (мин. 3 с).
    func startAutoCheck() {
        autoTask?.cancel()
        autoTask = nil
        autoTask = Task { [weak self] in
            while !Task.isCancelled {
                await self?.refresh()
                let iv = max(3, self?.cfg.autoCheckIntervalS ?? 10)
                try? await Task.sleep(for: .seconds(iv))
            }
        }
    }

    func stopAutoCheck() {
        autoTask?.cancel()
        autoTask = nil
    }

    /// WoL: первично relay (веб-сервер шлёт broadcast), резерв — прямая отправка.
    func wol() async {
        guard !busy else { return }
        busy = true
        defer { busy = false }
        let mac = cfg.pcMAC
        let relayURL = cfg.wolRelayURL.trimmingCharacters(in: .whitespaces)
        if !relayURL.isEmpty {
            do {
                let (sent, _, rmac) = try await WoLRelay.send(relayURL: relayURL,
                                                               token: cfg.wolRelayToken,
                                                               mac: mac)
                message = "✅ WoL: ×\(sent) → MAC \(rmac)"
                return
            } catch {
                do {
                    let (sent, _, _) = try WoL.send(macRaw: mac, unicastIP: cfg.pcIP)
                    message = "⚠️ WoL: relay недоступен — ×\(sent), может не будить"
                } catch {
                    message = "❌ WoL: \(error.localizedDescription)"
                }
                return
            }
        }
        do {
            let (sent, _, dmac) = try WoL.send(macRaw: mac, unicastIP: cfg.pcIP)
            message = "✅ WoL: ×\(sent) → MAC \(dmac)"
        } catch {
            message = "❌ WoL: \(error.localizedDescription)"
        }
    }

    func hibernate() async {
        guard !busy else { return }
        busy = true
        defer { busy = false }
        do {
            _ = try await api.command("hibernate", timeout: 15)
            pcUp = false
            message = "Гибернация: отправлена"
        } catch {
            message = "Гибернация: \(error.localizedDescription)"
        }
    }

    func startLM() async {
        guard !busy else { return }
        busy = true
        defer { busy = false }
        do {
            _ = try await api.command("start_lmstudio", timeout: 15)
            lmRunning = true
            message = "LM Studio: запускается"
            Task {
                try? await Task.sleep(nanoseconds: 3_000_000_000)
                await refresh()
            }
        } catch {
            message = "Старт LM: \(error.localizedDescription)"
        }
    }

    func stopLM() async {
        guard !busy else { return }
        busy = true
        defer { busy = false }
        do {
            _ = try await api.command("stop_lmstudio", timeout: 15)
            lmRunning = false
            message = "LM Studio: останавливается"
            Task {
                try? await Task.sleep(nanoseconds: 3_000_000_000)
                await refresh()
            }
        } catch {
            message = "Стоп LM: \(error.localizedDescription)"
        }
    }
}

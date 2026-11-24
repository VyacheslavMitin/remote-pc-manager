import Foundation
import Combine

/// Модель watch-клиента: тот же API, что у iOS-клиента (status, команды),
/// WoL — через relay (POST /wol на веб-сервер, как у iPhone; на часах broadcast
/// тоже недоступен). Настройки общие с iPhone (UserDefaults одного приложения
/// на устройстве — часы берут свои; значения вводишь в настройках iPhone,
/// если часы не спарены с этим iPhone, — или здесь, если добавишь экран настроек).
final class WatchModel: ObservableObject {
    let cfg: ConfigStore
    private let api: ApiClient

    @Published var pcUp: Bool? = nil        // nil = ещё не проверено
    @Published var lmRunning = false
    @Published var lmModelLoaded = false
    @Published var busy = false
    @Published var message = ""             // результат последнего действия

    init() {
        cfg = ConfigStore()
        api = ApiClient(host: cfg.pcIP, port: cfg.serverPort)
    }

    /// Статус: ПК (TCP-зонд порта сервера) + LM Studio (из status).
    func refresh() async {
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

    func toggleLM() async {
        guard !busy else { return }
        busy = true
        defer { busy = false }
        let on = !lmRunning
        do {
            _ = try await api.command(on ? "start_lmstudio" : "stop_lmstudio", timeout: 15)
            lmRunning = on
            message = on ? "LM Studio: запускается" : "LM Studio: останавливается"
            Task {
                try? await Task.sleep(nanoseconds: 3_000_000_000)
                await refresh()
            }
        } catch {
            message = "LM Studio: \(error.localizedDescription)"
        }
    }
}

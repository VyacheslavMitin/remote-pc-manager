import Foundation
import Combine

/// Настройки приложения. Структура зеркалирует client/config.json:
/// pc.ip, pc.mac, server.port, lmstudio.api_port, auto_check.{enabled, interval_s}.
///
/// На iOS нет доступа к client/config.json — конфиг живёт в UserDefaults
/// (аналог config.py). Значения по умолчанию — стандартные (как в client/config.py);
/// реальные (IP/MAC) задаются на экране настроек.
final class ConfigStore: ObservableObject {
    @Published var pcIP: String
    @Published var pcMAC: String
    @Published var serverPort: Int
    @Published var lmAPIPort: Int
    @Published var autoCheckEnabled: Bool
    @Published var autoCheckIntervalS: Int
    // WoL relay: адрес веб-сервера (NAS/мак), который шлёт magic packet сам
    // (iOS не умеет UDP-broadcast — Apple требует платный аккаунт).
    // Пусто = отправка напрямую с айфона (только unicast, может не будить).
    @Published var wolRelayURL: String
    @Published var wolRelayToken: String

    private static let storageKey = "rpcm.config"
    /// Общий контейнер настроек (App Group): приложение на iPhone и watch
    /// видят один и тот же конфиг (группа group.ru.vmitin.remotepc).
    private static let appGroup = "group.ru.vmitin.remotepc"
    private static var defaults: UserDefaults {
        UserDefaults(suiteName: appGroup) ?? .standard
    }

    init() {
        // Миграция: если конфиг был сохранён в стандартном контейнере
        // (до введения App Group), копируем его в общий.
        let legacy = UserDefaults.standard.data(forKey: Self.storageKey)
        if legacy != nil, Self.defaults.data(forKey: Self.storageKey) == nil {
            Self.defaults.set(legacy, forKey: Self.storageKey)
        }
        var ip = "192.168.1.100"
        var mac = "AA:BB:CC:DD:EE:FF"
        var serverPort = 8787
        var lmAPIPort = 1234
        var autoOn = true
        var interval = 10
        var relayURL = ""
        var relayToken = ""

        if let data = Self.defaults.data(forKey: Self.storageKey),
           let saved = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
            let pc = saved["pc"] as? [String: Any]
            let server = saved["server"] as? [String: Any]
            let lm = saved["lmstudio"] as? [String: Any]
            let auto = saved["auto_check"] as? [String: Any]
            ip = (pc?["ip"] as? String) ?? ip
            mac = (pc?["mac"] as? String) ?? mac
            serverPort = (server?["port"] as? Int) ?? serverPort
            lmAPIPort = (lm?["api_port"] as? Int) ?? lmAPIPort
            autoOn = (auto?["enabled"] as? Bool) ?? autoOn
            interval = (auto?["interval_s"] as? Int) ?? interval
            let relay = saved["relay"] as? [String: Any]
            relayURL = (relay?["url"] as? String) ?? relayURL
            relayToken = (relay?["token"] as? String) ?? relayToken
        }
        self.pcIP = ip
        self.pcMAC = mac
        self.serverPort = serverPort
        self.lmAPIPort = lmAPIPort
        self.autoCheckEnabled = autoOn
        self.autoCheckIntervalS = interval
        self.wolRelayURL = relayURL
        self.wolRelayToken = relayToken
    }

    func save() {
        let dict: [String: Any] = [
            "pc": [
                "ip": pcIP.trimmingCharacters(in: .whitespaces),
                "mac": ConfigStore.normalizeMAC(pcMAC),
            ],
            "server": ["port": serverPort],
            "lmstudio": ["api_port": lmAPIPort],
            "auto_check": ["enabled": autoCheckEnabled, "interval_s": autoCheckIntervalS],
            "relay": [
                "url": wolRelayURL.trimmingCharacters(in: .whitespaces),
                "token": wolRelayToken.trimmingCharacters(in: .whitespaces),
            ],
        ]
        if let data = try? JSONSerialization.data(withJSONObject: dict) {
            Self.defaults.set(data, forKey: Self.storageKey)
        }
    }

    /// MAC в формат aa:bb:cc:dd:ee:ff (как _normalize_mac в client/config.py).
    static func normalizeMAC(_ raw: String) -> String {
        let hex = Array(
            raw.lowercased().filter { "0123456789abcdef".contains($0) }
        ).prefix(12)
        var groups: [String] = []
        var cur = ""
        for ch in hex {
            cur.append(ch)
            if cur.count == 2 { groups.append(cur); cur = "" }
        }
        return groups.joined(separator: ":")
    }
}

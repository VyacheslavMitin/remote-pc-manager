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

    private static let storageKey = "rpcm.config"

    init() {
        var ip = "192.168.1.100"
        var mac = "AA:BB:CC:DD:EE:FF"
        var serverPort = 8787
        var lmAPIPort = 1234
        var autoOn = true
        var interval = 10

        if let data = UserDefaults.standard.data(forKey: Self.storageKey),
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
        }
        self.pcIP = ip
        self.pcMAC = mac
        self.serverPort = serverPort
        self.lmAPIPort = lmAPIPort
        self.autoCheckEnabled = autoOn
        self.autoCheckIntervalS = interval
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
        ]
        if let data = try? JSONSerialization.data(withJSONObject: dict) {
            UserDefaults.standard.set(data, forKey: Self.storageKey)
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

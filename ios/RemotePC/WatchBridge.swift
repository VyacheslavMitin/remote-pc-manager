import Foundation
import WatchConnectivity

/// Мост WatchConnectivity: отдаёт настройки с iPhone на спаренные Apple Watch
/// (application context — доставляется при следующем открытии watch-приложения).
///
/// Почему именно WatchConnectivity: буфер обмена на watchOS не существует
/// (UIPasteboard недоступен в watchOS SDK), а App Group-контейнер локален
/// для каждого устройства — общие механизмы между iPhone и Watch не работают.
final class WatchBridge: NSObject, WCSessionDelegate {
    static let shared = WatchBridge()
    private let queue = DispatchQueue(label: "ru.vmitin.remotepc.watchbridge")

    func activate() {
        guard WCSession.isSupported() else { return }
        queue.async {
            WCSession.default.delegate = self
            WCSession.default.activate()
        }
    }

    // iOS-only: в watchOS SDK эти колбэки помечены unavailable.
    // (WatchBridge компилируется в оба таргета — общий исходник.)
    #if !os(watchOS)
    // Сессия может деактивироваться (спящий режим, Bluetooth) — реактивируем.
    func sessionDidBecomeInactive(_ session: WCSession) {
        queue.async { WCSession.default.activate() }
    }

    func sessionDidDeactivate(_ session: WCSession) {
        queue.async { WCSession.default.activate() }
    }
    #endif

    // Обязательный для delegate в новых SDK: фиксируем состояние активации.
    func session(_ session: WCSession,
                 activationDidCompleteWith activationState: WCSessionActivationState,
                 error: Error?) {
        if let error {
            print("WatchBridge: активация WCSession не удалась: \(error)")
        }
    }

    /// Отправить настройки на часы. Контекст хранится на стороне часов
    /// и доставляется, когда watch-приложение откроется.
    func pushSettings(ip: String, mac: String, serverPort: Int,
                      relayURL: String, relayToken: String) {
        guard WCSession.isSupported() else { return }
        let dict: [String: Any] = [
            "v": 1,
            "ip": ip,
            "mac": mac,
            "server_port": serverPort,
            "relay_url": relayURL,
            "relay_token": relayToken,
        ]
        queue.async {
            do {
                try WCSession.default.updateApplicationContext(dict)
                print("WatchBridge: настройки отправлены на Apple Watch")
            } catch {
                print("WatchBridge: ошибка отправки: \(error)")
            }
        }
    }
}

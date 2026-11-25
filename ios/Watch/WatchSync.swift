import Foundation
import WatchConnectivity

/// Приём настроек с iPhone (application context через WatchConnectivity).
///
/// Направление — строго с iPhone: iOS-приложение вызывает
/// `updateApplicationContext`, а watch-приложение получает контекст
/// автоматически, когда становится активным (открыто/на передний план).
/// Вызывать fetch с часов нельзя (метод недоступен в watchOS SDK).
///
/// Почему именно WatchConnectivity: UIPasteboard в watchOS не существует,
/// App Group-контейнер локален для каждого устройства.
final class WatchSync: NSObject, WCSessionDelegate {
    static let shared = WatchSync()
    private let queue = DispatchQueue(label: "ru.vmitin.remotepc.watchsync")

    /// Настройки, полученные с iPhone (вызывается на главном потоке).
    var onContext: (([String: Any]) -> Void)?

    func activate() {
        guard WCSession.isSupported() else { return }
        queue.async {
            WCSession.default.delegate = self
            WCSession.default.activate()
        }
    }

    // В watchOS SDK нет sessionDidBecomeInactive/Deactivate —
    // единственные обязательные колбэки: activationDidCompleteWithState
    // (ниже) и опциональные didReceive* (ниже).

    // Обязательный для delegate в новых SDK: фиксируем состояние активации.
    func session(_ session: WCSession,
                 activationDidCompleteWith activationState: WCSessionActivationState,
                 error: Error?) {
        if let error {
            print("WatchSync: активация WCSession не удалась: \(error)")
        }
    }

    /// Контекст от iPhone — доставляется, когда приложение становится активным.
    func session(_ session: WCSession,
                 didReceiveApplicationContext applicationContext: [String: Any]) {
        DispatchQueue.main.async { self.onContext?(applicationContext) }
    }
}

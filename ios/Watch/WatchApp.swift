import SwiftUI
import WatchConnectivity

@main
struct RemotePCWatchApp: App {
    @StateObject private var model = WatchModel()

    init() {
        // init() — mutating, замыкание не может захватить self —
        // берём модель напрямую (это класс, ссылка живёт дольше).
        let model = self.model
        // Настройки с iPhone (WatchConnectivity): при получении — применить,
        // сохранить и сразу проверить статус.
        WatchSync.shared.onContext = { dict in
            guard dict["v"] as? Int == 1 else { return }
            if model.applyRemote(dict) {
                model.message = "✅ Настройки получены с iPhone"
                Task { await model.refresh() }
            }
        }
        WatchSync.shared.activate()
    }

    var body: some Scene {
        WindowGroup {
            WatchRootView(model: model)
        }
    }
}

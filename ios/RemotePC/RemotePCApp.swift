import SwiftUI

@main
struct RemotePCApp: App {
    @StateObject private var cfg = ConfigStore()

    init() {
        // Сессия WatchConnectivity: после сохранения настроек можно
        // отправить их на спаренные Apple Watch.
        WatchBridge.shared.activate()
    }

    var body: some Scene {
        WindowGroup {
            ContentView(cfg: cfg)
                .preferredColorScheme(.dark)   // тёмная тема — как у десктопного клиента
        }
    }
}

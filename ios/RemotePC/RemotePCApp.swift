import SwiftUI

@main
struct RemotePCApp: App {
    @StateObject private var cfg = ConfigStore()

    var body: some Scene {
        WindowGroup {
            ContentView(cfg: cfg)
                .preferredColorScheme(.dark)   // тёмная тема — как у десктопного клиента
        }
    }
}

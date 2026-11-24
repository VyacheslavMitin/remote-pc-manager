import SwiftUI

/// Главный экран часов: статус ПК + LM Studio и действия.
/// Единый стиль с iOS/веб-клиентами (тёмная тема, статус-точки,
/// «в сети» / «работает»).
struct WatchRootView: View {
    @EnvironmentObject var model: WatchModel
    @State private var showSettings = false

    var body: some View {
        VStack(spacing: 8) {
            statusRow("ПК",
                      state: model.pcUp,
                      onLabel: "в сети", offLabel: "не в сети")
            statusRow("LM Studio",
                      state: model.pcUp == true ? (model.lmRunning ? true : false) : nil,
                      onLabel: "работает", offLabel: "не запущена")

            Spacer(minLength: 0)

            HStack(spacing: 8) {
                actionButton("Пробудить", icon: "power", tint: Theme.accent) {
                    await model.wol()
                }
                actionButton("Гибернация", icon: "moon.zzz.fill", tint: Theme.muted) {
                    await model.hibernate()
                }
                actionButton(model.lmRunning ? "LM выкл" : "LM вкл", icon: "cpu", tint: Theme.muted) {
                    await model.toggleLM()
                }
            }

            if !model.message.isEmpty {
                Text(model.message)
                    .font(.system(size: 10))
                    .foregroundColor(Theme.muted)
                    .lineLimit(2)
                    .minimumScaleFactor(0.75)
            }

            Spacer(minLength: 0)
        }
        .padding(10)
        .overlay(alignment: .topTrailing) {
            Button {
                showSettings = true
            } label: {
                Image(systemName: "gearshape")
                    .font(.system(size: 14))
                    .foregroundColor(Theme.muted)
                    .padding(8)
            }
            .accessibilityLabel("Настройки")
        }
        .sheet(isPresented: $showSettings) {
            WatchSettingsView(model: model)
        }
        .task {
            // Авто-обновление, пока приложение открыто (как у iOS-клиента).
            while true {
                await model.refresh()
                try? await Task.sleep(nanoseconds: 10_000_000_000)
            }
        }
    }

    private func statusRow(_ name: String, state: Bool?, onLabel: String, offLabel: String) -> some View {
        HStack(spacing: 6) {
            Circle()
                .fill(state == nil ? Color.gray.opacity(0.6)
                      : (state == true ? Color.green : Color.red))
                .frame(width: 8, height: 8)
            Text(name)
                .font(.system(size: 13, weight: .semibold))
                .foregroundColor(Theme.title)
            Spacer(minLength: 4)
            Text(state == nil ? "…" : (state == true ? onLabel : offLabel))
                .font(.system(size: 12))
                .foregroundColor(state == nil ? Theme.muted
                              : (state == true ? Color.green : Color.red))
        }
    }

    private func actionButton(_ title: String, icon: String, tint: Color,
                              action: @escaping () async -> Void) -> some View {
        Button {
            Task { await action() }
        } label: {
            VStack(spacing: 3) {
                Image(systemName: icon).font(.system(size: 14))
                Text(title)
                    .font(.system(size: 10, weight: .medium))
                    .lineLimit(1)
                    .minimumScaleFactor(0.7)
            }
            .frame(maxWidth: .infinity)
        }
        .buttonStyle(.bordered)
        .tint(tint)
        .disabled(model.busy)
    }
}

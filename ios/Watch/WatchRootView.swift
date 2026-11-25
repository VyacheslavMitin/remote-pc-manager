import SwiftUI

/// Главный экран часов: статус ПК и LM Studio + 4 действия (2×2):
/// Пробудить · Гибернация · Вкл LM · Выкл LM.
/// Автопроверка статуса по интервалу + кнопка ручного пинга.
struct WatchRootView: View {
    @ObservedObject var model: WatchModel
    @State private var showSettings = false

    var body: some View {
        VStack(spacing: 7) {
            statusBlock
            actionsBlock
            messageBlock
            checkBlock
            unsyncBlock
        }
        .padding(8)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .overlay(alignment: .topTrailing) {
            Button { showSettings = true } label: {
                Image(systemName: "gearshape.fill")
                    .font(.system(size: 13))
                    .foregroundColor(Theme.muted)
                    .padding(6)
            }
            .buttonStyle(.plain)
        }
        .background(Theme.bg)
        .sheet(isPresented: $showSettings) {
            WatchSettingsView(model: model)
        }
        .task {
            model.startAutoCheck()   // автопроверка по интервалу (refresh внутри цикла)
        }
        .onDisappear {
            model.stopAutoCheck()
        }
    }

    // MARK: - Блоки (разбиты для typechecker Swift 6)

    private var statusBlock: some View {
        VStack(spacing: 4) {
            statusRow("ПК", model.pcUp)
            statusRow("LM Studio", model.lmRunning)
        }
    }

    private var actionsBlock: some View {
        VStack(spacing: 6) {
            HStack(spacing: 6) {
                action("power", "Пробудить", color: .green) { Task { await model.wol() } }
                action("moon.zzz.fill", "Гибри", color: .orange) { Task { await model.hibernate() } }
            }
            HStack(spacing: 6) {
                action("play.circle.fill", "Вкл LM", color: .cyan) { Task { await model.startLM() } }
                action("stop.circle.fill", "Выкл LM", color: .pink) { Task { await model.stopLM() } }
            }
        }
    }

    @ViewBuilder
    private var messageBlock: some View {
        if !model.message.isEmpty {
            Text(model.message)
                .font(.system(size: 10))
                .multilineTextAlignment(.center)
                .lineLimit(2)
                .minimumScaleFactor(0.7)
                .frame(maxWidth: .infinity)
                .foregroundColor(Theme.muted)
        }
    }

    private var checkBlock: some View {
        HStack(spacing: 6) {
            Text(model.lastCheck.map { "обновлено " + Self.timeFmt.string(from: $0) } ?? "ещё не проверено")
                .font(.system(size: 9))
                .foregroundColor(Theme.muted)
            Spacer(minLength: 2)
            Button {
                Task { await model.refresh() }
            } label: {
                Image(systemName: "arrow.triangle.2.circlepath")
                    .font(.system(size: 11))
                    .foregroundColor(Theme.muted)
            }
            .buttonStyle(.plain)
        }
    }

    @ViewBuilder
    private var unsyncBlock: some View {
        if model.looksUnsynced {
            Text("⚠️ Настройки пока дефолтные. С iPhone: Настройки → «Отправить на Apple Watch», затем закройте приложение на часах и откройте заново.")
                .font(.system(size: 9))
                .foregroundColor(Theme.danger)
                .lineLimit(4)
                .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    // MARK: - Вспомогательные

    static let timeFmt: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "HH:mm:ss"
        return f
    }()

    private func statusRow(_ title: String, _ value: Bool?) -> some View {
        let dot: Color
        let label: String
        let labelColor: Color
        switch value {
        case nil: dot = .gray; label = "…"; labelColor = Theme.muted
        case true: dot = .green; label = "работает"; labelColor = .green
        case false: dot = .red; label = "не в сети"; labelColor = .red
        }
        return HStack(spacing: 5) {
            Circle()
                .fill(dot)
                .frame(width: 7, height: 7)
            Text(title)
                .font(.system(size: 12, weight: .medium))
                .foregroundColor(Theme.text)
            Spacer(minLength: 2)
            Text(label)
                .font(.system(size: 11))
                .foregroundColor(labelColor)
        }
    }

    private func action(_ icon: String, _ label: String, color: Color,
                        action: @escaping () -> Void) -> some View {
        Button(action: action) {
            VStack(spacing: 2) {
                Image(systemName: icon)
                    .font(.system(size: 13))
                    .foregroundColor(color)
                Text(label)
                    .font(.system(size: 9))
                    .foregroundColor(Theme.text)
                    .lineLimit(1)
                    .minimumScaleFactor(0.6)
            }
            .frame(maxWidth: .infinity)
        }
        .buttonStyle(.bordered)
        .disabled(model.busy)
    }
}

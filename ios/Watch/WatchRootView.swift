import SwiftUI

/// Главный экран часов: только статусы (ПК, LM Studio, Strata) — кнопок действий
/// нет. Внизу — цель проверок (IP:порт, целиком, с уменьшением шрифта) и время
/// последней проверки + кнопка ручного обновления.
/// При «ПК не в сети» часы сами различают причины: NAS отвечает → молчит ПК;
/// NAS молчит → LAN заблокирован: на watchOS нет своей локальной сети-privacy
/// (TN3179), приconnected iPhone трафик проксируется через iPhone и разрешение
/// выдаётся на iPhone (Параметры → Конфиденциальность → Локальная сеть).
struct WatchRootView: View {
    @ObservedObject var model: WatchModel

    var body: some View {
        VStack(spacing: 8) {
            statusBlock
            Spacer(minLength: 0)
            lanHintBlock
            targetBlock
            checkBlock
        }
        .padding(8)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Theme.bg)
        .task {
            model.startAutoCheck()
        }
        .onDisappear {
            model.stopAutoCheck()
        }
    }

    // MARK: - Блоки

    private var statusBlock: some View {
        VStack(spacing: 5) {
            statusRow("ПК", model.pcUp)
            statusRow("LM Studio", model.lmUp)
            statusRow("Strata", model.strataUp)
        }
    }

    @ViewBuilder
    private var lanHintBlock: some View {
        if model.pcUp == false {
            if model.lanOK == true {
                Text("Часы видят NAS — не отвечает ПК (\(WatchConfig.pcHost):\(WatchConfig.pcPort)). Проверь: ПК включён, сервер запущен, брандмауэр не блокирует порт.")
                    .font(.system(size: 9))
                    .foregroundColor(Theme.muted)
                    .lineLimit(4)
                    .frame(maxWidth: .infinity, alignment: .leading)
            } else if model.lanOK == false {
                Text("Часы не видят локальную сеть: на iPhone — Параметры → Конфиденциальность и безопасность → Локальная сеть → разреши «Удалённый ПК» (трафик часов идёт через iPhone); часы и ПК — в одном Wi-Fi.")
                    .font(.system(size: 9))
                    .foregroundColor(Theme.danger)
                    .lineLimit(4)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
    }

    /// Цель проверок — одной строкой на всю ширину: IP:порт помещается целиком
    /// (шрифт уменьшается, если не влезает, — порт не обрезается).
    private var targetBlock: some View {
        Text("\(WatchConfig.pcHost):\(WatchConfig.pcPort) · LM :\(WatchConfig.lmPort) · Strata :\(WatchConfig.strataPort)")
            .font(.system(size: 10))
            .foregroundColor(Theme.muted)
            .lineLimit(1)
            .minimumScaleFactor(0.55)
            .frame(maxWidth: .infinity, alignment: .center)
    }

    private var checkBlock: some View {
        HStack(spacing: 6) {
            Text(model.lastCheck.map { "обновлено " + Self.timeFmt.string(from: $0) } ?? "ещё не проверено")
                .font(.system(size: 9))
                .foregroundColor(Theme.muted)
                .lineLimit(1)
                .minimumScaleFactor(0.7)
            Button {
                Task { await model.refresh() }
            } label: {
                Image(systemName: "arrow.triangle.2.circlepath")
                    .font(.system(size: 12))
                    .foregroundColor(Theme.muted)
            }
            .buttonStyle(.plain)
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
}

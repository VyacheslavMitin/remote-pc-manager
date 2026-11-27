import SwiftUI
import WatchKit

/// Главный экран часов: сверху статусы одной строкой (точки ПК/LMS/Str), под
/// ними — 6 кнопок в 3 ряда (монохромные эмодзи на цветном фоне, как в
/// веб-клиенте):
///   ряд 1 (ПК):    пробудить (⏻, синий) / гибернация (☾, нейтральная)
///   ряд 2 (LMS):   запустить (▶, зелёный) / остановить (⏹, красный)
///   ряд 3 (Str):   запустить (▶, зелёный) / остановить (⏹, красный)
/// Внизу — цель проверок и время последней проверки; сейчас скрыты
/// (showFooterInfo = false) — код вывода сохранён.
/// При «ПК не в сети» часы сами различают причины: NAS отвечает → молчит ПК;
/// NAS молчит → LAN заблокирован: на watchOS нет своей локальной сети-privacy
/// (TN3179), при connected iPhone трафик проксируется через iPhone и разрешение
/// выдаётся на iPhone (Параметры → Конфиденциальность → Локальная сеть).
struct WatchRootView: View {
    @ObservedObject var model: WatchModel
    /// Нижняя информационная строка (цель проверок, время, ручное обновление)
    /// пока не выводится; код блоков сохранён.
    private let showFooterInfo = false
    /// Отправка команды идёт одна за раз — на время кнопки неактивны.
    @State private var busyCommand: String? = nil

    var body: some View {
        ScrollView {
            VStack(spacing: 6) {
                statusBlock
                buttonsBlock
                if showFooterInfo {
                    lanHintBlock
                    targetBlock
                    checkBlock
                }
            }
            .frame(maxWidth: .infinity)
            .padding(.bottom, 8)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
        .background(Theme.bg)
        .task {
            model.startAutoCheck()
        }
        .onDisappear {
            model.stopAutoCheck()
        }
    }

    // MARK: - Блоки

    /// Статусы одной компактной строкой (точка + короткая подпись) — экономия
    /// по вертикали: цвет точки = работает / не в сети / не проверено.
    private var statusBlock: some View {
        HStack(spacing: 6) {
            statusChip("ПК", model.pcUp)
            statusChip("LMS", model.lmUp)
            statusChip("Str", model.strataUp)
        }
    }

    /// 6 кнопок, 3 ряда по 2, слева подпись ряда. Эмодзи с \u{FE0E} —
    /// текстовое (монохромное) начертание, иначе watchOS рисует цветные emoji.
    /// Цвета — как в веб/десктоп-клиентах: пробуждение ПК — accent
    /// (btn-primary), запуск LMS/Str — success (btn-success, ▶), остановка —
    /// danger (btn-danger, ⏹), гибернация — нейтральная.
    private var buttonsBlock: some View {
        VStack(spacing: 3) {
            buttonRow("ПК",
                      on: ("⏻\u{FE0E}", Theme.accent, { await model.wakePC() }),
                      off: ("\u{263E}", Theme.buttonBG, { await model.sendCommand("hibernate") }))
            buttonRow("LMS",
                      on: ("\u{25B6}\u{FE0E}", Theme.success, { await model.sendCommand("start_lmstudio") }),
                      off: ("\u{23F9}\u{FE0E}", Theme.danger, { await model.sendCommand("stop_lmstudio") }))
            buttonRow("Str",
                      on: ("\u{25B6}\u{FE0E}", Theme.success, { await model.sendCommand("start_strata") }),
                      off: ("\u{23F9}\u{FE0E}", Theme.danger, { await model.sendCommand("stop_strata") }))
        }
    }

    /// Ряд кнопок: короткая подпись слева + две компактные кнопки.
    private func buttonRow(_ label: String,
                           on: (String, Color, () async -> Bool),
                           off: (String, Color, () async -> Bool)) -> some View {
        HStack(spacing: 3) {
            Text(label)
                .font(.system(size: 9, weight: .medium))
                .foregroundColor(Theme.muted)
                .frame(width: 22, alignment: .leading)
            cmdButton(on.0, tint: on.1, on.2)
            cmdButton(off.0, tint: off.1, off.2)
        }
    }

    /// Кнопка команды: эмодзи на цветном фоне (как btn-primary/success/danger
    /// в веб-клиенте); вибрация об успехе/неудаче и немедленное обновление
    /// статусов (после пробуждения ПК «загорится» на следующем автоцикле).
    private func cmdButton(_ symbol: String, tint: Color,
                           _ action: @escaping () async -> Bool) -> some View {
        Button {
            guard busyCommand == nil else { return }
            busyCommand = symbol
            Task {
                let ok = await action()
                WKInterfaceDevice.current().play(ok ? .success : .failure)
                busyCommand = nil
                await model.refresh()
            }
        } label: {
            Text(symbol)
                .font(.system(size: 13))
                .frame(maxWidth: .infinity, minHeight: 32)
        }
        .buttonStyle(.borderedProminent)
        .tint(tint)
        .controlSize(.mini)
        .disabled(busyCommand != nil)
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

    private func statusChip(_ title: String, _ value: Bool?) -> some View {
        let dot: Color
        switch value {
        case nil: dot = .gray
        case true: dot = .green
        case false: dot = .red
        }
        return HStack(spacing: 3) {
            Circle()
                .fill(dot)
                .frame(width: 6, height: 6)
            Text(title)
                .font(.system(size: 10, weight: .medium))
                .foregroundColor(Theme.text)
        }
    }
}

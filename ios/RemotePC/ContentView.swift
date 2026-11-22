import SwiftUI

/// Главный экран: секции ПК / LM Studio + нижняя строка статуса.
/// Порт MainWindow из client/app.py (тёмная тема из client/theme.py).
struct ContentView: View {
    @StateObject private var model: AppModel
    @Environment(\.scenePhase) private var scenePhase
    @State private var showSettings = false

    init(cfg: ConfigStore) {
        _model = StateObject(wrappedValue: AppModel(cfg: cfg))
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 14) {
                    pcSection
                    lmSection
                }
                .padding(.horizontal, 14)
                .padding(.top, 6)
            }
            .background(Theme.bg.ignoresSafeArea())
            .navigationTitle("Удалённый ПК")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button { showSettings = true } label: {
                        Image(systemName: "gearshape.fill")
                            .font(.system(size: 18))
                    }
                    .tint(Theme.rowname)
                }
            }
            .safeAreaInset(edge: .bottom) { bottomBar }
        }
        .tint(Theme.accent)
        .sheet(isPresented: $showSettings) {
            SettingsView(model: model) { model.startAutoCheck() }
        }
        .onAppear {
            if scenePhase == .active { model.startAutoCheck() }
        }
        .onChange(of: scenePhase) { phase in
            // iOS: фоновый поллинг запрещён — проверяем, пока приложение открыто
            if phase == .active { model.startAutoCheck() } else { model.stopAutoCheck() }
        }
    }

    // MARK: - секции

    private var pcSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(model.pcTitle)
                .font(.system(size: 15, weight: .bold))
                .foregroundColor(Theme.title)
                .lineLimit(2)

            StatusRow(
                dot: Theme.dot(model.pcState),
                text: model.pcState == nil ? "—" : (model.pcState == true ? "в сети" : "не отвечает"),
                buttonTitle: model.checking ? "Проверка…" : "Проверить",
                disabled: model.busy,
                action: { Task { await model.manualCheckPC() } }
            )

            VStack(spacing: 10) {
                ActionButton(text: "Пробудить ПК", icon: "power",
                             color: Theme.accent, disabled: model.busy) {
                    Task { await model.wol() }
                }
                ActionButton(text: "Гибернация", icon: "moon.zzz.fill",
                             color: Theme.buttonBG, border: Theme.border, fg: Theme.text,
                             disabled: model.busy) {
                    Task { await model.hibernate() }
                }
            }
        }
        .padding(14)
        .background(
            RoundedRectangle(cornerRadius: 12)
                .fill(Theme.blockBG)
                .overlay(RoundedRectangle(cornerRadius: 12).stroke(Theme.blockBorder))
        )
    }

    private var lmSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(model.lmTitle)
                .font(.system(size: 15, weight: .bold))
                .foregroundColor(Theme.title)
                .lineLimit(2)

            StatusRow(
                dot: Theme.dot(model.lmState),
                text: model.lmState == nil ? "—" : (model.lmState == true ? "работает" : "не запущена"),
                buttonTitle: model.checking ? "Проверка…" : "Проверить",
                disabled: model.busy,
                action: { Task { await model.manualCheckLM() } }
            )

            VStack(spacing: 10) {
                ActionButton(text: "Включить", icon: "play.fill",
                             color: Theme.success, disabled: model.busy) {
                    Task { await model.startLM() }
                }
                ActionButton(text: "Выключить", icon: "stop.fill",
                             color: Theme.danger, disabled: model.busy) {
                    Task { await model.stopLM() }
                }
            }
        }
        .padding(14)
        .background(
            RoundedRectangle(cornerRadius: 12)
                .fill(Theme.blockBG)
                .overlay(RoundedRectangle(cornerRadius: 12).stroke(Theme.blockBorder))
        )
    }

    // MARK: - низ

    private var bottomBar: some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(model.statusLine)
                .font(.system(size: 12))
                .lineLimit(2)
            HStack {
                Text(model.autoLine)
                Spacer()
                Text("IP: \(model.cfg.pcIP)")
            }
            .font(.system(size: 11))
        }
        .foregroundColor(Theme.muted)
        .padding(.horizontal, 14)
        .padding(.vertical, 8)
        .background(Theme.bg2)
    }
}

// MARK: - переиспользуемые элементы

/// Строка «точка · текст · [Проверить]» (как .statusrow в app.py).
struct StatusRow: View {
    let dot: String
    let text: String
    let buttonTitle: String
    var disabled: Bool = false
    let action: () -> Void

    var body: some View {
        HStack(spacing: 8) {
            Text(dot).font(.system(size: 15))
            Text(text)
                .font(.system(size: 13))
                .foregroundColor(Theme.muted)
            Spacer()
            Button(buttonTitle, action: action)
                .font(.system(size: 13, weight: .semibold))
                .foregroundColor(disabled ? Theme.muted : Theme.text)
                .padding(.horizontal, 14)
                .padding(.vertical, 7)
                .background(RoundedRectangle(cornerRadius: 8).fill(Theme.buttonBG))
                .overlay(RoundedRectangle(cornerRadius: 8).stroke(Theme.border))
        }
        .disabled(disabled)
    }
}

/// Цветная кнопка действия (как #primary/#success/#danger в theme.py).
/// border/fg заданы — нейтральная кнопка (как обычная на веб/десктопе).
struct ActionButton: View {
    let text: String
    var icon: String? = nil
    let color: Color
    var border: Color? = nil
    var fg: Color? = nil
    var disabled: Bool = false
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 6) {
                if let icon { Image(systemName: icon).font(.system(size: 13)) }
                Text(text)
            }
            .font(.system(size: 14, weight: .semibold))
            .foregroundColor(disabled ? (fg ?? .white).opacity(0.5) : (fg ?? .white))
            .frame(maxWidth: .infinity)
            .padding(.vertical, 11)
            .background(
                RoundedRectangle(cornerRadius: 8)
                    .fill(disabled ? color.opacity(0.4) : color)
                    .border(border ?? Color.clear)
            )
        }
        .disabled(disabled)
    }
}

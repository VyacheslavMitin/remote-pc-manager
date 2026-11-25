import SwiftUI
import WatchConnectivity

/// Настройки для Apple Watch: IP, MAC, порт, relay (URL + токен).
///
/// Перенос с iPhone — только через WatchConnectivity (UIPasteboard в watchOS
/// недоступен, App Group не общий между устройствами): кнопка
/// «Синхронизировать с iPhone» тянет application context, отправленный
/// из iOS-приложения (Настройки → «Отправить на Apple Watch» / «Сохранить»).
///
/// После сохранения показываем «Сохранённые значения», прочитанные заново
/// из ConfigStore (источник истины) — видно, что реально записано.
struct WatchSettingsView: View {
    @ObservedObject var model: WatchModel
    @State private var ip: String
    @State private var mac: String
    @State private var port: String
    @State private var relayURL: String
    @State private var relayToken: String
    @State private var saved = false
    @State private var savedMsg: String?
    @State private var syncMsg: String?

    init(model: WatchModel) {
        self.model = model
        _ip = State(initialValue: model.cfg.pcIP)
        _mac = State(initialValue: model.cfg.pcMAC)
        _port = State(initialValue: String(model.cfg.serverPort))
        _relayURL = State(initialValue: model.cfg.wolRelayURL)
        _relayToken = State(initialValue: model.cfg.wolRelayToken)
    }

    private var tokenTrimmed: String {
        relayToken.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    var body: some View {
        Form {
            Section {
                TextField("IP ПК (например, 192.168.1.144)", text: $ip)
                    .autocorrectionDisabled()
                    .textInputAutocapitalization(.never)
                    .font(.system(size: 13))
                TextField("MAC для WoL (AA:BB:CC:DD:EE:FF)", text: $mac)
                    .autocorrectionDisabled()
                    .textInputAutocapitalization(.never)
                    .font(.system(size: 13))
                HStack {
                    Text("Порт сервера")
                        .font(.system(size: 13))
                        .foregroundColor(Theme.muted)
                    Spacer()
                    TextField("8787", text: $port)
                        .multilineTextAlignment(.trailing)
                        .frame(width: 56)
                        .font(.system(size: 13))
                }
                TextField("URL relay-сервера", text: $relayURL)
                    .autocorrectionDisabled()
                    .textInputAutocapitalization(.never)
                    .font(.system(size: 13))
            } header: {
                Text("Соединение")
            }

            Section {
                TextField("Токен целиком, как на iPhone", text: $relayToken)
                    .autocorrectionDisabled()
                    .textInputAutocapitalization(.never)
                    .font(.system(size: 12))
                // Предпросмотр: сколько символов и хвост — чтобы убедиться,
                // что введён весь токен, а не только начало.
                HStack(spacing: 6) {
                    Text("Символов: \(tokenTrimmed.count)")
                    Spacer()
                    if tokenTrimmed.count >= 4 {
                        Text("…\(String(tokenTrimmed.suffix(6)))")
                    }
                }
                .font(.system(size: 11))
                .foregroundColor(Theme.muted)
            } header: {
                Text("Relay-токен (WoL)")
            } footer: {
                Text("Нужен весь токен целиком. Если вводите вручную — сверьте с предпросмотром, что все символы на месте.")
                    .font(.system(size: 11))
                    .foregroundColor(Theme.muted)
            }

            Section {
                // Перенос с iPhone — только WatchConnectivity (UIPasteboard в
                // watchOS не существует, App Group не общий). Контекст
                // доставляется часам автоматически, когда приложение
                // становится активным — поэтому «кнопки» нет: отправь на
                // iPhone, закрой и открой приложение на часах.
                Text("Сейчас: закройте приложение на часах и откройте заново — если на iPhone нажали «Отправить на Apple Watch», настройки применятся автоматически.")
                    .font(.system(size: 11))
                    .foregroundColor(Theme.muted)
                if let sm = syncMsg {
                    Text(sm)
                        .font(.system(size: 11))
                        .foregroundColor(sm.hasPrefix("✅") ? Theme.success : Theme.danger)
                }
            } header: {
                Text("С iPhone")
            } footer: {
                Text("Как перенести: на iPhone — Настройки → «Отправить на Apple Watch» (или «Сохранить», он тоже отправляет). На часах — просто откройте приложение заново; IP, порт и токен подтянутся и сохранятся сами.")
                    .font(.system(size: 11))
                    .foregroundColor(Theme.muted)
            }

            // Сохранённые значения: читаем из ConfigStore — источник истины.
            Section {
                LabeledContent("IP", value: model.cfg.pcIP)
                LabeledContent("MAC", value: model.cfg.pcMAC)
                LabeledContent("Порт", value: String(model.cfg.serverPort))
                LabeledContent("Токен", value: model.cfg.wolRelayToken.isEmpty
                    ? "—"
                    : "…\(String(model.cfg.wolRelayToken.suffix(6))) (\(model.cfg.wolRelayToken.count) симв.)")
            } header: {
                Text("Сохранённые значения")
            }

            Section {
                Button("Сохранить") { save() }
                    .font(.system(size: 16, weight: .semibold))
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 2)
                if saved {
                    Text("✅ Сохранено")
                        .font(.system(size: 13))
                        .foregroundColor(Theme.success)
                }
                if let m = savedMsg {
                    Text(m)
                        .font(.system(size: 11))
                        .foregroundColor(Theme.danger)
                }
            }
        }
        .navigationTitle("Настройки")
    }

    private func save() {
        let ipV = ip.trimmingCharacters(in: .whitespacesAndNewlines)
        let macV = mac.trimmingCharacters(in: .whitespacesAndNewlines)
        let tokenV = relayToken.trimmingCharacters(in: .whitespacesAndNewlines)
        let urlV = relayURL.trimmingCharacters(in: .whitespacesAndNewlines)
        let portV = Int(port.trimmingCharacters(in: .whitespaces))

        if ipV.isEmpty || macV.isEmpty || tokenV.isEmpty || (portV == nil || portV! < 1 || portV! > 65535) {
            savedMsg = "Заполните IP, MAC, порт и токен"
            saved = false
            return
        }

        model.cfg.pcIP = ipV
        model.cfg.pcMAC = macV
        model.cfg.serverPort = portV!
        model.cfg.wolRelayURL = urlV
        model.cfg.wolRelayToken = tokenV

        // Сохранение + read-back: если на диске не то — показываем сразу,
        // а не молчим (тихий сброс был главной жалобой).
        let ok = model.cfg.save()
        let readBack = ConfigStore()
        let match = readBack.pcIP == ipV
            && readBack.pcMAC == macV
            && readBack.serverPort == portV!
            && readBack.wolRelayToken == tokenV

        if ok && match {
            saved = true
            savedMsg = nil
            model.reload()
            Task { await model.refresh() }
        } else {
            saved = false
            savedMsg = "⚠️ Не сохранилось. Попробуйте ещё раз — и сверьте с разделом «Сохранённые значения»."
        }
    }

}

import SwiftUI

/// Настройки часов (те же поля, что у iPhone-приложения). Если часы спарены
/// с тем же iPhone, конфиг общий через App Group — этот экран нужен, только
/// если часы не спарены с айфоном, где уже введены настройки.
struct WatchSettingsView: View {
    let model: WatchModel
    @State private var ip: String
    @State private var mac: String
    @State private var relayURL: String
    @State private var relayToken: String
    @State private var saved = false

    init(model: WatchModel) {
        self.model = model
        _ip = State(initialValue: model.cfg.pcIP)
        _mac = State(initialValue: model.cfg.pcMAC)
        _relayURL = State(initialValue: model.cfg.wolRelayURL)
        _relayToken = State(initialValue: model.cfg.wolRelayToken)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Настройки")
                .font(.system(size: 15, weight: .bold))
                .foregroundColor(Theme.title)

            field("IP ПК", $ip)
            field("MAC", $mac)
            field("Relay (веб-сервер)", $relayURL)
            field("Токен relay", $relayToken)

            if saved {
                Text("Сохранено")
                    .font(.system(size: 11))
                    .foregroundColor(Color.green)
            }

            Spacer(minLength: 4)

            Button("Сохранить") {
                save()
            }
            .buttonStyle(.borderedProminent)
            .tint(Theme.accent)
            .disabled(model.busy)
        }
        .padding(12)
    }

    private func field(_ label: String, _ text: Binding<String>) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label)
                .font(.system(size: 10))
                .foregroundColor(Theme.muted)
            TextField(label, text: text)
                .font(.system(size: 13))
                .autocorrectionDisabled()
                .textInputAutocapitalization(.never)
                .padding(6)
                .background(Theme.inputBG)
                .cornerRadius(6)
        }
    }

    private func save() {
        model.cfg.pcIP = ip.trimmingCharacters(in: .whitespaces)
        model.cfg.pcMAC = mac.trimmingCharacters(in: .whitespaces)
        model.cfg.wolRelayURL = relayURL.trimmingCharacters(in: .whitespaces)
        model.cfg.wolRelayToken = relayToken.trimmingCharacters(in: .whitespaces)
        model.cfg.save()
        saved = true
    }
}

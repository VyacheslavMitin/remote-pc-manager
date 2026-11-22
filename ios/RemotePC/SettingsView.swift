import SwiftUI

/// Настройки (порт SettingsDialog из client/settings_dialog.py).
/// Сохраняет в ConfigStore (UserDefaults) и, как десктоп, при смене порта LM
/// шлёт на сервер set_lm_port.
struct SettingsView: View {
    @ObservedObject var model: AppModel
    let onSaved: () -> Void
    @Environment(\.dismiss) private var dismiss

    @State private var ip: String
    @State private var mac: String
    @State private var serverPort: String
    @State private var lmPort: String
    @State private var autoOn: Bool
    @State private var interval: Int
    @State private var saveError: String?

    init(model: AppModel, onSaved: @escaping () -> Void) {
        self.model = model
        self.onSaved = onSaved
        let c = model.cfg
        _ip = State(initialValue: c.pcIP)
        _mac = State(initialValue: c.pcMAC)
        _serverPort = State(initialValue: String(c.serverPort))
        _lmPort = State(initialValue: String(c.lmAPIPort))
        _autoOn = State(initialValue: c.autoCheckEnabled)
        _interval = State(initialValue: c.autoCheckIntervalS)
    }

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    TextField("IP компьютера", text: $ip)
                        .keyboardType(.decimalPad)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                    TextField("MAC-адрес (аа:bb:cc:dd:ee:ff)", text: $mac)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                } header: {
                    Text("ПК (Wake-on-LAN)")
                }

                Section {
                    TextField("Порт сервера", text: $serverPort)
                        .keyboardType(.numberPad)
                    TextField("Порт LM Studio (API)", text: $lmPort)
                        .keyboardType(.numberPad)
                } header: {
                    Text("Сервер")
                }

                Section {
                    Toggle("Автопроверка", isOn: $autoOn)
                    if autoOn {
                        Stepper("Каждые \(interval) с", value: $interval, in: 2...60)
                    }
                }

                Section {
                    Text("Windows: ipconfig (IPv4-адрес) и PowerShell: Get-NetAdapter | Select Name, MacAddress. ПК и айфон должны быть в одной Wi-Fi-сети.")
                        .font(.system(size: 12))
                        .foregroundColor(Theme.muted)
                }

                if let e = saveError {
                    Section {
                        Text(e).foregroundColor(Theme.danger)
                    }
                }
            }
            .navigationTitle("Настройки")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Отмена") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Сохранить") { save() }
                        .fontWeight(.semibold)
                }
            }
        }
    }

    private func save() {
        saveError = nil
        let ipV = ip.trimmingCharacters(in: .whitespaces)
        guard !ipV.isEmpty else {
            saveError = "Укажите IP компьютера"
            return
        }
        guard let sp = Int(serverPort.trimmingCharacters(in: .whitespaces)),
              sp >= 1, sp <= 65535 else {
            saveError = "Порт сервера: число от 1 до 65535"
            return
        }
        guard let lp = Int(lmPort.trimmingCharacters(in: .whitespaces)),
              lp >= 1, lp <= 65535 else {
            saveError = "Порт LM Studio: число от 1 до 65535"
            return
        }

        let oldLM = model.cfg.lmAPIPort
        model.cfg.pcIP = ipV
        model.cfg.pcMAC = ConfigStore.normalizeMAC(mac)
        model.cfg.serverPort = sp
        model.cfg.lmAPIPort = lp
        model.cfg.autoCheckEnabled = autoOn
        model.cfg.autoCheckIntervalS = max(2, interval)
        model.cfg.save()

        // Как десктоп: при смене порта LM — сразу применить на сервере.
        if lp != oldLM {
            let api = ApiClient(host: ipV, port: sp)
            Task { try? await api.command("set_lm_port", args: ["port": lp], timeout: 4) }
        }

        onSaved()
        dismiss()
    }
}

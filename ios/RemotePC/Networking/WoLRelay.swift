import Foundation

/// WoL через relay: `POST {relay}/wol` на веб-сервер, который сам шлёт magic
/// packet broadcast'ом (iOS/Apple Watch не умеют UDP-broadcast — entitlement
/// multicast Apple выдает только платным аккаунтам). Та же схема, что у
/// веб-версии. Контракт: web/serve.py → {"ok": true, "sent", "to", "mac"}.
enum WoLRelay {

    struct RelayError: LocalizedError {
        let message: String
        var errorDescription: String? { message }
    }

    /// Отправить WoL через веб-сервер. Возвращает (сколько пакетов, куда, MAC).
    /// `relayURL` — базовый адрес сервера, без /wol (http://192.168.1.40:8090).
    static func send(relayURL: String, token: String, mac: String) async throws
        -> (sent: Int, to: String, mac: String) {
        let raw = relayURL.trimmingCharacters(in: .whitespaces)
        guard !raw.isEmpty, let base = URL(string: raw) else {
            throw RelayError(message: "relay: не задан адрес веб-сервера")
        }
        var req = URLRequest(url: base.appendingPathComponent("wol"))
        req.httpMethod = "POST"
        req.timeoutInterval = 8
        req.setValue("application/json; charset=utf-8", forHTTPHeaderField: "Content-Type")
        let t = token.trimmingCharacters(in: .whitespaces)
        if !t.isEmpty {
            req.setValue(t, forHTTPHeaderField: "X-Token")
        }
        req.httpBody = try JSONSerialization.data(withJSONObject: ["mac": mac])

        let (data, response) = try await URLSession.shared.data(for: req)
        guard let http = response as? HTTPURLResponse else {
            throw RelayError(message: "relay: некорректный ответ сервера")
        }
        if http.statusCode == 401 {
            throw RelayError(message: "relay: неверный или не задан токен (401)")
        }
        guard (200..<300).contains(http.statusCode) else {
            throw RelayError(message: "relay: HTTP \(http.statusCode) от сервера")
        }
        let json = (try? JSONSerialization.jsonObject(with: data) as? [String: Any]) ?? [:]
        guard (json["ok"] as? Bool) == true else {
            let msg = json["error"] as? String ?? "неизвестная ошибка"
            throw RelayError(message: "relay: \(msg)")
        }
        return ((json["sent"] as? Int) ?? 0,
                (json["to"] as? String) ?? "?",
                (json["mac"] as? String) ?? mac)
    }
}

import Foundation

/// Ошибка сервера/сети с человекочитаемым сообщением (как ServerAPIError в server_api.py).
struct ServerAPIError: LocalizedError {
    let message: String
    var errorDescription: String? { message }
}

/// HTTP/JSON-клиент сервера remote-pc-manager (POST /command).
/// iOS-порт client/server_api.py.
final class ApiClient {
    private let host: String
    private let port: Int

    init(host: String, port: Int) {
        self.host = host.trimmingCharacters(in: .whitespaces)
        self.port = port
    }

    /// Отправить команду и разобрать JSON-ответ.
    /// `args` — дополнительные поля тела (например, set_lm_port → {"port": 1234}).
    func command(_ name: String,
                 args: [String: Any] = [:],
                 timeout: TimeInterval = 8.0) async throws -> [String: Any] {
        guard !host.isEmpty, let url = URL(string: "http://\(host):\(port)/command") else {
            throw ServerAPIError(message: "Некорректный адрес ПК: \(host):\(port)")
        }

        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.timeoutInterval = timeout
        req.setValue("application/json; charset=utf-8", forHTTPHeaderField: "Content-Type")
        req.setValue("rpcm-client-ios/1.0", forHTTPHeaderField: "User-Agent")
        var body: [String: Any] = ["command": name]
        for (k, v) in args { body[k] = v }
        req.httpBody = try JSONSerialization.data(withJSONObject: body)

        do {
            let (data, resp) = try await URLSession.shared.data(for: req)
            guard let http = resp as? HTTPURLResponse else {
                throw ServerAPIError(message: "Не удалось связаться с ПК")
            }
            if http.statusCode < 200 || http.statusCode >= 300 {
                if let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                   let err = obj["error"] as? String {
                    throw ServerAPIError(message: err)
                }
                throw ServerAPIError(message: "HTTP \(http.statusCode)")
            }
            guard let obj = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
                throw ServerAPIError(message: "Некорректный ответ сервера")
            }
            if (obj["ok"] as? Bool) == false {
                throw ServerAPIError(message: (obj["error"] as? String) ?? "Команда завершилась с ошибкой")
            }
            return obj
        } catch let e as ServerAPIError {
            throw e
        } catch is URLError {
            throw ServerAPIError(message: "Не удалось связаться с ПК (проверьте IP, порт и Wi-Fi)")
        } catch {
            throw ServerAPIError(message: "Ошибка сети: \(error.localizedDescription)")
        }
    }
}

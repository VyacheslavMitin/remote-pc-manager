import Foundation

/// Константы watch-клиента — всё захардкожено в сборке, настроек на часах нет.
/// При переезде ПК/NAS на другие адреса менять здесь и пересобирать часы.
enum WatchConfig {
    /// ПК (сервер remote-pc-manager).
    static let pcHost = "192.168.1.144"
    static let pcPort = 8787
    /// LM Studio на ПК (OpenAI-совместимый сервер, GET /v1/models).
    static let lmPort = 4321
    /// Strata на ПК (llama.cpp-совместимый сервер, GET /health без ключа).
    static let strataPort = 8090
    /// NAS с веб-релеем — используется ТОЛЬКО для диагностики «видят ли часы
    /// локальную сеть» (любой HTTP-ответ = путь есть).
    static let nasHost = "192.168.1.40"
    static let nasPort = 8090

    /// Интервал автопроверки статуса, с.
    static let autoCheckIntervalS = 10
}

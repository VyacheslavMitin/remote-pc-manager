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
    /// NAS с веб-релеем — диагностика «видят ли часы локальную сеть» и
    /// пробуждение ПК (POST /wol: выключенный ПК не достать, magic packet
    /// шлёт всегда включённый NAS).
    static let nasHost = "192.168.1.40"
    static let nasPort = 8090
    /// Токен WoL (wol_token в client/config.json на NAS: принимается только на POST /wol).
    static let relayToken = "6a686e46e75f09cc50304c7a028339273aa99919048a587d"

    /// Интервал автопроверки статуса, с.
    static let autoCheckIntervalS = 10
}

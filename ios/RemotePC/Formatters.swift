import Foundation

/// Форматирование полей статусного ответа — порты _format_uptime/_format_context/
/// _format_gb/_format_version из client/app.py (тексты совпадают).
enum Format {

    /// "3 дн 4 ч 12 мин"
    static func uptime(_ s: Int?) -> String {
        guard let s, s >= 0 else { return "" }
        let d = s / 86400, h = (s % 86400) / 3600, m = (s % 3600) / 60
        var parts: [String] = []
        if d > 0 { parts.append("\(d) дн") }
        if h > 0 { parts.append("\(h) ч") }
        if m > 0 || parts.isEmpty { parts.append("\(m) мин") }
        return parts.joined(separator: " ")
    }

    /// «64K» / «128K» (контекст модели в токенах): 65536 -> «64K»,
    /// 131072 -> «128K»; не кратное 1024 — как есть (100000 -> «100000»).
    /// Как в _format_context (app.py) и formatContext (web).
    static func context(_ n: Int?) -> String {
        guard let n, n > 0 else { return "" }
        if n % 1024 == 0 {
            return "\(n / 1024)K"
        }
        return "\(n)"
    }

    /// "12.3 ГБ" (МБ → ГБ)
    static func gb(_ mb: Int?) -> String {
        guard let mb, mb > 0 else { return "" }
        let v = Double(mb) / 1024
        return v < 10 ? String(format: "%.1f ГБ", v) : String(format: "%.0f ГБ", v)
    }

    /// "v0.3.16" → "0.3.16", "0.3.16.0" → "0.3.16"
    static func version(_ s: String?) -> String {
        guard var v = s?.trimmingCharacters(in: .whitespaces) else { return "" }
        if v.hasPrefix("v") || v.hasPrefix("V") { v.removeFirst() }
        if v.hasSuffix(".0") { v = String(v.dropLast(2)) }
        return v
    }

    /// "Windows 11" → "Win 11" (как в _set_pc_title)
    static func osName(_ s: String?) -> String {
        guard var o = s?.trimmingCharacters(in: .whitespaces) else { return "" }
        o = o.replacingOccurrences(of: "Windows", with: "Win")
        return o
    }
}

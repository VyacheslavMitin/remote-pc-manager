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

    /// "128k" / "1.5M" (контекст модели в токенах)
    static func context(_ n: Int?) -> String {
        guard let n, n > 0 else { return "" }
        if n >= 1_000_000 {
            let v = Double(n) / 1_000_000
            return v == v.rounded() ? String(format: "%.0fM", v) : String(format: "%.1fM", v)
        }
        return "\(n / 1000)k"
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

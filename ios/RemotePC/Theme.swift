import SwiftUI

/// Палитра 1-в-1 с client/theme.py (тёмная тема PySide6-клиента).
enum Theme {
    static let bg = Color(hex: 0x1E1E20)
    static let bg2 = Color(hex: 0x242428)
    static let blockBG = Color(hex: 0x232327)
    static let blockBorder = Color(hex: 0x34343A)
    static let cardBG = Color(hex: 0x2A2A30)
    static let border = Color(hex: 0x3A3A40)
    static let buttonBG = Color(hex: 0x2A2A2E)
    static let inputBG = Color(hex: 0x222226)
    static let text = Color(hex: 0xE6E6E6)
    static let title = Color(hex: 0xF2F2F4)
    static let rowname = Color(hex: 0xCFCFD4)
    static let muted = Color(hex: 0x9A9AA2)
    static let accent = Color(hex: 0x1F6FEB)
    static let success = Color(hex: 0x1A7F37)
    static let danger = Color(hex: 0xB62324)

    /// Статус-точка, как у десктопного и веб-клиентов.
    static func dot(_ state: Bool?) -> String {
        switch state {
        case nil: return "⚪"
        case true: return "🟢"
        case false: return "🔴"
        }
    }
}

extension Color {
    init(hex: UInt32) {
        self.init(
            .sRGB,
            red: Double((hex >> 16) & 0xFF) / 255,
            green: Double((hex >> 8) & 0xFF) / 255,
            blue: Double(hex & 0xFF) / 255
        )
    }
}

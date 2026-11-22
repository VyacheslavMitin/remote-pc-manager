import Foundation

/// Wake-on-LAN: magic packet = 6×0xFF + 16×MAC. iOS-порт client/wol.py.
///
/// UDP broadcast на iOS не поддерживается фреймворком Network (TN3151) —
/// используем BSD-сокеты (официальный способ). На iOS broadcast требует
/// entitlement com.apple.developer.networking.multicast; без него sendto()
/// вернёт EPERM — тогда остаётся unicast на IP ПК (работает без entitlement).
enum WoL {

    /// Magic packet из MAC (разделители «-»/«:»/пробелы допустимы).
    static func magicPacket(macRaw: String) throws -> Data {
        let hex = Array(macRaw.lowercased().filter { "0123456789abcdef".contains($0) })
        guard hex.count == 12 else {
            throw WoLError.badMAC
        }
        var mac: [UInt8] = []
        for i in stride(from: 0, to: 12, by: 2) {
            guard let byte = UInt8(String(hex[i...i + 1]), radix: 16) else {
                throw WoLError.badMAC
            }
            mac.append(byte)
        }
        var packet = [UInt8](repeating: 0xFF, count: 6)
        for _ in 0..<16 { packet.append(contentsOf: mac) }
        return Data(packet)
    }

    static func normalizedMAC(_ raw: String) -> String {
        ConfigStore.normalizeMAC(raw)
    }

    /// Отправить magic packet. Возвращает (сколько пакетов, куда, MAC).
    /// Broadcast пробует первым (может не пройти без entitlement), unicast — запасной.
    @discardableResult
    static func send(macRaw: String, unicastIP: String, count: Int = 3) throws
        -> (sent: Int, to: String, mac: String) {
        let packet = try magicPacket(macRaw: macRaw)
        let mac = ConfigStore.normalizeMAC(macRaw)

        var sent = 0
        var used: [String] = []

        if sendPacket(packet, to: "255.255.255.255", times: count, broadcast: true) {
            sent += count
            used.append("255.255.255.255")
        }

        let ip = unicastIP.trimmingCharacters(in: .whitespaces)
        if !ip.isEmpty, ip != "255.255.255.255",
           sendPacket(packet, to: ip, times: count, broadcast: false) {
            sent += count
            used.append(ip)
        }

        guard sent > 0 else {
            throw WoLError.sendFailed
        }
        return (sent, used.joined(separator: ", "), mac)
    }

    // MARK: - BSD sockets

    /// `times` UDP-датаграмм в один адрес через один сокет.
    private static func sendPacket(_ packet: Data, to host: String, times: Int, broadcast: Bool) -> Bool {
        let fd = socket(AF_INET, SOCK_DGRAM, 0)
        guard fd >= 0 else { return false }
        defer { close(fd) }

        if broadcast {
            var one: Int32 = 1
            guard setsockopt(fd, SOL_SOCKET, SO_BROADCAST, &one,
                             socklen_t(MemoryLayout<Int32>.size)) == 0 else {
                return false
            }
        }

        guard let ipAddr = parseIPv4(host) else { return false }
        var addr = sockaddr_in()
        addr.sin_family = sa_family_t(AF_INET)
        addr.sin_port = UInt16(9).bigEndian
        addr.sin_addr = ipAddr
        let count = packet.count

        for _ in 0..<times {
            var ok = false
            packet.withUnsafeBytes { buf in
                if let base = buf.baseAddress {
                    withUnsafePointer(to: &addr) { sa in
                        let cast = UnsafeRawPointer(sa).assumingMemoryBound(to: sockaddr.self)
                        ok = (sendto(fd, base, count, 0, cast,
                                     socklen_t(MemoryLayout<sockaddr_in>.size)) == count)
                    }
                }
            }
            guard ok else { return false }
        }
        return true
    }

    private static func parseIPv4(_ host: String) -> in_addr? {
        var a = in_addr()
        let r = withUnsafeMutablePointer(to: &a) { p in
            p.withMemoryRebound(to: UInt8.self, capacity: 4) {
                inet_pton(AF_INET, host, $0)
            }
        }
        return r == 1 ? a : nil
    }

    enum WoLError: LocalizedError {
        case badMAC
        case sendFailed
        var errorDescription: String? {
            switch self {
            case .badMAC: return "MAC-адрес: введите 12 hex-символов (аа:bb:cc:dd:ee:ff)"
            case .sendFailed: return "Не удалось отправить magic packet (айфон не в сети?)"
            }
        }
    }
}

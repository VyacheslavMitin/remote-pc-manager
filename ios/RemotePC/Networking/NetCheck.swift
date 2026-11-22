import Foundation
import Network

/// «ПК в сети?» — TCP-подключение к порту сервера (смысл как у веб-клиента:
/// сервер на ПК ответил — ПК включён; ping/ICMP из песочницы iOS недоступен).
enum NetCheck {

    static func hostIsUp(host: String, port: Int, timeout: TimeInterval = 2.0) async -> Bool {
        let h = host.trimmingCharacters(in: .whitespaces)
        guard !h.isEmpty, let endpoint = NWEndpoint.Port(rawValue: UInt16(port)) else {
            return false
        }

        // «Резолвелось ровно один раз»: .ready / .failed / .cancelled или таймаут.
        final class State: @unchecked Sendable {
            let lock = NSLock()
            var settled = false
        }
        let st = State()
        let conn = NWConnection(host: .init(h), port: endpoint, using: .tcp)

        return await withCheckedContinuation { (cont: CheckedContinuation<Bool, Never>) in
            conn.stateUpdateHandler = { state in
                let ok: Bool
                switch state {
                case .ready: ok = true
                case .failed, .cancelled: ok = false
                default: return
                }
                st.lock.lock()
                let first = !st.settled
                st.settled = true
                st.lock.unlock()
                conn.cancel()
                if first { cont.resume(returning: ok) }
            }
            conn.start(queue: .global())

            DispatchQueue.global().asyncAfter(deadline: .now() + timeout) {
                st.lock.lock()
                let first = !st.settled
                st.settled = true
                st.lock.unlock()
                conn.cancel()
                if first { cont.resume(returning: false) }
            }
        }
    }
}

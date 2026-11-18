from typing import List, Dict, Optional
from core.peer import Peer


class Console:
    """
    Console presentation formatting and message display helper.
    """
    @staticmethod
    def info(msg: str) -> None:
        print(f"[*] {msg}")

    @staticmethod
    def success(msg: str) -> None:
        print(f"[✓] {msg}")

    @staticmethod
    def warning(msg: str) -> None:
        print(f"[!] {msg}")

    @staticmethod
    def error(msg: str) -> None:
        print(f"[-] {msg}")

    @staticmethod
    def chat_message(sender: str, text: str) -> None:
        print(f"[{sender}] {text}")

    @staticmethod
    def print_peer_list(
        peers: List[Peer],
        unread_counts: Optional[Dict[str, int]] = None,
        active_partner: Optional[str] = None,
        connected_peers: Optional[List[str]] = None,
    ) -> None:
        unread_counts = unread_counts or {}
        connected_set = {c.lower() for c in (connected_peers or [])}
        active_lower = active_partner.lower() if active_partner else None

        print(f"\n[*] Danh sách bạn bè online ({len(peers)}):")
        if not peers:
            print("    (Hiện chưa có ai online, đang quét mạng LAN...)")
            return

        for p in peers:
            p_lower = p.name.lower()
            unread = unread_counts.get(p_lower, 0)
            unread_str = f" | [Chưa đọc: {unread}]" if unread > 0 else ""
            status_tag = f"[{p.status.upper()}]"

            chat_tag = ""
            if active_lower and p_lower == active_lower:
                chat_tag = " [Đang chat]"
            elif p_lower in connected_set:
                chat_tag = " [Đã kết nối]"

            print(f"    - [{p.name}] {p.ip}:{p.tcp_port} {status_tag}{chat_tag}{unread_str}")
        print()

    @staticmethod
    def print_help() -> None:
        print("\n" + "=" * 60)
        print(" DANH SÁCH LỆNH HỖ TRỢ (LAN CHAT & FILE SHARING)")
        print("=" * 60)
        print("  /list                    : Xem danh sách bạn bè online & tin chưa đọc")
        print("  /chat <tên|port|ip:port> : Mở hoặc chuyển đổi phòng chat với bạn đó")
        print("  /send <đường_dẫn_tệp>    : Gửi tệp tới bạn đang chat")
        print("  /leave                   : Rời phòng chat hiện tại (tin mới sẽ là chưa đọc)")
        print("  /status <online|away>    : Đổi trạng thái hiển thị của bạn")
        print("  /history [tên]           : Xem lịch sử tin nhắn với bạn bè")
        print("  /help                    : Xem danh sách hướng dẫn lệnh")
        print("  /quit                    : Thoát ứng dụng")
        print("=" * 60 + "\n")

import sys
import threading
from typing import List, Dict, Optional
from core.peer import Peer


class Console:
    """
    Console presentation formatting and message display helper.
    """
    _lock = threading.Lock()
    _in_progress = False

    @staticmethod
    def write_line(message: str = "") -> None:
        with Console._lock:
            if Console._in_progress:
                # Xóa dòng progress bar đang chạy trước khi in dòng mới
                sys.stdout.write("\r" + " " * 79 + "\r")
                Console._in_progress = False
            sys.stdout.write(str(message) + "\n")
            sys.stdout.flush()

    @staticmethod
    def write_progress(message: str = "") -> None:
        with Console._lock:
            # Ghi đè trên cùng 1 dòng và đệm khoảng trắng (tránh lỗi hiển thị ký tự ?[K trên Windows)
            padded = str(message).ljust(78)
            sys.stdout.write(f"\r{padded}")
            sys.stdout.flush()
            Console._in_progress = True

    @staticmethod
    def info(msg: str) -> None:
        Console.write_line(f"[*] {msg}")

    @staticmethod
    def success(msg: str) -> None:
        Console.write_line(f"[✓] {msg}")

    @staticmethod
    def warning(msg: str) -> None:
        Console.write_line(f"[!] {msg}")

    @staticmethod
    def error(msg: str) -> None:
        Console.write_line(f"[-] {msg}")

    @staticmethod
    def chat_message(sender: str, text: str) -> None:
        Console.write_line(f"[{sender}]: {text}")

    @staticmethod
    def print_peer_list(
        peers: List[Peer],
        unread_counts: Optional[Dict[str, int]] = None,
        active_partner: Optional[str] = None,
        connected_peers: Optional[List[str]] = None,
        connected_ports: Optional[List[int]] = None,
        active_port: Optional[int] = None,
    ) -> None:
        unread_counts = unread_counts or {}
        connected_set = {c.lower() for c in (connected_peers or [])}
        connected_port_set = set(connected_ports or [])
        active_lower = active_partner.lower() if active_partner else None

        Console.write_line(f"\n[*] Danh sách bạn bè online ({len(peers)}):")
        if not peers:
            Console.write_line("    (Hiện chưa có ai online, đang quét mạng LAN...)")
            return

        for i, p in enumerate(peers, 1):
            p_lower = p.name.lower()
            unread = (
                unread_counts.get((p.ip, p.tcp_port), 0)
                or unread_counts.get(p.tcp_port, 0)
                or unread_counts.get(p_lower, 0)
            )
            unread_str = f" | [Chưa đọc: {unread}]" if unread > 0 else ""
            status_tag = f"[{p.status.upper()}]"

            chat_tag = ""
            if (active_port and p.tcp_port == active_port) or (not active_port and active_lower and p_lower == active_lower):
                chat_tag = " [Đang chat]"
            elif (p.tcp_port in connected_port_set) or (p_lower in connected_set):
                chat_tag = " [Đã kết nối]"

            Console.write_line(f"    {i}. [{p.name}] {p.ip}:{p.tcp_port} {status_tag}{chat_tag}{unread_str}")
        Console.write_line()

    @staticmethod
    def print_help() -> None:
        Console.write_line("\n" + "=" * 60)
        Console.write_line(" DANH SÁCH LỆNH HỖ TRỢ (LAN CHAT & FILE SHARING)")
        Console.write_line("=" * 60)
        Console.write_line("  /list                    : Xem danh sách bạn bè online & tin chưa đọc")
        Console.write_line("  /chat <số|tên|port>      : Mở hoặc chuyển đổi phòng chat (Ví dụ: /chat 1)")
        Console.write_line("  /send <đường_dẫn_tệp>    : Gửi tệp tới bạn đang chat")
        Console.write_line("  /leave                   : Rời phòng chat hiện tại (tin mới sẽ là chưa đọc)")
        Console.write_line("  /status <online|away>    : Đổi trạng thái hiển thị của bạn")
        Console.write_line("  /history [tên]           : Xem lịch sử tin nhắn với bạn bè")
        Console.write_line("  /help                    : Xem danh sách hướng dẫn lệnh")
        Console.write_line("  /quit                    : Thoát ứng dụng")
        Console.write_line("=" * 60 + "\n")

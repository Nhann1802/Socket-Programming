r"""
================================================================================
CÁC LỆNH SỬ DỤNG TRONG CHƯƠNG TRÌNH:
================================================================================
- /list                    : Xem danh sách bạn bè online, trạng thái kết nối & tin chưa đọc
- /chat <tên|port|ip:port> : Mở hoặc chuyển đổi tiêu điểm chat sang bạn đó
- /send <đường_dẫn_file>   : Gửi file tới người đang chat (Ví dụ: /send README.md)
                             File nhận sẽ tự động lưu vào: storage/downloads/
- /leave                   : Rời phòng chat hiện tại (tin nhắn đến sau đó sẽ là Chưa đọc)
- /status <online|away>    : Đổi trạng thái hiển thị của bạn
- /history [tên_bạn]       : Xem lịch sử tin nhắn
- /help                    : Hiển thị bảng trợ giúp lệnh
- /quit                    : Thoát chương trình
================================================================================
"""

import argparse

from config import (
    DEFAULT_UDP_PORT,
    DEFAULT_TCP_PORT,
    DEFAULT_BROADCAST_IP,
    is_tcp_port_available,
)
from ui.console import Console
from app import ChatApp
from cli import CLI, resolve_peer_target


def main():
    parser = argparse.ArgumentParser(description="LAN Chat & File Sharing P2P")
    parser.add_argument("--name", default="", help="Tên hiển thị của bạn (mặc định: User_<port>)")
    parser.add_argument("--tcp-port", type=int, default=DEFAULT_TCP_PORT, help="Cổng TCP lắng nghe")
    parser.add_argument("--udp-port", type=int, default=DEFAULT_UDP_PORT, help="Cổng UDP phát hiện peer")
    parser.add_argument("--broadcast-ip", default=DEFAULT_BROADCAST_IP, help="Địa chỉ Broadcast IP")
    args = parser.parse_args()

    tcp_port = args.tcp_port
    udp_port = args.udp_port
    broadcast_ip = args.broadcast_ip

    if not is_tcp_port_available(tcp_port):
        Console.warning(f"Cổng {tcp_port} đang bận, đang tự động tìm cổng khả dụng tiếp theo...")
        candidate = tcp_port + 1
        while candidate <= 65535 and not is_tcp_port_available(candidate):
            candidate += 1
        if candidate <= 65535:
            tcp_port = candidate
            Console.info(f"Đã chọn cổng rảnh: {tcp_port}")
        else:
            Console.error("Không tìm thấy cổng TCP khả dụng!")
            return

    me = args.name.strip() if args.name.strip() else f"User_{tcp_port}"

    app = ChatApp(me, tcp_port, udp_port, broadcast_ip)
    app.start()
    CLI(app).run()
    app.shutdown()


if __name__ == "__main__":
    main()

"""
LAN Chat & File Sharing - P2P Chat với luồng Yêu cầu / Chấp nhận (Phong cách Option A)
Tác giả: Nguyễn Đăng Huỳnh Nhân (Trưởng nhóm Mạng)
"""

import sys
import time
import argparse
import socket
import threading
from prompt_toolkit import PromptSession
from prompt_toolkit.patch_stdout import patch_stdout

from config import (
    DEFAULT_UDP_PORT,
    DEFAULT_TCP_PORT,
    DEFAULT_BROADCAST_IP,
    PEER_TIMEOUT,
    is_tcp_port_available,
)
from network.protocol import FrameType, send_frame, recv_frame
from network.udp_broadcast import UDPBroadcaster
from network.udp_listener import UDPListener
from network.tcp_server import TCPServer
from network.tcp_client import TCPClient

running = True
current_sock = None
partner_name = ""
pending_request = None          # Lưu yêu cầu chat đang chờ: {"sock": sock, "name": name}
send_lock = threading.Lock()
peers = {}
peers_lock = threading.Lock()


def on_peer_found(name: str, ip: str, tcp_port: int, status: str):
    """Phát hiện bạn mới qua UDP broadcast."""
    key = (ip, tcp_port)
    now = time.monotonic()
    with peers_lock:
        if key not in peers:
            print(f"[*] Tìm thấy bạn mới: [{name}] tại {ip}:{tcp_port} [{status}]")
        peers[key] = {"name": name, "status": status, "last_seen": now}


def peer_cleanup_loop():
    """Kiểm tra và thông báo khi một bạn offline (quá 10 giây không có tín hiệu)."""
    while running:
        time.sleep(0.5)
        now = time.monotonic()
        with peers_lock:
            expired = [k for k, v in peers.items() if now - v.get("last_seen", 0) > PEER_TIMEOUT]
            for k in expired:
                p_info = peers.pop(k)
                print(f"[-] [{p_info['name']}] đã rời mạng (offline).")


def receiver_thread_func(sock: socket.socket, name: str):
    """Luồng nhận tin nhắn ngầm từ bạn qua TCP."""
    global current_sock, partner_name
    left_announced = False
    while running:
        try:
            header, payload = recv_frame(sock)
            if header.get("type") == FrameType.MSG:
                msg_text = payload.decode("utf-8", errors="replace")
                print(f"[{name}] {msg_text}")
            elif header.get("type") == FrameType.BYE:
                print(f"[*] [{name}] đã rời cuộc trò chuyện.")
                left_announced = True
                break
        except Exception:
            break

    if current_sock == sock:
        current_sock = None
        partner_name = ""
        if not left_announced:
            print(f"[*] [{name}] đã rời cuộc trò chuyện.")
    try:
        sock.close()
    except OSError:
        pass


def on_chat_request_received(sock: socket.socket, peer_name: str, advertised_port: int, client_ip: str):
    """Được gọi khi bên B nhận được yêu cầu /chat từ bên A."""
    global pending_request
    if current_sock:
        # Nếu đang bận trò chuyện với người khác, tự động từ chối
        try:
            send_frame(sock, {"type": FrameType.CHAT_RESP, "name": "Đang bận", "status": "reject"})
            sock.close()
        except OSError:
            pass
        return

    pending_request = {"sock": sock, "name": peer_name}
    print(f"[*] Có yêu cầu chat đến từ [{peer_name}]. Gõ /accept để đồng ý hoặc /reject để từ chối")


def resolve_target(arg: str):
    """
    Thông minh phân giải mục tiêu chat:
      - Theo tên: /chat Duc
      - Theo IP:Port: /chat 26.29.104.124:2000
      - Theo Port: /chat 2000 (tự tìm IP của bạn bè nếu có trong danh sách)
    Trả về: (ip, port, display_name) hoặc (None, None, None)
    """
    arg = arg.strip()

    # 1. Tìm theo tên trong danh sách peers
    with peers_lock:
        for (ip, port), info in peers.items():
            if info["name"].lower() == arg.lower():
                return ip, port, info["name"]

    # 2. Định dạng IP:Port (ví dụ: 26.29.104.124:2000)
    if ":" in arg:
        parts = arg.split(":", 1)
        ip = parts[0].strip()
        try:
            port = int(parts[1].strip())
            with peers_lock:
                label = peers.get((ip, port), {}).get("name", f"{ip}:{port}")
            return ip, port, label
        except ValueError:
            return None, None, None

    # 3. Định dạng chỉ có số Port (ví dụ: 2000)
    if arg.isdigit():
        target_port = int(arg)
        with peers_lock:
            # Ưu tiên tìm xem có bạn nào đang mở port này không
            for (ip, port), info in peers.items():
                if port == target_port:
                    return ip, port, info["name"]
        return "127.0.0.1", target_port, f"{target_port}"

    return None, None, None


def main():
    global running, current_sock, partner_name, pending_request

    parser = argparse.ArgumentParser(description="Ứng dụng P2P Chat mạng LAN")
    parser.add_argument("--name", default="Nhan", help="Tên hiển thị của bạn")
    parser.add_argument("--tcp-port", type=int, default=DEFAULT_TCP_PORT, help="Cổng TCP lắng nghe")
    args = parser.parse_args()

    me = args.name
    tcp_port = args.tcp_port

    # 1. Khởi chạy TCP Server: kiểm tra nếu cổng bị trùng -> yêu cầu nhập lại
    while True:
        while not is_tcp_port_available(tcp_port):
            print(f"[!] Cổng {tcp_port} bị trùng (đang có người dùng) hoặc không hợp lệ!")
            try:
                val = input("Vui lòng nhập lại một cổng TCP khác (1024-65535): ").strip()
                if val.isdigit():
                    tcp_port = int(val)
                else:
                    print("[!] Cổng phải là số nguyên!")
            except (KeyboardInterrupt, EOFError):
                print("\n[*] Đã hủy.")
                return

        try:
            tcp_server = TCPServer(
                port=tcp_port,
                own_name=me,
                host="0.0.0.0",
                on_chat_request=on_chat_request_received,
            )
            tcp_server.start()
            break
        except OSError:
            print(f"[!] Cổng {tcp_port} bị trùng (đang có người dùng) hoặc không hợp lệ!")
            try:
                val = input("Vui lòng nhập lại một cổng TCP khác (1024-65535): ").strip()
                if val.isdigit():
                    tcp_port = int(val)
            except (KeyboardInterrupt, EOFError):
                print("\n[*] Đã hủy.")
                return

    # 2. Khởi chạy UDP Discovery
    listener = UDPListener(
        on_peer_discovered=on_peer_found,
        own_tcp_port=tcp_port,
        own_name=me,
        udp_port=DEFAULT_UDP_PORT,
    )
    listener.start()

    broadcaster = UDPBroadcaster(
        name=me,
        tcp_port=tcp_port,
        broadcast_ip=DEFAULT_BROADCAST_IP,
        udp_port=DEFAULT_UDP_PORT,
    )
    broadcaster.start()

    # 3. Khởi chạy luồng kiểm tra bạn bè offline (> 10s không có tín hiệu)
    cleanup_thread = threading.Thread(target=peer_cleanup_loop, name="PeerCleanup", daemon=True)
    cleanup_thread.start()

    print(f"[*] Khởi động thành công [{me}] trên cổng TCP {tcp_port}")
    print("[*] Gõ /chat <tên_bạn> (ví dụ: /chat Duc) hoặc /chat <port> để kết nối.")
    print("[*] Các lệnh: /accept, /reject, /list, /quit")

    session = PromptSession()

    def do_request_chat_worker(target_ip: str, target_port: int, target_label: str):
        global current_sock, partner_name
        try:
            accepted, sock, lock, r_name = TCPClient.request_chat(
                ip=target_ip,
                tcp_port=target_port,
                own_name=me,
                own_tcp_port=tcp_port,
                timeout=60.0,
            )
            if accepted:
                current_sock = sock
                partner_name = r_name
                threading.Thread(target=receiver_thread_func, args=(sock, partner_name), daemon=True).start()
                print(f"[*] Đã kết nối với [{partner_name}]. Gõ tin nhắn để trò chuyện, gõ /quit để thoát.")
            else:
                print(f"[-] Yêu cầu chat đã bị từ chối bởi [{r_name}].")
        except Exception as e:
            print(f"[-] Kết nối thất bại: {e}")

    with patch_stdout():
        while True:
            try:
                text = session.prompt("> ")
            except (KeyboardInterrupt, EOFError):
                break

            line = text.strip()
            if not line:
                continue

            if line == "/quit":
                break

            elif line == "/list":
                with peers_lock:
                    print(f"[*] Danh sách bạn bè online ({len(peers)}):")
                    if not peers:
                        print("    (Hiện chưa có ai online, đang quét mạng...)")
                    for (ip, port), info in peers.items():
                        print(f"    - [{info['name']}] {ip}:{port} [{info['status']}]")

            elif line.startswith("/chat"):
                parts = line.split(maxsplit=1)
                if len(parts) < 2:
                    print("[!] Cách dùng: /chat <tên_bạn> hoặc /chat <port> hoặc /chat <ip>:<port>")
                    continue

                target_str = parts[1].strip()
                target_ip, target_port, target_label = resolve_target(target_str)
                if not target_ip or not target_port:
                    print(f"[!] Không tìm thấy mục tiêu '{target_str}'. Hãy gõ /list để xem danh sách bạn bè online.")
                    continue

                print(f"[*] Đang gửi yêu cầu chat tới [{target_label}]...")

                threading.Thread(
                    target=do_request_chat_worker,
                    args=(target_ip, target_port, target_label),
                    daemon=True,
                ).start()

            elif line in ("/accept", "/y"):
                if pending_request:
                    req_sock = pending_request["sock"]
                    req_name = pending_request["name"]
                    pending_request = None
                    try:
                        send_frame(req_sock, {
                            "type": FrameType.CHAT_RESP,
                            "name": me,
                            "status": "accept"
                        })
                        current_sock = req_sock
                        partner_name = req_name
                        threading.Thread(target=receiver_thread_func, args=(req_sock, partner_name), daemon=True).start()
                        print(f"[*] Đã kết nối với [{partner_name}]. Gõ tin nhắn để trò chuyện, gõ /quit để thoát.")
                    except Exception as e:
                        print(f"[-] Không thể chấp nhận kết nối: {e}")
                else:
                    print("[!] Không có yêu cầu chat nào đang chờ.")

            elif line in ("/reject", "/n"):
                if pending_request:
                    req_sock = pending_request["sock"]
                    req_name = pending_request["name"]
                    pending_request = None
                    try:
                        send_frame(req_sock, {
                            "type": FrameType.CHAT_RESP,
                            "name": me,
                            "status": "reject"
                        })
                        req_sock.close()
                        print(f"[*] Đã từ chối yêu cầu chat từ [{req_name}].")
                    except OSError:
                        pass
                else:
                    print("[!] Không có yêu cầu chat nào đang chờ.")

            else:
                # Gửi tin nhắn nếu đang có cuộc trò chuyện
                if current_sock:
                    payload = line.encode("utf-8")
                    header = {"type": FrameType.MSG, "length": len(payload)}
                    try:
                        send_frame(current_sock, header, payload, send_lock=send_lock)
                        print(f"[{me}] {line}")
                    except Exception as e:
                        print(f"[-] Gửi tin nhắn thất bại: {e}")
                        current_sock = None
                        partner_name = ""
                else:
                    print("[!] Chưa kết nối. Gõ /chat <port> để kết nối trước.")

    running = False
    if current_sock:
        try:
            send_frame(current_sock, {"type": FrameType.BYE}, b"", send_lock=send_lock)
            current_sock.close()
        except OSError:
            pass

    broadcaster.stop()
    listener.stop()
    tcp_server.stop()
    print("[*] Tạm biệt!")


if __name__ == "__main__":
    main()

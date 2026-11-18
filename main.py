r"""
LAN Chat & File Sharing — Ứng dụng P2P Mạng LAN Hoàn Chỉnh
Bao gồm: UDP Discovery, TCP Framing, P2P Chat đa luồng, File Transfer riêng biệt

================================================================================
HƯỚNG DẪN CÁCH CHẠY (HOW TO RUN)
================================================================================
Để mô phỏng 2 hoặc nhiều người trò chuyện trên cùng một máy tính:

1. Mở Terminal 1 (Ví dụ: Huân):
   python main.py --name Huan --tcp-port 5001

2. Mở Terminal 2 (Ví dụ: Nhân):
   python main.py --name Nhan --tcp-port 5002

3. Mở Terminal 3 (Ví dụ: Đức):
   python main.py --name Duc --tcp-port 5003

(Tất cả tự động tìm thấy nhau qua UDP Broadcast!)

================================================================================
CÁCH HOẠT ĐỘNG CHAT & TIN NHẮN CHƯA ĐỌC (UNREAD):
================================================================================
- Huân gõ `/chat Nhan` để mở phòng trò chuyện với Nhân.
- Lúc này Đức cũng kết nối và gửi tin nhắn cho Huân:
  -> Kết nối giữa Đức và Huân TỰ ĐỘNG THIẾT LẬP (không bị từ chối / reject).
  -> Vì Huân đang mở phòng chat với Nhân, tin nhắn từ Đức sẽ tự động lưu vào
     danh sách UNREAD và hiện thông báo:
     `[*] [Tin nhắn chưa đọc từ Duc]: Alo Huân ơi! (Gõ /chat Duc để trả lời)`
  -> Huân gõ `/list` sẽ thấy:
     `    - [Duc] 127.0.0.1:5003 [ONLINE] [Đã kết nối] | [Chưa đọc: 1]`
     `    - [Nhan] 127.0.0.1:5002 [ONLINE] [Đang chat]`
  -> Huân gõ `/chat Duc` để chuyển tiêu điểm sang Đức, lập tức đọc tin nhắn
     và số chưa đọc trở về 0!

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

import sys
import os
import time
import argparse
import socket
import threading
from pathlib import Path

# Kích hoạt ANSI escape sequence trên Windows Terminal / PowerShell
if os.name == "nt":
    os.system("")

try:
    from prompt_toolkit import PromptSession
    from prompt_toolkit.patch_stdout import patch_stdout
    HAS_PROMPT_TOOLKIT = True
except ImportError:
    HAS_PROMPT_TOOLKIT = False

from config import (
    DEFAULT_UDP_PORT,
    DEFAULT_TCP_PORT,
    DEFAULT_BROADCAST_IP,
    PEER_TIMEOUT,
    CLEANUP_INTERVAL,
    DEFAULT_DOWNLOAD_DIR,
    is_tcp_port_available,
)
from network.protocol import FrameType, send_frame, recv_frame
from network.udp_broadcast import UDPBroadcaster
from network.udp_listener import UDPListener
from network.tcp_server import TCPServer
from network.tcp_client import TCPClient

from core.peer_manager import PeerManager
from core.message import Message
from core.message_manager import MessageManager
from core.status_manager import StatusManager
from core.chat_manager import ChatManager
from transfer.transfer_manager import TransferManager
from ui.console import Console
from ui.input_handler import InputHandler, Command

running = True


def resolve_peer_target(arg: str, peer_mgr: PeerManager, cached_peers=None):
    """
    Phân giải mục tiêu chat:
      1. Theo số thứ tự trong danh sách /list: /chat 1, /chat 2
      2. Theo tên: /chat Nhan
      3. Theo IP:Port: /chat 127.0.0.1:5002
      4. Theo Port: /chat 5002
    Trả về: (ip, port, display_name) hoặc (None, None, None)
    """
    arg = arg.strip()
    if not arg:
        return None, None, None

    # 1. Định dạng số thứ tự (index: 1, 2, 3...) từ danh sách peers
    if arg.isdigit():
        idx = int(arg)
        peers_list = cached_peers if (cached_peers is not None and len(cached_peers) > 0) else peer_mgr.list_peers()
        if 1 <= idx <= len(peers_list):
            target = peers_list[idx - 1]
            return target.ip, target.tcp_port, target.name

    # 2. Tìm theo tên trong danh sách peers
    peer = peer_mgr.find_by_name(arg)
    if peer:
        return peer.ip, peer.tcp_port, peer.name

    # 3. Định dạng IP:Port (ví dụ: 192.168.1.5:5001)
    if ":" in arg:
        parts = arg.split(":", 1)
        ip = parts[0].strip()
        try:
            port = int(parts[1].strip())
            p = peer_mgr.get_peer(ip, port)
            label = p.name if p else f"{ip}:{port}"
            return ip, port, label
        except ValueError:
            return None, None, None

    # 4. Định dạng chỉ có số Port (ví dụ: 5002) - dành cho cổng >= 1024
    if arg.isdigit():
        target_port = int(arg)
        p = peer_mgr.find_by_port(target_port)
        if p:
            return p.ip, p.tcp_port, p.name
        if target_port >= 1024:
            return "127.0.0.1", target_port, f"Port {target_port}"

    return None, None, None


def main():
    global running

    parser = argparse.ArgumentParser(description="LAN Chat & File Sharing P2P")
    parser.add_argument("--name", default="", help="Tên hiển thị của bạn (mặc định: User_<port>)")
    parser.add_argument("--tcp-port", type=int, default=DEFAULT_TCP_PORT, help="Cổng TCP lắng nghe")
    parser.add_argument("--udp-port", type=int, default=DEFAULT_UDP_PORT, help="Cổng UDP phát hiện peer")
    parser.add_argument("--broadcast-ip", default=DEFAULT_BROADCAST_IP, help="Địa chỉ Broadcast IP")
    args = parser.parse_args()

    tcp_port = args.tcp_port
    udp_port = args.udp_port
    broadcast_ip = args.broadcast_ip

    # 1. Tự động tìm port khả dụng nếu port được chỉ định bị chiếm
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

    # Tên người dùng
    me = args.name.strip() if args.name.strip() else f"User_{tcp_port}"

    # 2. Khởi tạo các Manager (Tầng Core)
    status_mgr = StatusManager("online")
    msg_mgr = MessageManager()
    chat_mgr = ChatManager()

    def on_peer_added(peer):
        Console.info(f"Tìm thấy bạn mới: [{peer.name}] tại {peer.ip}:{peer.tcp_port} [{peer.status}]")

    def on_peer_removed(peer):
        Console.warning(f"[{peer.name}] đã rời mạng (offline).")
        # Dọn dẹp session chat nếu peer này thoát
        chat_mgr.remove_session(peer.name)

    peer_mgr = PeerManager(on_peer_added=on_peer_added, on_peer_removed=on_peer_removed)

    # Khởi tạo TransferManager (Tầng Transfer)
    transfer_mgr = TransferManager(
        download_dir=DEFAULT_DOWNLOAD_DIR,
        on_notify=lambda msg: print(msg),
    )

    # 3. Hàm nhận tin nhắn ngầm từ bạn chat qua TCP
    def chat_receiver_thread(sock: socket.socket, partner_name: str):
        left_announced = False
        while running:
            try:
                header, payload = recv_frame(sock)
                frame_type = header.get("type")

                if frame_type == FrameType.MSG:
                    msg_text = payload.decode("utf-8", errors="replace")
                    active_partner = chat_mgr.get_active_partner()

                    # Nếu người gửi chính là người đang mở phòng chat -> hiện trực tiếp
                    if active_partner and active_partner.lower() == partner_name.lower():
                        msg_mgr.add_message(
                            Message(sender=partner_name, receiver=me, content=msg_text),
                            is_active_session=True,
                        )
                        Console.chat_message(partner_name, msg_text)
                    else:
                        # Người gửi KHÁC người đang chat -> Lưu vào UNREAD và thông báo
                        msg_mgr.add_message(
                            Message(sender=partner_name, receiver=me, content=msg_text),
                            is_active_session=False,
                        )
                        Console.info(
                            f"[Tin nhắn chưa đọc từ {partner_name}]: {msg_text}  (Gõ /chat {partner_name} để trả lời)"
                        )

                elif frame_type == FrameType.BYE:
                    Console.info(f"[{partner_name}] đã đóng kết nối trò chuyện.")
                    left_announced = True
                    break

            except Exception:
                break

        chat_mgr.remove_session(partner_name)
        if not left_announced:
            Console.info(f"[*] Kết nối với [{partner_name}] đã đóng.")

        try:
            sock.close()
        except OSError:
            pass

    # 4. Callback khi có kết nối chat đến (TỰ ĐỘNG CHẤP NHẬN - Không chặn / Không bắt reject)
    def on_incoming_chat_connection(sock: socket.socket, peer_name: str, advertised_port: int, client_ip: str):
        # Đăng ký session vào ChatManager
        chat_mgr.add_session(
            sock=sock,
            name=peer_name,
            ip=client_ip,
            port=advertised_port,
            set_active=False,  # Giữ nguyên phòng chat hiện tại nếu đang chat
        )

        # Khởi động luồng nhận tin nhắn cho peer này
        threading.Thread(
            target=chat_receiver_thread,
            args=(sock, peer_name),
            name=f"ChatReceiver-{peer_name}",
            daemon=True,
        ).start()

        active = chat_mgr.get_active_partner()
        if not active:
            # Chưa chat với ai -> tự động chọn bạn này làm active
            chat_mgr.set_active_partner(peer_name)
            msg_mgr.mark_as_read(peer_name)
            Console.success(f"Đã kết nối với [{peer_name}]. Nhập tin nhắn để bắt đầu trò chuyện!")
        else:
            # Đang chat với người khác -> thông báo bạn mới đã kết nối ở nền
            unread_count = msg_mgr.get_unread_count(peer_name)
            Console.info(
                f"[{peer_name}] đã kết nối với bạn. (Gõ /chat {peer_name} để chuyển sang {peer_name})"
            )

    # 5. Callback khi có kết nối FILE đến
    def on_incoming_file(sock: socket.socket, sender_name: str, advertised_port: int, client_ip: str):
        transfer_mgr.handle_incoming_file(
            sock=sock,
            sender_name=sender_name,
            advertised_port=advertised_port,
            client_ip=client_ip,
        )

    # 6. Callback khi có tin nhắn nhanh direct message
    def on_incoming_direct_msg(sock: socket.socket, sender_name: str, advertised_port: int, client_ip: str):
        try:
            header, payload = recv_frame(sock)
            if header.get("type") == FrameType.MSG:
                text = payload.decode("utf-8", errors="replace")
                active = chat_mgr.get_active_partner()
                is_active = (active is not None and active.lower() == sender_name.lower())
                msg_mgr.add_message(Message(sender=sender_name, receiver=me, content=text), is_active_session=is_active)
                if is_active:
                    Console.chat_message(sender_name, text)
                else:
                    Console.info(f"[Tin nhắn chưa đọc từ {sender_name}]: {text}  (Gõ /chat {sender_name} để trả lời)")
        except Exception:
            pass
        finally:
            try:
                sock.close()
            except OSError:
                pass

    # 7. Khởi động TCP Server
    tcp_server = TCPServer(
        port=tcp_port,
        own_name=me,
        host="0.0.0.0",
        on_chat_connection=on_incoming_chat_connection,
        on_file_connection=on_incoming_file,
        on_direct_msg=on_incoming_direct_msg,
    )
    tcp_server.start()

    # 8. Khởi động UDP Discovery (Listener & Broadcaster)
    def on_udp_peer_found(p_name: str, p_ip: str, p_port: int, p_status: str):
        peer_mgr.add_or_update(name=p_name, ip=p_ip, tcp_port=p_port, status=p_status)

    udp_listener = UDPListener(
        on_peer_discovered=on_udp_peer_found,
        own_tcp_port=tcp_port,
        own_name=me,
        udp_port=udp_port,
    )
    udp_listener.start()

    udp_broadcaster = UDPBroadcaster(
        name=me,
        tcp_port=tcp_port,
        status_provider=status_mgr.get_status,
        broadcast_ip=broadcast_ip,
        udp_port=udp_port,
    )
    udp_broadcaster.start()

    # 9. Luồng dọn dẹp peer offline (quá PEER_TIMEOUT giây)
    def peer_cleanup_loop():
        while running:
            time.sleep(CLEANUP_INTERVAL)
            peer_mgr.cleanup_expired(PEER_TIMEOUT)

    cleanup_thread = threading.Thread(target=peer_cleanup_loop, name="PeerCleanupWorker", daemon=True)
    cleanup_thread.start()

    # Banner khởi động
    Console.success(f"Khởi động thành công [{me}] trên cổng TCP {tcp_port} (UDP {udp_port})")
    Console.info("Gõ /help để xem danh sách lệnh, gõ /list để xem bạn bè online.")

    # 10. Luồng chủ động kết nối chat ra ngoài
    def do_connect_chat_worker(target_ip: str, target_port: int, target_name: str):
        try:
            Console.info(f"Đang kết nối tới [{target_name}] ({target_ip}:{target_port})...")
            # Sử dụng request_chat (bên kia sẽ tự động accept)
            accepted, sock, lock, remote_name = TCPClient.request_chat(
                ip=target_ip,
                tcp_port=target_port,
                own_name=me,
                own_tcp_port=tcp_port,
                timeout=10.0,
            )
            if accepted:
                chat_mgr.add_session(
                    sock=sock,
                    name=remote_name,
                    ip=target_ip,
                    port=target_port,
                    send_lock=lock,
                    set_active=True,
                )
                msg_mgr.mark_as_read(remote_name)
                threading.Thread(
                    target=chat_receiver_thread,
                    args=(sock, remote_name),
                    name=f"ChatReceiver-{remote_name}",
                    daemon=True,
                ).start()
                Console.success(
                    f"Đã kết nối với [{remote_name}]. Nhập tin nhắn để chat, /send <file> để gửi tệp, /leave để rời phòng."
                )
            else:
                Console.warning(f"Không thể kết nối với [{target_name}].")
        except Exception as e:
            Console.error(f"Kết nối thất bại tới [{target_name}]: {e}")

    use_prompt_toolkit = HAS_PROMPT_TOOLKIT
    session = None
    if use_prompt_toolkit:
        try:
            session = PromptSession()
        except Exception:
            session = None
            use_prompt_toolkit = False

    def get_input(prompt_str: str) -> str:
        if session and use_prompt_toolkit:
            return session.prompt(prompt_str)
        return input(prompt_str)

    # 11. Vòng lặp chính xử lý lệnh
    def run_cli_loop():
        global running
        last_listed_peers = []
        while True:
            # Dấu nhắc nhập tin nhắn luôn là '> ' theo đúng yêu cầu đề bài
            prompt_str = "> "

            try:
                raw_line = get_input(prompt_str)
            except (KeyboardInterrupt, EOFError):
                break

            cmd = InputHandler.parse(raw_line)

            if cmd.name == "EMPTY":
                continue

            elif cmd.name == "QUIT":
                break

            elif cmd.name == "HELP":
                Console.print_help()

            elif cmd.name == "LIST":
                active_peers = peer_mgr.list_peers()
                last_listed_peers = active_peers
                unread_map = msg_mgr.get_all_unread()
                connected_names = chat_mgr.list_connected_peer_names()
                Console.print_peer_list(
                    peers=active_peers,
                    unread_counts=unread_map,
                    active_partner=chat_mgr.get_active_partner(),
                    connected_peers=connected_names,
                )

            elif cmd.name == "STATUS":
                new_status = cmd.args.strip().lower()
                if new_status in ("online", "away"):
                    if status_mgr.set_status(new_status):
                        Console.success(f"Đã chuyển trạng thái sang: [{new_status.upper()}]")
                else:
                    Console.warning("Trạng thái không hợp lệ! Vui lòng dùng: /status online hoặc /status away")

            elif cmd.name == "CHAT":
                target_str = cmd.args.strip()
                if not target_str:
                    Console.warning("Cách dùng: /chat <số|tên_bạn|port>")
                    continue

                t_ip, t_port, t_name = resolve_peer_target(target_str, peer_mgr, last_listed_peers)
                if not t_ip or not t_port:
                    Console.error(f"Không tìm thấy peer '{target_str}'. Hãy gõ /list để xem danh sách bạn bè online.")
                    continue

                # Nếu ĐÃ CÓ kết nối trước đó với bạn này -> chỉ cần chuyển tiêu điểm (Switch Room)
                if chat_mgr.has_session(t_name):
                    chat_mgr.set_active_partner(t_name)
                    msg_mgr.mark_as_read(t_name)
                    Console.success(f"Đã chuyển sang phòng chat với [{t_name}].")
                    # Hiển thị 5 tin nhắn gần nhất để xem lại
                    history = msg_mgr.get_history(t_name)
                    if history:
                        print(f"--- 5 tin nhắn gần nhất với [{t_name}] ---")
                        for m in history[-5:]:
                            print(f"  [{m.formatted_time()}] {m.sender}: {m.content}")
                        print("------------------------------------------")
                    continue

                # Chưa có kết nối -> mở kết nối mới trong background
                threading.Thread(
                    target=do_connect_chat_worker,
                    args=(t_ip, t_port, t_name),
                    name="ConnectChatWorker",
                    daemon=True,
                ).start()

            elif cmd.name == "SEND":
                filepath = cmd.args.strip()
                if not filepath:
                    Console.warning("Cách dùng: /send <đường_dẫn_tệp>")
                    continue

                active_session = chat_mgr.get_active_session()
                if not active_session:
                    Console.warning("Bạn chưa mở phòng chat với ai. Hãy dùng /chat <tên> trước khi gửi file.")
                    continue

                partner = active_session["name"]
                p_ip = active_session["ip"]
                p_port = active_session["port"]

                if not os.path.isfile(filepath):
                    Console.error(f"Tệp không tồn tại: {filepath}")
                    continue

                Console.info(f"Đang chuẩn bị gửi tệp '{filepath}' tới [{partner}] ({p_ip}:{p_port})...")
                transfer_mgr.send_file_async(
                    target_ip=p_ip,
                    target_port=p_port,
                    own_name=me,
                    own_tcp_port=tcp_port,
                    filepath=filepath,
                )

            elif cmd.name == "LEAVE":
                cur_partner = chat_mgr.get_active_partner()
                if cur_partner:
                    chat_mgr.set_active_partner(None)
                    Console.info(
                        f"Đã rời phòng chat với [{cur_partner}]. Kết nối vẫn được duy trì ngầm, các tin nhắn đến sẽ được lưu vào Chưa đọc."
                    )
                else:
                    Console.warning("Hiện tại bạn chưa ở trong phòng chat nào.")

            elif cmd.name == "HISTORY":
                target_peer = cmd.args.strip() if cmd.args.strip() else chat_mgr.get_active_partner()
                if not target_peer:
                    Console.warning("Cách dùng: /history <tên_bạn>")
                    continue

                history = msg_mgr.get_history(target_peer)
                print(f"\n--- Lịch sử trò chuyện với [{target_peer}] ({len(history)} tin nhắn) ---")
                if not history:
                    print("  (Chưa có tin nhắn nào)")
                for m in history:
                    print(f"[{m.formatted_time()}] {m.sender}: {m.content}")
                print("----------------------------------------------------------------\n")
                msg_mgr.mark_as_read(target_peer)

            elif cmd.name == "DIRECT_MSG":
                parts = cmd.args.split(maxsplit=1)
                if len(parts) < 2:
                    Console.warning("Cách dùng: /msg <tên_bạn|port> <nội_dung_tin_nhắn>")
                    continue

                target_str = parts[0].strip()
                direct_text = parts[1].strip()

                t_ip, t_port, t_label = resolve_peer_target(target_str, peer_mgr, last_listed_peers)
                if not t_ip or not t_port:
                    Console.error(f"Không tìm thấy peer '{target_str}'. Hãy gõ /list để xem danh sách bạn bè online.")
                    continue

                def send_direct_worker(ip, port, label, text):
                    ok = TCPClient.send_direct_message(
                        ip=ip,
                        tcp_port=port,
                        own_name=me,
                        own_tcp_port=tcp_port,
                        message=text,
                    )
                    if ok:
                        msg_mgr.add_message(
                            Message(sender=me, receiver=label, content=text),
                            is_active_session=True,
                            conversation_partner=label,
                        )
                        Console.success(f"Đã gửi tin nhắn nhanh tới [{label}]: {text}")
                    else:
                        Console.error(f"Không thể gửi tin nhắn nhanh tới [{label}].")

                threading.Thread(
                    target=send_direct_worker,
                    args=(t_ip, t_port, t_label, direct_text),
                    daemon=True,
                ).start()

            elif cmd.name == "UNKNOWN":
                Console.warning(f"Lệnh không hợp lệ: '{cmd.args}'. Gõ /help để xem hướng dẫn.")

            elif cmd.name == "MESSAGE":
                active_session = chat_mgr.get_active_session()
                if active_session:
                    partner = active_session["name"]
                    s_sock = active_session["sock"]
                    s_lock = active_session["send_lock"]

                    payload = cmd.args.encode("utf-8")
                    header = {"type": FrameType.MSG, "length": len(payload)}
                    try:
                        send_frame(s_sock, header, payload, send_lock=s_lock)
                        msg_mgr.add_message(
                            Message(sender=me, receiver=partner, content=cmd.args),
                            is_active_session=True,
                            conversation_partner=partner,
                        )

                        # In tin nhắn đã gửi chuẩn định dạng
                        Console.chat_message(me, cmd.args)
                    except Exception as e:
                        Console.error(f"Gửi tin nhắn thất bại tới [{partner}]: {e}")
                        chat_mgr.remove_session(partner)
                else:
                    Console.warning("Bạn chưa chọn người để chat. Gõ /chat <tên_bạn> (ví dụ: /chat Nhan) hoặc /help.")

    if use_prompt_toolkit and session is not None:
        try:
            with patch_stdout():
                run_cli_loop()
        except Exception:
            run_cli_loop()
    else:
        run_cli_loop()

    # Dọn dẹp khi thoát
    running = False
    all_socks = chat_mgr.close_all()
    for s in all_socks:
        try:
            send_frame(s, {"type": FrameType.BYE}, b"")
            s.close()
        except OSError:
            pass

    udp_broadcaster.stop()
    udp_listener.stop()
    tcp_server.stop()
    Console.info("Đã đóng tất cả kết nối mạng. Tạm biệt!")


if __name__ == "__main__":
    main()

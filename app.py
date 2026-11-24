import socket
import threading
import time

from config import (
    PEER_TIMEOUT,
    CLEANUP_INTERVAL,
    DEFAULT_DOWNLOAD_DIR,
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
from ui.progress_display import ProgressDisplay


class ChatApp:
    def __init__(self, me: str, tcp_port: int, udp_port: int, broadcast_ip: str):
        self.me = me
        self.tcp_port = tcp_port
        self.udp_port = udp_port
        self.broadcast_ip = broadcast_ip
        self.running = True

        # 2. Khởi tạo các Manager (Tầng Core)
        self.status_mgr = StatusManager("online")
        self.msg_mgr = MessageManager()
        self.chat_mgr = ChatManager()

        self.peer_mgr = PeerManager(on_peer_added=self.on_peer_added, on_peer_removed=self.on_peer_removed)

        # Khởi tạo TransferManager (Tầng Transfer)
        self.progress_display = ProgressDisplay()
        self.transfer_mgr = TransferManager(
            download_dir=DEFAULT_DOWNLOAD_DIR,
            on_notify=Console.write_line,
            on_progress=self.handle_transfer_progress,
        )

    def on_peer_added(self, peer):
        Console.info(f"Tìm thấy bạn mới: [{peer.name}] tại {peer.ip}:{peer.tcp_port} [{peer.status}]")

    def on_peer_removed(self, peer):
        Console.warning(f"[{peer.name}] ({peer.ip}:{peer.tcp_port}) đã rời mạng (offline).")
        # Dọn dẹp session chat nếu peer này thoát
        self.chat_mgr.remove_session(target=(peer.ip, peer.tcp_port))

    def handle_transfer_progress(self, progress):
        self.progress_display.update(progress)
        if not progress.finished:
            Console.write_progress(f"[*] {progress.render_bar(55)}")

    # 3. Hàm nhận tin nhắn ngầm từ bạn chat qua TCP
    def chat_receiver_thread(self, sock: socket.socket, partner_name: str, partner_ip: str = "", partner_port: int = 0):
        left_announced = False
        display_tag = f"{partner_name}:{partner_port}" if partner_port > 0 else partner_name
        while self.running:
            try:
                header, payload = recv_frame(sock)
                frame_type = header.get("type")

                if frame_type == FrameType.MSG:
                    msg_text = payload.decode("utf-8", errors="replace")
                    active_sess = self.chat_mgr.get_active_session()

                    # Kiểm tra xem tin nhắn đến có đúng từ phòng chat đang mở không
                    is_active = False
                    if active_sess:
                        act_port = active_sess.get("port", 0)
                        if partner_port > 0 and act_port > 0:
                            is_active = (partner_port == act_port)
                        else:
                            is_active = (active_sess.get("name", "").lower() == partner_name.lower())

                    endpoint_key = (partner_ip, partner_port) if partner_port > 0 else partner_name

                    # Nếu người gửi chính là người đang mở phòng chat -> hiện trực tiếp
                    if is_active:
                        self.msg_mgr.add_message(
                            Message(sender=partner_name, receiver=self.me, content=msg_text),
                            is_active_session=True,
                            conversation_partner=endpoint_key,
                        )
                        Console.chat_message(partner_name, msg_text)
                    else:
                        # Người gửi KHÁC người đang chat -> Lưu vào UNREAD và chỉ thông báo số tin nhắn chưa đọc
                        self.msg_mgr.add_message(
                            Message(sender=partner_name, receiver=self.me, content=msg_text),
                            is_active_session=False,
                            conversation_partner=endpoint_key,
                        )
                        unread = self.msg_mgr.get_unread_count(endpoint_key)
                        reply_target = partner_port if partner_port > 0 else partner_name
                        Console.info(
                            f"[*] Bạn có {unread} tin nhắn chưa đọc từ [{display_tag}]. (Gõ /chat {reply_target} để xem)"
                        )

                elif frame_type == FrameType.BYE:
                    Console.info(f"[{display_tag}] đã đóng kết nối trò chuyện.")
                    left_announced = True
                    break

            except Exception:
                break

        # Chỉ xóa đúng session của socket này (tránh xóa nhầm người trùng tên khác)
        self.chat_mgr.remove_session(sock=sock)
        if not left_announced:
            Console.info(f"Kết nối với [{display_tag}] đã đóng.")

        try:
            sock.close()
        except OSError:
            pass

    # 4. Callback khi có kết nối chat đến (TỰ ĐỘNG CHẤP NHẬN - Không chặn / Không bắt reject)
    def on_incoming_chat_connection(self, sock: socket.socket, peer_name: str, advertised_port: int, client_ip: str):
        # Đăng ký session vào ChatManager theo (ip, port) duy nhất
        self.chat_mgr.add_session(
            sock=sock,
            name=peer_name,
            ip=client_ip,
            port=advertised_port,
            set_active=False,  # Giữ nguyên phòng chat hiện tại nếu đang chat
        )

        # Khởi động luồng nhận tin nhắn cho peer này
        threading.Thread(
            target=self.chat_receiver_thread,
            args=(sock, peer_name, client_ip, advertised_port),
            name=f"ChatReceiver-{peer_name}:{advertised_port}",
            daemon=True,
        ).start()

        active = self.chat_mgr.get_active_partner()
        if not active:
            # Chưa chat với ai -> tự động chọn bạn này làm active
            self.chat_mgr.set_active_partner((client_ip, advertised_port))
            self.msg_mgr.mark_as_read((client_ip, advertised_port))
            Console.success(f"Đã kết nối với [{peer_name}] ({client_ip}:{advertised_port}). Nhập tin nhắn để bắt đầu trò chuyện!")
        else:
            # Đang chat với người khác -> thông báo bạn mới đã kết nối ở nền
            Console.info(
                f"[{peer_name}] ({client_ip}:{advertised_port}) đã kết nối với bạn. (Gõ /chat {advertised_port} để chuyển sang {peer_name})"
            )

    # 5. Callback khi có kết nối FILE đến
    def on_incoming_file(self, sock: socket.socket, sender_name: str, advertised_port: int, client_ip: str):
        self.transfer_mgr.handle_incoming_file(
            sock=sock,
            sender_name=sender_name,
            advertised_port=advertised_port,
            client_ip=client_ip,
        )

    # 6. Callback khi có tin nhắn nhanh direct message
    def on_incoming_direct_msg(self, sock: socket.socket, sender_name: str, advertised_port: int, client_ip: str):
        try:
            header, payload = recv_frame(sock)
            if header.get("type") == FrameType.MSG:
                text = payload.decode("utf-8", errors="replace")
                active = self.chat_mgr.get_active_partner()
                is_active = (active is not None and active.lower() == sender_name.lower())
                self.msg_mgr.add_message(Message(sender=sender_name, receiver=self.me, content=text), is_active_session=is_active)
                if is_active:
                    Console.chat_message(sender_name, text)
                else:
                    unread = self.msg_mgr.get_unread_count(sender_name)
                    Console.info(f"[*] Bạn có {unread} tin nhắn chưa đọc từ [{sender_name}]. (Gõ /chat {sender_name} để xem)")
        except Exception:
            pass
        finally:
            try:
                sock.close()
            except OSError:
                pass

    # 8. Khởi động UDP Discovery (Listener & Broadcaster)
    def on_udp_peer_found(self, p_name: str, p_ip: str, p_port: int, p_status: str):
        self.peer_mgr.add_or_update(name=p_name, ip=p_ip, tcp_port=p_port, status=p_status)

    # 9. Luồng dọn dẹp peer offline (quá PEER_TIMEOUT giây)
    def peer_cleanup_loop(self):
        while self.running:
            time.sleep(CLEANUP_INTERVAL)
            self.peer_mgr.cleanup_expired(PEER_TIMEOUT)

    def start(self):
        # 7. Khởi động TCP Server
        self.tcp_server = TCPServer(
            port=self.tcp_port,
            own_name=self.me,
            host="0.0.0.0",
            on_chat_connection=self.on_incoming_chat_connection,
            on_file_connection=self.on_incoming_file,
            on_direct_msg=self.on_incoming_direct_msg,
        )
        self.tcp_server.start()

        self.udp_listener = UDPListener(
            on_peer_discovered=self.on_udp_peer_found,
            own_tcp_port=self.tcp_port,
            own_name=self.me,
            udp_port=self.udp_port,
        )
        self.udp_listener.start()

        self.udp_broadcaster = UDPBroadcaster(
            name=self.me,
            tcp_port=self.tcp_port,
            status_provider=self.status_mgr.get_status,
            broadcast_ip=self.broadcast_ip,
            udp_port=self.udp_port,
        )
        self.udp_broadcaster.start()

        cleanup_thread = threading.Thread(target=self.peer_cleanup_loop, name="PeerCleanupWorker", daemon=True)
        cleanup_thread.start()

        # Banner khởi động
        Console.success(f"Khởi động thành công [{self.me}] trên cổng TCP {self.tcp_port} (UDP {self.udp_port})")
        Console.info("Gõ /help để xem danh sách lệnh, gõ /list để xem bạn bè online.")

    # 10. Luồng chủ động kết nối chat ra ngoài
    def do_connect_chat_worker(self, target_ip: str, target_port: int, target_name: str):
        try:
            Console.info(f"Đang kết nối tới [{target_name}] ({target_ip}:{target_port})...")
            # Sử dụng request_chat (bên kia sẽ tự động accept)
            accepted, sock, lock, remote_name = TCPClient.request_chat(
                ip=target_ip,
                tcp_port=target_port,
                own_name=self.me,
                own_tcp_port=self.tcp_port,
                timeout=10.0,
            )
            if accepted:
                self.chat_mgr.add_session(
                    sock=sock,
                    name=remote_name,
                    ip=target_ip,
                    port=target_port,
                    send_lock=lock,
                    set_active=True,
                )
                self.msg_mgr.mark_as_read((target_ip, target_port))
                threading.Thread(
                    target=self.chat_receiver_thread,
                    args=(sock, remote_name, target_ip, target_port),
                    name=f"ChatReceiver-{remote_name}:{target_port}",
                    daemon=True,
                ).start()
                Console.success(
                    f"Đã kết nối với [{remote_name}] ({target_ip}:{target_port}). Nhập tin nhắn để chat, /send <file> để gửi tệp, /leave để rời phòng."
                )
                # Hiển thị 5 tin nhắn gần nhất nếu đã từng chat trước đó
                history = self.msg_mgr.get_history((target_ip, target_port))
                if history:
                    print(f"--- 5 tin nhắn gần nhất với [{remote_name}] ({target_ip}:{target_port}) ---")
                    for m in history[-5:]:
                        print(f"  [{m.formatted_time()}] [{m.sender}]: {m.content}")
                    print("---------------------------------------------------------------")
            else:
                Console.warning(f"Không thể kết nối với [{target_name}].")
        except Exception as e:
            Console.error(f"Kết nối thất bại tới [{target_name}]: {e}")

    # Dọn dẹp khi thoát
    def shutdown(self):
        self.running = False
        self.transfer_mgr.shutdown()
        all_socks = self.chat_mgr.close_all()
        for s in all_socks:
            try:
                send_frame(s, {"type": FrameType.BYE}, b"")
                s.close()
            except OSError:
                pass

        self.udp_broadcaster.stop()
        self.udp_listener.stop()
        self.tcp_server.stop()
        Console.info("Đã đóng tất cả kết nối mạng. Tạm biệt!")

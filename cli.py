import os
import sys
import threading

if os.name == "nt":
    os.system("")

try:
    from prompt_toolkit import PromptSession
    from prompt_toolkit.patch_stdout import patch_stdout
    HAS_PROMPT_TOOLKIT = True
except ImportError:
    HAS_PROMPT_TOOLKIT = False

from network.protocol import FrameType, send_frame
from network.tcp_client import TCPClient

from core.peer_manager import PeerManager
from core.message import Message
from ui.console import Console
from ui.input_handler import InputHandler


def resolve_peer_target(arg: str, peer_mgr: PeerManager, cached_peers=None):
    arg = arg.strip()
    if not arg:
        return None, None, None

    if arg.isdigit():
        idx = int(arg)
        peers_list = cached_peers if (cached_peers is not None and len(cached_peers) > 0) else peer_mgr.list_peers()
        if 1 <= idx <= len(peers_list):
            target = peers_list[idx - 1]
            return target.ip, target.tcp_port, target.name

    peer = peer_mgr.find_by_name(arg)
    if peer:
        return peer.ip, peer.tcp_port, peer.name

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

    if arg.isdigit():
        target_port = int(arg)
        p = peer_mgr.find_by_port(target_port)
        if p:
            return p.ip, p.tcp_port, p.name
        if target_port >= 1024:
            return "127.0.0.1", target_port, f"Port {target_port}"

    return None, None, None


class CLI:
    def __init__(self, app):
        self.app = app
        self.use_prompt_toolkit = HAS_PROMPT_TOOLKIT
        self.session = None
        self.last_listed_peers = []
        self.commands = {
            "HELP": self.cmd_help,
            "LIST": self.cmd_list,
            "STATUS": self.cmd_status,
            "CHAT": self.cmd_chat,
            "SEND": self.cmd_send,
            "LEAVE": self.cmd_leave,
            "HISTORY": self.cmd_history,
            "DIRECT_MSG": self.cmd_direct_msg,
            "UNKNOWN": self.cmd_unknown,
            "MESSAGE": self.cmd_message,
        }

    def get_input(self, prompt_str: str) -> str:
        if self.session and self.use_prompt_toolkit:
            return self.session.prompt(prompt_str)
        line = input(prompt_str)
        sys.stdout.write("\033[A\033[2K\r")
        sys.stdout.flush()
        return line

    def run(self):
        if self.use_prompt_toolkit:
            try:
                self.session = PromptSession(erase_when_done=True)
            except Exception:
                self.session = None
                self.use_prompt_toolkit = False
        if not self.use_prompt_toolkit:
            Console.info("Không dùng được prompt_toolkit: chỉ hiện thông báo kết quả truyền tệp, không có thanh tiến trình.")

        if self.use_prompt_toolkit and self.session is not None:
            try:
                with patch_stdout():
                    self.run_cli_loop()
            except Exception:
                self.run_cli_loop()
        else:
            self.run_cli_loop()

    def run_cli_loop(self):
        self.last_listed_peers = []
        while True:
            prompt_str = "> "

            try:
                raw_line = self.get_input(prompt_str)
            except (KeyboardInterrupt, EOFError):
                break

            cmd = InputHandler.parse(raw_line)

            if cmd.name == "QUIT":
                break

            handler = self.commands.get(cmd.name)
            if handler:
                handler(cmd)

    def cmd_help(self, cmd):
        Console.print_help()

    def cmd_list(self, cmd):
        peer_mgr = self.app.peer_mgr
        msg_mgr = self.app.msg_mgr
        chat_mgr = self.app.chat_mgr

        active_peers = peer_mgr.list_peers()
        self.last_listed_peers = active_peers
        unread_map = msg_mgr.get_all_unread()
        connected_names = chat_mgr.list_connected_peer_names()
        connected_ports = chat_mgr.list_connected_ports()
        active_port = chat_mgr.get_active_port()
        Console.print_peer_list(
            peers=active_peers,
            unread_counts=unread_map,
            active_partner=chat_mgr.get_active_partner(),
            connected_peers=connected_names,
            connected_ports=connected_ports,
            active_port=active_port,
        )

    def cmd_status(self, cmd):
        status_mgr = self.app.status_mgr

        new_status = cmd.args.strip().lower()
        if new_status in ("online", "away"):
            if status_mgr.set_status(new_status):
                Console.success(f"Đã chuyển trạng thái sang: [{new_status.upper()}]")
        else:
            Console.warning("Trạng thái không hợp lệ! Vui lòng dùng: /status online hoặc /status away")

    def cmd_chat(self, cmd):
        peer_mgr = self.app.peer_mgr
        msg_mgr = self.app.msg_mgr
        chat_mgr = self.app.chat_mgr
        last_listed_peers = self.last_listed_peers

        target_str = cmd.args.strip()
        if not target_str:
            Console.warning("Cách dùng: /chat <số|tên_bạn|port>")
            return

        if not target_str.isdigit() and ":" not in target_str:
            matching_peers = peer_mgr.find_all_by_name(target_str)
            candidates = []
            seen_ports = set()
            for p in matching_peers:
                if p.tcp_port not in seen_ports:
                    candidates.append((p.name, p.ip, p.tcp_port))
                    seen_ports.add(p.tcp_port)
            for s in chat_mgr.list_all_sessions():
                if s["name"].lower() == target_str.lower() and s["port"] not in seen_ports:
                    candidates.append((s["name"], s["ip"], s["port"]))
                    seen_ports.add(s["port"])

            if len(candidates) > 1:
                Console.warning(f"Tìm thấy {len(candidates)} bạn có cùng tên '[{target_str}]':")
                for idx, (c_name, c_ip, c_port) in enumerate(candidates, 1):
                    print(f"    - [{c_name}] tại {c_ip}:{c_port} (Cổng TCP: {c_port})")
                Console.info(f"-> Vui lòng chọn cụ thể bằng cách gõ: /chat <port> (ví dụ: /chat {candidates[0][2]}) hoặc /chat <số_thứ_tự_trong_/list>")
                return

        t_ip, t_port, t_name = resolve_peer_target(target_str, peer_mgr, last_listed_peers)
        if not t_ip or not t_port:
            Console.error(f"Không tìm thấy peer '{target_str}'. Hãy gõ /list để xem danh sách bạn bè online.")
            return

        target_key = (t_ip, t_port)
        if chat_mgr.has_session(target_key):
            chat_mgr.set_active_partner(target_key)
            msg_mgr.mark_as_read(target_key)
            Console.success(f"Đã chuyển sang phòng chat với [{t_name}] ({t_ip}:{t_port}).")
            history = msg_mgr.get_history(target_key)
            if history:
                print(f"--- 5 tin nhắn gần nhất với [{t_name}] ({t_ip}:{t_port}) ---")
                for m in history[-5:]:
                    print(f"  [{m.formatted_time()}] [{m.sender}]: {m.content}")
                print("---------------------------------------------------------------")
            return

        threading.Thread(
            target=self.app.do_connect_chat_worker,
            args=(t_ip, t_port, t_name),
            name="ConnectChatWorker",
            daemon=True,
        ).start()

    def cmd_send(self, cmd):
        chat_mgr = self.app.chat_mgr
        transfer_mgr = self.app.transfer_mgr
        me = self.app.me
        tcp_port = self.app.tcp_port

        filepath = cmd.args.strip()
        if not filepath:
            Console.warning("Cách dùng: /send <đường_dẫn_tệp>")
            return

        active_session = chat_mgr.get_active_session()
        if not active_session:
            Console.warning("Bạn chưa mở phòng chat với ai. Hãy dùng /chat <tên> trước khi gửi file.")
            return

        partner = active_session["name"]
        p_ip = active_session["ip"]
        p_port = active_session["port"]

        if not os.path.isfile(filepath):
            Console.error(f"Tệp không tồn tại: {filepath}")
            return

        Console.info(f"Đang chuẩn bị gửi tệp '{filepath}' tới [{partner}] ({p_ip}:{p_port})...")
        transfer_mgr.send_file_async(
            target_ip=p_ip,
            target_port=p_port,
            own_name=me,
            own_tcp_port=tcp_port,
            filepath=filepath,
        )

    def cmd_leave(self, cmd):
        chat_mgr = self.app.chat_mgr

        cur_partner = chat_mgr.get_active_partner()
        if cur_partner:
            chat_mgr.set_active_partner(None)
            Console.info(
                f"Đã rời phòng chat với [{cur_partner}]. Kết nối vẫn được duy trì ngầm, các tin nhắn đến sẽ được lưu vào Chưa đọc."
            )
        else:
            Console.warning("Hiện tại bạn chưa ở trong phòng chat nào.")

    def cmd_history(self, cmd):
        peer_mgr = self.app.peer_mgr
        msg_mgr = self.app.msg_mgr
        chat_mgr = self.app.chat_mgr
        last_listed_peers = self.last_listed_peers

        target_peer = cmd.args.strip()
        active_sess = chat_mgr.get_active_session()

        if not target_peer and not active_sess:
            Console.warning("Cách dùng: /history <số|tên_bạn|port>")
            return

        if target_peer:
            t_ip, t_port, t_name = resolve_peer_target(target_peer, peer_mgr, last_listed_peers)
            lookup_key = (t_ip, t_port) if (t_ip and t_port) else target_peer
            display_tag = f"[{t_name}] ({t_ip}:{t_port})" if (t_name and t_port) else f"[{target_peer}]"
        else:
            lookup_key = (active_sess["ip"], active_sess["port"]) if active_sess.get("port", 0) > 0 else active_sess["name"]
            display_tag = f"[{active_sess['name']}] ({active_sess['ip']}:{active_sess['port']})"

        history = msg_mgr.get_history(lookup_key)
        print(f"\n--- Lịch sử trò chuyện với {display_tag} ({len(history)} tin nhắn) ---")
        if not history:
            print("  (Chưa có tin nhắn nào)")
        for m in history:
            print(f"[{m.formatted_time()}] [{m.sender}]: {m.content}")
        print("----------------------------------------------------------------\n")
        msg_mgr.mark_as_read(lookup_key)

    def cmd_direct_msg(self, cmd):
        peer_mgr = self.app.peer_mgr
        msg_mgr = self.app.msg_mgr
        me = self.app.me
        tcp_port = self.app.tcp_port
        last_listed_peers = self.last_listed_peers

        parts = cmd.args.split(maxsplit=1)
        if len(parts) < 2:
            Console.warning("Cách dùng: /msg <tên_bạn|port> <nội_dung_tin_nhắn>")
            return

        target_str = parts[0].strip()
        direct_text = parts[1].strip()

        t_ip, t_port, t_label = resolve_peer_target(target_str, peer_mgr, last_listed_peers)
        if not t_ip or not t_port:
            Console.error(f"Không tìm thấy peer '{target_str}'. Hãy gõ /list để xem danh sách bạn bè online.")
            return

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

    def cmd_unknown(self, cmd):
        Console.warning(f"Lệnh không hợp lệ: '{cmd.args}'. Gõ /help để xem hướng dẫn.")

    def cmd_message(self, cmd):
        chat_mgr = self.app.chat_mgr
        msg_mgr = self.app.msg_mgr
        me = self.app.me

        active_session = chat_mgr.get_active_session()
        if active_session:
            partner = active_session["name"]
            s_sock = active_session["sock"]
            s_lock = active_session["send_lock"]

            payload = cmd.args.encode("utf-8")
            header = {"type": FrameType.MSG, "length": len(payload)}
            endpoint_key = (
                (active_session["ip"], active_session["port"])
                if active_session.get("port", 0) > 0
                else partner
            )
            try:
                send_frame(s_sock, header, payload, send_lock=s_lock)
                msg_mgr.add_message(
                    Message(sender=me, receiver=partner, content=cmd.args),
                    is_active_session=True,
                    conversation_partner=endpoint_key,
                )

                Console.chat_message(me, cmd.args)
            except Exception as e:
                Console.error(f"Gửi tin nhắn thất bại tới [{partner}]: {e}")
                chat_mgr.remove_session(sock=s_sock)
        else:
            Console.warning("Bạn chưa chọn người để chat. Gõ /chat <tên_bạn> (ví dụ: /chat Nhan) hoặc /help.")

import socket
import threading
from typing import Tuple, Optional, Callable
from network.protocol import send_frame, recv_frame, FrameType
from config import CONNECT_TIMEOUT


class TCPClient:
    """
    Handles outbound TCP connections to remote peers.
    Supports both direct INTRO handshake and interactive CHAT_REQ (request / accept) handshake.
    """
    @staticmethod
    def connect_to_peer(
        ip: str,
        tcp_port: int,
        own_name: str,
        own_tcp_port: int,
        channel: str = "chat",
        timeout: float = CONNECT_TIMEOUT,
        on_socket: Optional[Callable[[socket.socket], None]] = None,
    ) -> Tuple[socket.socket, threading.Lock, str]:
        """
        Direct INTRO handshake (used for file transfers or direct connections).
        """
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)

        try:
            if on_socket:
                on_socket(sock)
            sock.connect((ip, tcp_port))
            send_lock = threading.Lock()

            intro_header = {
                "type": FrameType.INTRO,
                "name": own_name,
                "tcp_port": own_tcp_port,
                "channel": channel,
            }
            send_frame(sock, intro_header, payload=b"", send_lock=send_lock)

            remote_intro, _ = recv_frame(sock)
            remote_name = remote_intro.get("name", "Peer")

            sock.settimeout(None)
            return sock, send_lock, remote_name

        except Exception:
            try:
                sock.close()
            except OSError:
                pass
            raise

    @staticmethod
    def request_chat(
        ip: str,
        tcp_port: int,
        own_name: str,
        own_tcp_port: int,
        timeout: float = 60.0,
    ) -> Tuple[bool, Optional[socket.socket], Optional[threading.Lock], str]:
        """
        Sends a CHAT_REQ to the remote peer and waits for their ACCEPT or REJECT decision.
        Returns:
            (is_accepted: bool, sock, send_lock, remote_peer_name)
        """
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(CONNECT_TIMEOUT)

        try:
            sock.connect((ip, tcp_port))
            send_lock = threading.Lock()

            req_header = {
                "type": FrameType.CHAT_REQ,
                "name": own_name,
                "tcp_port": own_tcp_port,
            }
            send_frame(sock, req_header, payload=b"", send_lock=send_lock)

            # Wait for user's decision (up to timeout seconds)
            sock.settimeout(timeout)
            resp_header, _ = recv_frame(sock)

            remote_name = resp_header.get("name", "Peer")
            status = resp_header.get("status", "reject")

            if status == "accept":
                sock.settimeout(None)
                return True, sock, send_lock, remote_name
            else:
                sock.close()
                return False, None, None, remote_name

        except Exception:
            try:
                sock.close()
            except OSError:
                pass
            raise

    @staticmethod
    def send_direct_message(
        ip: str,
        tcp_port: int,
        own_name: str,
        own_tcp_port: int,
        message: str,
        timeout: float = CONNECT_TIMEOUT,
    ) -> bool:
        """
        Sends a single direct message (MSG frame) without establishing a persistent chat session.
        Useful for unread messages / notification from outside the active room.
        """
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        try:
            sock.connect((ip, tcp_port))
            # Handshake with channel="direct_msg"
            intro_header = {
                "type": FrameType.INTRO,
                "name": own_name,
                "tcp_port": own_tcp_port,
                "channel": "direct_msg",
            }
            send_frame(sock, intro_header, payload=b"")

            # Remote peer acknowledges with INTRO
            recv_frame(sock)

            # Send MSG frame
            payload = message.encode("utf-8")
            msg_header = {"type": FrameType.MSG, "length": len(payload)}
            send_frame(sock, msg_header, payload=payload)
            return True
        except Exception:
            return False
        finally:
            try:
                sock.close()
            except OSError:
                pass


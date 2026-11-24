import socket
import threading
from typing import Callable, Optional
from network.protocol import recv_frame, send_frame, FrameType, ProtocolError
from config import SOCKET_TIMEOUT


class TCPServer:
    """
    Listens for incoming TCP connections (chat or file transfers),
    performs the bidirectional INTRO / CHAT_REQ handshake to identify the peer,
    and dispatches the socket to the appropriate callback handler.
    """
    def __init__(
        self,
        port: int,
        own_name: str,
        host: str = "0.0.0.0",
        on_chat_connection: Optional[Callable[[socket.socket, str, int, str], None]] = None,
        on_chat_request: Optional[Callable[[socket.socket, str, int, str], None]] = None,
        on_file_connection: Optional[Callable[[socket.socket, str, int, str], None]] = None,
        on_direct_msg: Optional[Callable[[socket.socket, str, int, str], None]] = None,
        max_workers: int = 20,
    ):
        self.port = port
        self.own_name = own_name
        self.host = host
        self.on_chat_connection = on_chat_connection
        self.on_chat_request = on_chat_request
        self.on_file_connection = on_file_connection
        self.on_direct_msg = on_direct_msg
        self.max_workers = max_workers

        self._server_sock: Optional[socket.socket] = None
        self._stop_event = threading.Event()
        self._accept_thread: Optional[threading.Thread] = None
        self._active_threads: list[threading.Thread] = []
        self._lock = threading.Lock()

    def start(self) -> None:
        """Binds TCP listener socket and starts the acceptor thread."""
        if self._accept_thread and self._accept_thread.is_alive():
            return

        self._server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        import os
        if os.name == "nt" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self._server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        else:
            self._server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server_sock.bind((self.host, self.port))
        self._server_sock.listen(10)
        self._server_sock.settimeout(1.0)

        self._stop_event.clear()
        self._accept_thread = threading.Thread(target=self._accept_loop, name="TCPAcceptor", daemon=True)
        self._accept_thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        """Stops accepting new connections and cleans up sockets."""
        self._stop_event.set()
        if self._server_sock:
            try:
                self._server_sock.close()
            except OSError:
                pass
            self._server_sock = None

        if self._accept_thread and self._accept_thread.is_alive():
            self._accept_thread.join(timeout=timeout)
            self._accept_thread = None

    def _accept_loop(self) -> None:
        """Accepts incoming TCP sockets and delegates to dispatch workers."""
        while not self._stop_event.is_set():
            try:
                client_sock, (client_ip, client_port) = self._server_sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break

            worker = threading.Thread(
                target=self._handle_incoming_connection,
                args=(client_sock, client_ip),
                name=f"TCPHandshake-{client_ip}:{client_port}",
                daemon=True,
            )
            with self._lock:
                self._active_threads = [t for t in self._active_threads if t.is_alive()]
                if len(self._active_threads) < self.max_workers:
                    self._active_threads.append(worker)
                    worker.start()
                else:
                    client_sock.close()

    def _handle_incoming_connection(self, sock: socket.socket, client_ip: str) -> None:
        """
        Reads initial frame to determine if it's an INTRO or CHAT_REQ.
        """
        sock.settimeout(SOCKET_TIMEOUT)
        try:
            header, _ = recv_frame(sock)
            frame_type = header.get("type")

            # 1. Chat Request Flow :
            if frame_type == FrameType.CHAT_REQ:
                peer_name = header.get("name", "Unknown")
                advertised_port = int(header.get("tcp_port", 0))
                sock.settimeout(None)

                if self.on_chat_connection:
                    send_frame(sock, {
                        "type": FrameType.CHAT_RESP,
                        "name": self.own_name,
                        "status": "accept"
                    })
                    self.on_chat_connection(sock, peer_name, advertised_port, client_ip)
                elif self.on_chat_request:
                    self.on_chat_request(sock, peer_name, advertised_port, client_ip)
                else:
                    sock.close()
                return

            # 2. Standard INTRO Flow (Backward Compatible)
            if frame_type == FrameType.INTRO:
                peer_name = header.get("name", "Unknown")
                advertised_port = int(header.get("tcp_port", 0))
                channel = header.get("channel", "chat")

                send_frame(sock, {
                    "type": FrameType.INTRO,
                    "name": self.own_name,
                    "tcp_port": self.port,
                    "channel": channel,
                })

                sock.settimeout(None)

                if channel == "chat" and self.on_chat_connection:
                    self.on_chat_connection(sock, peer_name, advertised_port, client_ip)
                elif channel == "file" and self.on_file_connection:
                    self.on_file_connection(sock, peer_name, advertised_port, client_ip)
                elif channel == "direct_msg" and self.on_direct_msg:
                    self.on_direct_msg(sock, peer_name, advertised_port, client_ip)
                else:
                    sock.close()
                return

            sock.close()

        except (ProtocolError, ConnectionResetError, OSError):
            try:
                sock.close()
            except OSError:
                pass

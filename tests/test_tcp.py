"""
Unit Tests for TCP Framing, Multi-Message Stream & Connection Lifecycle
Author: Nguyen Dang Huynh Nhan (Networking Lead)
"""

import unittest
import socket
import threading
import time
from network.protocol import (
    recv_exact,
    send_frame,
    recv_frame,
    FrameType,
    ProtocolError,
)
from network.tcp_server import TCPServer
from network.tcp_client import TCPClient


class TestTCPFraming(unittest.TestCase):
    def test_send_and_recv_msg_frame(self):
        # Create a loopback pair using standard sockets
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        port = server.getsockname()[1]

        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.connect(("127.0.0.1", port))
        conn, _ = server.accept()

        # Send a Vietnamese UTF-8 message
        msg_text = "Chào Nhân, Đức và Huân! Kiểm thử socket tiếng Việt có dấu."
        payload = msg_text.encode("utf-8")
        header = {"type": FrameType.MSG, "length": len(payload)}

        send_frame(client, header, payload)
        rec_header, rec_payload = recv_frame(conn)

        self.assertEqual(rec_header["type"], FrameType.MSG)
        self.assertEqual(rec_payload.decode("utf-8"), msg_text)

        client.close()
        conn.close()
        server.close()

    def test_back_to_back_frames(self):
        """Tests sending multiple frames back-to-back without boundary corruption."""
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        port = server.getsockname()[1]

        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.connect(("127.0.0.1", port))
        conn, _ = server.accept()

        messages = [
            f"Message #{i}: " + ("x" * (i * 20)) for i in range(10)
        ]

        # Send all 10 messages sequentially
        for m in messages:
            p = m.encode("utf-8")
            h = {"type": FrameType.MSG, "length": len(p)}
            send_frame(client, h, p)

        # Receive all 10 messages and verify exact match
        for expected in messages:
            h, p = recv_frame(conn)
            self.assertEqual(p.decode("utf-8"), expected)

        client.close()
        conn.close()
        server.close()

    def test_unexpected_eof(self):
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        port = server.getsockname()[1]

        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.connect(("127.0.0.1", port))
        conn, _ = server.accept()

        # Send only 2 bytes of the 4-byte length prefix and close abruptly
        client.sendall(b"\x00\x00")
        client.close()

        with self.assertRaises(ProtocolError):
            recv_frame(conn)

        conn.close()
        server.close()


class TestTCPServerClientIntegration(unittest.TestCase):
    def test_intro_handshake_chat(self):
        received_intro = []
        ready_event = threading.Event()

        server_side_sock = [None]

        def on_chat(sock, name, port, ip):
            server_side_sock[0] = sock
            received_intro.append((name, port, ip))
            # Echo back a response to verify socket usability
            send_frame(sock, {"type": FrameType.MSG, "length": 4}, b"ACK!")
            ready_event.set()

        # Pick random ephemeral port
        test_port = 15001
        server = TCPServer(
            port=test_port,
            own_name="NhanServer",
            host="127.0.0.1",
            on_chat_connection=on_chat,
        )
        server.start()

        time.sleep(0.1)

        # Client connects
        client_sock, send_lock, remote_name = TCPClient.connect_to_peer(
            ip="127.0.0.1",
            tcp_port=test_port,
            own_name="DucClient",
            own_tcp_port=15002,
            channel="chat",
        )
        self.assertEqual(remote_name, "NhanServer")

        self.assertTrue(ready_event.wait(timeout=2.0), "Handshake callback was not triggered")
        self.assertEqual(len(received_intro), 1)
        self.assertEqual(received_intro[0][0], "DucClient")
        self.assertEqual(received_intro[0][1], 15002)

        # Verify client can receive frame from server
        header, payload = recv_frame(client_sock)
        self.assertEqual(payload, b"ACK!")

        client_sock.close()
        if server_side_sock[0]:
            server_side_sock[0].close()
        server.stop()


if __name__ == "__main__":
    unittest.main()

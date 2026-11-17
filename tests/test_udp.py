"""
Unit Tests for UDP Discovery & Protocol Parsing
Author: Nguyen Dang Huynh Nhan (Networking Lead)
"""

import unittest
import time
import socket
import threading
from network.protocol import encode_hello, parse_hello
from network.udp_broadcast import UDPBroadcaster
from network.udp_listener import UDPListener


class TestUDPProtocol(unittest.TestCase):
    def test_encode_hello_valid(self):
        packet = encode_hello("Nhan", 5001, "online")
        self.assertEqual(packet, b"HELLO|Nhan|5001|online")

        packet_away = encode_hello("Duc", 5002, "away")
        self.assertEqual(packet_away, b"HELLO|Duc|5002|away")

    def test_encode_hello_invalid_name(self):
        # Delimiter pipe character forbidden
        with self.assertRaises(ValueError):
            encode_hello("Nhan|Hacker", 5001, "online")

        # Newline forbidden
        with self.assertRaises(ValueError):
            encode_hello("Nhan\nAdmin", 5001, "online")

        # Empty name forbidden
        with self.assertRaises(ValueError):
            encode_hello("   ", 5001, "online")

    def test_encode_hello_invalid_port(self):
        with self.assertRaises(ValueError):
            encode_hello("Nhan", 80, "online")  # Well-known privileged port
        with self.assertRaises(ValueError):
            encode_hello("Nhan", 70000, "online")  # Out of range

    def test_encode_hello_invalid_status(self):
        with self.assertRaises(ValueError):
            encode_hello("Nhan", 5001, "busy")

    def test_parse_hello_valid(self):
        raw = b"HELLO|Huan|5003|online"
        res = parse_hello(raw)
        self.assertIsNotNone(res)
        name, port, status = res
        self.assertEqual(name, "Huan")
        self.assertEqual(port, 5003)
        self.assertEqual(status, "online")

    def test_parse_hello_malformed(self):
        self.assertIsNone(parse_hello(b"INVALID|Huan|5003|online"))
        self.assertIsNone(parse_hello(b"HELLO|Huan|abc|online"))
        self.assertIsNone(parse_hello(b"HELLO|Huan|5003"))
        self.assertIsNone(parse_hello(b""))


class TestUDPNetworkDiscovery(unittest.TestCase):
    def test_discovery_and_filtering(self):
        discovered_peers = []
        lock = threading.Lock()

        def on_discovered(name, ip, tcp_port, status):
            with lock:
                discovered_peers.append((name, ip, tcp_port, status))

        # Use an ephemeral unassigned port for test isolation
        test_udp_port = 19999

        # Listener configured with own_tcp_port = 5001
        listener = UDPListener(
            on_peer_discovered=on_discovered,
            own_tcp_port=5001,
            own_name="Nhan",
            bind_ip="127.0.0.1",
            udp_port=test_udp_port,
        )
        listener.start()

        time.sleep(0.1)

        # Broadcaster 1 (simulating peer Duc on port 5002) -> should be discovered
        broadcaster_peer = UDPBroadcaster(
            name="Duc",
            tcp_port=5002,
            broadcast_ip="127.0.0.1",
            udp_port=test_udp_port,
            interval=1.0,
        )
        broadcaster_peer.start()

        # Broadcaster 2 (simulating self on port 5001) -> should be filtered out!
        broadcaster_self = UDPBroadcaster(
            name="Nhan",
            tcp_port=5001,
            broadcast_ip="127.0.0.1",
            udp_port=test_udp_port,
            interval=1.0,
        )
        broadcaster_self.start()

        # Wait for packets to arrive
        time.sleep(0.5)

        broadcaster_peer.stop()
        broadcaster_self.stop()
        listener.stop()

        with lock:
            peer_names = [p[0] for p in discovered_peers]
            self.assertIn("Duc", peer_names, "External peer Duc should be discovered")
            self.assertNotIn("Nhan", peer_names, "Own announcement should be filtered out")


if __name__ == "__main__":
    unittest.main()

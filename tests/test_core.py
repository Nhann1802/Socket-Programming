import unittest
import time
from core.peer import Peer
from core.peer_manager import PeerManager
from core.message import Message
from core.message_manager import MessageManager
from core.status_manager import StatusManager
from core.chat_manager import ChatManager
from ui.input_handler import InputHandler


class TestCoreModules(unittest.TestCase):
    def test_peer_and_manager(self):
        added = []
        removed = []
        pm = PeerManager(on_peer_added=lambda p: added.append(p.name),
                         on_peer_removed=lambda p: removed.append(p.name))

        p, is_new = pm.add_or_update("Alice", "192.168.1.10", 5001, "online")
        self.assertTrue(is_new)
        self.assertEqual(len(added), 1)
        self.assertEqual(pm.count(), 1)

        # Update presence
        p2, is_new2 = pm.add_or_update("Alice", "192.168.1.10", 5001, "away")
        self.assertFalse(is_new2)
        self.assertEqual(p2.status, "away")

        # Find
        found = pm.find_by_name("alice")
        self.assertIsNotNone(found)
        self.assertEqual(found.tcp_port, 5001)

        # Cleanup expired
        p.last_seen = time.monotonic() - 15.0
        expired = pm.cleanup_expired(timeout_sec=10.0)
        self.assertEqual(len(expired), 1)
        self.assertEqual(pm.count(), 0)
        self.assertEqual(len(removed), 1)

    def test_message_manager(self):
        mm = MessageManager()
        mm.add_message(Message(sender="Alice", receiver="Bob", content="Hello!"), is_active_session=False)
        self.assertEqual(mm.get_unread_count("Alice"), 1)

        history = mm.get_history("Alice")
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0].content, "Hello!")

        mm.mark_as_read("Alice")
        self.assertEqual(mm.get_unread_count("Alice"), 0)

    def test_message_manager_endpoint_isolation(self):
        mm = MessageManager()
        # B on port 5002 sends a message
        mm.add_message(
            Message(sender="B", receiver="A", content="Hello from 5002"),
            is_active_session=False,
            conversation_partner=("127.0.0.1", 5002),
        )
        # B on port 5004 sends a message
        mm.add_message(
            Message(sender="B", receiver="A", content="Hello from 5004"),
            is_active_session=False,
            conversation_partner=("127.0.0.1", 5004),
        )

        # Unread counts are isolated
        self.assertEqual(mm.get_unread_count(("127.0.0.1", 5002)), 1)
        self.assertEqual(mm.get_unread_count(("127.0.0.1", 5004)), 1)
        # Total unread count across all peers when called with no arguments
        self.assertEqual(mm.get_unread_count(), 2)

        # Histories are isolated
        hist_5002 = mm.get_history(("127.0.0.1", 5002))
        hist_5004 = mm.get_history(("127.0.0.1", 5004))
        self.assertEqual(len(hist_5002), 1)
        self.assertEqual(hist_5002[0].content, "Hello from 5002")
        self.assertEqual(len(hist_5004), 1)
        self.assertEqual(hist_5004[0].content, "Hello from 5004")

        # Mark 5002 as read does NOT clear 5004
        mm.mark_as_read(("127.0.0.1", 5002))
        self.assertEqual(mm.get_unread_count(("127.0.0.1", 5002)), 0)
        self.assertEqual(mm.get_unread_count(("127.0.0.1", 5004)), 1)

    def test_peer_manager_find_all_by_name(self):
        pm = PeerManager()
        pm.add_or_update("B", "127.0.0.1", 5002, "online")
        pm.add_or_update("B", "127.0.0.1", 5004, "online")
        pm.add_or_update("Alice", "127.0.0.1", 5003, "online")

        matches = pm.find_all_by_name("b")
        self.assertEqual(len(matches), 2)
        ports = {p.tcp_port for p in matches}
        self.assertEqual(ports, {5002, 5004})

    def test_status_manager(self):
        sm = StatusManager("online")
        self.assertEqual(sm.get_status(), "online")
        self.assertTrue(sm.set_status("away"))
        self.assertEqual(sm.get_status(), "away")
        self.assertFalse(sm.set_status("invalid_status"))

    def test_chat_manager_multi_sessions(self):
        cm = ChatManager()
        # Mock socket objects
        s1 = object()
        s2 = object()

        # Connect Nhan
        cm.add_session(s1, "Nhan", "127.0.0.1", 5002, set_active=True)
        self.assertEqual(cm.get_active_partner(), "Nhan")
        self.assertTrue(cm.has_session("nhan"))

        # Connect Duc while chatting with Nhan (set_active=False)
        cm.add_session(s2, "Duc", "127.0.0.1", 5003, set_active=False)
        self.assertEqual(cm.get_active_partner(), "Nhan") # Still focused on Nhan
        self.assertTrue(cm.has_session("duc"))

        # Switch to Duc
        self.assertTrue(cm.set_active_partner("Duc"))
        self.assertEqual(cm.get_active_partner(), "Duc")

        # Leave room
        cm.set_active_partner(None)
        self.assertIsNone(cm.get_active_partner())
        self.assertTrue(cm.has_session("duc")) # Background session stays open!

    def test_duplicate_peer_names_no_collision(self):
        cm = ChatManager()
        s_b5002 = object()
        s_b5004 = object()
        s_c5003 = object()

        # A chats with B:5002
        cm.add_session(s_b5002, "B", "127.0.0.1", 5002, set_active=True)
        # C:5003 is also connected in background
        cm.add_session(s_c5003, "C", "127.0.0.1", 5003, set_active=False)

        self.assertEqual(cm.get_active_partner(), "B")
        self.assertEqual(cm.get_active_port(), 5002)

        # Another peer also named B connects from port 5004
        cm.add_session(s_b5004, "B", "127.0.0.1", 5004, set_active=False)

        # Verify B:5002 is still active and intact
        self.assertEqual(cm.get_active_partner(), "B")
        self.assertEqual(cm.get_active_port(), 5002)
        self.assertEqual(cm.session_count(), 3)
        self.assertTrue(cm.has_session(("127.0.0.1", 5002)))
        self.assertTrue(cm.has_session(("127.0.0.1", 5004)))
        self.assertTrue(cm.has_session(("127.0.0.1", 5003)))

        # If B:5002 disconnects (using its specific socket instance)
        removed_sess = cm.remove_session(sock=s_b5002)
        self.assertIsNotNone(removed_sess)
        self.assertEqual(removed_sess["name"], "B")
        self.assertEqual(removed_sess["port"], 5002)

        # Crucial check: Active partner must NOT randomly jump to C:5003!
        self.assertIsNone(cm.get_active_partner())
        self.assertEqual(cm.get_active_port(), 0)

        # Crucial check: B:5004 must NOT be deleted!
        self.assertTrue(cm.has_session(("127.0.0.1", 5004)))
        self.assertTrue(cm.has_session(("127.0.0.1", 5003)))
        self.assertEqual(cm.session_count(), 2)

    def test_input_handler(self):
        cmd = InputHandler.parse("/chat Alice")
        self.assertEqual(cmd.name, "CHAT")
        self.assertEqual(cmd.args, "Alice")

        cmd = InputHandler.parse("/send my_file.pdf")
        self.assertEqual(cmd.name, "SEND")
        self.assertEqual(cmd.args, "my_file.pdf")

        cmd = InputHandler.parse("/leave")
        self.assertEqual(cmd.name, "LEAVE")

        cmd = InputHandler.parse("/history Alice")
        self.assertEqual(cmd.name, "HISTORY")
        self.assertEqual(cmd.args, "Alice")

        cmd = InputHandler.parse("Xin chao")
        self.assertEqual(cmd.name, "MESSAGE")
        self.assertEqual(cmd.args, "Xin chao")

    def test_resolve_peer_target_by_index(self):
        from main import resolve_peer_target
        pm = PeerManager()
        pm.add_or_update("Alice", "192.168.1.10", 5001, "online")
        pm.add_or_update("Bob", "192.168.1.11", 5002, "online")

        # 1. Resolve by 1-based index
        ip, port, name = resolve_peer_target("1", pm)
        self.assertEqual(name, "Alice")
        self.assertEqual(ip, "192.168.1.10")
        self.assertEqual(port, 5001)

        ip2, port2, name2 = resolve_peer_target("2", pm)
        self.assertEqual(name2, "Bob")
        self.assertEqual(ip2, "192.168.1.11")
        self.assertEqual(port2, 5002)

        # 2. Resolve by Name
        ip3, port3, name3 = resolve_peer_target("Bob", pm)
        self.assertEqual(name3, "Bob")

        # 3. Resolve by valid port
        ip4, port4, name4 = resolve_peer_target("5001", pm)
        self.assertEqual(name4, "Alice")

        # 4. Out of range index
        ip5, port5, name5 = resolve_peer_target("99", pm)
        self.assertIsNone(ip5)


if __name__ == "__main__":
    unittest.main()

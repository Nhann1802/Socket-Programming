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

    def test_input_handler(self):
        cmd = InputHandler.parse("/chat Alice")
        self.assertEqual(cmd.name, "CHAT")
        self.assertEqual(cmd.args, "Alice")

        cmd = InputHandler.parse("/send my_file.pdf")
        self.assertEqual(cmd.name, "SEND")
        self.assertEqual(cmd.args, "my_file.pdf")

        cmd = InputHandler.parse("/leave")
        self.assertEqual(cmd.name, "LEAVE")

        cmd = InputHandler.parse("Xin chao")
        self.assertEqual(cmd.name, "MESSAGE")
        self.assertEqual(cmd.args, "Xin chao")


if __name__ == "__main__":
    unittest.main()

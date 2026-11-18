from dataclasses import dataclass
from typing import Optional


@dataclass
class Command:
    name: str
    args: str = ""


class InputHandler:
    """
    Parses raw user input strings into structured commands.
    """
    @staticmethod
    def parse(line: str) -> Command:
        text = line.strip()
        if not text:
            return Command(name="EMPTY")

        if text.startswith("/"):
            parts = text.split(maxsplit=1)
            cmd_name = parts[0].lower()
            cmd_args = parts[1].strip() if len(parts) > 1 else ""

            if cmd_name in ("/quit", "/exit"):
                return Command(name="QUIT")
            elif cmd_name in ("/list", "/peers"):
                return Command(name="LIST")
            elif cmd_name == "/chat":
                return Command(name="CHAT", args=cmd_args)
            elif cmd_name in ("/msg", "/tell"):
                return Command(name="DIRECT_MSG", args=cmd_args)
            elif cmd_name in ("/accept", "/y"):
                return Command(name="ACCEPT")
            elif cmd_name in ("/reject", "/n"):
                return Command(name="REJECT")
            elif cmd_name == "/send":
                return Command(name="SEND", args=cmd_args)
            elif cmd_name == "/leave":
                return Command(name="LEAVE")
            elif cmd_name == "/status":
                return Command(name="STATUS", args=cmd_args)
            elif cmd_name == "/history":
                return Command(name="HISTORY")
            elif cmd_name in ("/help", "/?"):
                return Command(name="HELP")
            else:
                return Command(name="UNKNOWN", args=cmd_name)

        return Command(name="MESSAGE", args=text)

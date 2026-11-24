import socket
import os
from pathlib import Path

# ==============================================================================
# NETWORK & DISCOVERY CONFIGURATION
# ==============================================================================
DEFAULT_UDP_PORT = 9999
DEFAULT_TCP_PORT = 5001
DEFAULT_BROADCAST_IP = "255.255.255.255"

# Heartbeat & Timeout parameters
HEARTBEAT_INTERVAL = 3.0    # Seconds between UDP HELLO broadcasts
PEER_TIMEOUT = 10.0          # Seconds before a peer is marked offline
CLEANUP_INTERVAL = 0.5      # Frequency of peer cleanup scan

# Socket timing & buffering
SOCKET_TIMEOUT = 5.0
CONNECT_TIMEOUT = 5.0

# ==============================================================================
# PROTOCOL LIMITS & CHUNK SIZES
# ==============================================================================
MAX_HEADER_SIZE = 8 * 1024       # 8 KiB maximum header size (prevent memory abuse)
MAX_MSG_SIZE = 64 * 1024         # 64 KiB maximum text message length
FILE_CHUNK_SIZE = 64 * 1024      # 64 KiB per file streaming chunk
MAX_FILE_SIZE = 10 * 1024 ** 3   # Giới hạn mỗi tệp: 10 GiB.

# ==============================================================================
# STORAGE & PATH CONFIGURATION
# ==============================================================================
BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DOWNLOAD_DIR = str(BASE_DIR / "downloads")


def validate_port(port: int) -> bool:
    """Validates whether a port number is within the valid user range (1024 - 65535)."""
    return isinstance(port, int) and 1024 <= port <= 65535


def is_tcp_port_available(port: int, host: str = "0.0.0.0") -> bool:
    """Checks whether a TCP port is currently free to bind on host."""
    if not validate_port(port):
        return False
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            if os.name == "nt" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                s.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            s.bind((host, port))
            return True
        except OSError:
            return False


def get_local_ip() -> str:
    """
    Attempts to discover the preferred outbound local IPv4 address by probing
    a public endpoint (without sending actual packets over the wire).
    Falls back to 127.0.0.1 if network is unavailable.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # 8.8.8.8 is used merely to determine default routing interface
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip

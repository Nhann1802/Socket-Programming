import json
import struct
import socket
import threading
from typing import Optional, Tuple, Any, Dict
from config import MAX_HEADER_SIZE, MAX_MSG_SIZE, validate_port


class ProtocolError(Exception):
    """Raised when incoming data violates protocol framing or limits."""
    pass


class FrameType:
    INTRO = "INTRO"
    MSG = "MSG"
    FILE = "FILE"
    BYE = "BYE"
    CHAT_REQ = "CHAT_REQ"
    CHAT_RESP = "CHAT_RESP"


# ==============================================================================
# UDP PROTOCOL: HELLO PACKET ENCODING & PARSING
# ==============================================================================
def encode_hello(name: str, tcp_port: int, status: str = "online") -> bytes:
    """
    Encodes presence packet format: HELLO|<name>|<tcp_port>|<status>
    Raises ValueError if parameters contain invalid characters or port is out of range.
    """
    clean_name = name.strip()
    clean_status = status.strip().lower()

    if not clean_name:
        raise ValueError("Peer name cannot be empty")
    if "|" in clean_name or "\n" in clean_name or "\r" in clean_name:
        raise ValueError("Peer name cannot contain delimiter '|' or newline characters")
    if not validate_port(tcp_port):
        raise ValueError(f"Invalid TCP port: {tcp_port}. Must be 1024-65535")
    if clean_status not in ("online", "away"):
        raise ValueError(f"Invalid status: {status}. Must be 'online' or 'away'")

    packet_str = f"HELLO|{clean_name}|{tcp_port}|{clean_status}"
    return packet_str.encode("utf-8")


def parse_hello(raw_bytes: bytes) -> Optional[Tuple[str, int, str]]:
    """
    Parses incoming UDP broadcast payload.
    Returns (name, tcp_port, status) if valid, or None if malformed.
    """
    try:
        text = raw_bytes.decode("utf-8")
        parts = text.split("|")
        if len(parts) != 4:
            return None
        if parts[0] != "HELLO":
            return None

        name = parts[1].strip()
        tcp_port = int(parts[2])
        status = parts[3].strip().lower()

        if not name or not validate_port(tcp_port) or status not in ("online", "away"):
            return None

        return name, tcp_port, status
    except (UnicodeDecodeError, ValueError):
        return None


# ==============================================================================
# TCP FRAMING: STREAM ENCODING & DECODING
# ==============================================================================
def recv_exact(sock: socket.socket, n: int) -> bytes:
    """
    Receives exactly n bytes from a TCP socket.
    Raises ConnectionResetError if EOF is encountered before any bytes are read.
    Raises ProtocolError if EOF occurs mid-stream (partial read).
    """
    if n == 0:
        return b""

    chunks = []
    received = 0
    while received < n:
        try:
            chunk = sock.recv(n - received)
        except (socket.timeout, BlockingIOError):
            raise
        except OSError as e:
            raise ConnectionResetError(f"Socket error during recv_exact: {e}") from e

        if not chunk:
            if received == 0:
                raise ConnectionResetError("Connection closed by remote peer (EOF)")
            raise ProtocolError(f"Unexpected EOF: expected {n} bytes, received {received} bytes")

        chunks.append(chunk)
        received += len(chunk)

    return b"".join(chunks)


def send_frame(sock: socket.socket, header: Dict[str, Any], payload: bytes = b"",
               send_lock: Optional[threading.Lock] = None) -> None:
    """
    Encodes and transmits a full TCP frame:
    [4-byte header length (!I)][JSON UTF-8 header][payload]
    Thread-safe when send_lock is provided.
    """
    if not isinstance(header, dict) or "type" not in header:
        raise ProtocolError("Header must be a dictionary containing 'type'")

    try:
        header_json = json.dumps(header, ensure_ascii=False)
        header_bytes = header_json.encode("utf-8")
    except Exception as e:
        raise ProtocolError(f"Failed to serialize header to JSON: {e}") from e

    header_len = len(header_bytes)
    if header_len > MAX_HEADER_SIZE:
        raise ProtocolError(f"Header length ({header_len} B) exceeds max limit ({MAX_HEADER_SIZE} B)")

    length_prefix = struct.pack("!I", header_len)
    frame_bytes = length_prefix + header_bytes + payload

    if send_lock:
        with send_lock:
            sock.sendall(frame_bytes)
    else:
        sock.sendall(frame_bytes)


def recv_header(sock: socket.socket) -> Dict[str, Any]:
    """
    Reads the 4-byte prefix and unpacks the JSON header.
    Validates size against MAX_HEADER_SIZE.
    """
    prefix = recv_exact(sock, 4)
    header_len = struct.unpack("!I", prefix)[0]

    if header_len == 0 or header_len > MAX_HEADER_SIZE:
        raise ProtocolError(f"Invalid header length: {header_len} (limit: {MAX_HEADER_SIZE})")

    header_raw = recv_exact(sock, header_len)
    try:
        header = json.loads(header_raw.decode("utf-8"))
    except Exception as e:
        raise ProtocolError(f"Failed to decode JSON header: {e}") from e

    if not isinstance(header, dict) or "type" not in header:
        raise ProtocolError("Header must be a JSON object containing a 'type' field")

    return header


def recv_frame(sock: socket.socket) -> Tuple[Dict[str, Any], bytes]:
    """
    Reads a complete frame (header + payload) for small frames (MSG, INTRO, BYE).
    For large files, callers should use recv_header() and read chunks streamingly.
    """
    header = recv_header(sock)
    frame_type = header.get("type")

    payload_len = 0
    if frame_type == FrameType.MSG:
        payload_len = header.get("length", 0)
        if payload_len < 0 or payload_len > MAX_MSG_SIZE:
            raise ProtocolError(f"MSG payload length {payload_len} out of allowed bounds (0 - {MAX_MSG_SIZE})")
    elif frame_type == FrameType.FILE:
        # If caller called recv_frame on FILE, size is header["size"]
        payload_len = header.get("size", 0)

    payload = recv_exact(sock, payload_len) if payload_len > 0 else b""
    return header, payload

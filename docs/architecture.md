# LAN Chat & File Sharing — Kiến trúc Hệ thống & Luồng Mạng (Architecture)
> **Tác giả:** Nguyễn Đăng Huỳnh Nhân (Networking Lead)  
> **Phiên bản:** 1.0  

---

## 1. Mô hình Phân lớp Hệ thống (Layered Architecture)

Hệ thống được thiết kế theo 3 tầng độc lập, giao tiếp thông qua các Interface và Callback rõ ràng:

```text
+-------------------------------------------------------------+
|                  TẦNG GIAO DIỆN & CLI (UI Layer)             |
|   Phụ trách: Huân (ScreenManager, InputHandler, Console)    |
+-------------------------------------------------------------+
                              |
                              v
+-------------------------------------------------------------+
|                  TẦNG CORE & DỮ LIỆU (Core Layer)           |
|   Phụ trách: Đức (PeerManager, ChatManager, MessageManager) |
+-------------------------------------------------------------+
                              |
                              v
+-------------------------------------------------------------+
|               TẦNG MẠNG & PROTOCOL (Networking Layer)       |
|   Phụ trách: Nhân (UDP Discovery, TCP Server/Client, Framing)|
+-------------------------------------------------------------+
```

---

## 2. Mô hình Đa luồng (Threading Model)

Để đảm bảo các thao tác mạng (I/O) không bao giờ làm đứng giao diện dòng lệnh hay làm gián đoạn việc chat khi đang truyền file dung lượng lớn:

| Luồng (Thread) | Module đảm nhiệm | Nhiệm vụ | Vòng đời |
|---|---|---|---|
| **Main Thread** | `main.py`, `ui/` | Nhận input từ bàn phím, phân tích lệnh, hiển thị màn hình | Chạy đến khi người dùng gõ `/quit` hoặc tắt app |
| **UDP Broadcaster** | `network/udp_broadcast.py` | Phát định kỳ gói tin `HELLO` 3 giây/lần | Chạy daemon đến khi gọi `stop()` |
| **UDP Listener** | `network/udp_listener.py` | Lắng nghe gói tin phát hiện peer trên cổng `9999` | Chạy daemon đến khi gọi `stop()` |
| **TCP Acceptor** | `network/tcp_server.py` | Chờ và tiếp nhận các kết nối TCP đến | Chạy daemon đến khi server tắt |
| **TCP Dispatcher** | `network/tcp_server.py` | Đọc frame `INTRO` ban đầu, phân loại sang luồng Chat hoặc File | Thoát ngay sau khi bàn giao socket |
| **Chat Receiver** | `core/chat_manager.py` | Đọc liên tục các frame `MSG` từ một peer cụ thể | Tồn tại suốt thời gian kết nối với peer đó |
| **File Worker** | `transfer/` | Đọc / ghi các chunk tập tin 64 KiB qua kết nối TCP riêng | Thoát khi truyền xong tệp hoặc gặp lỗi |

---

## 3. Luồng hoạt động chi tiết (Sequence Workflows)

### 3.1. Tự động tìm kiếm Peer (UDP Discovery)
1. Instance khởi động:
   * Khởi chạy `UDPListener` lắng nghe trên cổng `9999`.
   * Khởi chạy `UDPBroadcaster` phát gói `HELLO|<name>|<tcp_port>|online`.
2. Khi máy khác nhận được gói tin:
   * `UDPListener` trích xuất `(source_ip, advertised_tcp_port)`.
   * Kiểm tra nếu không phải chính mình $\rightarrow$ gọi callback `PeerManager.add_or_update(name, ip, tcp_port, status)`.
3. Bộ dọn dẹp `PeerManager` quét mỗi `0.5` giây:
   * Nếu `now - last_seen > 10.0s` $\rightarrow$ peer chuyển sang trạng thái offline.

### 3.2. Thiết lập cuộc trò chuyện (TCP Chat Handshake)
1. Người dùng A gõ lệnh `/chat B`.
2. `ChatManager` gọi `TCPClient.connect_to_peer(ip, tcp_port, own_name, own_tcp_port, channel="chat")`.
3. Bên nhận (máy B) chấp nhận kết nối tại `TCPServer`:
   * Đọc frame `INTRO`. Thấy `channel == "chat"`, gọi callback `on_chat_connection`.
   * Bàn giao socket cho luồng `ChatReceiver` của máy B.
4. Hai bên gửi nhận các frame `MSG` an toàn qua hàm `send_frame` và `recv_frame` được bảo vệ bởi `send_lock`.

### 3.3. Tách biệt kênh truyền file (Independent File Channel)
* Khi người dùng gõ `/send <file>`, hệ thống mở một **kết nối TCP hoàn toàn mới** với `channel="file"` tới máy nhận.
* Nhờ đó, dữ liệu file chạy trên socket và worker riêng, không chiếm dụng socket chat và không làm gián đoạn việc gõ/nhận tin nhắn tức thời.

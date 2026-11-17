# LAN Chat & File Sharing — Tài liệu Giao thức (Protocol Specification)
> **Phụ trách:** Nguyễn Đăng Huỳnh Nhân (Networking Lead)  
> **Phiên bản:** 1.0  
> **Trạng thái:** Đã triển khai và vượt qua bộ kiểm thử tự động.

---

## 1. Giao thức UDP Presence (Peer Discovery)

### 1.1. Mục đích
Cho phép các máy tính trong cùng mạng LAN tự động tìm thấy nhau, cập nhật trạng thái hoạt động (`online` hoặc `away`), và phát hiện khi một máy thoát hoặc mất kết nối mà không cần máy chủ trung tâm (Serverless P2P).

### 1.2. Định dạng Packet
Gói tin UDP được gửi dưới dạng chuỗi UTF-8 dạng plain-text phân cách bằng dấu gạch đứng `|`:

```text
HELLO|<name>|<tcp_port>|<status>
```

* **`HELLO`**: Tiền tố bắt buộc xác định loại gói tin discovery.
* **`<name>`**: Tên hiển thị của người dùng (UTF-8, không được chứa dấu `|`, không chứa ký tự xuống dòng `\r`, `\n`).
* **`<tcp_port>`**: Cổng TCP mà instance này đang mở lắng nghe kết nối chat/file (từ 1024 đến 65535).
* **`<status>`**: Trạng thái hiện tại của peer, chỉ chấp nhận một trong hai giá trị: `online` hoặc `away`.

### 1.3. Quy tắc truyền nhận & Định danh Peer
1. **Chu kỳ phát:** Mỗi peer tự động broadcast gói `HELLO` **3 giây một lần** tới địa chỉ broadcast (`255.255.255.255` hoặc broadcast của subnet) trên cổng **9999**.
2. **Định danh duy nhất (Peer ID):** Khóa định danh của một peer trong phiên là bộ đôi:
   $$\text{Peer ID} = (\text{Source IP}, \text{Advertised TCP Port})$$
   *Lý do:* Không dùng IP thuần túy vì có thể có nhiều instance chạy đồng thời trên cùng một máy (loopback). Không dùng Source Port UDP vì cổng này do hệ điều hành cấp phát ngẫu nhiên mỗi lần gửi.
3. **Lọc gói tin của chính mình:** Bên nhận lấy IP nguồn từ socket (`src_ip`). Nếu `advertised_tcp_port == own_tcp_port` và `src_ip` thuộc local IP của máy thì gói tin sẽ bị bỏ qua.
4. **Hết hạn (Timeout):** Nếu sau **10 giây** mà không nhận được heartbeat mới từ một peer, peer đó được coi là offline và xóa khỏi danh sách hoạt động.

---

## 2. Giao thức TCP Framing (Chat & File Transfer)

### 2.1. Vấn đề luồng byte của TCP
Do TCP là giao thức hướng luồng byte liên tục (byte-stream oriented), không bảo toàn ranh giới thông điệp (message boundary). Nhiều thông điệp gửi liên tiếp có thể bị dính gói hoặc xé gói. Giao thức áp dụng cơ chế **Length-Prefixed Framing**.

### 2.2. Cấu trúc Frame
Mọi thông điệp TCP đều tuân thủ cấu trúc 3 phần rõ ràng:

```text
+-------------------------+-------------------------+-------------------------+
|  4-byte Header Length   |       JSON Header       |         Payload         |
|      (uint32, !I)       |         (UTF-8)         |       (Raw bytes)       |
+-------------------------+-------------------------+-------------------------+
```

1. **Header Length (4 bytes):** Số nguyên không dấu 32-bit theo thứ tự Network Byte Order (Big-Endian, định dạng `!I` trong Python `struct`). Giới hạn tối đa: **8 KiB (8192 bytes)**.
2. **JSON Header:** Chuỗi JSON chứa metadata của frame. Bắt buộc phải có trường `"type"`.
3. **Payload:** Dữ liệu nhị phân hoặc chuỗi byte đính kèm có độ dài xác định bởi Header.

---

## 3. Các loại Frame (Frame Types)

### 3.1. Frame `INTRO` (Bắt tay nhận diện)
Được bên chủ động kết nối (Client) gửi **ngay lập tức** sau khi kết nối TCP thành công đến Listener của Peer.

* **Cấu trúc Header:**
```json
{
  "type": "INTRO",
  "name": "Nhan",
  "tcp_port": 5001,
  "channel": "chat"
}
```
* **Các trường:**
  * `name`: Tên của peer gửi kết nối.
  * `tcp_port`: Cổng TCP lắng nghe của peer gửi.
  * `channel`: `"chat"` (kênh chat dài hạn) hoặc `"file"` (kênh truyền tệp tạm thời).
* **Payload:** Rỗng (`0` bytes).

### 3.2. Frame `MSG` (Tin nhắn văn bản)
Dùng trên kênh `chat` để truyền tin nhắn trò chuyện giữa hai bên.

* **Cấu trúc Header:**
```json
{
  "type": "MSG",
  "length": 34
}
```
* **Payload:** Nội dung tin nhắn mã hóa UTF-8 có kích thước đúng bằng `length` byte (giới hạn tối đa 64 KiB).

### 3.3. Frame `FILE` (Truyền tập tin)
Dùng trên kết nối TCP riêng biệt (`channel="file"`).

* **Cấu trúc Header:**
```json
{
  "type": "FILE",
  "filename": "tailieu.pdf",
  "size": 1048576
}
```
* **Payload:** Dòng byte nhị phân của tập tin có tổng độ dài `size` byte, được truyền theo từng chunk (mặc định 64 KiB/chunk).

### 3.4. Frame `BYE` (Đóng kết nối)
Báo hiệu chủ động kết thúc kết nối một cách an toàn trước khi đóng socket.

```json
{
  "type": "BYE"
}
```

---

## 4. Hợp đồng API Module `network/protocol.py`

| Tên hàm | Chữ ký | Mô tả & Hợp đồng xử lý lỗi |
|---|---|---|
| `recv_exact` | `(sock, n) -> bytes` | Lặp `sock.recv()` đến khi gom đủ đúng `n` bytes. Ném `ConnectionResetError` nếu gặp EOF khi chưa nhận được byte nào. Ném `ProtocolError` nếu EOF xuất hiện giữa chừng. |
| `send_frame` | `(sock, header, payload=b"", send_lock=None)` | Đóng gói 4 byte độ dài + JSON header + payload. Luồng an toàn (Thread-safe) khi truyền kèm `send_lock`. |
| `recv_header`| `(sock) -> dict` | Đọc 4 byte độ dài, kiểm tra giới hạn `MAX_HEADER_SIZE`, giải mã JSON và trả về dictionary. |
| `recv_frame` | `(sock) -> (dict, bytes)` | Đọc toàn bộ header và payload của các frame ngắn (`MSG`, `INTRO`, `BYE`). |
| `encode_hello`| `(name, tcp_port, status) -> bytes` | Kiểm tra tính hợp lệ và đóng gói chuỗi `HELLO`. Ném `ValueError` nếu tham số chứa ký tự cấm. |
| `parse_hello` | `(raw_bytes) -> (name, tcp_port, status) \| None` | Phân tích gói UDP; trả về tuple nếu đúng định dạng hoặc `None` nếu lỗi/giả mạo. |

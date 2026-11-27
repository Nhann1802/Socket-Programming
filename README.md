## Socket Programming — LAN Chat & File Sharing
---

### Thông tin đồ án

- **Môn học:** Mạng Máy Tính
- **Lớp:** 25C04
- **Đề tài:** Xây dựng ứng dụng trò chuyện và chia sẻ tập tin trong mạng LAN bằng Socket
- **Giao diện:** Dòng lệnh (CLI)

### Thành viên thực hiện

| STT | Họ và tên | MSSV |
|---|---|---|
| 1 | Nguyễn Đăng Huỳnh Nhân | 25127221 |
| 2 | Đào Vạn Đức | 25127036 |
| 3 | Nguyễn Minh Huân | 25127050 |

---

# Cài đặt 
Yêu cầu: Python 3.10+ 
Cài đặt thư viện:
```bash 
python -m pip install prompt_toolkit
```

# Sử dụng

#### 1. Chạy nhiều terminal trên CÙNG 1 MÁY TÍNH
Mỗi terminal cần lắng nghe trên một cổng TCP khác nhau để tránh xung đột cổng:
- **Terminal 1 (Ví dụ: Nhân):**
  ```powershell
  python main.py --name Nhan --tcp-port 5001
  ```
- **Terminal 2 (Ví dụ: Đức):**
  ```powershell
  python main.py --name Duc --tcp-port 5002
  ```
*(Ghi chú: Nếu không truyền `--tcp-port` ở terminal thứ 2, ứng dụng sẽ tự động dò và chọn cổng rảnh tiếp theo như 5002, 5003...)*

#### 2. Chạy trên 2 MÁY TÍNH KHÁC NHAU (chung mạng LAN / Wi-Fi)
Vì mỗi máy tính có địa chỉ IP riêng biệt nên có thể chạy lệnh trực tiếp mà không lo trùng cổng:
- **Máy A:**
  ```powershell
  python main.py --name Nhan
  ```
- **Máy B:**
  ```powershell
  python main.py --name Duc
  ```
*(Hai máy sẽ tự động tìm thấy nhau qua giao thức UDP Broadcast trên cổng 9999).*

---

### 3. Các thao tác lệnh cơ bản
1. **Xem bạn bè online:** `/list`
2. **Mở phòng chat:** `/chat <tên | port | số_thứ_tự>` (Ví dụ: `/chat Duc`, `/chat 5002` hoặc `/chat 1`)
3. **Nhắn tin:** Gõ nội dung tin nhắn và nhấn Enter.
4. **Gửi file:** `/send <đường_dẫn_tệp>` (Ví dụ: `/send README.md`). Tệp nhận sẽ được lưu tự động tại `downloads/`.
5. **Rời phòng chat hiện tại:** `/leave` (tin nhắn đến sau đó sẽ lưu vào danh sách Chưa đọc).
6. **Thoát chương trình:** `/quit` (hủy lượt truyền đang chạy nếu có, dọn file tạm rồi thoát).

---

### 4. Quy tắc an toàn truyền tệp & giao diện (Transfer & UI)
- Giới hạn mỗi tệp là **10 GiB**. Tệp nhận nằm trong thư mục `downloads/`.
- Tên tệp không hợp lệ được đổi theo quy tắc Windows; dòng kết quả hiển thị đường dẫn thực tế.
- Tệp trùng tên được tự động đánh số thêm `_1`, `_2`... và mỗi lượt nhận có file tạm `.part` riêng biệt.
- Nếu quá trình truyền bị lỗi hoặc người dùng gõ `/quit`, file tạm `.part` của lượt đó sẽ được xóa tự động. (Tắt cưỡng bức tiến trình hoặc mất điện không đảm bảo dọn file tạm).
- Khi có `prompt_toolkit`, mỗi lượt gửi/nhận có thanh tiến trình ở dưới dòng nhập, cập nhật liên tục ~10 lần/giây. Chat và thông báo vẫn hiển thị mà không làm mất nội dung đang gõ dở.
- Nếu không cài đặt `prompt_toolkit`, ứng dụng vẫn truyền tệp bình thường và in thông báo hoàn tất cuối cùng.

---
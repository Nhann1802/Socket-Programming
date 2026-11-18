# Socket Programming — LAN Chat & File Sharing

## Thông tin đồ án

- **Môn học:** Mạng Máy Tính
- **Lớp:** 25C04
- **Đề tài:** Xây dựng ứng dụng trò chuyện và chia sẻ tập tin trong mạng LAN bằng Socket
- **Giao diện:** Dòng lệnh (CLI)
## Thành viên thực hiện

| STT | Họ và tên | MSSV |
|---|---|---|
| 1 | Nguyễn Đăng Huỳnh Nhân | 25127221 |
| 2 | Đào Vạn Đức | 25127036 |
| 3 | Nguyễn Minh Huân | 25127050 |
## Chạy và kiểm thử

Dùng Python 3.10 trở lên và terminal tương tác:

```sh
python -m pip install -r requirements.txt
python main.py --name A --tcp-port 5001
python main.py --name B --tcp-port 5002
python -m unittest discover -s tests -v
```

Thử nhiều instance trên cùng máy: thêm `--broadcast-ip 127.255.255.255`.
Dùng `/list`, `/chat B`, nhập tin nhắn và `/send <đường_dẫn_tệp>`.
`/quit` hủy lượt truyền đang chạy, dọn file tạm rồi thoát.

Giới hạn mỗi tệp là **10 GiB**. Tệp nhận nằm trong `storage/downloads/`.
Tên không hợp lệ được đổi theo quy tắc Windows; dòng kết quả hiển thị đường dẫn thực tế.
Tệp trùng tên được thêm `_1`, `_2`... và mỗi lượt nhận có file tạm riêng.
Nếu truyền lỗi hoặc `/quit`, file tạm của lượt đó được xóa. Tắt cưỡng bức tiến trình hoặc mất điện không đảm bảo dọn file tạm.

Khi có `prompt_toolkit`, mỗi lượt gửi/nhận có một thanh ở dưới dòng nhập, cập nhật khoảng 10 lần/giây.
Chat và thông báo vẫn hiển thị, giữ nguyên nội dung đang gõ.
Khi xong, thanh biến mất và có một dòng kết quả; tệp nhỏ có thể xong trước lần redraw tiếp theo.
Nếu thiếu thư viện, ứng dụng vẫn truyền file nhưng chỉ in kết quả cuối, không có thanh cập nhật.
Thông báo gửi 100% nghĩa là dữ liệu đã gửi qua socket; giao thức hiện tại không có ACK xác nhận lưu ở bên nhận.

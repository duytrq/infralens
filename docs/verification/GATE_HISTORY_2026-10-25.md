# Lọc lịch sử theo gate — 2026-10-25

Endpoint lịch sử có query gate_status: passed, failed, incomplete, disabled,
pending, unavailable. Bộ lọc phối hợp với execution status và áp dụng trong
SQLite trước LIMIT/cursor. Mặc định giữ kết quả API cũ; không đổi schema DB,
không đánh giá lại report hoặc thay đổi baseline.

Disabled gồm request cũ chưa có gate. Pending chỉ là gate đã bật chưa có quyết
định khi queued/running; unavailable là gate đã bật nhưng đã kết thúc mà chưa có
quyết định. Hai trường hợp này không được gộp thành gate passed.

Dashboard thêm bộ chọn gate, giữ lựa chọn qua polling, bỏ response đã cũ khi
đổi bộ lọc. Đổi bộ lọc xóa cursor và vô hiệu nút trang cũ tới khi có response.
Tạo lượt mới xóa cả hai bộ lọc để thấy lượt mới ngay trong lịch sử.

## Kiểm thử

- Thêm **21 test cases**: cả sáu nhóm trạng thái, project scope, request/report
  cũ, pagination không lặp/bỏ sót, kết hợp execution/gate, input sai không echo,
  authentication và project không tồn tại.
- Backend: **96 passed**.
- Toàn bộ suite: **681 passed, 9 skipped, 16 deselected**, 112,71 giây. Gồm 7
  test mới của [sửa lỗi hủy](CANCELLATION_2026-10-25.md) ở commit riêng trước đó.
- Ruff check, format check, uv lock check, git diff --check và Node --check JS đạt.
- Warning TestClient/httpx deprecated đã có sẵn. Không chạy lại AWS/Terraform live
  hoặc các suite external-tool chưa được chọn.

Wheel ở reports/history-filter-build/infralens-0.1.0-py3-none-any.whl build đạt.
Giải nén và import với Python -I từ đúng package tạm: asset có bộ lọc, API tạo
import run bị gate chặn, gate_status=failed trả đúng ID, phối hợp status=failed
trả rỗng vì execution vẫn succeeded. Script local:
reports/verify_history_filter_wheel.py.

## Trình duyệt

Chạy server localhost:8765 với registry demo, token lấy từ file local mà không
in ra log. Click/select trên in-app browser và đọc kết quả thật:

1. Gate chặn + Hoàn tất: thấy đúng 4 lượt trước khi tạo demo mới; có thể mở report
   #7, đọc gate và comparison. Gate chặn + Lỗi: danh sách rỗng.
2. Không lọc execution: Gate đạt trả 3 lượt, Không bật gate trả 6 lượt. Pending,
   unavailable và incomplete trả rỗng do database demo không có những tình huống
   đó; các nhóm có dữ liệu được kiểm chứng bằng test API ở trên.
3. Từ hai bộ lọc không khớp dữ liệu, nạp plan ví dụ và tạo lượt #16 với ngưỡng
   high: cả hai bộ lọc tự về tất cả, lượt mới xuất hiện rồi hoàn tất. Không gọi AWS.
4. Lọc lại Gate chặn + Hoàn tất: thấy #16 cùng bốn lượt cũ, report #16 giữ đủ 4
   finding, gate khớp 2 high, exit 1. Không có console error/warn trong phiên.

Ảnh desktop đã xem: reports/backend/gate-history-filter-2026-10-25.png.
Không chạy ma trận viewport mobile trong lượt này. Sau kiểm thử, ngắt kết nối,
đóng tab do agent mở và dừng preview server.

Hướng dẫn: [Backend — phân trang và bộ lọc](../BACKEND.md#phân-trang-chống-lặp-và-giới-hạn).

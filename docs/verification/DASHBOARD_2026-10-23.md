# Dashboard local — 2026-10-23

Môi trường: Windows, Python trong `.venv`, backend FastAPI trên localhost:8765,
SQLite demo hiện có. Không gọi AWS/Terraform thật hoặc tạo hạ tầng trong lần này.

## Phạm vi thay đổi

- Dashboard buildless HTML/CSS/JS tiếng Việt, cùng origin với API; đóng gói trong
  `infralens/backend/static/`. Route public chỉ phục vụ bốn asset có tên cố định.
- Kết nối token trong bộ nhớ, project/mode theo quyền registry, import file/ví dụ,
  timeout/trace/lookback, idempotency cho retry, trạng thái/hủy/lịch sử phân trang.
- Resource diff, priority, source, candidate CloudTrail, ghi chú phạm vi,
  filter address, tải JSON, comparison tự chọn baseline.
- CSP, anti-frame, no-store, nosniff; render dữ liệu bằng textContent. Poll chỉ
  dựng lại hàng lịch sử khi dữ liệu/selection thay đổi để giữ focus ổn định.
- Layout có media query 1100/760 px; phiên này kiểm tra trực quan trên viewport
  desktop của in-app browser, chưa chạy kiểm tra thiết bị mobile thật.

## Kết quả

`python -m pytest -q tests/test_backend.py tests/test_process.py`: **50 passed**.
Có một StarletteDeprecationWarning từ TestClient/httpx, không phải lỗi test.
Năm case mới xác minh asset public, không nhúng token/path runtime, API vẫn yêu
cầu auth và không thể truy cập file Python/database bằng route asset/traversal.

Bài test hủy refresh có lần thất bại vì không đến phase plan trong 5 giây.
Theo dõi launcher thật xác nhận version mất khoảng 3,3 giây trên Windows;
đã nâng cửa sổ chờ khởi động trong test lên 20 giây, giữ nguyên assert hủy và
timeout production. Bộ 50 test sau sửa chạy thành công.

Kiểm tra trình duyệt thật bằng CUA trên local dashboard:

- Token sai bị từ chối; token đúng lấy project demo. Refresh/trace bị disable
  theo registry. Reload quay về form kết nối. Ngắt kết nối thực tế xóa toàn bộ
  resource card, history row, project option và report notes khỏi DOM.
- Nạp ví dụ và tạo run `2b9ac593b5e247d9a0d5cc15dd466b2a`: thấy queued/running
  rồi tự cập nhật succeeded, 4 resource, priority high=2/medium=1/unknown=1.
  Comparison với lượt sạch trước trả new=4. Filter `resized` còn đúng một card.
- Xem lượt sạch cũ: cả bốn chỉ số bằng 0, no_longer_reported=4, có giải thích
  giới hạn của nhãn này.
- Import JSON hỏng có marker giả lập: UI chỉ hiện lỗi định dạng có kiểm soát,
  không echo marker/nội dung file.
- Import plan giả có chuỗi HTML và password đánh dấu sensitive qua file chooser:
  run `3e2f192ba79b48fdb2af8de3745bf34d` succeeded, markup hiển thị nguyên văn,
  hai phía password đều `[Đã ẩn: sensitive]`.
- Tải JSON từ nút dashboard: parse được 4 resource, không có marker password,
  giữ chuỗi markup dưới dạng dữ liệu. Console không có warning/error ở lần kiểm tra.

`node --check src/infralens/backend/static/app.js` thành công.
Ruff check/format cho backend và test thành công.
Build wheel bằng `uv build --wheel`: cả HTML/CSS/JS/demo JSON có trong wheel.
Giải nén wheel vào thư mục tạm và import package từ đó: bốn asset đúng bản hiện
tại đều trả HTTP 200, API không token vẫn trả 401.

Launcher `examples/backend/start_dashboard.ps1` đã parse và chạy thật bằng
PowerShell với token demo có sẵn: worker_alive=true, dashboard HTTP 200. Launcher
chạy foreground, giữ token cũ và phục hồi environment khi dừng. Preview server
được dừng sau kiểm chứng; dùng launcher để mở lại, nhập token từ file local.

Các báo cáo demo, fixture QA và ảnh chụp nằm trong `reports/backend/` (Git ignore).
Chưa publish website, commit hoặc push GitHub. Refresh/CloudTrail UI dùng API có
sẵn; không thực hiện lại demo AWS trong lần này. Các kiểm chứng AWS trước đó
được ghi trong biên bản riêng.

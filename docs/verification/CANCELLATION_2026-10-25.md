# Hủy lượt chạy tại thời điểm lưu kết quả — 2026-10-25

Trước sửa, worker kiểm tra cancellation rồi mới dựng gate và lưu report.
Yêu cầu hủy đến giữa hai bước làm status cancelled nhưng vẫn giữ report/gate
passed, failed hoặc incomplete; error_code cũng có thể còn lỗi thực thi cũ.

Store.finish quyết định trạng thái, report, has_drift và error_code trong cùng
một SQL UPDATE. Khi cancel_requested đã được lưu, không giữ báo cáo và trả
cancel_requested. Nếu completion commit trước, cancel trả 409 và giữ kết quả.
Không đổi schema hoặc sửa lại các report lịch sử.

Thêm 7 test cases: chặn worker đúng trước report commit cho ba loại gate,
late completion/error/shutdown không report, và completion thắng trước cancel.
Trước sửa: 6 failed/1 passed. Sau sửa: 7 passed.

Toàn bộ backend + gate: **132 passed**. Ruff cho các file Python thay đổi và
git diff --check đạt. Không chạy Terraform/AWS hoặc thay đổi dashboard trong
phần sửa lỗi này. Warning TestClient/httpx deprecated có sẵn vẫn còn.

# Backend và dashboard gate — 2026-10-23

Phạm vi: đưa policy CLI drift-gate-v1 vào request API, worker, lịch sử và
dashboard cục bộ. Demo dùng plan giả lập; không gọi AWS, không tạo hạ tầng,
không bật GitHub Actions. Thay đổi ở checkout local, chưa commit/push.

## Hành vi đã bổ sung

- API nhận object `gate` strict với any_drift, minimum_priority high/medium/null,
  unknown_priority. Từ chối sai kiểu, threshold lạ, trường lạ mà không echo input.
- Khi bật, worker đánh giá cùng helper với CLI, lưu đầy đủ quyết định cùng report.
  Gate failed/exit 1 vẫn là execution succeeded; trace lỗi cho failed và gate
  incomplete/exit 3. Không có report không được coi là gate passed.
- Metadata/lịch sử chỉ thêm tóm tắt status/exit_code/matched_count hoặc null;
  criteria nằm trong request. Báo cáo không bị lọc theo gate.
- Không migration DB. Tắt/null/rỗng/toàn false chuẩn hóa thành payload cũ, giữ
  fingerprint và replay key cũ. Criteria bật được chuẩn hóa đủ ba trường; đổi
  criteria cùng Idempotency-Key trả 409. Queue cũ vẫn chạy sau restart.
- Comparison giữ semantics finding/context: gate chặn vẫn dùng làm baseline;
  gate criteria khác nhau không làm finding thành changed.
- Dashboard có ngưỡng và checkbox unknown độc lập; cột Gate riêng trong lịch sử,
  panel quyết định cùng số resource khớp và danh sách có thể mở rộng. Báo cáo cũ
  ghi gate không bật. JSON download giữ quyết định và toàn bộ finding.
- Demo client có --gate-priority, --gate-unknown, --gate-any; giữ cách gọi cũ.

## Kiểm thử tự động

Thêm **26 test cases** ở `tests/test_backend.py`: ngưỡng/unknown/OR/deduplicate,
giữ finding và sensitive redaction, metadata, compatibility request trước gate,
durable queue/restart, replay/conflict, lịch sử, baseline qua criteria khác nhau,
validation privacy, trace/engine precedence và hủy queued không báo gate passed.

Chạy toàn bộ `python -m pytest -q`:
**653 passed, 9 skipped, 16 deselected**, 101,83 giây.
Warning hiện có: Starlette TestClient dùng httpx deprecated. Các kiểm thử cần
tool/môi trường bên ngoài chưa được chọn trong lệnh mặc định; không chạy AWS live.

Ruff check toàn repo, Ruff format check 83 file, uv lock check và git diff check
đều đạt. Node --check cho app.js đạt.

Wheel `reports/backend-gate-build/infralens-0.1.0-py3-none-any.whl` build thành công.
Giải nén vào thư mục tạm, chạy Python -I với package path riêng và xác minh import
đến đúng wheel: HTML/JS chứa gate, tạo import run bằng TestClient cho execution
succeeded nhưng gate failed/exit 1/matched 1. Script kiểm tra ở
`reports/verify_backend_gate_wheel.py` (artifact local, Git ignored).

## Demo qua API thật

Server local 127.0.0.1:8765, project drift-demo, token lấy từ file local và không
in vào log/bằng chứng. Ba lần chạy demo_client.py đều đạt:

| Cờ | Report drift | Report sạch | Artifact local |
| --- | --- | --- | --- |
| --gate-priority high --gate-unknown | gate failed, khớp 3/4 | gate passed, khớp 0 | reports/backend/gate-demo.json |
| --gate-any --gate-priority medium --gate-unknown | gate failed, khớp 4/4, không đếm trùng | gate passed | reports/backend/gate-any-demo.json |
| Không cờ gate | không có gate trong report | không có gate | reports/backend/gate-disabled-demo.json |

Mỗi demo xác minh retry cùng Idempotency-Key nhận lại run, hai job succeeded,
comparison báo 4 resource không còn được báo cáo. Schema mới được lưu ở
`reports/backend/gate-openapi.json`.

Sau dừng server khi queue rỗng, mở lại cùng DB qua app lifespan/TestClient và
kiểm tra lịch sử vẫn chứa quyết định failed/matched 3, passed và các report cũ
không gate; không còn job queued/running.

## Kiểm chứng trình duyệt

Thao tác trên in-app browser, không dùng gọi API ẩn để giả lập click:

1. Đăng nhập, nạp ví dụ 4 drift, chọn high + unknown và tạo lượt #7. Kết quả
   execution Hoàn tất, Gate chặn, matched 3; tổng finding vẫn 4 (2 high/1 medium/1
   unknown). Mở danh sách thấy đúng hai high và một unknown.
2. Import `examples/drift/plan.json`, high không kèm unknown: lượt #10 có một
   finding thiếu ngữ cảnh do sensitive data; Gate đạt/exit 0, finding vẫn hiển thị.
3. Chọn lượt cũ #4: panel cũ được thay bằng “Gate không bật cho lượt này”.
4. Không đặt ngưỡng, chỉ bật unknown: lượt #11 Gate chặn/exit 1, matched 1.
5. Quay lại #7, tải JSON từ nút download thật; kiểm tra gate failed/matched 3
   và resources 4. Bản tải lưu ở reports/backend/gate-dashboard-download.json.
6. Không có console error/warn trong phiên. Ngắt kết nối xóa token/report,
   đóng tab do agent mở và dừng preview server. Không để server chạy sau bàn giao.

Ảnh desktop đã xem trực tiếp:
`reports/backend/gate-dashboard-2026-10-23.png` và
`reports/backend/gate-passed-2026-10-23.png`.

## Giới hạn

Gate là quyết định review theo heuristic, không chứng nhận hạ tầng an toàn hoặc
phủ đầy đủ. Import chưa xác minh độ mới/độ phủ. Backend dùng chung token cục bộ;
chưa có RBAC/lịch tự động/thông báo. Không đánh giá lại các report lịch sử đã lưu.
UI được kiểm tra desktop trong lượt này; không chạy lại ma trận viewport mobile.

Hướng dẫn dùng: [Backend gate](../BACKEND.md#gate-theo-ưu-tiên).

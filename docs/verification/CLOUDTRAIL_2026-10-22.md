# Kiểm chứng CloudTrail trace — 22/10/2026

Đã truy vấn CloudTrail Event History thật bằng profile `infralens-sandbox`,
region `ap-southeast-2`. Chỉ gọi STS GetCallerIdentity và CloudTrail LookupEvents;
không tạo lại tài nguyên sandbox hoặc thay đổi cấu hình AWS.

## Đầu vào và kết quả

Đầu vào replay được dựng từ các báo cáo drift chuẩn hóa của lần chạy
`8b769c0a794c`. Đây là kiểm chứng tra cứu trên lịch sử thật, không phải một
lần refresh Terraform mới hoặc một lần lặp lại sáu tình huống tạo tài nguyên.

| Báo cáo cục bộ | Kết quả |
| --- | --- |
| `reports/aws-drift/8b769c0a794c/trace-live.json` | 2 sự kiện ModifyInstanceAttribute cho EC2; 4 sự kiện Authorize/RevokeSecurityGroupIngress cho SG |
| `reports/aws-drift/8b769c0a794c/trace-delete-live.json` | 1 sự kiện TerminateInstances, định danh resource có source saved |

Cả hai báo cáo có `trace.status: complete`, resource status matched và actor
ARN/type cùng thời điểm UTC. Actor của các thao tác demo là Root trong sandbox.
CLI chạy với `--fail-on-drift`, trả `1` đúng kỳ vọng vì đầu vào có drift;
không có lỗi lookup. Báo cáo thật được Git ignore, không sao chép ID/ARN vào đây.

Các sự kiện khôi phục cấu hình sau demo cũng xuất hiện trong cửa sổ lịch sử
của replay. Mọi sự kiện đều có relation candidate; chương trình không chọn
sự kiện cuối cùng làm nguyên nhân và không suy ra một người cụ thể từ role.
Với drift refresh mới, cửa sổ tra cứu kết thúc tại checked_at của lần check.

## Độ phủ kiểm thử

Suite mặc định sau cập nhật: **302 passed, 9 skipped, 14 deselected**.
Hai kiểm thử tích hợp Terraform thật cũng đạt. Ruff lint/format và
`uv lock --check` đạt.

Botocore Stubber kiểm tra phân trang, deduplicate, giới hạn trang/resource,
lọc sai resource/account/region, đọc/request thất bại, API khác thuộc tính,
thời điểm ngoài cửa sổ, định danh bị che, unsupported change và dữ liệu lỗi.
Test CLI kiểm tra output JSON sạch, nhập plan vẫn truy vấn AWS, fail-on-drift,
thiếu dependency, lỗi quyền vẫn lưu báo cáo và mã 3 ưu tiên hơn mã 1.
Test request pacing kiểm tra khoảng cách 0,55 giây và dừng khi hết budget.

Đây là phiên bản đầu cho EC2/Security Group; xem [phạm vi và giới hạn](../CLOUDTRAIL.md).

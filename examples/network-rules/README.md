# Demo drift của Security Group rule tách riêng

Plan JSON giả lập và file HCL để định vị source. Không phải cấu hình triển khai;
group ID trong plan là dữ liệu minh họa. Không chạy apply cho bộ fixture này.

```powershell
.\.venv\Scripts\infralens.exe drift .\examples\network-rules `
  --plan-json .\examples\network-rules\plan.json `
  --format json --output .\reports\network-rules-demo.json --fail-on-drift
```

| Resource | Thay đổi | Ưu tiên |
| --- | --- | --- |
| widen_ports | TCP 22 → 22–23, CIDR /0 giữ nguyên | high |
| new_ipv6 | IPv6 nội bộ → ::/0 | high |
| narrow_ports | TCP 443–444 → 443 | medium |
| widen_egress | Egress 443 → 443–444 | medium |
| legacy_direction | Rule cũ egress → ingress, nguồn /0 | high |
| hidden_context | Port mở rộng nhưng CIDR sensitive | unknown |

Mong đợi 6 resource, 6 attribute, high=3/medium=2/unknown=1. Exit 1 là kết quả
đúng do có drift và bật fail-on-drift. Có thể bỏ cờ để trả 0 khi phân tích thành công.
Trong bảng/JSON, ngữ cảnh rule giữ protocol/CIDR không đổi và vẫn che sensitive.

Dashboard: chạy `examples/backend/start_dashboard.ps1`, chọn project
`network-rules-demo`, import `examples/network-rules/plan.json` rồi tạo lượt.
Mở **Ngữ cảnh rule · gồm thuộc tính không đổi** để xem đủ thông tin so sánh.
Project này chỉ import và tắt CloudTrail; không yêu cầu AWS.

## Demo CloudTrail offline

```powershell
.\.venv\Scripts\python.exe .\examples\network-rules\trace_demo.py
.\.venv\Scripts\python.exe .\examples\network-rules\trace_demo.py --format json
```

Cần extra aws-trace để có boto3/botocore, không cần tài khoản hoặc phiên AWS.
Script dùng plan, identity và event giả, Stubber chặn mọi request. Hai resource
matched, một partial vì event thiếu rule ID, một legacy skipped. Có ví dụ rule
đã xóa dùng saved ID và RevokeSecurityGroupEgress. Kết quả vẫn là candidate,
không xác nhận ai gây ra drift. Demo trả exit 0 khi hoàn tất.

Khác với script offline, `infralens drift --trace` thông thường truy vấn AWS thật.
Xem [hướng dẫn CloudTrail](../../docs/CLOUDTRAIL.md) trước khi bật trace cho project thật.

# CloudTrail cho Security Group rule — 2026-10-23

Phạm vi mới: `aws_vpc_security_group_ingress_rule` và
`aws_vpc_security_group_egress_rule`. Legacy `aws_security_group_rule` vẫn được
bỏ qua rõ lý do; không suy account/region từ composite ID của Terraform.

## Thay đổi

- Parser chỉ giữ thêm parent security_group_id và alias security_group_rule_id
  của hai loại rule mới. Cùng cơ chế sensitive union và observed/saved như id/arn;
  không giữ raw resource và không tăng attribute drift count.
- ID sgr/ARN rule phải khớp; parent SG hợp lệ; alias nếu có phải khớp. Update
  yêu cầu observed identity, delete dùng saved. Thiếu/masked/unknown/conflict
  chặn session/lookup, không lấy network_context để đi vòng mask.
- LookupEvents dùng ResourceName của group cha, giữ nguyên STS scope check,
  resource/page cap, paginator, throttle, timeout/cancel và allowlist đầu ra.
- `cloudtrail_rules.py` đối chiếu request theo schema cụ thể: group, exact rule
  ID và field của ModifySecurityGroupRules. Description và revoke theo hướng
  ingress/egress. Không quét ID trong tag/description/response hoặc nested key lạ.
- Event chưa đủ request shape nhưng đã qua metadata filter được đếm riêng theo
  EventId, làm trace partial; không đánh đồng với không có thay đổi. Wrong-rule
  event bị loại. Lỗi AWS vẫn giữ các event đã chuẩn hóa ở trang trước.
- CLI/dashboard thêm thông tin exact-rule-ID matching, parent lookup và số event
  chưa xác định. Không thêm endpoint, EC2 API hoặc quyền IAM.

## Kiểm chứng

`python -m pytest -q`: **570 passed, 9 skipped, 16 deselected**, 91,84 giây.
Có một deprecation warning TestClient/httpx hiện có. Các suite external-tool
không tự chạy trong lệnh mặc định; không chạy lại Terraform/AWS live trong lượt này.

**62 test mới** trong `tests/test_rule_cloudtrail.py`:

- PascalCase Query envelope singleton/list, SDK list và camelCase set/items;
  reference parent ID/ARN hoặc rule ID/ARN.
- Sửa port trên đúng rule/field, description API và revoke đúng ingress/egress;
  saved identity cho rule xóa.
- Loại rule khác cùng group, group khác, field khác, read/error/scope/time không
  khớp, thiếu resource reference và ID mồi nằm trong description/response.
- Schema chưa xác định trả partial và đếm EventId duy nhất; scope mismatch không
  lookup; sensitive/unknown/invalid/missing/conflicting identity không tạo session.
- Mixed unsupported attributes, event giữ lại sau lỗi page tiếp theo, CLI import
  không gọi Terraform, backend qua worker/SQLite/restart giữ trace chuẩn hóa.
- Giá trị private giả trong request/response/access key/IP và raw plan không có
  trong báo cáo; marker không xuất hiện trong database/WAL/SHM sau worker dừng.

Ruff check/format toàn src/tests và script demo thành công. Node syntax check
dashboard JS và uv lock check thành công. Wheel ở
`reports/rule-trace-build/infralens-0.1.0-py3-none-any.whl` build thành công;
giải nén/import package riêng xác nhận bốn asset đúng bản hiện tại trả HTTP 200,
API không token vẫn trả 401.

## Demo tái lập không AWS

```powershell
.\.venv\Scripts\python.exe .\examples\network-rules\trace_demo.py --format json
```

Fake credentials, STS identity và CloudTrail event qua botocore Stubber; không
gửi request AWS và không chạy Terraform. Script chỉ ghi report ra stdout.
Đã chạy thành công và kiểm tra artifact Git ignored
`reports/network-rule-trace-demo.json`: 4 resource, **matched=2/partial=1/skipped=1**,
top-level partial và has_errors=false; review high=3/medium=0/unknown=1.
Mỗi event có relation=candidate, actor/event/time và matched_attributes.
Script demo exit 0; CLI thật vẫn giữ semantics fail-on-drift/error.

## Giới hạn

Chưa kiểm chứng matcher mới trên sự kiện AWS live. Chưa hỗ trợ tag-only trên
rule riêng, legacy rule, Authorize*, DeleteSecurityGroup hoặc revoke bằng
IpPermissions mà thiếu rule ID. Event payload/request variant không được nhận
diện không được đoán. Không kết luận actor là nguyên nhân drift; no_events không
chứng minh không có thay đổi. Không tạo/sửa tài nguyên AWS, không commit/push.

Tham khảo chính thức: [ModifySecurityGroupRules](https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_ModifySecurityGroupRules.html),
[RevokeSecurityGroupIngress](https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_RevokeSecurityGroupIngress.html),
[UpdateSecurityGroupRuleDescriptionsIngress](https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_UpdateSecurityGroupRuleDescriptionsIngress.html),
[AWS CloudTrail Lake sample](https://github.com/aws-samples/cloud-trail-lake-query-samples/blob/main/ec2-public-security-group.sql).

# CloudTrail trace cho drift

`--trace` bổ sung sự kiện AWS liên quan vào báo cáo drift: API được gọi, thời
điểm UTC, actor và event ID. Mỗi sự kiện có `relation: candidate`; người đọc
cần đối chiếu bối cảnh để xác định nguyên nhân. Chương trình không chọn sự kiện
mới nhất làm thủ phạm và không khẳng định không có thay đổi khi thiếu sự kiện.

## Chạy

```powershell
cd C:\work\infralens
.\.venv\Scripts\python.exe -m pip install -e '.[aws-trace]'
# Hoặc: uv sync --locked --extra aws-trace

.\.venv\Scripts\infralens.exe drift C:\path\to\infra `
  --trace --lookback-days 7 `
  --profile infralens-sandbox --region ap-southeast-2 `
  --format json --output .\reports\drift-trace.json --fail-on-drift
```

Dự án Terraform cần được init trước như khi chạy drift thường. Trace dùng
credential chain cục bộ, không đọc hoặc in access key. Profile tạo bằng
`aws login` được hỗ trợ nhờ dependency `boto3[crt]`. AWS identity cần gọi được
STS `GetCallerIdentity` và CloudTrail `LookupEvents`; không cần tạo trail,
event data store hay cấp quyền ghi CloudTrail.

`--plan-json` tránh chạy Terraform. Kết hợp với `--trace` vẫn truy vấn AWS thật.
`checked_at` của imported plan là lúc phân tích file, không chứng nhận thời
điểm thu thập dữ liệu trong file. Tài nguyên đã xóa vẫn tra được bằng ID/ARN
có source `saved`.

## Phạm vi hiện tại

| Loại resource | Thuộc tính/action | API ứng viên |
| --- | --- | --- |
| `aws_instance` | `instance_type` | ModifyInstanceAttribute có request instanceType |
| `aws_instance` | delete | TerminateInstances |
| `aws_security_group` | `ingress` | Authorize/RevokeSecurityGroupIngress, ModifySecurityGroupRules |
| `aws_security_group` | `egress` | Authorize/RevokeSecurityGroupEgress, ModifySecurityGroupRules |
| `aws_security_group` | delete | DeleteSecurityGroup |
| Cả hai | `tags`, `tags_all` | CreateTags, DeleteTags |
| `aws_vpc_security_group_ingress_rule`, `aws_vpc_security_group_egress_rule` | Protocol, port, CIDR, prefix list, SG reference | ModifySecurityGroupRules, đúng rule ID và field trong request |
| Hai loại rule trên | `description` | ModifySecurityGroupRules hoặc UpdateSecurityGroupRuleDescriptionsIngress/Egress đúng hướng |
| Hai loại rule trên | delete | RevokeSecurityGroupIngress/Egress đúng hướng và rule ID |

Chỉ hỗ trợ ARN partition `aws`. Resource phải có ID/ARN known, khớp nhau,
khớp account từ STS và region của profile/`--region`. ID/ARN sensitive, thiếu
định danh, resource/thuộc tính chưa hỗ trợ hoặc khác scope được ghi `skipped`
với lý do cụ thể. Không lấy ID từ thuộc tính bị che để truy vấn vòng qua mask.

Một profile được dùng cho một account/region mỗi lần chạy. Terraform dùng
provider alias, region riêng hoặc assume role khác profile có thể tạo các
resource bị bỏ qua do scope mismatch. Chọn profile/region khớp tài nguyên cần tra.

### Rule Security Group tách riêng

Trace giữ thêm `identifiers.security_group_id` (group cha) và
`identifiers.security_group_rule_id` nếu provider cung cấp alias này. Chúng dùng
cùng quy tắc che sensitive và source observed/saved như id/arn; không được tính
vào số attribute drift. ID `sgr-...` và ARN `security-group-rule/sgr-...` phải khớp.
Group cha phải có ID `sg-...` hợp lệ; alias nếu có phải khớp ID chính.

Đối với update, identity phải có source observed; không lấy saved fallback cho
một định danh observed unknown/missing. Delete dùng source saved. Sensitive ở
bất kỳ identity nào chặn lookup; không dùng network_context để đi vòng mask.
Scope account/region vẫn được đối chiếu ARN và STS như các resource khác.

LookupEvents truy vấn **group cha**, vì sự kiện thay đổi rule có thể được index
bằng Security Group. Sau đó event phải có tham chiếu đúng parent/rule, request
GroupId đúng, rule ID đúng trong vị trí schema được hỗ trợ và nằm trong window.
Với ModifySecurityGroupRules, chỉ gắn matched_attributes xuất hiện trong phần
update của đúng rule; không gán sự kiện sửa description cho drift port.
Không tìm ID bằng substring hay quét tùy ý trong description/tag/response.

Hỗ trợ EC2 Query envelope `<EventName>Request` với field PascalCase, singleton/
list hoặc field list SDK tương ứng, và dạng camelCase set/items. Không suy đoán
cấu trúc lạ. Metadata bổ sung của trace rule:

```json
{
  "correlation": "exact_rule_id",
  "lookup_scope": "parent_security_group",
  "unresolved_rule_events": 1
}
```

`unresolved_rule_events` đếm event ID duy nhất đã qua kiểm tra metadata chung
nhưng request chưa đủ để xác định rule/field. Khi khác 0, status là partial;
không được diễn giải như không có thay đổi. Lỗi AWS vẫn giữ event đã chuẩn hóa
từ trang trước và trả has_errors/exit 3 như trước.

Giới hạn còn lại: `aws_security_group_rule` legacy vẫn unsupported_resource;
tag-only trên rule mới là unsupported_change, mixed tag/network là partial.
Chưa tương quan Authorize*, xóa group cha hoặc revoke chỉ bằng IpPermissions
không có rule ID. Cùng group có thể được query lại cho nhiều rule; vẫn giữ cap
20 resource/4 page và throttle hiện có. Không thêm EC2 API hoặc quyền AWS mới.

Demo hoàn toàn offline, dùng fake credentials và botocore Stubber:

```powershell
.\.venv\Scripts\python.exe .\examples\network-rules\trace_demo.py
# JSON trên stdout:
.\.venv\Scripts\python.exe .\examples\network-rules\trace_demo.py --format json
```

Demo không gọi AWS hoặc Terraform: matched=2, partial=1, skipped=1, has_errors=false.
Lệnh demo trả 0 khi hoàn tất; đây là script minh họa, không phải gate fail-on-drift.
CLI `infralens drift --trace` với dự án/plan thật vẫn dùng AWS thật.

Tra cứu theo ResourceName bằng ID, rồi kiểm tra tham chiếu resource chính xác,
event source EC2, account, region và khoảng thời gian. Loại sự kiện đọc,
request lỗi và API ngoài ánh xạ. Giữ actor ARN/type/username/service và session
issuer ARN khi có; không đưa raw CloudTrailEvent, requestParameters,
responseElements, accessKeyId, source IP hay user agent vào báo cáo.

## Giới hạn và trạng thái

- `--lookback-days`: 1–90, mặc định 7. Khoảng tra cứu kết thúc ở `checked_at`.
- Tối đa 20 resource đủ điều kiện, 4 trang × 50 sự kiện/resource. Paginator
  của SDK xử lý token; deduplicate theo event ID, sắp xếp mới nhất trước.
- Mỗi HTTP attempt LookupEvents được giãn tối thiểu 0,55 giây trong process.
  Không điều phối quota với các process khác.
- Budget bắt đầu request trace lấy từ `--timeout` (mặc định 300 giây), riêng
  với budget plan. SDK connect/read timeout là 5/10 giây, tối đa 2 attempts.
  Request đang chạy có thể kết thúc sau budget; Ctrl+C vẫn ngắt được.

Top-level `trace.status`:

| Status | Ý nghĩa |
| --- | --- |
| `not_needed` | Không có drift; không tạo session hoặc gọi AWS |
| `complete` | Hoàn tất các lookup được hỗ trợ; không xác nhận nguyên nhân drift |
| `partial` | Có resource bị bỏ qua, bị giới hạn, dữ liệu lỗi hoặc lookup lỗi |
| `error` | Không thể khởi tạo SDK/session/scope cho trace |

Mỗi resource có `trace.status`, `events` và lý do/giới hạn khi cần. `matched`
có sự kiện ứng viên; `no_events` là tra cứu không có ứng viên trong phần đã
quét. `unsupported_attributes` nêu phần chưa được ánh xạ khi resource có nhiều
thuộc tính drift. Lỗi ở trang sau vẫn giữ sự kiện chuẩn hóa từ các trang trước.

Nếu có lỗi AWS, dependency hoặc hết budget, `trace.has_errors` là true và CLI
trả `3` sau khi xuất báo cáo drift. Mã này ưu tiên hơn `--fail-on-drift`.
Partial do giới hạn/scope chưa hỗ trợ không tự gây lỗi thực thi; xem status
trong JSON để đánh giá độ phủ. Khi không có lỗi trace, mã thoát drift vẫn là
`0` hoặc `1` theo `--fail-on-drift`.

Event History chỉ bao phủ management events theo region trong 90 ngày và sự
kiện có thể đến muộn. Các thay đổi data plane, API thiếu ResourceName, thay đổi
cũ hơn khoảng tra cứu hoặc nằm ngoài 200 sự kiện đầu có thể không xuất hiện.
ModifySecurityGroupRules có thể liên quan ingress hoặc egress; actor có thể
là assumed role hoặc AWS service, chưa chắc là một người cụ thể.

## Kiểm chứng

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_cloudtrail.py
```

Unit test dùng botocore Stubber; kết quả truy vấn AWS thật nằm trong
[biên bản kiểm chứng trace](verification/CLOUDTRAIL_2026-10-22.md).
Mở rộng rule riêng: [biên bản kiểm chứng](verification/RULE_CLOUDTRAIL_2026-10-23.md).

Nguồn AWS: [LookupEvents API](https://docs.aws.amazon.com/boto3/latest/reference/services/cloudtrail/client/lookup_events.html),
[Event History](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/view-cloudtrail-events.html),
[nội dung event](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-event-reference-record-contents.html).
Schema request: [ModifySecurityGroupRules](https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_ModifySecurityGroupRules.html),
[RevokeSecurityGroupIngress](https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_RevokeSecurityGroupIngress.html),
[UpdateSecurityGroupRuleDescriptionsIngress](https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_UpdateSecurityGroupRuleDescriptionsIngress.html),
[ví dụ AWS CloudTrail Lake](https://github.com/aws-samples/cloud-trail-lake-query-samples/blob/main/ec2-public-security-group.sql).

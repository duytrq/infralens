# Ưu tiên và hướng dẫn xử lý drift

CLI tự bổ sung mức ưu tiên, lý do và hướng xử lý vào báo cáo drift. Phần này
chỉ đọc kết quả đã được che sensitive, không gọi thêm Terraform hoặc AWS.
Quy tắc giúp phân loại công việc review; đây không phải kết luận bảo mật,
độ nghiêm trọng kinh doanh hay bằng chứng ai gây ra thay đổi.

## Chạy demo

```powershell
cd C:\work\infralens
.\.venv\Scripts\infralens.exe drift .\examples\drift-review `
  --plan-json .\examples\drift-review\plan.json `
  --format json --output .\reports\drift-review-demo.json --fail-on-drift
```

Dữ liệu giả lập, không triển khai tài nguyên AWS. Kết quả mong đợi:

| Resource | Tình huống | Priority |
| --- | --- | --- |
| aws_instance.missing | Provider báo resource biến mất | high |
| aws_instance.resized | instance_type t3.micro → t3.small | medium |
| aws_instance.tagged | Đổi tag AccessProject | unknown |
| aws_security_group.web | Thêm TCP 22 từ 0.0.0.0/0 | high |

Lệnh trả `1` vì có drift và đã bật fail-on-drift. Nếu không bật, vẫn xuất đầy đủ
kết quả và trả `0` khi không có lỗi thực thi. Các mức ưu tiên không lọc hoặc bỏ
qua drift; unknown vẫn gây exit 1 khi bật fail-on-drift.

## Quy tắc hiện tại

| Signal | Priority | Điều kiện |
| --- | --- | --- |
| resource_missing | high | Action delete do provider refresh báo |
| world_ingress_added_or_expanded | high | Ingress inline hoặc rule tách riêng thêm/mở rộng nguồn IPv4/IPv6 /0 |
| network_rules_changed | medium | Ingress/egress inline hoặc rule tách riêng có cấu trúc được hỗ trợ |
| instance_type_changed | medium | aws_instance.instance_type có cả hai giá trị string known |
| tag_context_required | unknown | Tag thay đổi cần kiểm tra vai trò trong quyền truy cập/automation |
| values_unavailable | unknown | Giá trị sensitive, unknown, absent hoặc thiếu value |
| network_details_unavailable | unknown | Rule không đủ thông tin hoặc protocol chưa hỗ trợ |
| unclassified_change | unknown | Thuộc tính/resource khác hoặc không có delta hiển thị |

Rule mạng hiện hỗ trợ TCP/UDP, tên protocol tcp/udp hoặc số dạng string 6/17,
và -1 (mọi protocol). Xét riêng hai họ IPv4/IPv6 và gộp khoảng port có cùng
coverage. Thu hẹp port, gộp các khoảng liền kề, sửa mô tả hoặc đổi thứ tự rule
không bị hiểu là mở rộng world ingress. Chỉ so các rule /0 trong SG đang xét;
không mô phỏng route, NACL, prefix list, SG tham chiếu hoặc các SG khác.
Hỗ trợ thêm `aws_vpc_security_group_ingress_rule`,
`aws_vpc_security_group_egress_rule` và `aws_security_group_rule` (dạng cũ).
Protocol `all` cũng được chuẩn hóa thành `-1`. Protocol ICMP, prefix list,
SG tham chiếu và self-reference vẫn cần review thủ công; không mở rộng các nguồn
này để suy đoán coverage. Cấu trúc thiếu/sai kiểu dữ liệu trả unknown.

High không chứng nhận resource truy cập được từ Internet. Một rule /0 mới cho
website công khai có thể là thay đổi đúng ý định. Tag không mặc định là ít rủi
ro vì tag có thể tham gia ABAC hoặc automation. Đây là policy tích hợp
`builtin-review-v2`. Đã có [gate CLI theo priority](DRIFT_CI.md);
chưa có file policy tùy chỉnh.
V2 mở rộng rule tách riêng; báo cáo đã lưu với v1 không được tự sửa lại.

Priority của resource là high nếu có signal high; nếu chưa có high nhưng có
signal unknown thì là unknown; trường hợp còn lại là medium. Mọi signal vẫn
được giữ để phần chưa rõ không bị che bởi một signal đã hiểu.

## Security Group rule tách riêng

Ví dụ saved state có TCP 22 từ `0.0.0.0/0`, observed đổi `to_port` thành 23.
Dù chỉ `to_port` xuất hiện trong attributes, engine vẫn cần biết protocol và CIDR
không đổi để xác định world ingress đã mở rộng. Trường `network_context` bổ sung
hai snapshot tối thiểu `before`/`after`, phiên bản `security-group-rule-v1`.
Nó chỉ giữ field mạng được cho phép: group/region, direction (dạng cũ), protocol,
port và các trường nguồn CIDR/reference. Không sao chép toàn bộ resource/state.

Mỗi field vẫn dùng status known/absent/sensitive/unknown. Sensitive ở một phía
che cả hai phía, kể cả giá trị không đổi hoặc phần tử trong collection. Mask
unknown không được thay bằng saved value. Context không tăng số attribute drift.
CLI và dashboard có phần ngữ cảnh riêng, gồm cả field không đổi.

Các trường hợp cần phân biệt:

- Mở rộng port/protocol, thêm IPv6 /0 hoặc chuyển egress sang ingress /0: high.
- Chuyển rule /0 sang group hoặc region khác: không dùng coverage ở target cũ
  để kết luận target mới đã được phủ; cần high review cho ingress ở target mới.
- Thu hẹp port/CIDR, chỉ sửa description, hoặc đổi egress: medium nếu đủ dữ liệu.
  Điều này không phải kết luận mọi thay đổi egress đều ít rủi ro.
- Sensitive/unknown ở ngữ cảnh cần thiết: unknown. Báo cáo cũ không có context
  không được dựng lại từ riêng những attribute đã đổi.
- Xóa resource vẫn high như các resource managed khác, không cần context mới.

Comparison lịch sử xét cả ngữ cảnh mạng: hai lần cùng đổi port nhưng một lần
nguồn là /0 và lần kia nguồn nội bộ không bị gọi là unchanged. Nếu thiếu context
ở báo cáo cũ hoặc context bị ẩn, kết quả có thể indeterminate. Comparison vẫn
chỉ xuất address/path/status, không sao chép giá trị mạng.

CloudTrail đã hỗ trợ hai resource rule ingress/egress mới khi đủ identity,
đối chiếu chính xác rule ID. Legacy vẫn unsupported_resource;
xem [phạm vi và độ phủ CloudTrail](CLOUDTRAIL.md).

Demo offline mới:

```powershell
.\.venv\Scripts\infralens.exe drift .\examples\network-rules `
  --plan-json .\examples\network-rules\plan.json `
  --format json --output .\reports\network-rules-demo.json --fail-on-drift
```

Kết quả: 6 resource, high=3, medium=2, unknown=1, exit 1 do fail-on-drift.
Không cần AWS/Terraform executable cho import. Backend demo đăng ký thêm project
`network-rules-demo`: chọn project, import file trên rồi mở ngữ cảnh trong card.

## Hai hướng xử lý để người phụ trách lựa chọn

1. **Khôi phục cấu hình đã duyệt**: xác nhận ý định hiện tại, xem normal Terraform
   plan, kiểm tra toàn bộ thay đổi/replacement rồi dùng quy trình apply của nhóm.
2. **Chấp nhận thay đổi ngoài Terraform đã được duyệt**: sửa code mô tả trạng thái
   hoặc việc xóa được chấp thuận, rồi review normal plan theo quy trình của nhóm.

State đã lưu là baseline quan sát, không nhất thiết là cấu hình mong muốn mới
nhất. Code có thể có thay đổi chưa apply. Cập nhật state bằng refresh-only không
tự sửa code. Khi provider báo resource mất, kiểm tra scope và nhu cầu phục hồi
dữ liệu trước khi cân nhắc tạo lại. Nếu có CloudTrail, chỉ dùng các event ứng
viên làm bối cảnh để đối chiếu phê duyệt thay đổi.

Hướng dẫn là văn bản tĩnh, không dựng lệnh apply/destroy, không ghép giá trị từ
plan vào shell command, không thực thi bước sửa hoặc ghi lại state.

## JSON

`resources[].assessment` có policy, priority, signals (code/priority/description/
paths) và guidance (review_steps cùng hai choices có title/id/steps).
Phần assessment không sao chép giá trị trước/sau hoặc raw CloudTrail vào hướng
dẫn. Các giá trị hiện có trong attributes vẫn chịu quy tắc che sensitive của engine.

Ví dụ tổng hợp demo:

```json
{
  "review_summary": {
    "policy": "builtin-review-v2",
    "priority_counts": {"high": 2, "medium": 1, "unknown": 1}
  }
}
```

Không có resource drift thì không sinh assessment/summary giả. Thứ tự resource,
has_drift, số resource/attribute, source, identifiers và trace được giữ nguyên.

## Kiểm chứng

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_drift_review.py
```

[Biên bản kiểm chứng](verification/DRIFT_REVIEW_2026-10-22.md).
Phần rule tách riêng: [kiểm chứng v2](verification/NETWORK_RULES_2026-10-23.md).

Tham khảo: [reconcile drift với Terraform](https://developer.hashicorp.com/terraform/tutorials/state/resource-drift),
[security group rules](https://docs.aws.amazon.com/vpc/latest/userguide/security-group-rules.html),
[tag và ABAC](https://docs.aws.amazon.com/IAM/latest/UserGuide/introduction_attribute-based-access-control.html).
Schema đối chiếu AWS provider 6.70.0:
[ingress rule](https://github.com/hashicorp/terraform-provider-aws/blob/v6.70.0/website/docs/r/vpc_security_group_ingress_rule.html.markdown),
[egress rule](https://github.com/hashicorp/terraform-provider-aws/blob/v6.70.0/website/docs/r/vpc_security_group_egress_rule.html.markdown),
[legacy rule](https://github.com/hashicorp/terraform-provider-aws/blob/v6.70.0/website/docs/r/security_group_rule.html.markdown).

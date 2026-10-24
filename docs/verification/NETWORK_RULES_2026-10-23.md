# Security Group rule drift — 2026-10-23

Phạm vi: review cho `aws_vpc_security_group_ingress_rule`,
`aws_vpc_security_group_egress_rule`, `aws_security_group_rule`; ngữ cảnh mạng
đã chuẩn hóa trong engine/CLI/backend/dashboard và comparison lịch sử.
Schema đối chiếu tài liệu chính thức HashiCorp AWS provider 6.70.0.

## Thiết kế

- `network_context` version `security-group-rule-v1` giữ field mạng allowlist,
  before/after, kể cả giá trị không đổi. Không giữ raw resource, variables, outputs
  hay field khác không đổi. Không tăng số resource/attribute drift.
- Sensitive ở một phía che cả hai phía, nested mask che cả field collection;
  unknown ở observed không được lấy saved value thay thế.
- Review policy `builtin-review-v2`: /0 ingress mới/mở rộng là high; narrowing,
  description hoặc egress là medium khi đủ semantics; context thiếu/masked hay
  ICMP/prefix-list/SG-reference/self-reference là unknown. Delete vẫn high.
- Old egress hoặc coverage ở target SG/region khác không phủ ingress tại target
  mới. Không mô hình route/NACL/public reachability hay coverage của SG khác.
- Worker khôi phục context từ normalized queue; báo cáo cũ không có trường này
  vẫn đọc được. Không tự thay đổi assessment của báo cáo đã lưu.
- Comparison xét cả context, không xuất giá trị. Context sensitive/unknown/missing
  có thể cho indeterminate; không suy đoán unchanged khi dữ liệu chưa đủ.
- CLI và dashboard hiển thị context riêng; dashboard vẫn render textContent.
  Chưa mở rộng CloudTrail cho các resource rule tách riêng.

## Tự động

`python -m pytest -q`: **508 passed, 9 skipped, 16 deselected** trong 82,70 giây.
Một cảnh báo deprecation Starlette TestClient/httpx hiện có, không phải lỗi test.
Các suite external-tool không được tự chạy trong lệnh mặc định.

`tests/test_network_rule_drift.py`: **63 test mới**, gồm CIDR/protocol/port,
IPv4/IPv6, narrowing, egress/direction, target group/region, mask ở field/root/
collection, ngữ cảnh không đổi, thiếu context trong báo cáo cũ, CLI exit code,
backend qua worker/SQLite/restart và comparison không sao chép giá trị.

Chạy riêng integration Terraform thật bằng Terraform 1.16.5:

```powershell
$env:INFRALENS_TEST_TERRAFORM = 'C:/tools/terraform/terraform.exe'
.\.venv\Scripts\python.exe -m pytest -q tests/integration/test_terraform_integration.py --run-terraform --run-network
```

**4 passed** trong 40,47 giây. Đây là regression với terraform_data/local_file,
cấu hình HCL/JSON và nested module; không phải kiểm thử live SG trên AWS.

Ruff check toàn `src tests` và format check **54 file** thành công.
`node --check` dashboard JS và `uv lock --check` thành công.
Build wheel `reports/network-rules-build/infralens-0.1.0-py3-none-any.whl` thành công.
Giải nén wheel sang thư mục tạm, import backend từ đó: bốn asset đúng nội dung
hiện tại trả 200, API không token vẫn trả 401.

## Demo CLI và trình duyệt

Fixture `examples/network-rules/plan.json`: **6 resource/6 attribute**, priority
**high=3, medium=2, unknown=1**, policy v2, source located cả 6. CLI exit **1**
đúng với fail-on-drift. Artifact `reports/network-rules-demo.json` và output
`reports/network-rules-cli.txt` được Git ignore. CIDR sensitive trong context
được che; diagnostic values_unavailable trỏ vào path cidr_ipv4.

Dashboard chạy bằng launcher local, chọn `network-rules-demo`, import file qua
file chooser: run `9ed302e1bb624c2995092ce34eea869d` (#5) succeeded, số đếm 6/3/2/1.
Filter widen_ports, mở ngữ cảnh thấy protocol TCP và CIDR /0 giữ nguyên,
to_port 22 → 23. JSON tải bằng nút dashboard giữ context/policy/count đúng,
không chứa CIDR đã đánh dấu sensitive. Lưu bằng chứng tại
`reports/backend/network-rules-browser-report.json`.

Import lần hai với cùng delta port nhưng CIDR nền đổi thành subnet nội bộ ở
cả saved/observed: run `8ec24d756bc2425fbc99aff0303f51c1` (#6) succeeded,
high=2/medium=3/unknown=1. Dashboard comparison hiện **changed=1, unchanged=4,
indeterminate=1**. Changed path là cidr_ipv4; finding có context sensitive
giữ indeterminate. Console không có warning/error khi kiểm tra.

Ảnh chụp `reports/backend/network-rule-context-2026-10-23.png` cho thấy TCP/CIDR
không đổi và port thay đổi. Preview server được dừng sau kiểm chứng; dùng
`examples/backend/start_dashboard.ps1` để mở lại.

Không tạo/sửa tài nguyên AWS trong lần này. Chưa commit/push. Kiểm thử SG live,
CloudTrail cho rule riêng, ICMP và reference expansion còn là phạm vi tiếp theo.

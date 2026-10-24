# Drift engine

Đã có [bộ demo sáu tình huống AWS](AWS_DRIFT_DEMO.md) với Terraform sandbox,
chương trình chạy và cleanup riêng. Xem trạng thái kiểm chứng thực tế trong tài liệu đó.

Drift là thay đổi của tài nguyên Terraform quản lý so với state đã lưu.
Ví dụ: state lưu EC2 `t3.micro`, người dùng đổi trên AWS thành `t3.small`;
InfraLens hiển thị `t3.micro → t3.small`. Việc chỉ sửa code sang `t3.small`
khi AWS vẫn khớp state không phải drift và không làm CI fail.

## Chạy bản clone trên máy này

```powershell
cd C:\work\infralens
.\.venv\Scripts\infralens.exe drift .\examples\drift --plan-json .\examples\drift\plan.json
.\.venv\Scripts\infralens.exe drift .\examples\drift --plan-json .\examples\drift\plan.json --format json
```

Dữ liệu trong `examples/drift/plan.json` là giả lập, gồm thay đổi instance type
và một thuộc tính sensitive để minh họa che dữ liệu. Không có tài nguyên AWS
nào được triển khai cho ví dụ này. Các giá trị `example-...` là placeholder.

Đối với dự án Terraform thật, cài Terraform lên PATH, init dự án, chọn workspace
và xác thực backend/provider như quy trình Terraform hiện có:

```powershell
.\.venv\Scripts\infralens.exe drift C:\path\to\infra --var-file dev.tfvars --profile dev --region ap-southeast-1
.\.venv\Scripts\infralens.exe drift C:\path\to\infra --format json --output .\reports\drift.json --fail-on-drift
```

`--var-file` tính từ thư mục Terraform, có thể lặp lại và giữ nguyên thứ tự;
`--output` tính từ CWD. Có output thì stdout là bảng, file theo format đã chọn.
Không có output và format JSON thì stdout chỉ chứa JSON. Mã thoát: `0` thành công;
`1` có drift khớp gate đã chọn; `2` đầu vào không hợp lệ; `3` lỗi công cụ/I/O;
Trace lỗi AWS/SDK trả `3` sau khi xuất báo cáo drift; `130` là người dùng ngắt lệnh.

Ngoài fail-on-drift, có `--fail-on-priority high|medium` và `--fail-on-unknown`
cho CI. Gate không lọc finding; xem [tiêu chí, JSON và mẫu pipeline](DRIFT_CI.md).

## Luồng xử lý

1. CLI validate đường dẫn, tùy chọn và chống ghi báo cáo đè nguồn/tfvars/state.
2. `terraform.py` tìm executable, kiểm tra phiên bản, chuẩn bị môi trường.
3. Chạy `plan -refresh-only -detailed-exitcode -input=false -lock-timeout=10s`.
   Mã `0` và `2` là kết quả plan hợp lệ; không dùng mã `2` như kết luận drift
   vì thay đổi output cũng có thể làm Terraform trả mã đó.
4. Chạy `show -json` trên plan tạm; `drift.py` chỉ phân tích `resource_drift`.
5. Chuẩn hóa và che giá trị sensitive trước khi render/ghi JSON. Không giữ raw
   plan/state/variables/outputs trong đối tượng báo cáo.
6. Gắn vị trí code, CloudTrail khi bật trace, mức ưu tiên và hướng dẫn review.
7. Ghi báo cáo qua writer atomic sẵn có, rồi quyết định mã thoát CI.

Không tự chạy init/apply/refresh/destroy; không ghi lại state đã refresh.
Giữ cơ chế state lock. Runner chung xử lý timeout/Ctrl+C và tiến trình con
trên Windows/Linux. Plan tạm vẫn có thể chứa secrets cho tới khi được dọn;
thư mục tạm riêng không bảo vệ khỏi người có quyền quản trị hay crash hệ điều hành.

## Hợp đồng JSON

```json
{
  "schema_version": "1.0",
  "kind": "drift",
  "terraform_version": "1.16.5",
  "input_mode": "refresh_only",
  "checked_at": "2026-10-21T00:00:00+00:00",
  "has_drift": true,
  "summary": {"resources": 1, "attributes": 1},
  "resources": [{
    "address": "aws_instance.demo",
    "resource_type": "aws_instance",
    "actions": ["update"],
    "source": {
      "status": "located",
      "context": "current_configuration",
      "block_address": "aws_instance.demo",
      "locations": [{
        "file": "C:/work/infra/main.tf",
        "start_line": 6,
        "end_line": 9,
        "syntax": "hcl"
      }]
    },
    "attributes": [{
      "path": ["instance_type"],
      "before": {"status": "known", "value": "t3.micro"},
      "after": {"status": "known", "value": "t3.small"}
    }]
  }],
  "normalizations": [],
  "notes": []
}
```

`checked_at` là thời điểm phân tích UTC, không phải thời điểm thay đổi tài nguyên.
Resource có thêm `identifiers` khi provider cung cấp `id` hoặc `arn`. Mỗi giá trị
có status/value và source `observed` hoặc `saved`; tài nguyên bị xóa vẫn giữ
định danh từ state cũ để có thể tra cứu sự kiện liên quan. ID/ARN được đánh dấu
sensitive bị che. Đây là metadata bổ sung, không được tính vào số thuộc tính drift.
Rule ingress/egress mới còn giữ group cha và alias security_group_rule_id nếu có,
với cùng status/source/sensitivity, để CloudTrail đối chiếu đúng rule.
`input_mode` là `refresh_only` khi tạo plan thật hoặc `imported_plan` khi đọc file.
Các trạng thái giá trị khác: `absent`, `unknown`, `sensitive`; chúng không có
trường value. `known` với `value: null` khác thuộc tính không tồn tại.
Path là danh sách khóa để phân biệt tag có dấu chấm với cấu trúc lồng nhau.
Collection được báo nguyên thuộc tính vì JSON không giữ thông tin list/set.
Collection có phần tử sensitive được che toàn bộ.

CLI tự bổ sung `source` cho resource drift, trỏ đến block khai báo trong mã
hiện tại. Vị trí là file tuyệt đối và dòng bắt đầu/kết thúc, không chứa đoạn mã
hay giá trị biểu thức. `located`, `ambiguous`, `unavailable` mô tả mức xác định;
trường `reason` giải thích khi chưa định vị được. Xem [chi tiết](SOURCE_LOCATIONS.md).

`assessment` bổ sung priority, signals và guidance cho từng resource. Top-level
`review_summary` đếm priority high/medium/unknown theo policy builtin-review-v2.
Unknown cần người kiểm tra, không có nghĩa rủi ro thấp. Các trường này chỉ hỗ trợ
review; không thay đổi has_drift hoặc exit code. Xem [quy tắc và hướng dẫn](DRIFT_REVIEW.md).
Khi bật gate CLI, report có thêm `gate` với criteria/matched_resources/exit_code.
Nếu không bật gate, không có trường bổ sung này. Priority chỉ ảnh hưởng exit khi
người gọi chọn cờ gate tương ứng.

Rule Security Group tách riêng có thể có `network_context` chứa các field mạng
before/after, gồm cả field không đổi cần cho review. Context được che sensitive,
không chứa raw resource và không được cộng vào số attribute drift. Báo cáo cũ
không có trường này vẫn đọc được; context thiếu không được tự suy đoán.

`normalizations` ghi các khác biệt biểu diễn đã được chuẩn hóa. Hiện chỉ coi
`null` và `{}` tương đương ở trường `tags` của `aws_instance`,
`aws_security_group` và `root_block_device[].tags` của `aws_instance`, khi
provider là `registry.terraform.io/hashicorp/aws`. AWS provider 6.70.0 đã tạo
các khác biệt này ngay sau apply trong lần thử thực tế. Mỗi mục lưu address,
path và lý do; nếu chỉ có khác biệt này thì không kết luận có drift.
Thêm/xóa tag thật, đổi giá trị tag và các trường khác vẫn được báo bình thường.
Quy tắc này không áp dụng chung cho mọi thuộc tính `null`/rỗng.

## Phạm vi và giới hạn

- Chỉ tài nguyên managed trong state/workspace được chọn; không tìm tài nguyên
  ngoài Terraform, không nhận diện tài khoản AWS hoặc workspace mong muốn thay người dùng.
- Chất lượng refresh phụ thuộc provider: một số thay đổi không quan sát được,
  computed/default normalization có thể tạo drift; không kết luận mọi drift là thao tác của người.
- Không so sánh source với saved state để liệt kê riêng các thay đổi code chưa apply.
  Những thay đổi này được loại khỏi kết luận drift bằng chế độ refresh-only.
- Vị trí nguồn chỉ đến block resource, chưa suy ra dòng thuộc tính, locals hoặc
  biến tạo ra giá trị. Không tự sửa code/hạ tầng. Có thể bật
  [CloudTrail trace](CLOUDTRAIL.md) để gắn sự kiện ứng viên với actor/thời điểm
  cho EC2/Security Group; đây không phải kết luận nguyên nhân drift.
- Nhập plan JSON không xác minh được `-target`, refresh, freshness hoặc workspace;
  kết quả chỉ phản ánh phần resource_drift có trong file, không chứng nhận AWS hiện tại.
- Chỉ che những giá trị Terraform đánh dấu sensitive. IP, tag hoặc giá trị
  nội bộ không được đánh dấu vẫn có thể xuất hiện. Dùng báo cáo như dữ liệu riêng tư.
- Plan incomplete/errored/deferred, schema chưa hỗ trợ và sensitivity metadata lỗi
  bị từ chối. Source phải hợp lệ với provider/configuration hiện tại để plan chạy được.
- Provider/backend trên HCP remote có thể không hỗ trợ lưu plan theo cách này;
  hiện cần môi trường cho phép `plan -out` và `show -json` cục bộ.
- Docker image scanner hiện không chứa Terraform; chạy drift từ môi trường có
  Terraform và provider/backend phù hợp.

## Kiểm thử

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\ruff.exe check
.\.venv\Scripts\ruff.exe format --check

# Nếu Terraform chưa có trên PATH, trỏ tới executable đã cài.
$env:INFRALENS_TEST_TERRAFORM = 'C:\path\to\terraform.exe'
.\.venv\Scripts\python.exe -m pytest -q tests/integration/test_terraform_integration.py --run-terraform --run-network
```

Suite mặc định dùng executable Terraform giả để kiểm tra ranh giới process,
tham số, timeout, lỗi, cleanup và báo cáo. Suite thật dùng `terraform_data` và
`local_file` trong thư mục tạm: code mới/chưa apply, baseline sạch, sửa code,
sửa file ngoài Terraform, sửa cả hai và xóa file. Chỉ fixture local_file được
apply để thiết lập state cho test; InfraLens không gọi apply.
Fixture terraform_data cần Terraform >=1.4; adapter hỗ trợ Terraform >=1.1,<2.
Provider local_file nhận diện file theo hash nên sửa nội dung ngoài Terraform
được nó báo là resource biến mất (`delete`), không phải update content.

Tham khảo: [Terraform refresh-only](https://developer.hashicorp.com/terraform/cli/commands/plan#planning-modes)
và [định dạng JSON resource_drift](https://developer.hashicorp.com/terraform/internals/json-format#plan-representation).

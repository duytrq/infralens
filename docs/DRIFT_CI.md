# Gate CI theo ưu tiên drift

Gate quyết định mã thoát từ **toàn bộ** finding đã đánh giá. Nó không lọc report,
không apply và không sửa state. Priority là heuristic `builtin-review-v2`, không
phải mức độ rủi ro được bảo đảm cho mọi workload.

Backend và dashboard cũng hỗ trợ cùng policy: xem [request gate và trạng thái
thực thi](BACKEND.md#gate-theo-ưu-tiên). Gate chặn không biến lượt thu thập đã
thành công thành lỗi thực thi; report giữ cả hai quyết định riêng biệt.

## Tùy chọn

| Tùy chọn | Khi nào trả exit 1 |
| --- | --- |
| `--fail-on-drift` | Bất kỳ managed resource drift, kể cả unknown |
| `--fail-on-priority high` | Có resource priority high |
| `--fail-on-priority medium` | Có resource priority medium hoặc high |
| `--fail-on-unknown` | Có resource priority unknown hoặc chưa được đánh giá hợp lệ |

Ngưỡng nhận high/medium, không phân biệt hoa/thường, bỏ khoảng trắng hai đầu.
Giá trị khác trả 2 trước khi khởi tạo engine, đọc plan hoặc tạo output.
Unknown không được xếp vào thang high/medium. Muốn chặn cả high và unknown:

```powershell
.\.venv\Scripts\infralens.exe drift .\examples\drift-review `
  --plan-json .\examples\drift-review\plan.json `
  --fail-on-priority high --fail-on-unknown `
  --format json --output .\reports\drift-gate.json
```

Demo có 4 resource: high=2/medium=1/unknown=1. Gate khớp 3 resource và trả 1,
report vẫn chứa đủ 4 resource. Không cần AWS/Terraform executable khi import
không bật trace. Với dự án thật, bỏ plan-json để chạy refresh-only như trước.

Các cờ kết hợp bằng OR: `--fail-on-drift --fail-on-priority high` vẫn chặn cả
medium/unknown vì cờ đầu chặn mọi drift. Không bỏ qua finding do cờ cũ bị ghi đè.
Một resource khớp nhiều tiêu chí chỉ được đếm một lần, nhưng giữ đủ reason code.

`--fail-on-unknown` dùng **priority hiệu lực của resource**. Resource priority high
có thêm signal unknown vẫn được tính high; cần ngưỡng high để chặn trường hợp đó.
Assessment thiếu policy/priority, policy không phải phiên bản hiện tại hoặc
priority không nhận diện được được xếp unknown và tăng unassessed_resources.

## Mã thoát và báo cáo

- **0:** Gate đã chọn không khớp finding. Vẫn có thể có drift medium/unknown.
- **1:** Có finding khớp ít nhất một tiêu chí gate.
- **2:** Tùy chọn/đường dẫn không hợp lệ trước khi chạy engine.
- **3:** Lỗi engine/plan JSON, trace AWS/dependency hoặc ghi báo cáo; ưu tiên hơn exit 1.
- **130:** Người dùng ngắt lệnh.

Report được xuất trước khi trả 1. Nếu trace has_errors=true mà drift report vẫn
có thể xuất, gate.status=incomplete, gate.exit_code=3; không ghi nhận gate passed
để che lỗi trace. Partial trace không có lỗi thực thi vẫn giữ semantics hiện tại:
gate xét drift, còn độ phủ trace được ghi riêng. Không tự biến partial thành 3.
Lỗi trước khi có report hoặc lỗi ghi file không tạo báo cáo thành công giả;
writer vẫn giữ file cũ nguyên vẹn khi không thể thay thế.

Khi bật bất kỳ cờ gate (kể cả fail-on-drift cũ), JSON có thêm trường `gate` và
bảng có phần CI gate. Nếu không bật cờ nào, report giữ nguyên cấu trúc trước đó.

```json
{
  "gate": {
    "policy": "drift-gate-v1",
    "review_policy": "builtin-review-v2",
    "status": "failed",
    "exit_code": 1,
    "criteria": {
      "any_drift": false,
      "minimum_priority": "high",
      "unknown_priority": true
    },
    "priority_counts": {"high": 2, "medium": 1, "unknown": 1},
    "unassessed_resources": 0,
    "matched_count": 3,
    "matched_resources": [
      {"address": "aws_instance.missing", "priority": "high", "reasons": ["priority_threshold"]}
    ],
    "reason_codes": []
  }
}
```

Mảng matched_resources trong ví dụ được rút gọn; report thật chứa đủ 3 mục.
Gate chỉ thêm address/priority/reasons/count, không sao chép giá trị thuộc tính,
secret hay raw event vào quyết định. Báo cáo chính vẫn theo quy tắc sensitive
của Terraform. Đây là gate CLI; backend/API chưa nhận tùy chọn gate và trạng thái
succeeded của job vẫn chỉ có nghĩa engine thực thi thành công.

Gate passed không chứng nhận hạ tầng sạch/đúng ý định. Import plan vẫn chưa
xác minh freshness, workspace và coverage; untracked resources không được quét.

## Demo 8 tình huống offline

```powershell
.\.venv\Scripts\python.exe .\examples\ci\demo_gate.py
.\.venv\Scripts\python.exe .\examples\ci\demo_gate.py --format json
```

Script gọi CLI thật bằng các plan giả trong thư mục tạm, không gọi Terraform/AWS.
Nó kiểm tra clean, cho phép/chặn medium, cho phép/chặn unknown, high, mixed và
cờ any-drift kết hợp ngưỡng. Demo trả 0 khi cả 8 hành vi đúng, kể cả các case
CLI con phải trả 1. Không cần đăng nhập AWS. JSON stdout chỉ là bằng chứng demo,
không phải Terraform plan để import lại.

## Mẫu GitHub Actions

[examples/ci/drift-gate.yml](../examples/ci/drift-gate.yml) là mẫu dành cho checkout
InfraLens này (source package và fixture Terraform cùng repo). Nó chưa nằm trong
`.github/workflows`, chưa được kích hoạt/chạy trên GitHub. Nếu dùng cho repo hạ
tầng riêng, cài wheel InfraLens có gate thay cho bước pip install checkout đó,
rồi chỉnh project/plan path theo repo của bạn.

Mẫu dùng workflow_dispatch, Python 3.12, GitHub.com hosted runner, quyền contents
read và action SHA đã pin. Input được truyền qua environment rồi quote trong Bash;
không nội suy trực tiếp vào mã shell. Không cấu hình AWS hoặc tự tạo plan.
File plan phải có sẵn từ quy trình Terraform tin cậy của nhóm.

Bước gate không có continue-on-error hoặc `|| true`. Upload chạy với always()
để giữ normalized report khi gate trả 1; không upload raw plan/state. Tên artifact
gắn run ID/attempt, retention 7 ngày. Fixture mặc định có drift, nên job sẽ thất
bại do policy khi dùng mặc định. Nếu lỗi xảy ra trước khi có report, uploader có
thể không tìm thấy file; lỗi ban đầu vẫn được giữ. Report có thể chứa dữ liệu chưa
được đánh dấu sensitive, cần chọn phạm vi truy cập artifact phù hợp.

Đã parse YAML, kiểm tra SHA/input/upload scope và chạy nguyên bước Bash local;
chưa kiểm chứng orchestration/upload trên GitHub Actions. Tham khảo chính thức:
[checkout](https://github.com/actions/checkout),
[setup-python](https://github.com/actions/setup-python),
[upload-artifact](https://github.com/actions/upload-artifact).

[Biên bản kiểm chứng](verification/DRIFT_GATE_2026-10-23.md).

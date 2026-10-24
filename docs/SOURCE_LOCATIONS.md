# Định vị khai báo Terraform trong báo cáo drift

Lệnh drift tự tìm block resource tương ứng trong mã nguồn hiện tại, rồi thêm
file và khoảng dòng vào cả terminal lẫn JSON. Không cần bật thêm tùy chọn.

```powershell
cd C:\work\infralens
# Cài/cập nhật dependency của checkout, bao gồm python-hcl2 8.x.
uv sync --locked --group dev --extra aws-trace --extra aws-demo

# Demo offline; không chạy Terraform hoặc gọi AWS.
.\.venv\Scripts\infralens.exe drift .\examples\drift `
  --plan-json .\examples\drift\plan.json
```

Ví dụ demo hiển thị:

```text
Source aws_instance.demo: located
  C:\work\infralens\examples\drift\main.tf:6-9 (resource block)
```

Với dự án thật, tiếp tục dùng lệnh `infralens drift <PATH>` và các tùy chọn
profile/region/trace như trước. Đây là bước đọc và phân tích file, không gọi
init, tải module, chạy biểu thức Terraform hay sửa hạ tầng/state.

## Dữ liệu JSON

```json
{
  "source": {
    "status": "located",
    "context": "current_configuration",
    "block_address": "module.app.module.child.aws_instance.demo",
    "locations": [{
      "file": "C:/work/infra/modules/child/main.tf",
      "start_line": 12,
      "end_line": 25,
      "syntax": "hcl"
    }]
  }
}
```

`file` là đường dẫn tuyệt đối; dòng bắt đầu/kết thúc tính từ 1 và bao gồm
block resource. `syntax` là hcl hoặc json. Trong `.tf.json`, dòng đầu chỉ đến
key nhãn resource cuối cùng, ví dụ `"demo": {`, dòng cuối là cuối body đó.
Không xuất source excerpt, expression, module source URL hoặc giá trị trong file.

## Resource instance và module

- `count` và `for_each`: bỏ selector theo cấu trúc địa chỉ, giữ đúng tên module,
  loại resource và tên resource. Các key có dấu chấm, ngoặc hoặc quote không bị
  chia nhầm thành một module khác. Nhiều instance dùng chung vị trí block.
- Mỗi module chỉ tìm trong các file `.tf`/`.tf.json` trực tiếp của thư mục đó.
  Không quét mọi thư mục con để tìm tên trùng.
- Module local với source literal `./...` hoặc `../...` được theo đường dẫn
  tương đối với module cha, kể cả module ở ngoài thư mục root.
- Module đã init dùng metadata `modules/modules.json` trong `TF_DATA_DIR`,
  mặc định `.terraform`. Tra theo chuỗi tên module, không theo instance selector.
  Module call phải vẫn tồn tại trong code cha trước khi dùng metadata đã cài.
- Hỗ trợ block HCL và dạng block JSON object/array, kể cả module lồng nhau.
  HCL dùng AST từ python-hcl2; JSON được validate trước khi lấy span key/body.
  Comment, chuỗi hay heredoc chứa chữ giống resource không tạo vị trí giả.

## Trạng thái và giới hạn

| Status | Ý nghĩa |
| --- | --- |
| `located` | Một block khớp loại/tên resource trong đúng module |
| `ambiguous` | Có nhiều block trùng, gồm trường hợp base và override |
| `unavailable` | Không xác định được vị trí; xem reason |

Các reason gồm `resource_not_declared`, `module_not_declared`,
`module_not_installed`, `module_manifest_invalid`, `ambiguous_module`,
`parse_error`, `source_unreadable`, `unsupported_address` và giới hạn đọc file.
Khi có nhiều resource declaration, các vị trí ứng viên được giữ trong locations.
Nếu có file không parse được, các vị trí tìm thấy chưa được xác nhận là duy nhất.

Không tự merge override để suy ra nơi tạo ra giá trị cuối cùng. Chỉ xác định
block, chưa truy ngược qua biến/locals/dynamic block tới dòng thuộc tính.
Literal HCL phức tạp mà parser không đọc được sẽ cần metadata module đã init;
parser chưa hỗ trợ cú pháp mới thì báo unavailable thay vì đoán bằng regex.

Giới hạn mỗi file 2 MiB, tổng dữ liệu đọc 16 MiB, 200 file/module, 100 thư mục
module được cache và độ sâu module address 64. Giới hạn tính riêng mỗi lệnh
drift. Chỉ đọc file cấu hình và metadata module cần thiết, không đọc tfvars/state
để định vị nguồn. File bắt đầu bằng dấu chấm được bỏ qua.
Output được bảo vệ khỏi ghi đè metadata module/backend, kể cả qua hardlink,
và khỏi ghi vào thư mục TF_DATA_DIR tùy chỉnh.

`source.context` luôn là current_configuration, kể cả khi đọc `--plan-json`.
Mã có thể đã đổi từ lúc tạo plan; vị trí không chứng nhận Git revision hoặc code
lúc phát sinh thay đổi. Resource đã xóa khỏi code vẫn có thể có drift và source
unavailable. Kết quả định vị nguồn không làm thay đổi has_drift hoặc exit code.

## Kiểm thử

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_source_locations.py
$env:INFRALENS_TEST_TERRAFORM = 'C:\path\to\terraform.exe'
.\.venv\Scripts\python.exe -m pytest -q tests/integration/test_terraform_integration.py --run-terraform --run-network
```

[Biên bản kiểm chứng](verification/SOURCE_LOCATIONS_2026-10-22.md).

Nguồn: [API parser HCL](https://github.com/amplify-education/python-hcl2/blob/main/docs/01_getting_started.md),
[cú pháp JSON Terraform](https://developer.hashicorp.com/terraform/language/syntax/json),
[module sources](https://developer.hashicorp.com/terraform/language/modules/sources).

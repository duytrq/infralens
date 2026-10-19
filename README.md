# InfraLens

Nền tảng CLI Python cho kiểm tra bảo mật và drift của dự án Terraform.
Phiên bản **0.1.0** trên nhánh `feature/cli` chỉ triển khai giao diện lệnh,
chuẩn hóa/kiểm tra đầu vào, logging và xử lý lỗi.

**Chưa có scan engine, drift engine hay CloudTrail trace.** Lệnh hợp lệ trả mã
`4` với thông báo tính năng chưa triển khai. CLI không gọi Trivy, Terraform,
AWS hoặc network; không kiểm tra binary/credentials, tạo báo cáo, tạo thư mục
output, sửa Terraform hoặc thao tác state. Các lựa chọn format và chính sách
findings mới được khai báo và lưu trong `ScanOptions`/`DriftOptions`.

## Cài đặt và chạy

Yêu cầu Python **≥3.10** và [uv](https://docs.astral.sh/uv/).
Từ thư mục repo:

```bash
uv sync --locked
uv run infralens
uv run infralens --help
uv run infralens --version
uv run python -m infralens --help
```

`infralens` không có subcommand sẽ hiện help và thoát `0`. Phiên bản lấy từ
package metadata. Để cài CLI độc lập từ repo: `uv tool install .`.

Global options `--help`, `--version`, `--verbose`, `--no-color` đặt **trước**
subcommand. Help riêng của lệnh dùng `infralens scan --help` hoặc
`infralens drift --help`. Help và thông báo lỗi dùng tiếng Anh.

## Scan

Các ví dụ dưới đây giả định `./infra` chứa ít nhất một tệp Terraform trực tiếp:

```bash
uv run infralens scan ./infra
uv run infralens --verbose scan "./terraform project" --severity "high, critical"
uv run infralens --no-color scan ./infra --format json --output ./reports/security.json
uv run infralens scan ./infra --format sarif --fail-on HIGH
```

| Tham số | Quy tắc |
| --- | --- |
| `PATH` | Thư mục Terraform bắt buộc. |
| `--severity` | Danh sách phân cách bằng dấu phẩy: `UNKNOWN,LOW,MEDIUM,HIGH,CRITICAL`. Mặc định chọn tất cả; không phân biệt hoa thường, bỏ khoảng trắng quanh mỗi giá trị và loại giá trị trùng. Từ chối mục rỗng/không hợp lệ. |
| `--format` | `table`, `json`, `sarif`; mặc định `table`. Không suy luận từ đuôi output; chưa có renderer. |
| `--output` | Đường dẫn tệp báo cáo dự kiến; chưa ghi tệp. |
| `--fail-on` | Một ngưỡng `LOW`, `MEDIUM`, `HIGH`, `CRITICAL`, không phân biệt hoa thường. Mặc định không thất bại vì findings. |

Hợp đồng cho engine sau này: ngưỡng bao gồm chính mức đó và các mức cao hơn
(`HIGH` gồm HIGH và CRITICAL). `--severity` chỉ lọc báo cáo; **không thay đổi**
việc đánh giá `--fail-on` trên toàn bộ findings. Nhánh này chưa đánh giá findings.

## Drift

```bash
uv run infralens drift ./infra
uv run infralens drift ./infra --var-file dev.tfvars --var-file overrides.tfvars
uv run infralens drift ./infra --format json --output ./reports/drift.json --fail-on-drift
uv run infralens --verbose drift ./infra --profile dev --region ap-southeast-1
uv run infralens drift ./infra --trace
uv run infralens drift ./infra --trace --lookback-days 14
```

| Tham số | Quy tắc |
| --- | --- |
| `PATH` | Thư mục Terraform bắt buộc; chưa yêu cầu state hay `.terraform`. |
| `--var-file` | Có thể lặp lại, giữ thứ tự kể cả tệp trùng. Mỗi đường dẫn phải là tệp đọc được; không đọc/log nội dung. |
| `--format` | `table` hoặc `json`, mặc định `table`; chưa có renderer. |
| `--output` | Đường dẫn tệp báo cáo dự kiến; chưa ghi tệp. |
| `--profile`, `--region` | Tùy chọn; bỏ khoảng trắng ở đầu/cuối và từ chối chuỗi trắng. Chưa truy cập AWS hoặc kiểm tra credentials. |
| `--trace` | Yêu cầu CloudTrail trace, hiện chưa hỗ trợ. |
| `--lookback-days` | Số nguyên dương, chỉ dùng với `--trace`. Khi trace bật, mặc định 7 ngày. |
| `--fail-on-drift` | Khai báo chính sách thoát `1` khi có drift; chưa được đánh giá. |

Sau khi **tất cả** đầu vào hợp lệ, drift thường báo `Drift engine is not
implemented.`; drift có `--trace` báo `CloudTrail trace is not supported yet.`.
Cả hai đều thoát `4`. Lỗi cú pháp/đầu vào luôn được báo trước lỗi thiếu tính năng.

## Quy tắc đường dẫn

- `PATH` tương đối tính từ thư mục gọi CLI. Nó phải tồn tại, là thư mục đọc
  được, có ít nhất một tệp `.tf` hoặc `.tf.json` trực tiếp bên trong. Các tệp
  Terraform trực tiếp phải đọc được; không quét đệ quy.
- `--var-file` tương đối tính từ **thư mục Terraform**, không phải thư mục gọi
  CLI. Đường dẫn tuyệt đối cũng được chấp nhận.
- `--output` tương đối tính từ **thư mục gọi CLI**. Đích không được là thư mục
  hoặc trùng tệp Terraform/var-file đầu vào, kể cả qua symlink/hardlink.
- Cho phép cha của output chưa tồn tại, ví dụ `./reports/security.json`.
  Chỉ kiểm tra tổ tiên hiện có và quyền ghi sơ bộ, không tạo thư mục/tệp.
  Engine tương lai vẫn cần xử lý lỗi I/O tại thời điểm ghi thực tế.
- Dùng dấu nháy cho đường dẫn có khoảng trắng. Symlink được chuẩn hóa về đích.

## Logging và mã thoát

Help/version ghi ra **stdout**; logging và lỗi ghi ra **stderr**. Scan/drift
hiện để stdout trống để dành cho dữ liệu báo cáo sau này. Logging mặc định
`WARNING`; `--verbose` bật `DEBUG` để theo dõi các bước kiểm tra.

CLI hiện dùng văn bản thuần cho cả help và lỗi, nên `--no-color`, biến môi trường
`NO_COLOR` và stream không phải terminal đều không có ANSI. Không log nội dung
Terraform/tfvars/state, credentials hay environment. Lỗi ngoài dự kiến chỉ có
thông báo chung; verbose bổ sung tên tệp, dòng và hàm trong stack, không in source,
biến cục bộ hoặc exception payload. Cấu hình tắt pretty exceptions và locals
dựa trên [tài liệu Typer](https://typer.tiangolo.com/tutorial/exceptions/).

| Mã | Ý nghĩa |
| --- | --- |
| `0` | Help/version thành công; dành cho engine hoàn tất sau này. |
| `1` | Dành cho findings vượt ngưỡng hoặc drift khi bật `--fail-on-drift`. |
| `2` | Sai cú pháp hoặc đầu vào không hợp lệ. |
| `3` | Lỗi thực thi/I/O hoặc lỗi ngoài dự kiến. |
| `4` | Engine hoặc trace chưa triển khai. |
| `130` | Người dùng ngắt bằng Ctrl+C. |

## Phát triển và kiểm chứng

```bash
uv sync --locked --python 3.10
uv run pytest -q
uv run ruff check
uv run ruff format --check
uv build
```

Mã nguồn ở `src/infralens/`: `cli.py` khai báo lệnh và dựng dataclass;
`options.py` lưu options; `validation.py` kiểm tra đầu vào; `errors.py` và
`logging.py` xử lý chung; `handlers.py` báo tính năng chưa triển khai.
`tests/` dùng pytest và Typer CliRunner, kèm kiểm tra entrypoint đã cài,
`python -m infralens`, Ctrl+C và tính bất biến của fixture Terraform.
Lockfile `uv.lock` cố định dependencies cho môi trường phát triển.

Upload, dashboard, CI runner, backend API và mọi thao tác thay đổi Terraform/state
không thuộc phạm vi nhánh này.

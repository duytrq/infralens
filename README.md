# InfraLens

CLI Python để quét bảo mật mã Terraform và kiểm tra drift hạ tầng.

**Security scan đã hoạt động bằng Trivy.** Drift và CloudTrail trace hiện chỉ
validate đầu vào rồi trả mã `4`. Upload cloud chưa được triển khai.

## Chạy trực tiếp

Yêu cầu Python **>=3.10**, [uv](https://docs.astral.sh/uv/) và
[Trivy **0.76.x**](https://github.com/aquasecurity/trivy/releases/tag/v0.76.0)
trên PATH. Phiên bản chuẩn dùng để kiểm thử là 0.76.0.

```bash
uv sync --locked
uv run infralens --help
uv run infralens --version
uv run infralens scan ./infra
```

Cài CLI độc lập: `uv tool install .`. Cách này vẫn yêu cầu Trivy trên máy.
`python -m infralens` và executable `infralens` dùng cùng CLI.

Không có subcommand sẽ hiện help và thoát `0`. Global options `--verbose`,
`--no-color`, `--version` đặt **trước** subcommand. Help và thông báo CLI dùng
tiếng Anh; terminal sử dụng văn bản thuần, không ANSI.

## Chạy bằng Docker

**Chỉ cần Docker; không cần cài Python hay Trivy trên máy.** Image chứa cả
InfraLens và Trivy. Bản này hướng tới Linux/WSL, image `linux/amd64`.

```bash
docker build --platform linux/amd64 -t infralens:local .
mkdir -p reports .infralens-cache

docker run --rm --init \
  --user "$(id -u):$(id -g)" \
  -e HOME=/tmp \
  -v "$PWD/infra:/workspace:ro" \
  -v "$PWD/reports:/reports" \
  -v "$PWD/.infralens-cache:/cache" \
  infralens:local scan /workspace \
  --format sarif \
  --output /reports/security.sarif \
  --fail-on HIGH
```

Tự thay `$PWD/infra` bằng thư mục dự án cần quét. Các thư mục mount trên host
phải tồn tại; thư mục báo cáo/cache phải cho phép UID/GID được chọn ghi.

| Đường dẫn container | Mục đích |
| --- | --- |
| `/workspace` | Mã nguồn, mount chỉ đọc. |
| `/reports` | Báo cáo; ví dụ trên tạo `./reports/security.sarif` trên host. |
| `/cache` | Cache Trivy được giữ lại giữa các lần chạy. |

Container mặc định chạy bằng user `10001:10001`; `--user` trong ví dụ giúp file
báo cáo thuộc người dùng host. `--init` chuyển tiếp tín hiệu khi nhấn Ctrl+C.
Scan không cần Docker socket hoặc AWS credentials.

Image nền, uv và Trivy được ghim digest trong Dockerfile; dependencies Python
được cài từ lockfile. Chưa có launcher tự mount hoặc pipeline publish registry.
Nếu Docker Desktop báo WSL integration chưa bật, bật integration cho distro
đang chạy trước khi sử dụng lệnh `docker` trong WSL.

## Security scan

```bash
uv run infralens scan ./infra
uv run infralens --verbose scan "./terraform project" --severity "high, critical"
uv run infralens scan ./infra --format json --output ./reports/security.json
uv run infralens scan ./infra --format sarif --output ./reports/security.sarif
uv run infralens scan ./infra --severity LOW --fail-on HIGH
uv run infralens scan ./infra --timeout 120
```

| Tham số | Hành vi |
| --- | --- |
| `PATH` | Thư mục đọc được có ít nhất một `.tf` hoặc `.tf.json` trong cây thư mục. |
| `--severity` | Danh sách UNKNOWN,LOW,MEDIUM,HIGH,CRITICAL phân cách bằng dấu phẩy; mặc định tất cả. Không phân biệt hoa thường, bỏ khoảng trắng và giá trị trùng; từ chối mục rỗng/không hợp lệ. |
| `--format` | `table`, `json`, `sarif`; mặc định `table`. Không suy luận từ đuôi output. |
| `--output` | File báo cáo, tương đối với CWD hoặc tuyệt đối. |
| `--fail-on` | Ngưỡng LOW,MEDIUM,HIGH,CRITICAL gồm chính mức đó và các mức cao hơn. Mặc định không thất bại vì findings. |
| `--timeout` | Số giây nguyên dương cho scan, mặc định 300. Kiểm tra phiên bản giới hạn 10 giây; convert báo cáo giới hạn 60 giây. |

Trivy quét cấu hình Terraform đệ quy; InfraLens không chạy Terraform hay AWS CLI.
Bước khám phá đầu vào bỏ qua `.git`, `.terraform` và không đi theo symlink thư mục.
Việc resolve và đánh giá module do Trivy đảm nhiệm.

`--severity` chỉ lọc **báo cáo**. `--fail-on` đánh giá **tất cả findings chưa
bị ignore**. Vì vậy `--severity LOW --fail-on HIGH` vẫn trả `1` nếu có
HIGH/CRITICAL bị ẩn. UNKNOWN không vượt các ngưỡng LOW–CRITICAL.

Bảng terminal gồm tổng số findings, số đang hiển thị, số lượng theo severity,
rule ID, cảnh báo, resource và vị trí nguồn khi xác định được. Thứ tự hiển thị:
CRITICAL, HIGH, MEDIUM, LOW, UNKNOWN. Thiếu dòng thì chỉ hiện file; thiếu cả
vị trí thì hiện `unknown location`.

| Lựa chọn | stdout | File |
| --- | --- | --- |
| Mặc định | Bảng kết quả | Không tạo. |
| JSON/SARIF, không output | Chỉ dữ liệu JSON/SARIF | Không tạo. |
| Có output | Bảng kết quả | Định dạng đã chọn. |

JSON giữ schema gốc của Trivy; SARIF dùng phiên bản 2.1.0. Mỗi lệnh chỉ quét
một lần, sau đó chuyển đổi báo cáo từ JSON. Báo cáo có thể chứa trích đoạn
mã nguồn do Trivy cung cấp. Báo cáo được xuất trước khi trả exit code `1`.

### Checks, ignore và network

- Dùng built-in checks của Trivy; lần chạy có thể tải bản checks cập nhật.
  Khi Trivy dùng embedded checks thay thế, InfraLens báo warning.
- Tôn trọng ignore inline và `.trivyignore` trong thư mục quét; không nạp
  `trivy.yaml` từ project/CWD.
- Các biến `TRIVY_*` từ môi trường không được dùng để thay đổi scanner,
  filter, output hoặc chính sách. Ngoại lệ: `TRIVY_CACHE_DIR` để cấu hình cache.
  Proxy/TLS và cấu hình Git/Docker thông thường vẫn được kế thừa.
- Telemetry Trivy được tắt.
- Trivy có thể tải remote Terraform modules. Quét local không bảo đảm offline
  hoặc hoàn toàn không có network; mã nguồn và báo cáo không được InfraLens
  upload lên cloud.
- Trivy thực hiện static analysis, không truy vấn provider để resolve giá trị
  chỉ biết từ hạ tầng thật. Chất lượng phát hiện phụ thuộc checks và khả năng
  phân tích của Trivy. Lỗi parse được phát hiện phải trả lỗi, không báo scan sạch.

Tham khảo [Terraform coverage](https://trivy.dev/docs/v0.76/guide/coverage/iac/terraform/)
và [report conversion](https://trivy.dev/docs/v0.76/guide/configuration/reporting/).

## Đường dẫn và ghi báo cáo

- PATH tương đối tính từ thư mục gọi CLI; symlink đầu vào được chuẩn hóa.
- Scan kiểm tra Terraform trong thư mục con; drift vẫn yêu cầu ít nhất một
  `.tf` hoặc `.tf.json` trực tiếp trong PATH.
- Output không được là thư mục, trùng source/tfvars/state/lockfile, kể cả qua
  symlink/hardlink. Các tên file Terraform đầu vào cũng không được dùng làm
  tên output mới.
- Cho phép thư mục output chưa tồn tại; tạo ở bước xuất báo cáo.
- Ghi qua file tạm rồi thay thế atomically. Nếu ghi thất bại, báo cáo cũ được
  giữ nguyên. File báo cáo mới có quyền riêng tư `0600` trên Linux.
- JSON trung gian được lưu trong thư mục tạm riêng và dọn sau khi kết thúc.
  Source và state không bị sửa.

## Drift

```bash
uv run infralens drift ./infra
uv run infralens drift ./infra --var-file dev.tfvars --var-file overrides.tfvars
uv run infralens drift ./infra --format json --output ./reports/drift.json --fail-on-drift
uv run infralens drift ./infra --profile dev --region ap-southeast-1
uv run infralens drift ./infra --trace --lookback-days 14
```

Drift hiện validate đầu vào rồi trả mã `4`: thông báo engine chưa triển khai,
hoặc CloudTrail trace chưa hỗ trợ khi có `--trace`. Lỗi đầu vào được báo trước.
Không kiểm tra binary/credentials, gọi Terraform/AWS, đọc nội dung state/tfvars
hoặc tạo báo cáo cho drift.

`--var-file` có thể lặp lại, tính tương đối từ thư mục Terraform, giữ thứ tự.
Format là table/json; profile/region từ chối chuỗi trắng. `--lookback-days`
là số nguyên dương, chỉ dùng cùng trace; mặc định 7 khi trace bật.

## Logging và exit code

Help/version và dữ liệu báo cáo ghi stdout; logging, diagnostics và lỗi ghi
stderr. `--verbose` bật DEBUG để xem các bước xử lý, không in raw stderr của
Trivy, exception payload, source, credentials hoặc environment.

| Mã | Ý nghĩa |
| --- | --- |
| `0` | Thành công; findings không vượt ngưỡng hoặc không đặt ngưỡng. |
| `1` | Findings đạt/vượt fail-on. |
| `2` | Sai cú pháp hoặc đầu vào không hợp lệ. |
| `3` | Thiếu/sai phiên bản Trivy, lỗi scan/convert/JSON, timeout hoặc I/O. |
| `4` | Drift engine hoặc trace chưa triển khai. |
| `130` | Người dùng ngắt bằng Ctrl+C. |

Lỗi thực thi/ghi báo cáo ưu tiên hơn trạng thái findings. Timeout và Ctrl+C
dừng process group của công cụ và dọn tài nguyên tạm.

## Phát triển và kiểm chứng

```bash
uv sync --locked --python 3.10
uv run pytest -q
uv run ruff check
uv run ruff format --check
uv build

# Có Trivy 0.76.x trên PATH:
uv run pytest -q tests/integration/test_trivy_integration.py --run-integration
uv run pytest -q tests/integration/test_trivy_integration.py --run-integration --run-network

# Sau khi build image:
uv run pytest -q tests/integration/test_docker.py --run-docker
```

Suite mặc định dùng fixture và executable giả, không yêu cầu Trivy/Docker/network.
Các suite công cụ ngoài được chọn bằng flag; khi đã chọn, thiếu dependency
hoặc lỗi runtime sẽ làm test fail, không tự skip.

Có thể đặt `INFRALENS_TEST_TRIVY` bằng đường dẫn executable cho integration tests;
`TRIVY_CACHE_DIR` để dùng chung cache. Docker tests dùng `infralens:local`;
`INFRALENS_TEST_IMAGE` và `INFRALENS_TEST_DOCKER` cho phép đổi image/executable.
Tests Docker dùng volume riêng để hỗ trợ cả daemon từ xa, kiểm tra source chỉ
đọc, UID file báo cáo, cache, exit code và SIGINT; tự dọn container/volume đã tạo.

Mã nguồn trong `src/infralens/`: CLI/options/validation, handler orchestration,
Trivy adapter, process runner, reporting và error/logging chung.
Quyết định triển khai và checklist ở `tasks/plan.md`, `tasks/todo.md`.

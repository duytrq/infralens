# InfraLens

CLI Python để quét bảo mật mã Terraform và kiểm tra drift hạ tầng.

**Security scan đã hoạt động bằng Trivy.** Drift và CloudTrail trace hiện chỉ
validate đầu vào rồi trả mã `4`. Upload cloud chưa được triển khai.

## Cài wheel có sẵn Trivy (khuyến nghị)

Yêu cầu Python **>=3.10** và [uv](https://docs.astral.sh/uv/). Wheel bundle
chứa Trivy **0.76.0**; không cần cài Trivy riêng, Docker hoặc mount thư mục.
Hiện hỗ trợ Linux/WSL **x64** và Windows native **x64**. macOS và ARM64 để sau.

Tải đúng wheel từ build artifacts được cung cấp, rồi cài một lần:

```bash
# Linux/WSL x64
uv tool install ./infralens-0.1.0-py3-none-linux_x86_64.whl
infralens scan ./infra --format sarif --output ./reports/security.sarif
```

```powershell
# Windows x64 (PowerShell)
uv tool install .\infralens-0.1.0-py3-none-win_amd64.whl
infralens scan .\infra --format sarif --output .\reports\security.sarif
```

Nếu shell chưa tìm thấy `infralens`, chạy `uv tool update-shell` rồi mở terminal
mới. CLI dùng được ở mọi repo; đường dẫn input/output tương đối tính từ thư mục
gọi lệnh. Cập nhật bằng `uv tool install --reinstall <wheel-mới>`; gỡ bằng
`uv tool uninstall infralens`. Chưa tự publish package lên PyPI.

Mỗi wheel chỉ chứa một binary cho nền tảng tương ứng. Kích thước khoảng **49 MiB
Linux**, **50 MiB Windows**; binary sau cài khoảng **166/170 MiB** (chưa tính
dependencies Python và cache checks). Trivy được gọi trực tiếp bằng đường dẫn
nội bộ. Bundle lỗi/sai phiên bản trả exit `3` và hướng dẫn cài lại; không tự tải
executable hoặc chuyển sang Trivy khác trên PATH. `--verbose` cho biết scanner
đến từ `bundle` hay `PATH` cùng phiên bản.
SHA-256 của binary đã cài được kiểm tra một lần khi khởi tạo mỗi lệnh scan.

## Cài từ mã nguồn và dùng CLI ở nhiều repo

Yêu cầu Python **>=3.10**, [uv](https://docs.astral.sh/uv/) và
[Trivy **0.76.x**](https://github.com/aquasecurity/trivy/releases/tag/v0.76.0)
trên PATH. Phiên bản chuẩn dùng để kiểm thử là 0.76.0.

```bash
# Chạy ở thư mục bất kỳ; uv tải mã nguồn và cài CLI vào môi trường riêng.
# Cần Git và quyền truy cập repo GitHub này.
uv tool install 'git+https://github.com/duytrq/infralens.git'
infralens --help
infralens --version
```

Cài một lần, sau đó gọi `infralens` từ bất kỳ repo Terraform nào; không cần
clone repo InfraLens, chạy `uv sync` hay thêm dependency vào từng repo cần quét.
Trivy vẫn phải được cài riêng trên PATH. Nếu shell chưa tìm thấy `infralens`,
chạy `uv tool update-shell` rồi mở terminal mới. Xem
[hướng dẫn cài tool của uv](https://docs.astral.sh/uv/guides/tools/#installing-tools).

### Wheel phát triển không bundle

Nếu được cung cấp file wheel (`.whl`), tải file về rồi cài bằng đường dẫn tới
file đó. Ví dụ với package phiên bản 0.1.0 trong thư mục Downloads:

```bash
uv tool install "$HOME/Downloads/infralens-0.1.0-py3-none-any.whl"
infralens --version
```

Thay đường dẫn/tên file bằng package thực tế nhận được. Người đóng gói có thể
chạy `uv build` trong repo InfraLens để tạo wheel ở `dist/` rồi chuyển file đó
cho người dùng. Wheel `py3-none-any` tạo bằng `uv build` thông thường là bản
phát triển, **vẫn cần Trivy trên PATH**. Muốn tạo wheel bundle, dùng quy trình
đóng gói bên dưới. Không yêu cầu package đã được phát hành trên PyPI.

### Quét nhiều repo bằng cùng một bản cài

```bash
# Đứng trong repo thứ nhất, quét toàn bộ Terraform trong repo.
cd /path/to/repo-a
infralens scan . --format json --output ./reports/security.json

# Chuyển sang repo khác, chỉ quét thư mục infra.
cd /path/to/repo-b
infralens scan ./infra --format sarif --output ./reports/security.sarif

# Hoặc đứng ở bất kỳ đâu và truyền đường dẫn tuyệt đối.
infralens scan /path/to/repo-a/infra
infralens scan "/path/to/repo with spaces/infra"
```

Thay `/path/to/...` bằng đường dẫn repo trên máy. Mỗi lệnh quét một thư mục,
bao gồm các thư mục con có Terraform. PATH và `--output` tương đối đều tính từ
thư mục đang đứng khi gọi lệnh; vì vậy hai lệnh đầu ghi báo cáo vào từng repo
tương ứng. Repo cần quét không cần có `pyproject.toml` hay `uv.lock`.

### Cập nhật và gỡ cài đặt

```bash
# Lấy lại mã nguồn mới từ Git và cài lại.
uv tool install --reinstall 'git+https://github.com/duytrq/infralens.git'

# Hoặc cài lại từ file wheel mới đã tải về.
uv tool install --reinstall /path/to/infralens-0.1.0-py3-none-any.whl

# Gỡ CLI khi không còn sử dụng.
uv tool uninstall infralens
```

Để dùng đúng một revision khi cài từ Git, thêm `@<commit-sha>` vào cuối URL
(thay `<commit-sha>` bằng SHA thực tế).

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
infralens scan ./infra
infralens --verbose scan "./terraform project" --severity "high, critical"
infralens scan ./infra --format json --output ./reports/security.json
infralens scan ./infra --format sarif --output ./reports/security.sarif
infralens scan ./infra --severity LOW --fail-on HIGH
infralens scan ./infra --timeout 120
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
File nguồn `.tf`/`.tf.json` dạng symlink bị từ chối vì Trivy không bảo đảm quét
chúng; không trả scan sạch cho nguồn bị bỏ qua.
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
  symlink/hardlink, hoặc ghi đè `.trivyignore`. Các tên file Terraform đầu vào
  và tên `.trivyignore` cũng không được dùng làm
  tên output mới.
- Cho phép thư mục output chưa tồn tại; tạo ở bước xuất báo cáo.
- Ghi qua file tạm rồi thay thế atomically. Nếu ghi thất bại, báo cáo cũ được
  giữ nguyên. File báo cáo mới có quyền riêng tư `0600` trên Linux.
- JSON trung gian được lưu trong thư mục tạm riêng và dọn sau khi kết thúc.
  Source và state không bị sửa.
- Windows xuất UTF-8 cả khi redirect stdout/stderr; Ctrl+C/Ctrl+Break trả `130`.
  Timeout/ngắt lệnh dọn Trivy và tiến trình con qua Windows Job Object. Quyền
  báo cáo trên Windows theo ACL kế thừa của thư mục đích; `0600` chỉ áp dụng POSIX.

## Drift

```bash
infralens drift ./infra
infralens drift ./infra --var-file dev.tfvars --var-file overrides.tfvars
infralens drift ./infra --format json --output ./reports/drift.json --fail-on-drift
infralens drift ./infra --profile dev --region ap-southeast-1
infralens drift ./infra --trace --lookback-days 14
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

### Đóng gói bản bundle

Archive Trivy chính thức, URL và SHA-256 được ghim trong `vendor/trivy.json`.
Script chỉ tải ở bước chuẩn bị build, kiểm tra checksum rồi lấy binary/LICENSE;
không commit binary vào Git. Build hook kiểm tra manifest, checksum executable
và đúng kiến trúc trước khi đưa vào wheel. License Apache-2.0 của Trivy nằm cùng
binary tại `infralens/_vendor/trivy/LICENSE`; nguồn/phần mềm bên thứ ba được ghi
trong `vendor/README.md`.

```bash
uv sync --locked
uv run python scripts/bundle_trivy.py linux_x86_64
INFRALENS_BUNDLE_PLATFORM=linux_x86_64 uv build --wheel
uv run python scripts/verify_bundle.py dist/infralens-0.1.0-py3-none-linux_x86_64.whl
```

```powershell
uv sync --locked
uv run python scripts/bundle_trivy.py win_amd64
$env:INFRALENS_BUNDLE_PLATFORM = "win_amd64"
uv build --wheel
Remove-Item Env:\INFRALENS_BUNDLE_PLATFORM
uv run python scripts/verify_bundle.py dist/infralens-0.1.0-py3-none-win_amd64.whl
```

Có thể dùng `--archive <file-đã-tải>` cho bước chuẩn bị; checksum vẫn bắt buộc.
Build bundle thiếu/sai binary phải thất bại. Wheel không chứa database CVE/Java
hay bản checks riêng: chỉ bật Terraform và giữ cơ chế checks/cache hiện tại.
Không tách engine/policy thành một fork Go cần bảo trì.

`scripts/verify_bundle.py` dùng `uv tool install` trong thư mục tạm riêng, chạy
ngoài checkout với PATH rỗng, kiểm tra scan thật, JSON/SARIF, Unicode, ignore và
fail-on. Workflow `Bundled scanner` kiểm thử Linux/Windows với Python 3.10/3.14,
tạo wheel và checksum dưới dạng artifacts, cùng Docker smoke trên Linux; không
tự publish. Windows runner CI phải có quyền tạo symlink. Máy Windows không có
quyền này chỉ bỏ qua các test symlink thật với WinError 1314; đặt
`INFRALENS_REQUIRE_SYMLINKS=1` để yêu cầu chúng chạy như CI. Linux chạy đầy đủ.

Nâng Trivy: cập nhật phiên bản/URL/checksum từ release chính thức trong manifest,
chuẩn bị lại hai nền tảng rồi chạy toàn bộ kiểm thử. Adapter hiện hỗ trợ 0.76.x;
đổi minor phải kiểm tra và cập nhật compatibility guard. Không tự nâng binary
khi người dùng chạy scan.

### Phát triển từ checkout

Các lệnh dưới đây dành cho người phát triển, chạy trong repo mã nguồn InfraLens:

```bash
uv sync --locked --python 3.10
uv run infralens --help
uv run infralens scan ./tests/fixtures/clean
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

`uv run python -m infralens` và `uv run infralens` dùng cùng CLI trong môi
trường phát triển. Nếu muốn cài CLI độc lập từ checkout local, dùng
`uv tool install .` thay cho URL Git hoặc file wheel ở trên.

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

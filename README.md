# InfraLens

Công cụ nội bộ cho nhóm DevOps kiểm tra bảo mật mã Terraform, phát hiện drift
hạ tầng và lưu lịch sử kiểm tra trên dashboard. CLI chạy trên máy cá nhân hoặc
CI; backend AWS lưu báo cáo và phục vụ giao diện web.

- **Security:** dùng Trivy để phát hiện cấu hình Terraform không an toàn,
  hiển thị finding kèm vị trí code và xuất JSON/SARIF.
- **Drift:** dùng Terraform refresh-only để so sánh state đã lưu với hạ tầng
  quan sát được; có mức ưu tiên review, CI gate và CloudTrail candidates.
- **Dashboard:** quản lý project/API key, xem lịch sử Security/Drift, lọc findings,
  so sánh Drift, tải JSON và xóa từng lần kiểm tra.

[Dashboard dev](https://ddsw2osqv2rj2.cloudfront.net) ·
[Hướng dẫn sử dụng](docs/USER_GUIDE.md) · [Changelog](CHANGELOG.md)

## Cài CLI

Cần **Python >=3.10** và [uv](https://docs.astral.sh/uv/).
Tải wheel từ artifacts của workflow [Bundled scanner](.github/workflows/bundle.yml),
chọn đúng nền tảng rồi cài:

```bash
# Linux/WSL x64
uv tool install ./infralens-0.1.0-py3-none-linux_x86_64.whl
```

```powershell
# Windows x64
uv tool install .\infralens-0.1.0-py3-none-win_amd64.whl
```

Hai wheel này chứa **Trivy 0.76.0**, không cần cài scanner riêng. Nếu shell chưa
nhận lệnh, chạy `uv tool update-shell` rồi mở terminal mới.
Cập nhật bằng `uv tool install --reinstall <wheel-mới>`.

Có thể cài từ Git:

```bash
uv tool install 'git+https://github.com/duytrq/infralens.git'
```

Bản cài từ Git và wheel `py3-none-any` **cần Trivy 0.76.x trên PATH**.
Thêm `@<commit-sha>` vào URL Git để chọn đúng revision.
Package chưa phát hành trên PyPI. Terraform được cài riêng nếu dùng Drift thực tế.

## Chạy kiểm tra

Các ví dụ giả định code Terraform nằm trong `./infra`. Bỏ đường dẫn để dùng
thư mục hiện tại; input/output tương đối tính từ thư mục gọi lệnh.

### Security

```bash
infralens scan ./infra
infralens scan ./infra --fail-on HIGH
infralens scan ./infra --format sarif --output ./reports/security.sarif
```

Quét đệ quy bằng Trivy; không cần tài khoản InfraLens hoặc AWS credentials.
`--fail-on HIGH` chặn HIGH/CRITICAL. Không đặt gate thì findings không làm lệnh fail.

### Drift và CloudTrail

```bash
infralens drift ./infra
infralens drift ./infra --fail-on ANY
infralens drift ./infra --trace 7 --region ap-southeast-1
```

Cần **Terraform >=1.1,<2**, project đã `terraform init`, chọn đúng workspace
và có quyền truy cập backend/provider. InfraLens không tự init/apply hoặc ghi lại
state. Drift so sánh **state với hạ tầng thực tế**, không phải mọi thay đổi code
chưa apply.

`--trace DAYS` tra CloudTrail trong 1–90 ngày bằng AWS credentials của runner/máy
cá nhân; mặc định tắt. Các event là ứng viên liên quan để review, chưa chứng minh
nguyên nhân drift. Hiện chỉ hỗ trợ một số thay đổi EC2/Security Group.

Có thể thử dữ liệu mẫu mà không gọi Terraform/AWS:

```bash
infralens drift ./examples/drift-review \
  --plan-json ./examples/drift-review/plan.json
```

Ví dụ này chạy trong checkout InfraLens; plan mẫu không đại diện hạ tầng đang chạy.
Drift hỗ trợ gate `ANY`, `HIGH`, `MEDIUM` (gồm HIGH), `UNKNOWN`, hoặc kết hợp
như `HIGH,UNKNOWN`. `--severity` chỉ lọc hiển thị, không thay đổi gate.

## Upload và xem báo cáo

Đăng nhập dashboard bằng tài khoản Cognito được cấp, tạo key tại **API keys**.
Sau đó cấu hình CLI một lần:

```bash
infralens cloud configure --api-url https://8maelv4bic.execute-api.ap-southeast-1.amazonaws.com
infralens cloud login

infralens scan ./infra --upload --fail-on HIGH
infralens drift ./infra --upload --scope dev-default --trace 7
```

- Khi chưa chọn project, CLI tìm gốc Git của thư mục được quét, lấy **tên thư mục
  gốc trên máy** làm tên project và chuẩn hóa thành ID không có hash. Không lấy
  tên từ Git remote. ID trùng sẽ hỏi dùng project đã có hoặc nhập ID khác.
- Liên kết API/project được lưu vào `.infralens.toml`. Commit file này để các bản
  clone/CI dùng cùng project. API key được lưu riêng trên máy, không nằm trong repo.
- Có thể chọn project rõ ràng bằng `cloud project use ID` hoặc truyền
  `--project ID` cho lần upload. Dữ liệu thuộc tài khoản; không có quản lý team/RBAC.
- Drift upload cần `--scope` để phân biệt môi trường/workspace. So sánh mặc định
  chọn lần completed trước cùng tài khoản/project/scope/input mode.
- Terminal vẫn hiển thị kết quả. JSON mặc định lưu tại `.infralens/reports/`
  trong thư mục gọi lệnh; thêm đường dẫn này vào `.gitignore`. Gate fail vẫn upload.
- Mỗi lần chạy tạo run/báo cáo mới, kể cả kết quả giống nhau. Upload lỗi giữ file
  local; kiểm tra dashboard trước khi chạy lại nếu chưa rõ server đã nhận hay chưa.
- Với thư mục trong Git repo, CLI gửi commit, nhánh, trạng thái thay đổi chưa commit
  và đường dẫn tương đối từ repo root. Metadata được đọc trước khi scan tạo report.
  Detached HEAD có commit nhưng không có tên nhánh; repo chưa có commit hoặc máy
  thiếu Git vẫn scan/upload được, nhưng không có Git metadata. Báo cáo cũ không
  tự bổ sung thông tin này; cần tạo một lượt scan mới bằng CLI đã cập nhật.

Sau khi upload được xác nhận, CLI in `Dashboard: https://.../runs/<run-id>` để
mở thẳng báo cáo. Khi chạy trên GitHub Actions, link cũng xuất hiện trong job
Summary, kể cả khi gate fail. Địa chỉ dashboard được lấy từ API đang dùng;
không cần cấu hình thêm URL. Nếu không lấy được link, kết quả upload/gate vẫn
được giữ nguyên. Có thể mở project → **Security/Drift** để tìm run và tải JSON.

Mở project → **By commit** để xem Security và Drift của cùng commit/thư mục quét.
Mỗi lượt vẫn giữ thời gian, scope và gate riêng vì cùng code có thể quan sát các
trạng thái AWS khác nhau. Các lượt có thay đổi chưa commit được giữ riêng theo
run; báo cáo cũ hoặc không có Git nằm trong **Without Git metadata**. Nhóm chỉ
bao gồm lịch sử đã tải, dùng **Load more reports** để tìm thêm các lượt cũ.
Trang chi tiết của cả Security và Drift hiển thị SHA đầy đủ, nhánh và trạng thái
checkout ở phần **Source revision** gần đầu trang.
Security cần chờ analysis ready; CloudTrail xuất hiện nếu lần chạy đã bật trace.
Giới hạn report: Security **50 MiB**, Drift **2 MiB**. CLI hiện chưa có lệnh
liệt kê/tải lại báo cáo từ cloud. `cloud status` chỉ xem cấu hình; `cloud logout`
xóa key local, còn thu hồi key thực hiện trên dashboard.

## Dùng trong CI

Runner cần cài CLI và scanner như trên. Truyền cấu hình qua environment:

| Biến | Cách cung cấp |
| --- | --- |
| `INFRALENS_API_URL` | API URL của môi trường InfraLens. |
| `INFRALENS_API_KEY` | Secret của CI; không nhập key vào workflow hoặc repo. |
| `INFRALENS_PROJECT` | Project ID đã tạo, hoặc dùng `.infralens.toml` đã commit. |

```bash
infralens scan ./infra --upload --fail-on HIGH
```

Không cần `cloud login` tương tác trong CI. Khi trùng ID mà chưa có binding,
CI dừng để yêu cầu chọn rõ project. Với Drift thực tế, runner cần Terraform,
credentials và bước init/workspace trước khi gọi CLI.

Repo Terraform cần có workflow riêng để chạy InfraLens khi push. Các workflow
trong repo này kiểm thử/build CLI, backend và frontend; chưa tự deploy AWS.
Nếu checkout mã nguồn InfraLens từ repo khác, `ref` chọn nhánh/tag/commit,
`path` chọn thư mục trên runner. Bản thay đổi local phải được push trước khi CI dùng.

## Kiến trúc và mã nguồn

```text
Máy cá nhân / CI: InfraLens CLI → Trivy / Terraform / CloudTrail
                            → API Gateway + Lambda → DynamoDB
                            → S3 private (upload qua presigned URL)
Dashboard: React → Cognito + API; phân phối qua CloudFront + S3 private
```

Backend lưu metadata trong StorageTable, findings đã index trong FindingsTable,
report JSON trong S3. DynamoDB Streams kích hoạt Lambda phân tích Security;
EventBridge chạy cleanup. Hạ tầng ứng dụng được quản lý bằng AWS SAM/CloudFormation.
Tạo project không tạo thêm bucket/table riêng.

| Thư mục | Nội dung |
| --- | --- |
| `src/infralens/`, `tests/` | CLI và kiểm thử. |
| `backend/` | API, authorizer, phân tích báo cáo và cleanup. |
| `frontend/` | Dashboard React/Vite/TypeScript. |
| `infra/` | Templates, deploy/publish và kiểm kê AWS. |
| `contracts/` | OpenAPI cho backend/frontend. |
| `examples/` | Terraform/plan mẫu cho demo. |

## Phát triển

Tại checkout InfraLens:

```bash
uv sync --locked
uv run infralens --help
uv run pytest -q
uv run ruff check
uv run ruff format --check
```

Suite mặc định dùng fixtures, không gọi AWS thật. Xem
[phát triển CLI, Docker và build wheel bundle](docs/DEVELOPMENT.md),
[backend](backend/README.md), [frontend](frontend/README.md),
[triển khai AWS](infra/README.md) và [publish dashboard](infra/FRONTEND.md).

| Exit code | Ý nghĩa |
| --- | --- |
| `0` | Thành công; không có gate khớp hoặc chưa bật gate. |
| `1` | Findings/drift khớp gate đã chọn. |
| `2` | Tham số, đầu vào hoặc cấu hình không hợp lệ. |
| `3` | Lỗi công cụ, CloudTrail, mạng/upload, timeout hoặc I/O. |
| `130` | Người dùng ngắt lệnh. |

Chi tiết flags, định dạng báo cáo và xử lý lỗi:
[hướng dẫn sử dụng](docs/USER_GUIDE.md),
[luồng Drift](docs/DRIFT_INTEGRATION.md).

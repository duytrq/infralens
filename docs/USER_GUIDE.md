# Hướng dẫn sử dụng InfraLens

Cập nhật **2026-10-29**. InfraLens kiểm tra **Security** (cấu hình Terraform không
an toàn) và **Drift** (hạ tầng thực tế lệch so với state đã lưu). Chạy kiểm tra ở
máy/CI; dashboard dùng để xem báo cáo đã upload.

- Dashboard: https://ddsw2osqv2rj2.cloudfront.net
- API dev: `https://8maelv4bic.execute-api.ap-southeast-1.amazonaws.com`

## 1. Cài CLI

Cần Python **>=3.10**, `uv` và wheel bản mới được cung cấp. Package chưa phát hành
lên PyPI. Linux/WSL x64, chạy tại thư mục chứa wheel:

```bash
uv tool install --reinstall ./infralens-0.1.0-py3-none-linux_x86_64.whl
infralens --version
```

Windows x64, PowerShell:

```powershell
uv tool install --reinstall .\infralens-0.1.0-py3-none-win_amd64.whl
infralens --version
```

Wheel bundle chứa Trivy; `boto3` được cài tự động cùng CLI. Không cần cài SDK riêng.
Nếu shell chưa nhận lệnh, chạy `uv tool update-shell` rồi mở terminal mới.
Bản cài từ mã nguồn/wheel `py3-none-any` cần Trivy **0.76.x** trên PATH.
Xem [README](../README.md) nếu dùng mã nguồn thay vì wheel.

## 2. Thiết lập API một lần và quản lý project

```bash
infralens cloud configure --api-url https://8maelv4bic.execute-api.ap-southeast-1.amazonaws.com
infralens cloud project create my-app --name "My application infrastructure"
infralens cloud status
```

`configure` lưu API URL trên máy. `create` tạo project trên hệ thống rồi tự chọn
project đó cho các lần upload tiếp theo. Project ID `my-app` là do bạn đặt, dài
1–64 ký tự chữ thường/số/dấu `-` hoặc `_`, bắt đầu bằng chữ hoặc số.
`--name` là tên hiển thị, mặc định bằng ID; thêm `--no-select` nếu chỉ muốn tạo.

Với project đã có từ dashboard hoặc CLI:

```bash
infralens cloud project list
infralens cloud project use my-app
```

`list` tự lấy các trang kết quả, đánh dấu project đang chọn bằng `*`.
`use` kiểm tra project tồn tại và thuộc tài khoản đang đăng nhập trước khi lưu lựa chọn.
**Một project chứa được cả Security và Drift**; dashboard chia thành hai tab.

### CLI có cần đăng nhập không?

| Thao tác | Xác thực |
| --- | --- |
| Security scan local | Không cần đăng nhập hoặc AWS credentials. |
| Drift local trên AWS | Cần credentials/quyền cho Terraform backend/provider; không cần Cognito nếu không upload. |
| `cloud configure`, `cloud status` | Chỉ thao tác cấu hình local, không đăng nhập. |
| Project create/list/use hoặc `--upload` | Phải xác thực Cognito. CLI tự mở trình duyệt để đăng nhập. |

Dùng tài khoản được quản trị viên cấp, cùng tài khoản sẽ xem dữ liệu trên dashboard.
Hệ thống chưa mở tự đăng ký. Khi CLI mở browser, hoàn tất trong khoảng 3 phút,
để browser truy cập callback `localhost:8765` rồi quay lại terminal. Phiên đăng nhập
trên browser có thể giúp bạn không phải nhập lại password ở lệnh sau; CLI không lưu
password/access token/refresh token trên máy. Một lệnh cloud mới có thể mở browser lại.

CI/terminal không tương tác phải cung cấp `INFRALENS_ACCESS_TOKEN` qua secret
environment. Đây là Cognito **access token** còn hạn, có scope `infralens/api`,
không phải AWS access key hoặc ID token. Chưa có cơ chế machine identity trong CLI.
Tài khoản Cognito không cấp quyền AWS cho Terraform/CloudTrail.

### Cấu hình được lưu ở đâu?

- Linux/WSL: `$XDG_CONFIG_HOME/infralens/config.json`, mặc định `~/.config/infralens/config.json`.
- Windows: `%APPDATA%\infralens\config.json`.
- File chỉ có API URL và Project ID đã chọn, không có thông tin đăng nhập.

Thứ tự ưu tiên khi upload:

| Giá trị | Ưu tiên từ cao xuống thấp |
| --- | --- |
| API URL | `--api-url` → `INFRALENS_API_URL` → API đã lưu |
| Project | `--project` → `INFRALENS_PROJECT` → project đã chọn |

Project đã lưu chỉ được dùng khi API đang dùng khớp API của cấu hình. Khi đổi API,
hãy tạo/chọn project cho hệ thống mới. Scan local không đọc cấu hình cloud.

## 3. Security scan

Các ví dụ giả định bạn đứng tại repo hạ tầng, mã Terraform nằm trong `./infra`.
Nếu đang đứng ngay thư mục Terraform, thay `./infra` bằng `.`. Input/output tương
đối tính từ thư mục đang gọi lệnh. Không cần `terraform init` hoặc AWS CLI để scan.
Scanner có thể cần mạng để tải checks hoặc remote Terraform modules.

Quét và xem tại terminal:

```bash
infralens scan ./infra
infralens scan ./infra --severity HIGH,CRITICAL --fail-on HIGH
```

Xuất local:

```bash
infralens scan ./infra --format json --output ./reports/security.json
infralens scan ./infra --format sarif --output ./reports/security.sarif
```

Sau khi cấu hình API/chọn project ở mục 2, quét và upload không cần nhập lại hai giá trị đó:

```bash
infralens scan ./infra --format json --output ./reports/security.json --fail-on HIGH --upload
```

Mở project → **Security** trên dashboard, Refresh rồi chờ **Analysis: ready**.
Nếu cần ghi đè lựa chọn cho riêng một lệnh, thêm `--project other-project` hoặc
`--api-url https://your-api.example.com`; hai flag này không đổi cấu hình đã lưu.

### Đọc kết quả terminal

Mỗi finding có severity/rule, file:dòng, resource, mô tả và code được scanner cung cấp.
Dấu `>` và màu đánh dấu dòng liên quan; source tối đa 9 dòng, `...` là phần rút gọn.
Nếu không có code thì hiện `Source excerpt unavailable` và vẫn giữ finding.

- **CRITICAL:** chữ đỏ, không tô nền.
- **HIGH:** cam; **MEDIUM:** vàng; **LOW:** cyan; **UNKNOWN:** tím.
- Màu tự tắt khi redirect/pipe. Tắt chủ động bằng `infralens --no-color scan ./infra`
  hoặc đặt `NO_COLOR=1`. JSON/SARIF và file report không bị thêm mã màu terminal.

`--fail-on HIGH` trả exit `1` nếu có HIGH/CRITICAL chưa bị ignore. `--severity`
chỉ lọc hiển thị; không làm giảm phạm vi gate. Khi bật upload, JSON local/upload
luôn có toàn bộ findings chưa bị suppression để counts trên dashboard khớp dữ liệu.
Không upload thì JSON/SARIF vẫn lọc theo `--severity` như bình thường.
Giới hạn Security JSON trên cloud là **50 MiB**.

## 4. Drift

Drift thật cần Terraform ổn định **>=1.1,<2**, checkout đã init, đúng backend,
workspace, biến và credentials/quyền cho provider. Với AWS, có thể dùng profile,
biến môi trường hoặc IAM role; AWS CLI chỉ cần nếu quy trình nhóm dùng nó, ví dụ
`aws sso login`. SDK cho `--trace` đã được cài cùng InfraLens.

```bash
terraform -chdir=./infra init
terraform -chdir=./infra workspace show
infralens drift ./infra --format json --output ./reports/drift.json --fail-on HIGH
```

CLI dùng `terraform plan -refresh-only`: **state đã lưu ↔ hạ tầng provider quan sát**.
Không tự apply/destroy hoặc ghi lại state. Chỉ sửa code chưa apply không phải drift;
resource ngoài state không nằm trong phạm vi kiểm tra.

Upload vào cùng project đã chọn, thêm scope để định danh account/workspace/environment:

```bash
infralens drift ./infra --format json --output ./reports/drift.json --fail-on HIGH --upload --scope dev-default
```

Dùng cùng scope cho các lần kiểm tra cùng phạm vi, đổi scope khi đổi môi trường.
Scope theo quy tắc ký tự của Project ID và do client khai báo; server không tự
chứng thực account/workspace. Mở project → **Drift** để xem kết quả.
Giới hạn Drift JSON trên cloud là **2 MiB**.

| Flag riêng của Drift | Tác dụng |
| --- | --- |
| `--var-file dev.tfvars` | File biến tính từ Terraform root; có thể lặp lại. |
| `--profile dev --region ap-southeast-1` | Dùng AWS profile/region đã cấu hình. |
| `--trace --lookback-days 7` | Tìm sự kiện CloudTrail ứng viên, chủ yếu EC2/Security Group; không xác nhận ai gây drift. |
| `--fail-on HIGH` / `--fail-on MEDIUM` | Chặn high / medium trở lên theo review priority. |
| `--fail-on-drift` | Chặn mọi managed resource drift. |
| `--fail-on-unknown` | Chặn priority unknown/chưa đánh giá được. |
| `--plan-json plan.json` | Đọc plan JSON có sẵn; không chứng thực độ mới/workspace/coverage. |

Các gate kết hợp bằng OR. `--fail-on-priority` vẫn là alias của `--fail-on`.
Security dùng severity LOW/MEDIUM/HIGH/CRITICAL; Drift dùng review priority
MEDIUM/HIGH, là heuristic cần con người review.

## 5. Dashboard và so sánh

Đăng nhập tại https://ddsw2osqv2rj2.cloudfront.net. Bạn có thể tạo project trên web
bằng **New project** hoặc dùng CLI ở mục 2; sau đó chọn project → tab **Security/Drift**.
Dữ liệu riêng theo tài khoản, không chia sẻ chỉ vì trùng Project ID.

- Security: lọc severity/rule/file, mở finding để xem source/hướng xử lý;
  **Retry analysis** xử lý lại báo cáo trên server, không chạy lại scanner.
- Drift: lọc thời gian/scope/gate, xem saved state/observed, source, priority,
  CI gate và CloudTrail candidates. `[sensitive]`, `[unknown]`, `[absent]` khác nhau;
  `null` là một giá trị riêng. Gate passed/disabled không khẳng định không có drift.
- Comparison mặc định chọn lần completed trước cùng tài khoản/project/scope/input mode.
  Có thể chọn Baseline run ID khác tương thích. Lần đầu chưa có baseline là bình thường.

| Comparison | Ý nghĩa |
| --- | --- |
| new | Mới xuất hiện trong danh sách drift. |
| changed | Bằng chứng drift thay đổi. |
| unchanged | Bằng chứng giữ nguyên. |
| no_longer_reported | Không còn trong báo cáo hiện tại; chưa đủ để kết luận đã sửa. |
| indeterminate | Không đủ dữ liệu để kết luận bằng nhau. |

**Download JSON** tải report; **Delete** xóa lượt/report, không sửa hạ tầng.
**Refresh** chỉ lấy lại dữ liệu đã lưu. Dashboard không chạy Terraform/Trivy hoặc
khắc phục drift; muốn có quan sát mới cần chạy CLI/CI.

## 6. Upload lỗi và exit code

CLI chỉ tạo report theo `--output`, **không tạo file manifest và không có command
retry upload**. Mỗi lệnh `scan/drift --upload` là một lần quét mới và upload mới.
Bạn có thể dùng lại tên output; báo cáo mới thay file cũ bằng thao tác ghi atomic.

- Quét/xuất thành công: report nằm ở `--output`, kể cả khi gate fail.
- Gate fail: vẫn upload trước khi trả `1`.
- Upload lỗi: trả `3`, ghi rõ nguyên nhân và đường dẫn report local còn được giữ.
- Mạng lỗi: kiểm tra kết nối/DNS/proxy/TLS/API URL. `401`: đăng nhập/token hết hạn;
  `403`: thiếu quyền; `404`: sai project/API; `429` hoặc `5xx`: dịch vụ bận/lỗi.
- Nếu mất kết nối sau khi đã gửi, server có thể đã nhận report. **Kiểm tra dashboard
  trước khi chạy lại lệnh** để tránh tạo lượt trùng. Metadata/checksum vẫn được tính
  trong RAM và server kiểm tra đầy đủ; người dùng không cần quản lý file phụ.

| Exit | Ý nghĩa |
| --- | --- |
| 0 | Thành công, không có gate khớp; vẫn có thể có findings/drift nếu chưa bật gate. |
| 1 | Findings/drift khớp điều kiện chặn. |
| 2 | Tham số/đầu vào/cấu hình không hợp lệ. |
| 3 | Lỗi công cụ, trace, mạng/upload hoặc I/O. |
| 130 | Người dùng ngắt lệnh. |

Lỗi công cụ không được xem là kết quả sạch. Trace lỗi vẫn có thể giữ/upload bằng
chứng drift nhưng trả `3`. Khi cần hỗ trợ, gửi Project ID, scope/run ID nếu có,
CLI version, exit code và thông báo đã bỏ dữ liệu riêng tư. Không gửi password,
token, AWS credentials, raw state/tfvars hoặc URL download đã ký.

## 7. CI và demo

CI đặt `INFRALENS_API_URL`, `INFRALENS_PROJECT` qua environment và
`INFRALENS_ACCESS_TOKEN` qua secret environment. Sau đó dùng cùng lệnh upload ở
mục 3/4, không cần browser hoặc cấu hình máy người dùng. Token hết hạn phải được
cấp lại; CLI không tự lưu/gia hạn token cho pipeline.

Demo Drift không dùng AWS, chạy tại checkout InfraLens:

```bash
infralens drift ./examples/drift-review --plan-json ./examples/drift-review/plan.json --format json --output ./reports/drift-demo.json
```

Kết quả mẫu: 4 resource, high=2/medium=1/unknown=1; không cần Terraform/AWS nếu không
bật trace. Đây là dữ liệu giả, không chạy apply. Thư mục
`/home/lozshi/uet/security-demo` cũng có sẵn fixture để thử Security.

CLI có chung `PATH`, `--format`, `--output`, `--fail-on`, `--timeout` (mặc định 300
giây), `--upload`, `--project`, `--api-url`. Flag toàn cục như `--verbose` và
`--no-color` đặt trước subcommand. Xem `scan --help`, `drift --help`,
`cloud --help` và [chi tiết Drift](DRIFT_INTEGRATION.md).

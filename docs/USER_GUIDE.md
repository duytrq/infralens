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

## 2. Setup một lần

Tại repo hạ tầng, chạy:

```bash
infralens cloud setup
```

CLI hỏi API URL (nếu chưa lưu), mở browser đăng nhập Cognito khi cần, rồi cho
chọn hoặc tạo project. API/project luôn được gắn với repo qua `.infralens.toml`;
có thể commit file này cho cả nhóm dùng. Không có token trong repo và không có
project mặc định chung trên máy. Project chung của bản CLI cũ được bỏ qua.
API dev: `https://8maelv4bic.execute-api.ap-southeast-1.amazonaws.com`.

Tạo project có hướng dẫn:

```bash
infralens cloud project create
```

CLI hỏi Project ID và Display name. Nếu truyền ID (`cloud project create my-app`),
CLI chỉ hỏi tên; Enter nhận tên mặc định bằng ID, giống bước tạo project của setup.
Trong script/CI phải truyền đủ ID và `--name`, không có prompt hoặc fallback im lặng.

Có thể dùng từng lệnh riêng hoặc trong script:

```bash
infralens cloud configure --api-url https://8maelv4bic.execute-api.ap-southeast-1.amazonaws.com
infralens cloud login
infralens cloud project create my-app --name "My infrastructure"
infralens cloud project list
infralens cloud project use my-app
infralens cloud configure list
```

`create` tự gắn project với repo hiện tại; `--no-select` chỉ tạo. `project use` không có ID
sẽ mở danh sách chọn trên terminal tương tác. ID dài 1–64 ký tự chữ thường/số/`-`/`_`,
bắt đầu bằng chữ hoặc số. Một project chứa cả Security và Drift.

### Đăng nhập một lần

Scan local không cần tài khoản InfraLens; Drift thật vẫn cần credentials/quyền
cho Terraform backend/provider. Project và upload dùng Cognito. CLI lưu phiên,
tự dùng lại access token và gia hạn khi gần hết hạn; không mở browser mỗi lệnh.
Cấu hình hiện tại: access token 15 phút, refresh token 30 ngày. Khi phiên không còn
gia hạn được, terminal tương tác mở browser lại; CI báo cần cập nhật xác thực.
Lỗi mạng không xóa phiên hay ép đăng nhập lại.

`cloud login` đăng nhập mới một cách chủ động. Dùng tài khoản được quản trị viên
cấp, hoàn tất browser callback `localhost:8765` trong khoảng 3 phút.
`cloud logout` xóa phiên CLI local và yêu cầu thu hồi refresh token; không đăng
xuất dashboard hoặc xóa API/project. Nếu mạng lỗi CLI nói rõ chưa xác nhận thu hồi.
Access token đã phát hành có thể vẫn được API Gateway chấp nhận đến khi hết hạn.

`cloud configure list` (hoặc alias `cloud status`) không gọi mạng hoặc mở browser: hiển thị API/project, nguồn cấu hình
và tình trạng token local. Token còn hạn local không chứng minh chưa bị thu hồi.

### Cấu hình repo và credentials

```toml
api_url = "https://8maelv4bic.execute-api.ap-southeast-1.amazonaws.com"
project = "my-app"
```

`.infralens.toml` chỉ nhận hai trường trên; scope Drift vẫn phải truyền rõ theo
môi trường. `project use ID` cập nhật file repo gần nhất đã tìm được, hoặc tạo
file ở thư mục hiện tại khi chưa có, sau khi kiểm tra quyền truy cập project. Setup chạy lại không bắt tạo project hoặc login lại.

Khi upload, Project ID lấy từ **flag → biến môi trường → repo**; không có fallback
về project trên máy. API URL vẫn có thể lấy từ cấu hình máy để thuận tiện setup.
Thiếu project thì lệnh dừng trước khi quét và hướng dẫn `cloud setup`. CI có thể
chỉ định project tường minh bằng `INFRALENS_PROJECT` hoặc `--project`. CLI tìm file
repo từ thư mục **được quét**, đi lên đến gốc Git (kể cả Git worktree), không lấy
repo của terminal khi quét một đường dẫn khác. Khi đổi API, project đã lưu của API
cũ không được tự dùng cho API mới. Scan local không đọc cloud config.

- Cấu hình máy chỉ lưu API URL: `$XDG_CONFIG_HOME/infralens/config.json`, mặc định `~/.config/infralens/config.json`;
  Windows dùng `%APPDATA%\infralens\config.json`.
- Phiên theo API: `sessions/<hash-api>.json` cạnh file cấu hình. Có access/refresh token,
  không có mật khẩu. Linux/WSL dùng thư mục `0700`, file `0600`; Windows giới hạn ACL
  cho người dùng hiện tại. Không chia sẻ hoặc commit thư mục này.
- `cloud status` cho biết file repo và nguồn API/project đang dùng. Env overrides
  `INFRALENS_API_URL`/`INFRALENS_PROJECT` vẫn có hiệu lực.

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
infralens scan ./infra --fail-on HIGH --upload
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
infralens drift ./infra --fail-on HIGH --upload --scope dev-default
```

Dùng cùng scope cho các lần kiểm tra cùng phạm vi, đổi scope khi đổi môi trường.
Scope là nhãn cloud, không truyền biến hoặc chọn workspace/backend cho Terraform.
`--var-file` mới cung cấp giá trị biến. Ví dụ hai môi trường có state riêng:

```bash
infralens drift --var-file dev.tfvars --upload --scope dev
infralens drift --var-file prod.tfvars --upload --scope prod
```

Chọn đúng backend/workspace/credentials trước mỗi lệnh. Đổi tfvars hoặc scope không
tự tạo state riêng; CLI không suy ra scope từ tên hoặc nội dung file biến.

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

### Đọc output Drift trên terminal

Drift dùng cùng các thao tác quen thuộc với Security: `PATH` mặc định `.`,
`--format table/json`, `--output`, `--fail-on`, `--severity`, `--upload`,
`--project`, `--api-url`, `--timeout` và global `--no-color`.

```bash
infralens drift
infralens drift --severity HIGH,MEDIUM --fail-on HIGH
infralens --no-color drift --format json --output reports/drift.json
infralens drift --trace --region ap-southeast-1 --lookback-days 1
```

- Mỗi resource là một card: priority màu, địa chỉ/action, file:dòng, ID và lý do ngắn.
  HIGH cam, MEDIUM vàng, UNKNOWN tím; có nhãn chữ khi tắt màu/redirect.
- `Current configuration` chỉ hiển thị các biểu thức thuộc tính liên quan trong
  HCL/`.tf.json`, đánh dấu `>` ở dòng tương ứng. Đây là code hiện tại, không phải
  code lịch sử hoặc bản chụp state. Thuộc tính computed/không khai báo có thể không
  có excerpt. Source ngoài Terraform root, không đọc được hoặc parse không chắc chắn
  sẽ báo unavailable; không đoán dòng thay đổi.
- `Saved state -> Observed`: mỗi thuộc tính hiển thị `-` giá trị state và `+` giá trị
  provider quan sát. Object/rule lớn được tách thành các path nhỏ; phần dài được
  rút gọn và có báo xem JSON đầy đủ. Không lặp nguyên context không thay đổi.
- Các đoạn hướng dẫn review/restore/adopt chung và note dài không còn in mặc định.
  JSON vẫn giữ đầy đủ dữ liệu có cấu trúc, policy/guidance và gate.
- `--severity` của Drift nhận HIGH/MEDIUM/UNKNOWN, chỉ lọc card terminal.
  Counts, gate, JSON local và JSON upload vẫn tính trên toàn bộ resource drift.
  `--fail-on HIGH` chặn high; `--fail-on MEDIUM` chặn medium/high;
  thêm `--fail-on-unknown` nếu muốn chặn cả unknown.
- Code lấy theo AST và chỉ các thuộc tính liên quan; không đọc tfvars để in ra,
  không chép các trường bên cạnh. Giá trị được đánh dấu sensitive/unknown vẫn che.
  Excerpt chỉ phục vụ terminal/file table, không được thêm vào JSON/upload.

Trace xuất hiện ngay trong từng card: số candidate, thời gian, API action và actor,
hiện tối đa hai event rồi báo số còn lại trong JSON. Rule có thể ghi `exact rule ID`.
`unsupported resource`, `no matching events found`, `lookup failed` là các kết quả
khác nhau. Summary cho biết số resource có candidate, số unsupported và lookup có
lỗi không; `partial` do unsupported không đồng nghĩa có lỗi AWS. Event là ứng viên
liên quan, chưa chứng minh người gây drift. Trace lỗi thực sự vẫn trả exit `3`.

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

`PATH` mặc định là thư mục hiện tại. Khi dùng `--upload`, format mặc định là JSON;
không truyền `--output` thì CLI lưu tại `.infralens/reports/` trong thư mục gọi lệnh,
với tên loại scan + thời gian UTC + hậu tố riêng. Thêm `.infralens/reports/` vào
`.gitignore` của repo để không commit reports. Terminal vẫn hiển thị findings như
thường. `--format sarif/table --upload` bị từ chối; có thể truyền output JSON riêng.

Không tạo manifest và không có lệnh retry upload. Một lệnh mới tạo một lượt scan mới.
CLI báo đích API/project/scope trên stderr trước khi quét, báo gate và run ID khi upload.
Giữ JSON/SARIF stdout sạch để dùng trong script.

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

Runner sạch không có phiên đăng nhập máy cá nhân. Trong đợt này CI vẫn dùng access
token được cấp bên ngoài, có hạn 15 phút; chưa có API key hoặc tự cấp token dài hạn.
Runner có phiên đã lưu có thể tự gia hạn nhưng không mở browser.

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

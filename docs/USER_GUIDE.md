# Hướng dẫn sử dụng InfraLens

InfraLens hỗ trợ hai công việc: **Security** tìm cấu hình Terraform không an toàn;
**Drift** phát hiện hạ tầng thực tế đã thay đổi so với Terraform state đã lưu.
Bạn chạy kiểm tra bằng CLI trên máy hoặc CI, sau đó xem báo cáo trên dashboard.

Hướng dẫn áp dụng cho bản tích hợp Security/Drift, cập nhật ngày **2026-10-29**.

| Địa chỉ | Mục đích |
| --- | --- |
| [Dashboard](https://ddsw2osqv2rj2.cloudfront.net) | Đăng nhập, tạo project, xem báo cáo. |
| `https://8maelv4bic.execute-api.ap-southeast-1.amazonaws.com` | API dùng trong tham số `--api-url` của CLI. |

## Cú pháp chung của Security và Drift

Hai lệnh dùng cùng cách truyền thư mục và bộ flag chung:

```bash
infralens scan ./infra --format json --output ./reports/security-001.json --fail-on HIGH
infralens drift ./infra --format json --output ./reports/drift-001.json --fail-on HIGH
```

| Tham số chung | Cách dùng ở cả hai lệnh |
| --- | --- |
| `PATH` | Thư mục Terraform, đặt sau `scan` hoặc `drift`. |
| `--format` | Mặc định `table`; cả hai nhận `json`. Security có thêm `sarif`. |
| `--output` | File kết quả, đường dẫn tương đối với thư mục đang gọi lệnh. |
| `--fail-on` | Ngưỡng trả exit `1`; không phân biệt hoa/thường. Bỏ flag này nếu không muốn bật gate theo ngưỡng. |
| `--timeout` | Timeout của engine, đơn vị giây, mặc định `300`. |
| `--upload` | Bật upload; cần `--format json --output`, `--project` và `--api-url`. Mặc định tắt. |
| `--project`, `--api-url` | Project ID đã tạo và HTTPS API origin; dùng khi bật upload. |

`--fail-on HIGH` áp dụng theo thang đánh giá của từng tính năng: Security dùng
severity (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`); Drift dùng review priority (`MEDIUM`,
`HIGH`). Drift vẫn nhận `--fail-on-priority` như alias của `--fail-on` để các lệnh cũ
tiếp tục chạy. `--fail-on-drift` và `--fail-on-unknown` vẫn là tiêu chí bổ sung riêng.

Khi upload, thêm cùng bộ `--upload --project my-app --api-url ...`. Riêng Drift
cần thêm `--scope` để phân biệt account/workspace/environment khi so sánh báo cáo.
Security có `--severity`; Drift có `--var-file`, `--profile`, `--region`, `--trace`
và `--plan-json` theo công việc của từng engine. Xem tất cả bằng `scan --help`
hoặc `drift --help`. Flag toàn cục như `--verbose` đặt trước subcommand, ví dụ
`infralens --verbose scan ./infra` hoặc `infralens --verbose drift ./infra`.

## 1. Chuẩn bị và cài CLI

### Bạn cần những gì?

| Bạn muốn làm gì? | Cần chuẩn bị |
| --- | --- |
| Xem báo cáo trên dashboard | Trình duyệt và tài khoản được quản trị viên cấp. |
| Quét Security | InfraLens CLI và Trivy 0.76.x; wheel bundle đã chứa Trivy. |
| Kiểm tra Drift trên hạ tầng thật | InfraLens CLI, Terraform ổn định `>=1.1,<2`, project đã init và quyền truy cập backend/provider. |
| Thử Drift bằng plan JSON có sẵn | InfraLens CLI và bộ ví dụ; không cần Terraform hoặc AWS nếu không bật trace. |
| Tìm sự kiện CloudTrail | AWS credentials và quyền tra cứu CloudTrail trong phạm vi cần kiểm tra; `boto3` được cài tự động cùng CLI. |
| Upload Security/Drift | Có mạng, project đã tạo và tài khoản Cognito tương ứng. |

**AWS CLI không bắt buộc.** Với hạ tầng AWS, Terraform và boto3 có thể sử dụng
credentials từ biến môi trường, profile có sẵn hoặc IAM role trên runner.
Nếu nhóm dùng `aws sso login` để đăng nhập thì cần AWS CLI cho bước đăng nhập đó.
Tài khoản dashboard không cấp quyền truy cập AWS cho Terraform.

### Cài từ wheel được cung cấp

Nhận wheel **bản đã tích hợp Security/Drift upload** từ người phụ trách hệ thống.
Package chưa được phát hành lên PyPI; không dùng `pip install infralens` để giả
định nhận đúng bản của hệ thống này. Cần Python **>=3.10** và công cụ `uv`.

Linux/WSL x64, chạy tại thư mục chứa wheel:

```bash
uv tool install ./infralens-0.1.0-py3-none-linux_x86_64.whl
infralens --version
infralens drift --help
```

Windows x64, PowerShell:

```powershell
uv tool install .\infralens-0.1.0-py3-none-win_amd64.whl
infralens --version
infralens drift --help
```

Nếu nhận wheel tên khác, thay bằng đúng tên file được cấp. Wheel `py3-none-any`
không bundle Trivy: muốn quét Security phải có Trivy 0.76.x trên PATH.
Wheel không bundle Terraform. Nếu nhận mã nguồn thay vì wheel, xem
[cách cài từ mã nguồn](../README.md#cài-từ-mã-nguồn-và-dùng-cli-ở-nhiều-repo).
Mã nguồn cũng phải là revision có `scan --upload` và Drift/upload; cài từ nhánh mặc định
không bảo đảm nhận được bản tích hợp này.

Không tìm thấy lệnh sau khi cài? Chạy `uv tool update-shell`, mở terminal mới rồi
thử lại. Nếu nâng cấp bản đã cài, dùng `uv tool install --reinstall <đường-dẫn-wheel-mới>`.

`boto3` là dependency mặc định: cài hoặc cập nhật CLI bằng các lệnh trên sẽ tự cài
SDK cho CloudTrail. Không cần `--with boto3` hoặc extra riêng; muốn tra cứu chỉ cần
chuẩn bị AWS credentials/quyền phù hợp rồi bật `--trace` khi chạy Drift.

## 2. Đăng nhập và tạo project

1. Mở [dashboard](https://ddsw2osqv2rj2.cloudfront.net), chọn **Sign in**.
2. Đăng nhập bằng tài khoản được quản trị viên cấp. Nếu chưa có tài khoản,
   liên hệ quản trị viên; hệ thống hiện không mở tự đăng ký.
3. Tại **Projects**, chọn **New project**.
4. Nhập **Project name**, ví dụ `My application infrastructure`.
5. Nhập **Project ID**, ví dụ `my-app`, rồi chọn **Create project**.

Project ID là định danh cố định, dài 1–64 ký tự: chữ thường, số, dấu `-` hoặc `_`,
bắt đầu bằng chữ hoặc số. Các ví dụ bên dưới dùng `my-app`; thay bằng ID bạn đã tạo.

Mỗi project có hai tab **Security** và **Drift**. Dữ liệu riêng theo tài khoản:
hãy dùng cùng tài khoản khi đăng nhập CLI và dashboard. Tạo project không tự
kết nối AWS hoặc tự chạy kiểm tra hạ tầng.

## 3. Quét Security

Trong terminal, đi đến repo chứa mã Terraform của bạn. Các ví dụ giả định mã nằm
trong `./infra`; nếu bạn đang đứng ngay thư mục Terraform, thay `./infra` bằng `.`.
Đường dẫn tương đối của input/output được tính từ thư mục đang gọi lệnh.

```bash
infralens scan ./infra
infralens scan ./infra --format json --output ./reports/security.json
infralens scan ./infra --format sarif --output ./reports/security.sarif
```

CLI quét các file Terraform trong cây thư mục, in từng finding theo mức
`CRITICAL`, `HIGH`, `MEDIUM`, `LOW`, `UNKNOWN`; có rule ID, resource, vị trí nguồn
và đoạn code từ report khi xác định được. Dấu `>` đánh dấu dòng liên quan.
Không cần `terraform init` hoặc AWS credentials cho Security.
Scanner có thể cần mạng để tải checks hoặc remote modules.

Khi chạy trên terminal, severity có màu riêng: CRITICAL nền đỏ, HIGH đỏ, MEDIUM
vàng, LOW cyan, UNKNOWN tím; dòng code liên quan cũng được tô màu. Khi redirect
ra file/pipe, màu tự tắt. Để chủ động tắt màu, dùng
`infralens --no-color scan ./infra` hoặc đặt `NO_COLOR=1`.
JSON/SARIF và file report không bị thêm mã màu của giao diện terminal.

Ví dụ dạng hiển thị (ở đây là văn bản không màu):

```text
[HIGH] AWS-0107
  main.tf:27 | aws_security_group.public_admin
  Security group rule allows unrestricted ingress from any IP address.

  > 27 |     cidr_blocks = ["0.0.0.0/0"]
```

Mỗi excerpt hiển thị tối đa 9 dòng; `...` là phần bị rút gọn. Nếu scanner không
cung cấp source, finding vẫn được giữ và có thông báo `Source excerpt unavailable`.

Để CI trả thất bại khi có finding từ HIGH trở lên:

```bash
infralens scan ./infra --format json --output ./reports/security.json --fail-on HIGH
```

Exit `1` trong trường hợp này nghĩa là findings vượt ngưỡng; báo cáo vẫn được xuất.
`--severity` chỉ lọc nội dung hiển thị, không làm giảm phạm vi đánh giá `--fail-on`.

### Đưa Security lên dashboard

Tạo project theo mục 2, sau đó chạy (có thể dùng nguyên một dòng trên Bash/PowerShell):

```bash
infralens scan ./infra --format json --output ./reports/security-001.json --fail-on HIGH --upload --project my-app --api-url https://8maelv4bic.execute-api.ap-southeast-1.amazonaws.com
```

CLI mở trình duyệt để đăng nhập Cognito. Dùng cùng tài khoản đã tạo project,
hoàn tất trong khoảng 3 phút rồi quay về terminal. Callback dùng `localhost:8765`.
Không cần AWS credentials để upload Security. Nếu không bật `--upload`, scan vẫn
chỉ xuất báo cáo local.

Upload yêu cầu JSON và file output; không nhận SARIF/table và không cần `--scope`.
JSON được lưu/upload giữ **toàn bộ findings chưa bị suppression**. Khi bật upload,
`--severity` chỉ lọc bảng terminal; ví dụ `--severity LOW --fail-on HIGH` vẫn upload
HIGH/CRITICAL và có thể trả `1`. Với lệnh không upload, JSON/SARIF vẫn được lọc như cũ.

CLI tạo `security-001.json` và manifest `security-001.json.upload.json`.
Gate fail vẫn upload rồi trả `1`; upload lỗi giữ hai file và trả `3`.
Lượt scan mới dùng output mới, ví dụ `security-002.json`; muốn gửi lại cùng lượt,
dùng `cloud upload` theo mục 6, thay tên report/manifest bằng các file Security.
Giới hạn Security JSON là **50 MiB**. Báo cáo có thể chứa source snippets/giá trị
cấu hình, vì vậy chỉ bật upload khi muốn lưu chúng lên hệ thống.

Khi đã có dữ liệu trên web: mở project → **Security** → mở một scan → lọc findings
theo severity, rule hoặc file → mở finding để đọc mô tả, hướng xử lý và source.
Chờ **Analysis: ready** để xem findings đã được xử lý. Nếu analysis lỗi, có thể
**Download JSON** và chọn **Retry analysis** khi giao diện cung cấp nút này.
Retry chỉ xử lý lại báo cáo đã lưu, không chạy lại Trivy.

## 4. Kiểm tra Drift và upload lên dashboard

### Bước 1: Chuẩn bị đúng Terraform project

Chọn đúng checkout, backend, workspace, account và region của môi trường cần kiểm tra.
Project cần file `.tf` hoặc `.tf.json` trực tiếp trong thư mục truyền vào CLI.
Nếu chưa init, thực hiện theo cấu hình backend của nhóm; ví dụ cơ bản:

```bash
terraform -chdir=./infra init
terraform -chdir=./infra workspace show
```

Workspace hiển thị phải là workspace bạn định kiểm tra. AWS credentials cần cho
provider đọc tài nguyên; remote backend có thể cần thêm quyền đọc state và khóa
state theo cấu hình của nhóm. Nếu dùng profile đã cấu hình, truyền
`--profile dev --region ap-southeast-1`; nếu dùng credentials/role từ môi trường,
có thể bỏ `--profile`.

### Bước 2: Chạy kiểm tra local

```bash
infralens drift ./infra --format json --output ./reports/drift-local.json
```

Nếu project yêu cầu biến từ file, thêm `--var-file dev.tfvars`. Đường dẫn
`--var-file` tính từ Terraform root `./infra`, vì vậy ví dụ này đọc
`./infra/dev.tfvars`. Có thể lặp lại tham số nếu cần nhiều file.

CLI chạy `terraform plan -refresh-only` rồi đọc kết quả; không tự apply,
destroy hoặc ghi lại state đã refresh. Nó so sánh **state đã lưu ↔ hạ tầng provider
quan sát được**. Chỉ sửa file `.tf` mà chưa apply không được tính là drift;
resource ngoài state không nằm trong phạm vi kiểm tra.

### Bước 3: Chạy và upload

Ví dụ Bash trên Linux/WSL:

```bash
infralens drift ./infra --format json --output ./reports/drift-001.json --fail-on HIGH \
  --upload --project my-app \
  --api-url https://8maelv4bic.execute-api.ap-southeast-1.amazonaws.com --scope dev-default
```

PowerShell có thể dùng cùng lệnh trên một dòng:

```powershell
infralens drift ./infra --format json --output ./reports/drift-001.json --fail-on HIGH --upload --project my-app --api-url https://8maelv4bic.execute-api.ap-southeast-1.amazonaws.com --scope dev-default
```

`--scope` là tên ổn định đại diện cho một account/workspace/environment, ví dụ
`dev-default` hoặc `prod-main`. Dùng cùng scope cho các lần kiểm tra cùng phạm vi;
đổi scope khi chuyển môi trường. Scope dùng quy tắc ký tự giống Project ID và
do bạn khai báo, không phải account/workspace được server tự xác nhận.

CLI mở trình duyệt để đăng nhập Cognito. Đăng nhập **cùng tài khoản đã tạo project**,
hoàn tất trước khi hết thời gian chờ khoảng 3 phút, rồi quay về terminal.
CLI nhận callback trên `localhost:8765`; dùng máy có thể mở trình duyệt và truy
cập callback của chính phiên CLI. Mỗi lệnh upload có thể cần đăng nhập lại.

Sau khi thành công:

- `./reports/drift-001.json` là báo cáo đã xuất.
- `./reports/drift-001.json.upload.json` lưu thông tin để retry chính lượt upload đó.
- Dashboard: mở `my-app` → **Drift** → **Refresh** → mở lượt mới nhất.

Mỗi lần **kiểm tra mới** dùng tên output mới, ví dụ `drift-002.json`. CLI từ chối
ghi đè output có manifest upload sẵn. Báo cáo cloud tối đa **2 MiB**.

### Thêm CloudTrail hoặc điều kiện chặn CI

Thêm vào lệnh Drift những tham số cần dùng:

| Tham số | Tác dụng |
| --- | --- |
| `--trace --lookback-days 7` | Tìm sự kiện CloudTrail liên quan trong 7 ngày; phạm vi hỗ trợ chủ yếu EC2/Security Group. |
| `--fail-on-drift` | Trả exit `1` khi phát hiện bất kỳ managed resource drift nào. |
| `--fail-on HIGH` | Trả exit `1` khi có drift được đánh giá high. |
| `--fail-on MEDIUM` | Chặn cả medium và high. |
| `--fail-on-unknown` | Chặn resource có priority unknown hoặc chưa đánh giá được. |

Các điều kiện gate kết hợp bằng OR và không lọc bớt resource khỏi báo cáo.
Gate thất bại vẫn upload báo cáo rồi trả exit `1`. CloudTrail chỉ đưa ra sự kiện
ứng viên để điều tra, không xác nhận chắc chắn ai gây drift. Nếu trace lỗi nhưng
đã có báo cáo, CLI vẫn có thể upload báo cáo và trả exit `3`.

## 5. Đọc báo cáo Drift trên dashboard

Trong project, chọn **Drift**. Bạn có thể lọc theo thời gian, **Scope** và **Gate**,
sau đó chọn **Apply filters**. Mở một lượt để xem:

| Nội dung | Cách đọc |
| --- | --- |
| Resources with drift / Changed attributes | Số resource và thuộc tính được ghi nhận có thay đổi. |
| Saved state / Observed | Giá trị trong state đã lưu và giá trị provider quan sát. |
| Review priority | `high`, `medium`, `unknown`; hỗ trợ ưu tiên review, không phải kết luận bảo mật. Unknown cần xem xét thủ công. |
| Source in current configuration | Vị trí resource block trong mã nguồn tại lúc tạo báo cáo, không bảo đảm là dòng thuộc tính gây thay đổi. |
| CloudTrail candidates | Sự kiện liên quan nếu đã bật trace và có dữ liệu trong phạm vi hỗ trợ. |
| CI gate | Kết quả theo tiêu chí đã bật: passed, failed, incomplete hoặc disabled. |
| Collection / Trace | Việc thu thập có hoàn tất hay bị lỗi một phần. |

`[sensitive]` là giá trị được Terraform đánh dấu nhạy cảm và đã che;
`[unknown]` là chưa biết; `[absent]` là không còn thuộc tính. `null` là một giá trị
riêng, khác absent. Collection partial hoặc trace lỗi không có nghĩa là kiểm tra
đã hoàn tất thành công. Gate passed/disabled cũng không có nghĩa là không có drift.

### So sánh các lần kiểm tra

Mục **Comparison** mặc định chọn lần completed trước trong cùng tài khoản,
project, scope và input mode. Lần đầu chưa có baseline là bình thường. Có thể
nhập **Baseline run ID** rồi chọn **Compare** để chọn một lượt tương thích khác.

| Kết quả | Ý nghĩa |
| --- | --- |
| `new` | Resource mới xuất hiện trong danh sách drift. |
| `changed` | Bằng chứng drift thay đổi so với baseline. |
| `unchanged` | Bằng chứng drift giữ nguyên. |
| `no_longer_reported` | Không còn xuất hiện trong báo cáo hiện tại; chưa đủ để kết luận đã sửa. |
| `indeterminate` | Không đủ dữ liệu để kết luận bằng nhau, ví dụ có giá trị sensitive/unknown. |

**Download JSON** tải báo cáo. **Delete drift run** rồi **Confirm deletion** xóa
lượt khỏi lịch sử; thao tác không sửa/xóa hạ tầng AWS. Dashboard không chạy lại
Terraform và không tự khắc phục drift. Dùng **Refresh** để đọc lại kết quả đã lưu;
muốn có quan sát mới cần chạy CLI/CI lần nữa.

## 6. Upload lỗi: retry mà không chạy lại scanner

Giữ nguyên cả report và manifest, rồi chạy:

```bash
infralens cloud upload --report ./reports/drift-001.json \
  --manifest ./reports/drift-001.json.upload.json \
  --api-url https://8maelv4bic.execute-api.ap-southeast-1.amazonaws.com
```

Retry dùng lại run ID cũ. Không sửa report, manifest hoặc đổi API URL: checksum
và thông tin lượt được kiểm tra trước khi gửi. Nếu chưa có manifest, không dùng
lệnh retry này; khắc phục lỗi ban đầu và tạo một lượt kiểm tra mới với output mới.
Lệnh hỗ trợ cả Security và Drift: thay `drift-001.json` bằng `security-001.json`
và manifest tương ứng khi retry Security. Retry không chạy Trivy/Terraform;
nó không tạo report/metadata mới từ một file JSON bất kỳ.

## 7. Thử nghiệm và dùng trong CI

### Demo Drift không truy cập AWS

Nếu đã có checkout mã nguồn InfraLens bản tích hợp, đứng tại repo đó và chạy:

```bash
infralens drift ./examples/drift-review --plan-json ./examples/drift-review/plan.json --format json --output ./reports/drift-demo.json
```

Ví dụ có **4 resource drift**, priority **high=2, medium=1, unknown=1**. Không cần
Terraform/AWS vì đang đọc fixture và không bật `--trace`. Đây là dữ liệu giả lập;
không chạy apply cho bộ ví dụ. Lệnh này chưa upload lên dashboard. File import
không chứng minh độ mới, workspace hoặc mức bao phủ của hạ tầng thật.

### CI không mở trình duyệt

Runner cần CLI, Terraform, checkout đã init và credentials/role cho provider/backend.
Để upload không tương tác, pipeline phải được cấp secret environment
`INFRALENS_ACCESS_TOKEN`: **Cognito access token** còn hạn, có scope `infralens/api`
và thuộc tài khoản sở hữu project. Đây không phải AWS access key hoặc ID token.
Hệ thống hiện chưa có lệnh CLI tự cấp/gia hạn token cho CI hay machine identity.

Khi runner đã có token, dùng lệnh Security/upload ở mục 3 hoặc Drift/upload ở mục 4,
thêm gate theo nhu cầu
và tên output duy nhất cho mỗi lần chạy. Không truyền token trong command line
hoặc in token vào log. Token hết hạn thì cấp token mới rồi retry manifest.

## 8. Lỗi thường gặp và cách xử lý

| Hiện tượng | Kiểm tra / xử lý |
| --- | --- |
| `infralens` không được nhận diện | `uv tool update-shell`, mở terminal mới; kiểm tra đúng môi trường cài. |
| Không có `--upload` trong `scan --help` hoặc `drift --help` | Bạn đang dùng CLI cũ; cài lại wheel/revision tích hợp được cấp. |
| Không tìm thấy Terraform/Trivy | Drift thật cần Terraform trên PATH; Security cần wheel bundle hoặc Trivy 0.76.x. |
| Terraform plan thất bại | Kiểm tra init, workspace, biến đầu vào, credentials và quyền backend/provider; lỗi công cụ không phải kết quả sạch. |
| CloudTrail không chạy | Kiểm tra credentials, region và quyền. Nếu báo SDK bị thiếu, cài lại CLI bằng wheel mới; boto3 được cài tự động. |
| Browser login timeout/callback lỗi | Dùng terminal tương tác; kiểm tra trình duyệt truy cập được `localhost:8765` và cổng chưa bị ứng dụng khác chiếm. |
| Project không tìm thấy hoặc upload bị từ chối | Tạo project trước; dùng đúng Project ID và cùng tài khoản trên CLI/dashboard. |
| Dashboard chưa thấy lượt vừa chạy | Chọn đúng tab Security/Drift, bỏ lọc sai scope/thời gian, Refresh; kiểm tra upload đã hoàn tất. |
| `Report upload is not complete` | Retry upload bằng đúng report/manifest; Refresh trên web không thực hiện upload. |
| `No comparable baseline` | Cần một lượt completed trước cùng project/scope/input mode; không so imported plan với refresh-only. |
| Output có manifest sẵn | Lượt mới chọn output mới; nếu chỉ muốn gửi lại thì dùng `cloud upload`. |
| Báo cáo vượt giới hạn hoặc bị sửa checksum | Giới hạn Security 50 MiB, Drift 2 MiB. Giữ báo cáo local; không chỉnh JSON để ép retry. Chọn phạm vi phù hợp hoặc tạo lượt mới hợp lệ. |
| Security tab trống | Chạy `scan --upload` với đúng project/tài khoản; scan local không tự gửi report. |
| Bảng đang lọc không có kết quả nhưng còn nút tải thêm | Tải trang kế tiếp; trang hiện tại có thể rỗng sau lọc. |

| Exit code CLI | Ý nghĩa |
| --- | --- |
| `0` | Thực thi thành công; không có điều kiện gate thất bại. Vẫn có thể có findings/drift nếu chưa bật gate. |
| `1` | Findings/drift khớp ngưỡng hoặc điều kiện chặn đã chọn. |
| `2` | Sai tham số hoặc đầu vào. |
| `3` | Lỗi công cụ, trace, upload, timeout hoặc ghi/đọc file; cần xem thông báo lỗi. |
| `130` | Người dùng ngắt lệnh. |

Nếu cần hỗ trợ, gửi run ID, Project ID, scope, lệnh đã bỏ thông tin nhạy cảm,
phiên bản CLI và exit code. Báo cáo có thể chứa giá trị hạ tầng/source;
chỉ chia sẻ qua kênh được nhóm cho phép. Không gửi password, token, AWS credentials,
raw state/tfvars hoặc URL download đã ký. Đăng xuất bằng **Sign out** khi dùng xong
trên máy dùng chung.

Chi tiết bổ sung: [CLI README](../README.md),
[Drift tích hợp](DRIFT_INTEGRATION.md), [frontend](../frontend/README.md).

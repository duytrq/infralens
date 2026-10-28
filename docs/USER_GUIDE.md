# Hướng dẫn sử dụng InfraLens

InfraLens hỗ trợ hai công việc: **Security** tìm cấu hình Terraform không an toàn;
**Drift** phát hiện hạ tầng thực tế đã thay đổi so với Terraform state đã lưu.
Bạn chạy kiểm tra bằng CLI trên máy hoặc CI, sau đó xem báo cáo trên dashboard.

Hướng dẫn áp dụng cho bản tích hợp Security/Drift, cập nhật ngày **2026-10-28**.

| Địa chỉ | Mục đích |
| --- | --- |
| [Dashboard](https://ddsw2osqv2rj2.cloudfront.net) | Đăng nhập, tạo project, xem báo cáo. |
| `https://8maelv4bic.execute-api.ap-southeast-1.amazonaws.com` | API dùng trong tham số `--api-url` của CLI. |

## 1. Chuẩn bị và cài CLI

### Bạn cần những gì?

| Bạn muốn làm gì? | Cần chuẩn bị |
| --- | --- |
| Xem báo cáo trên dashboard | Trình duyệt và tài khoản được quản trị viên cấp. |
| Quét Security | InfraLens CLI và Trivy 0.76.x; wheel bundle đã chứa Trivy. |
| Kiểm tra Drift trên hạ tầng thật | InfraLens CLI, Terraform ổn định `>=1.1,<2`, project đã init và quyền truy cập backend/provider. |
| Thử Drift bằng plan JSON có sẵn | InfraLens CLI và bộ ví dụ; không cần Terraform hoặc AWS nếu không bật trace. |
| Tìm sự kiện CloudTrail | Thư viện `boto3`, AWS credentials và quyền tra cứu CloudTrail trong phạm vi cần kiểm tra. |
| Upload Drift | Có mạng, project đã tạo và tài khoản Cognito tương ứng. |

**AWS CLI không bắt buộc.** Với hạ tầng AWS, Terraform và boto3 có thể sử dụng
credentials từ biến môi trường, profile có sẵn hoặc IAM role trên runner.
Nếu nhóm dùng `aws sso login` để đăng nhập thì cần AWS CLI cho bước đăng nhập đó.
Tài khoản dashboard không cấp quyền truy cập AWS cho Terraform.

### Cài từ wheel được cung cấp

Nhận wheel **bản đã tích hợp Drift/upload** từ người phụ trách hệ thống.
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
Mã nguồn cũng phải là revision có tính năng Drift/upload; cài từ nhánh mặc định
không bảo đảm nhận được bản tích hợp này.

Không tìm thấy lệnh sau khi cài? Chạy `uv tool update-shell`, mở terminal mới rồi
thử lại. Nếu nâng cấp bản đã cài, dùng `uv tool install --reinstall <đường-dẫn-wheel-mới>`.

Để bật CloudTrail, bổ sung `boto3` khi cài, ví dụ trên Linux/WSL:

```bash
uv tool install --reinstall --with boto3 ./infralens-0.1.0-py3-none-linux_x86_64.whl
```

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

CLI quét các file Terraform trong cây thư mục, in findings theo mức
`CRITICAL`, `HIGH`, `MEDIUM`, `LOW`, `UNKNOWN`; có rule ID, resource và vị trí nguồn
khi xác định được. Không cần `terraform init` hoặc AWS credentials cho Security.
Scanner có thể cần mạng để tải checks hoặc remote modules.

Để CI trả thất bại khi có finding từ HIGH trở lên:

```bash
infralens scan ./infra --format json --output ./reports/security.json --fail-on HIGH
```

Exit `1` trong trường hợp này nghĩa là findings vượt ngưỡng; báo cáo vẫn được xuất.
`--severity` chỉ lọc nội dung hiển thị, không làm giảm phạm vi đánh giá `--fail-on`.

**Đưa Security lên dashboard:** bản CLI hiện tại chưa có `scan --upload` và
dashboard chưa có nút import báo cáo. Các lệnh trên tạo báo cáo local.
Dashboard Security đọc báo cáo đã được pipeline/client gửi qua API của hệ thống;
nếu nhóm chưa cấu hình bước này, tab sẽ chưa có dữ liệu. Người phụ trách pipeline
có thể tham khảo [API upload](../backend/README.md) và
[dashboard API](../backend/DASHBOARD.md). `cloud upload` hiện chỉ retry Drift,
không dùng để upload file Security vừa xuất.

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
infralens drift ./infra --format json --output ./reports/drift-001.json \
  --upload --project my-app --scope dev-default \
  --api-url https://8maelv4bic.execute-api.ap-southeast-1.amazonaws.com
```

PowerShell có thể dùng cùng lệnh trên một dòng:

```powershell
infralens drift ./infra --format json --output ./reports/drift-001.json --upload --project my-app --scope dev-default --api-url https://8maelv4bic.execute-api.ap-southeast-1.amazonaws.com
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
| `--fail-on-priority high` | Trả exit `1` khi có drift được đánh giá high. |
| `--fail-on-priority medium` | Chặn cả medium và high. |
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

## 6. Upload lỗi: retry mà không chạy lại Terraform

Giữ nguyên cả report và manifest, rồi chạy:

```bash
infralens cloud upload --report ./reports/drift-001.json \
  --manifest ./reports/drift-001.json.upload.json \
  --api-url https://8maelv4bic.execute-api.ap-southeast-1.amazonaws.com
```

Retry dùng lại run ID cũ. Không sửa report, manifest hoặc đổi API URL: checksum
và thông tin lượt được kiểm tra trước khi gửi. Nếu chưa có manifest, không dùng
lệnh retry này; khắc phục lỗi ban đầu và tạo một lượt kiểm tra mới với output mới.

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

Khi runner đã có token, dùng cùng lệnh Drift/upload ở mục 4, thêm gate theo nhu cầu
và tên output duy nhất cho mỗi lần chạy. Không truyền token trong command line
hoặc in token vào log. Token hết hạn thì cấp token mới rồi retry manifest.

## 8. Lỗi thường gặp và cách xử lý

| Hiện tượng | Kiểm tra / xử lý |
| --- | --- |
| `infralens` không được nhận diện | `uv tool update-shell`, mở terminal mới; kiểm tra đúng môi trường cài. |
| Không có `--upload` trong help | Bạn đang dùng CLI cũ; cài lại wheel/revision tích hợp được cấp. |
| Không tìm thấy Terraform/Trivy | Drift thật cần Terraform trên PATH; Security cần wheel bundle hoặc Trivy 0.76.x. |
| Terraform plan thất bại | Kiểm tra init, workspace, biến đầu vào, credentials và quyền backend/provider; lỗi công cụ không phải kết quả sạch. |
| CloudTrail không chạy | Kiểm tra boto3, credentials, region và quyền; nếu chỉ cần drift, bỏ `--trace`. |
| Browser login timeout/callback lỗi | Dùng terminal tương tác; kiểm tra trình duyệt truy cập được `localhost:8765` và cổng chưa bị ứng dụng khác chiếm. |
| Project không tìm thấy hoặc upload bị từ chối | Tạo project trước; dùng đúng Project ID và cùng tài khoản trên CLI/dashboard. |
| Dashboard chưa thấy lượt vừa chạy | Chọn tab Drift, bỏ lọc sai scope/thời gian, Refresh; kiểm tra upload đã hoàn tất. |
| `Report upload is not complete` | Retry upload bằng đúng report/manifest; Refresh trên web không thực hiện upload. |
| `No comparable baseline` | Cần một lượt completed trước cùng project/scope/input mode; không so imported plan với refresh-only. |
| Output có manifest sẵn | Lượt mới chọn output mới; nếu chỉ muốn gửi lại thì dùng `cloud upload`. |
| Báo cáo vượt 2 MiB hoặc bị sửa checksum | Giữ báo cáo local; không chỉnh JSON để ép retry. Phối hợp người phụ trách để chọn phạm vi Terraform phù hợp hoặc tạo lượt mới hợp lệ. |
| Security tab trống | Scan local không tự upload; xác nhận pipeline đã gửi report qua API. |
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

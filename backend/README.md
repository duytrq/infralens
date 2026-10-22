# Backend lưu trữ InfraLens

Backend cung cấp API quản lý project, metadata lần scan, findings và báo cáo JSON trên AWS.
Mỗi tài khoản Cognito có dữ liệu riêng. Dashboard và tích hợp các lệnh `cloud` /
`scan --upload` trong CLI là bước tiếp theo; CLI hiện tại vẫn chỉ scan và xuất local.

## Kiến trúc

```text
CLI -- đăng nhập Code + PKCE --> Cognito
CLI -- access token ----------> HTTP API Gateway --> Lambda --> DynamoDB
CLI -- presigned PUT/GET ------------------------------------> S3 private
DynamoDB Streams -------------> Lambda phân tích JSON --> DynamoDB findings
EventBridge mỗi giờ ----------> Lambda cleanup
```

Deploy tạo một bộ tài nguyên dùng chung cho toàn dịch vụ. Tạo project chỉ ghi một
item DynamoDB, không tạo bucket/table hoặc IAM role mới. Tách stack `dev` và `prod`.
Backend không chạy Trivy và không cần nhận AWS credentials của người dùng.

- `/v1/config` công khai thông tin OAuth cần cho client; không chứa storage config.
- API Gateway kiểm tra chữ ký, issuer, audience/client, expiry và scope của JWT.
  Lambda chỉ tin `requestContext.authorizer.jwt.claims`, kiểm tra access token và
  scope `infralens/api`; `sub` xác định chủ sở hữu. Không đọc owner từ body/header.
- Cognito Lite, public client không secret, OAuth code grant, callback mặc định
  `http://localhost:8765/callback`. Client phải dùng PKCE S256 và kiểm tra state.
- Admin tạo tài khoản; chưa mở đăng ký công khai. Không dùng Cognito Identity Pool.
- Dashboard có public app client riêng trong cùng User Pool và CORS theo
  `DashboardOrigin` (dev mặc định `http://localhost:5173`); xem [DASHBOARD.md](DASHBOARD.md).

Backend là project Python >=3.12 riêng, có `uv.lock` riêng. Dependencies SDK,
JSON validator và streaming parser không được đóng gói vào CLI.

## Chạy kiểm thử và build

Chạy từ **repository root** trên Linux/WSL x64, cần uv và GNU make:

```bash
uv sync --project backend --locked
uv run --project backend ruff check backend
uv run --project backend ruff format --check backend
uv run --project backend pytest -q backend/tests
uv run --project backend python backend/scripts/export_contract.py --check
uv run --project backend cfn-lint infra/template.yaml

uvx --from aws-sam-cli==1.169.0 sam validate --lint \
  --template-file infra/template.yaml --region ap-southeast-1
uvx --from aws-sam-cli==1.169.0 python infra/verify_template.py
uvx --from aws-sam-cli==1.169.0 sam build --template-file infra/template.yaml
uv run --project backend python -S backend/scripts/verify_artifacts.py \
  .aws-sam/build/ApiFunction .aws-sam/build/CleanupFunction
uv build --project backend
```

Tests dùng Moto để tích hợp SDK S3/DynamoDB; không gọi tài khoản AWS thật. Chúng
kiểm tra authorization boundary, schema, retry, phân trang, checksum, JSON và các
interleaving completion/deletion. Moto không chứng minh chữ ký presigned URL,
bucket policy hoặc JWT authorizer hoạt động trên AWS; cần smoke test sau deploy.

Makefile cài runtime dependencies từ `requirements.txt` có hash, rồi copy module
backend vào từng Lambda. `verify_artifacts.py` dùng `python -S` để chạy handler
thật từ artifact mà không mượn dependencies từ môi trường development.

Sau khi cập nhật dependencies hoặc request schema:

```bash
uv lock --project backend
uv export --project backend --locked --no-dev --no-emit-project \
  --no-header --no-annotate --output-file backend/requirements.txt --quiet
uv run --project backend python backend/scripts/export_contract.py
```

Backend CI kiểm tra lock/export/contract, lint, tests, template, build, artifact
runtime và audit cả runtime/dev dependencies. Kiểm tra template render SAM thành
CloudFormation cho dev/prod, xác nhận tất cả route, JWT scopes, event payload và
cấu hình Lambda sau khi merge Globals. Không gọi API AWS trong bước này.
Workflow không tự deploy hoặc dùng
production credentials.

## Deploy một lần cho mỗi môi trường

Người vận hành cần AWS credentials có quyền tạo stack và các tài nguyên trong
template: CloudFormation, IAM, Lambda, API Gateway, Cognito, S3, DynamoDB, Logs và
EventBridge. AWS profile này không được phân phối cho người sử dụng CLI.

Sau khi build và xem xét template:

Tạo stack `infra/artifacts.yaml` theo [hướng dẫn hạ tầng](../infra/README.md)
để có bucket chứa gói Lambda được quản lý và gắn tag. Không dùng `--resolve-s3`
trong quy trình này để tránh tạo thêm stack/bucket phụ ngoài inventory.

```bash
uvx --from aws-sam-cli==1.169.0 sam deploy \
  --template-file .aws-sam/build/template.yaml \
  --stack-name infralens-dev \
  --region ap-southeast-1 \
  --s3-bucket <ArtifactsBucket-output> \
  --s3-prefix infralens-dev \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides Environment=dev ReserveConcurrency=false \
  --tags Project=infralens Environment=dev ManagedBy=cloudformation Deployment=infralens-dev \
  --confirm-changeset

aws cloudformation describe-stacks \
  --stack-name infralens-dev --region ap-southeast-1 \
  --query 'Stacks[0].Outputs'
```

Bucket code artifacts và bucket báo cáo là hai tài nguyên khác nhau, cùng có tag
deployment. Callback phải khớp chính xác giữa cấu hình Cognito và client.
Prefix Cognito domain hỗ trợ một stack cho mỗi Environment trong account/region.

Outputs gồm `ApiEndpoint`, `UserPoolId`, `ClientId`, `AuthDomain`, `ReportsBucket`
và `StorageTable`. Người dùng chỉ cần `ApiEndpoint`; `/v1/config` cung cấp thông tin
công khai còn lại cho đăng nhập. Không ghi token hoặc AWS keys vào config app.

Admin cấp tài khoản bằng Cognito console hoặc `admin-create-user`. Với người dùng
thật, quy trình này có thể gửi email mời; chỉ thực hiện cho người được phép nhận.

## Smoke test trên AWS

Tạo native JSON bằng scanner hiện tại, rồi dùng tài khoản đã được admin cấp:

```bash
uv run infralens scan tests/fixtures/clean \
  --format json --output /tmp/infralens-smoke-report.json

uv run --project backend python backend/scripts/smoke.py \
  --endpoint https://API_ID.execute-api.ap-southeast-1.amazonaws.com \
  --report /tmp/infralens-smoke-report.json
```

Cần Trivy trên PATH hoặc dùng CLI wheel đã bundle. Smoke tool mở trình duyệt,
nhận callback ở loopback, kiểm tra state/PKCE và giữ token trong RAM. Tool không
lưu token hoặc mật khẩu. Nó tạo/reuse project `backend-smoke`, đăng ký run UUID
mới, thử checksum sai, upload đúng, từ chối overwrite, retry/complete, đọc lịch sử,
download đúng byte và yêu cầu xóa run khi kết thúc. Thời gian trong metadata của
smoke run là thời gian kiểm thử ingestion, không phải thời điểm scan ban đầu.

Kiểm tra phân quyền trên AWS với hai tài khoản khác nhau: tạo run ở A, dùng token
B gọi GET/complete/download/DELETE cùng run; tất cả phải trả 404. Request không có
JWT, sai chữ ký/issuer/client, hết hạn hoặc thiếu scope phải bị gateway từ chối.

## Hợp đồng API

[OpenAPI 3.1](../contracts/openapi.json) là artifact được xuất từ runtime schema.
Schema field, enum, giới hạn và response được kiểm tra trong tests.

| Method / path | Hành vi |
| --- | --- |
| `GET /v1/config` | Cấu hình OAuth, format JSON và giới hạn upload; không cần token. |
| `PUT /v1/projects/{project_id}` | Body `{"name":"Tên project"}`; 201 khi tạo, 200 khi retry cùng tên, 409 khi tên khác. |
| `GET /v1/projects` | Liệt kê project của chính mình; `limit`, `cursor`. |
| `GET /v1/projects/{project_id}` | Chi tiết project; không thấy project tài khoản khác. |
| `POST /v1/runs` | Đăng ký immutable metadata/manifest; project phải tồn tại. |
| `POST /v1/runs/{run_id}/complete` | Xác minh S3/JSON rồi publish lịch sử; idempotent. |
| `GET /v1/runs` | Lịch sử ready; `project_id`, `from`, `to`, `limit`, `cursor`. |
| `GET /v1/runs/{run_id}` | Metadata pending/ready; deleting hoặc không thuộc mình trả 404. |
| `GET /v1/runs/{run_id}/artifacts/json` | URL download 5 phút; chỉ cho run ready. |
| `DELETE /v1/runs/{run_id}` | 202 khi còn chờ URL hết hạn; 204 khi xóa xong; 404 nếu không tồn tại. |

Response đăng ký có `run` và `upload` (URL, method, headers, expires_at). Gửi nguyên
headers được trả về, gồm content type/length, SHA-256, checksum algorithm,
`If-None-Match: *` và staging tag. Retry cùng run/metadata cấp URL mới; run ready
trả `upload: null`. Giữ nguyên run UUID v4 và metadata khi retry; thay đổi bất kỳ
metadata nào dưới cùng UUID trả 409. Contention có thể trả 409, client cần retry.

Upload URL tối đa 15 phút và không vượt deadline 7 ngày của session pending.
Nếu PUT retry trả 412 vì file đã tồn tại, gọi complete để xác minh file đã upload.
Client không được tự tạo object key; key chứa generation riêng do server tạo để
request xóa/complete cũ không ảnh hưởng run mới nếu UUID được dùng lại sau xóa.

List endpoints dùng cursor opaque, scope theo tài khoản và bộ lọc. `from`/`to`
inclusive theo thời điểm bắt đầu scan; kết quả mới nhất trước, limit 1-100 (mặc
định 20). GSI eventual consistency có thể khiến run vừa complete xuất hiện chậm.
Trang có thể rỗng nhưng vẫn có `next_cursor` khi index đang phản ánh việc xóa;
client phải tiếp tục nếu cursor chưa null. GET trực tiếp dùng strong read.

Lỗi Lambda có dạng `{"error":{"code":"...","message":"..."}}`.
Gateway có thể trả `{"message":"Unauthorized"}` hoặc message throttling trước
khi Lambda được gọi. Không trả stack trace, raw diagnostics hoặc thông tin AWS.

## Metadata và giới hạn

- Định danh: schema version 1, run UUID, project ID và `run_type=security_scan`.
- Thời gian: started/finished có timezone và tối đa 6 chữ số thập phân; duration
  là số nguyên ms. Server chuẩn hóa UTC và tự ghi received/uploaded timestamp.
- Source: đường dẫn tương đối, optional Git commit/branch/dirty. Không có remote
  URL, đường dẫn tuyệt đối, hostname hoặc email trong scan metadata.
- Tool: Infralens version, Trivy version, optional checks version xác định được.
- Options: fail_on, severity filter local, hash ignore file hoặc null.
- Result: trạng thái completed, threshold passed/failed/not_evaluated, tổng và
  counts theo cả năm severity, danh sách mã warning. Counts dùng toàn bộ findings
  không bị suppression; không bị bộ lọc hiển thị cắt bớt.
- Artifact: native schema-2 JSON, số byte và SHA-256 lowercase hex. Chưa nhận SARIF.
- Tối đa 64 KiB metadata và 50 MiB JSON; chưa hỗ trợ multipart. JSON envelope được
  streaming-validate, giới hạn depth 64, key 4096 ký tự và 128 root fields.

Backend kiểm tra cú pháp/native envelope và tính nhất quán nội bộ metadata, không
chứng thực Trivy đã chạy hay independently tính lại findings. JSON có thể chứa
source snippets; chỉ upload khi người dùng yêu cầu. Scan errors không có kết quả
hợp lệ chưa được ghi thành run. CLI `--format sarif` vẫn chỉ điều khiển local export.

## Trạng thái, dọn dẹp và vận hành

```text
pending -- verify HEAD + streamed JSON + retain tag --> ready
pending / ready -- conditional claim --> deleting -- S3 delete --> removed
```

DynamoDB dùng PK theo Cognito sub; hai sparse index phục vụ history theo user /
project. Index thứ ba chỉ chứa pending/deleting để cleanup không scan toàn bảng.
Revision và generation bảo vệ cập nhật cạnh tranh, kể cả sau khi tái dùng UUID.
Không cấu hình TTL cho ready runs.

Cleanup mỗi giờ xử lý tối đa 100 pending và 100 deleting đến hạn. Lỗi dependency
giữ lại công việc trong index và làm Lambda invocation thất bại để có metric/retry.
Khi delete, run bị ẩn ngay; tombstone giữ đến khi URL upload đã hết hạn cộng một
phút, rồi worker xóa file lần nữa trước khi xóa metadata. Thời điểm `delete_after`
là sớm nhất có thể dọn, không phải cam kết worker chạy đúng giây đó.

S3 staging tag `state=pending` tự hết hạn sau 7 ngày để dọn cả upload bắt đầu trước
URL hết hạn nhưng kết thúc muộn. S3 lifecycle thực hiện bất đồng bộ. Ready objects
có tag `state=ready` và không có lịch xóa tự động. Không bật bucket versioning.

S3 private, mã hóa SSE-S3, bucket owner enforced, TLS-only và từ chối PUT ghi đè /
thiếu staging tag. API role có ListBucket để HEAD file chưa tồn tại trả 404 thay
vì 403; role không được cấp cho người dùng. Cleanup role chỉ đọc/cập nhật record,
query cleanup index và xóa object; không được đọc nội dung báo cáo.

Lambda on-demand không gắn VPC, không NAT Gateway hay provisioned concurrency.
HTTP API throttle 10 request/s, burst 20. Mặc định Lambda dùng concurrency chung
của AWS account để hỗ trợ account mới có quota 10. `ReserveConcurrency=true`
đặt API reserved concurrency 10 và cleanup 1; chỉ bật khi quota account đủ cho cả
11 reservation và phần unreserved tối thiểu mà AWS yêu cầu. Đây là giới hạn tải
chung, không phải hạn mức chi phí cho mỗi tài khoản.
Log giữ 14 ngày, không log event/body/token/URL. Theo dõi API Gateway 5xx/429,
Lambda Errors/Duration/Throttles và log `cleanup_result` / `cleanup_dependency_error`.

Đề xuất AWS Budget 5 USD/tháng cho thử nghiệm; cảnh báo không phải hard spending
cap. Chi phí tăng theo dữ liệu giữ lại, downloads và người dùng Cognito. Email/SMS
có biểu phí riêng; template chỉ bật optional TOTP và không tạo thông báo email.

Rollback code bằng cách build/deploy phiên bản backend trước vào cùng stack.
Thay đổi schema cần tương thích trước khi rollout client. Không xóa stack để rollback:
S3, DynamoDB và Cognito có Retain/UpdateReplacePolicy và deletion protection thích
hợp. Dữ liệu được giữ lại khi xóa stack vẫn có thể phát sinh phí và cần admin quản
lý riêng; không có lệnh tự động xóa tài nguyên production.

## Nguồn thiết kế

- [AWS JWT authorizers](https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-jwt-authorizer.html)
- [Cognito authorization code/PKCE](https://docs.aws.amazon.com/cognito/latest/developerguide/authorization-endpoint.html)
- [S3 conditional writes](https://docs.aws.amazon.com/AmazonS3/latest/userguide/conditional-writes.html)
- [S3 PutObject checksums and headers](https://docs.aws.amazon.com/AmazonS3/latest/API/API_PutObject.html)
- [DynamoDB/S3 consistency boundaries](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/bp-use-s3-too.html)

## Dashboard backend

Projects with latest scan, paginated findings, background indexing, retry,
separate browser login and CORS are documented in [DASHBOARD.md](DASHBOARD.md).
The CLI cloud integration and dashboard frontend remain separate deliverables.

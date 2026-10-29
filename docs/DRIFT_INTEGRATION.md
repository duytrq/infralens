# Drift trong InfraLens

## Kiến trúc

Engine từ drift_develop (snapshot 4213a2d) chạy tại CLI/CI. Backend dùng Lambda,
API Gateway, Cognito, S3 và DynamoDB; dashboard dùng React/TypeScript hiện có.
FastAPI, SQLite, worker thực thi Terraform và frontend JavaScript của bản local
không phải dependency của hệ thống này. Không chuyển dữ liệu SQLite cũ.

## Chạy local

```bash
uv sync --locked
uv run infralens drift ./infra --format json --output ./reports/drift.json
uv run infralens drift ./infra --trace --lookback-days 7
uv run infralens drift ./examples/drift-review \
  --plan-json ./examples/drift-review/plan.json \
  --fail-on HIGH --fail-on-unknown --format json
```

Chạy từ repo hạ tầng cần quét, dùng CLI đã cài hoặc đường dẫn tuyệt đối phù hợp.
Terraform ổn định >=1.1,<2, checkout đã init, workspace và credentials của
backend/provider do người dùng chuẩn bị. Terraform không được bundle cùng Trivy.
`boto3` được cài tự động cùng CLI; không cần extra hoặc cài SDK riêng để dùng
CloudTrail. CLI không nhận credentials từ dashboard.

Refresh-only so sánh state đã lưu với hạ tầng provider quan sát được. Chỉ sửa code
chưa apply không phải drift. Không tự init/apply/destroy hoặc ghi lại state.
Plan JSON được import chỉ phản ánh phần resource_drift trong file; freshness,
workspace và coverage không được chứng thực.

Giữ nguyên sensitive/unknown/absent; known-null khác absent. Chỉ che giá trị được
Terraform đánh dấu sensitive. Collection được báo nguyên thuộc tính vì JSON không
giữ đủ thông tin phân biệt list/set. Network context là dữ liệu allowlist đã che
sensitive, có thể gồm field không đổi để giúp review.

CloudTrail chỉ trả sự kiện ứng viên cho EC2/Security Group trong phạm vi hỗ trợ;
không khẳng định actor là người gây drift. Thiếu quyền hoặc lỗi SDK giữ báo cáo
drift, đánh dấu trace lỗi và trả exit 3. Partial coverage không có lỗi thực thi
không tự biến thành thất bại engine.

## Gate và exit

- `--fail-on-drift`: chặn mọi managed resource drift.
- `--fail-on HIGH`: chặn high; `MEDIUM`: chặn medium và high.
- `--fail-on-unknown`: chặn unknown hoặc assessment chưa nhận diện được.
- Các tiêu chí kết hợp bằng OR, không lọc bớt resource trong report.
- Exit 0: gate không khớp hoặc không bật; 1: gate khớp; 2: input sai;
  3: lỗi công cụ/trace/upload/I/O; 130: ngắt lệnh. Lỗi thực thi ưu tiên hơn gate.

Priority thuộc policy builtin-review-v2, là heuristic hỗ trợ review. Gate passed
không chứng nhận hạ tầng sạch hoặc bao phủ đầy đủ.
`--fail-on` không phân biệt hoa/thường, cùng cách truyền ngưỡng với Security.
`--fail-on-priority` vẫn được nhận như alias để tương thích lệnh cũ.

## Upload và đăng nhập

Cấu hình API một lần, tạo hoặc chọn project ngay trong CLI:

```bash
infralens cloud configure --api-url https://8maelv4bic.execute-api.ap-southeast-1.amazonaws.com
infralens cloud project create my-project --name "My project"
# Hoặc chọn project đã có:
infralens cloud project list
infralens cloud project use my-project

infralens drift ./infra --format json --output ./reports/drift.json \
  --upload --scope dev-default
```

Upload cần JSON output, project, scope và HTTPS API origin. API/project được lấy
từ flag > `INFRALENS_API_URL`/`INFRALENS_PROJECT` > cấu hình đã lưu. Project đã
chọn gắn với API đã lưu. `scope` là ID ổn định do nhóm đặt cho một
account/workspace/environment; thay scope khi đổi phạm vi. Đây là khai báo của
client, không phải xác nhận tài khoản AWS từ server.

CLI tạo JSON local đã chuyển source location thành đường dẫn tương đối với
Terraform root. Source nằm ngoài root được đánh dấu unavailable. Không upload
raw plan/state/tfvars, raw CloudTrail event, profile hay credentials. Giá trị tài
nguyên không đánh dấu sensitive vẫn có thể chứa thông tin riêng tư.

Metadata UUID/timestamps/checksum chỉ giữ trong RAM; checksum tính trên đúng byte
file đã ghi, kể cả newline Windows. Không tạo `.upload.json` và không có lệnh
`cloud upload`. Mỗi HTTP request chỉ thử một lần. Upload lỗi thông báo nguyên
nhân và đường dẫn report còn giữ, trả `3`. Nếu chưa xác nhận được kết quả, kiểm
tra dashboard trước khi chạy lại vì lệnh mới tạo run mới. Gate fail vẫn upload
rồi trả `1`; lỗi trace còn report vẫn upload rồi trả `3`. Report vượt 2 MiB vẫn
được xuất local, nhưng không upload.

Quét local không cần tài khoản InfraLens. Thao tác project và upload cần Cognito:
CLI tương tác mở browser qua Code + PKCE S256, kiểm tra state và dùng callback
localhost đã đăng ký. Token chỉ trong RAM của một lệnh; lệnh cloud khác có thể
mở browser lại. Cấu hình chỉ lưu API URL và project, không lưu token.

CI/noninteractive cung cấp `INFRALENS_ACCESS_TOKEN` bằng secret environment của
pipeline. Token phải còn hạn và có scope infralens/api cho cùng User Pool/client.
Không truyền token bằng command line, không commit token; v1 chưa có machine
identity. Credentials Terraform/AWS ở runner độc lập với Cognito dùng cloud.

## Contract và vòng đời

- POST `/v1/runs`: nhận security_scan hoặc drift. Drift giữ report schema "1.0"
  và kind drift; envelope metadata schema_version vẫn là số 1.
- Complete/download/delete dùng endpoint hiện có. Metadata tối đa 64 KiB;
  security JSON giữ giới hạn 50 MiB, drift JSON tối đa 2 MiB.
- Complete kiểm tra schema, đường dẫn, tính nhất quán summary/priority/gate và
  tính lại số liệu từ report trước khi publish. Không chứng thực Terraform/AWS.
- GET `/v1/runs?run_type=drift`: history với project_id, from/to, scope,
  gate_status, limit và cursor. Mặc định không truyền run_type vẫn là security.
- Projects có include=latest_scan,latest_drift. latest_scan chỉ dành cho security.
- GET `/v1/runs/{id}/drift/report`: report ready, có kiểm tra ownership.
- GET `/v1/runs/{id}/drift/comparison`: baseline tự chọn hoặc baseline_id,
  hỗ trợ limit/cursor. Dùng baseline_run_id của trang đầu khi lấy trang tiếp.

Drift bỏ qua Trivy indexing/retry/backfill. Metadata ở DynamoDB, toàn bộ report
ở S3; không thêm bảng. Ready/pending/deleting, generation, conditional PUT,
cleanup và phân quyền Cognito sub theo đúng storage hiện có.

Comparison chỉ nhận cùng owner/project/scope/input mode. Baseline mặc định là
lần completed trước theo started_at/run_id; gate failed vẫn hợp lệ, trace execution
error không làm baseline. Sensitive/unknown hoặc network context thiếu tạo kết
quả indeterminate khi không thể chứng minh bằng nhau. no_longer_reported không
chứng minh đã sửa. Comparison không sao chép values, source hoặc actor.

History có thể có trang rỗng và next_cursor do lọc hoặc eventual consistency;
tiếp tục phân trang. Budget lookup hết trả lỗi retryable, không giả là thiếu dữ liệu.

## Kiểm chứng và rollout

Dev đã deploy cả backend và frontend ngày 2026-10-27. Mở
[dashboard](https://ddsw2osqv2rj2.cloudfront.net), đăng nhập, chọn project rồi chọn
tab **Security** hoặc **Drift**. Tab Drift hiển thị báo cáo đã upload bằng CLI/CI.
Release hiện tại: `20261027T100344Z-d9e3b434ac36`; kiểm tra trực tiếp Cognito/API/S3
và cả hai luồng trên CloudFront đã pass.

```bash
uv run --locked pytest -q
uv run --locked pytest -q tests/integration/test_terraform_integration.py \
  --run-terraform --run-network
uv run --project backend --locked pytest -q backend/tests
uv run --project backend --locked python backend/scripts/export_contract.py --check
```

Frontend dùng generate:check, lint, typecheck, Vitest, Playwright và build như
README frontend. Test browser bao gồm 320/768/1024/1440px, safe text, bàn phím,
pending/partial/error, filters, download/delete và comparison pagination.

Deploy backend trước, rồi frontend, cuối cùng phân phối CLI. Dùng quy trình SAM
và frontend publish/rollback hiện có. Smoke dev: tạo project, upload imported
fixture offline, xem/download/compare trên web; sau đó chạy refresh-only với
checkout Terraform tin cậy và kiểm tra ownership bằng tài khoản thứ hai.

Không cần migration security. Rollback frontend/CLI độc lập; backend phải giữ bản
vẫn đọc/download/delete được drift đã lưu. Không xóa stack để rollback. Theo dõi
API 5xx/429, Lambda errors/duration và api_response; không log report/token.

Bằng chứng thực thi: [drift-integration-verification.md](../tasks/drift-integration-verification.md).

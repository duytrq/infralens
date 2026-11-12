# Triển khai và theo dõi tài nguyên InfraLens

Hai stack dùng chung bộ tag:

| Tag | Dev |
| --- | --- |
| Project | infralens |
| Environment | dev |
| ManagedBy | cloudformation |
| Deployment | infralens-dev |

`infralens-dev` chứa backend. `infralens-dev-artifacts` chỉ chứa bucket gói deploy
và bucket policy. Không tạo bucket/table theo từng project hoặc người dùng.

Dev đã deploy vào account `695650811791`, region `ap-southeast-1` ngày 2026-10-21.
API endpoint: `https://8maelv4bic.execute-api.ap-southeast-1.amazonaws.com`.
Inventory: [infralens-dev.json](deployments/infralens-dev.json).
Kết quả kiểm thử AWS: [infralens-dev-verification.json](deployments/infralens-dev-verification.json).

## Deploy

Kiểm tra account bằng `aws sts get-caller-identity` trước khi thực hiện. Ví dụ
dùng profile `default`, region Singapore; mọi lệnh phải dùng cùng profile/region.

```bash
aws cloudformation deploy --profile default --region ap-southeast-1 \
  --template-file infra/artifacts.yaml --stack-name infralens-dev-artifacts \
  --parameter-overrides Environment=dev Deployment=infralens-dev \
  --tags Project=infralens Environment=dev ManagedBy=cloudformation Deployment=infralens-dev

aws cloudformation describe-stacks --profile default --region ap-southeast-1 \
  --stack-name infralens-dev-artifacts --query 'Stacks[0].Outputs'
```

Dùng output `ArtifactsBucket` cho `sam deploy --s3-bucket` như hướng dẫn trong
[backend README](../backend/README.md). Không dùng SAM `--resolve-s3`: bucket phụ
tự tạo sẽ khó kiểm kê cùng deployment. Mặc định không reserve Lambda concurrency;
account mới có quota 10 không đáp ứng được cấu hình reserve 11 executions.

## Kiểm kê và kiểm tra tag

Chạy sau deploy và trước khi xóa stack. Script chỉ gọi API đọc; kiểm tra từng loại
tài nguyên thay vì phụ thuộc vào Resource Groups Tagging API vốn không bao phủ
tất cả tài nguyên. File không chứa credential/token, có thể giữ cùng hồ sơ vận hành.

```bash
uv run --project backend python infra/inventory.py \
  --profile default --account <AWS-account-id> --region ap-southeast-1 \
  --stack infralens-dev infralens-dev-artifacts \
  --output infra/deployments/infralens-dev.json
```

SAM truyền tag của Lambda xuống IAM role; API có tag trên cả API và stage. Bucket,
DynamoDB, Cognito pool, log group và EventBridge rule có tag tường minh trong
template. `verify_template.py` kiểm tra template sau SAM transform; `inventory.py`
kiểm tra tag thực tế trên AWS và trả lỗi nếu thiếu. Các resource con không hỗ trợ
tag (permission, bucket policy, Cognito client/domain/resource server) được ghi
đầy đủ physical ID và quan hệ dọn dẹp trong inventory.

Tag chỉ giúp tìm tài nguyên, không tự xóa tài nguyên. Có thể tra tag
`Deployment=infralens-dev` trên AWS; luôn đối chiếu thêm inventory và CloudFormation.

## Xóa sạch môi trường sau này

Đây là hướng dẫn thao tác có chủ đích; deploy không tự thực hiện các bước xóa.

1. Dừng client upload, xuất inventory mới và sao lưu báo cáo nếu cần.
2. Xóa stack backend `infralens-dev`, chờ `stack-delete-complete`. CloudFormation
   xóa API, Lambda, IAM role, schedule, log group và resource con của Cognito.
3. **S3 reports, DynamoDB và Cognito pool được Retain**. Lấy physical ID từ
   inventory trước khi xóa stack; chúng vẫn tồn tại và có thể phát sinh phí.
4. Xóa toàn bộ object trong đúng reports bucket rồi xóa bucket. Bucket không bật
   versioning; kiểm tra cả incomplete multipart uploads nếu từng upload thủ công.
5. Tắt deletion protection của đúng DynamoDB table rồi xóa table, chờ hoàn tất.
6. Kiểm tra Cognito domain đã bị xóa theo stack; nếu còn thì xóa domain trước.
   Tắt deletion protection của đúng user pool rồi xóa pool.
7. Xóa stack `infralens-dev-artifacts`, chờ hoàn tất. Artifacts bucket cũng Retain:
   xóa các gói deploy và template trong bucket rồi xóa bucket.
8. Đối chiếu tất cả physical ID trong inventory, kiểm tra lại tag và IAM role
   (IAM là tài nguyên toàn cục). Không coi việc xóa stack là đã xóa hết tài nguyên.

Không tự động quét/xóa toàn bộ account theo tag. Luôn xác nhận account và đối chiếu
physical ID để tránh đụng đến tài nguyên của hệ thống khác.

## Dashboard resources

The backend also owns a retained/deletion-protected `FindingsTable`, a tagged
analysis Lambda/log group/stream mapping and a
separate Cognito dashboard client. Add `FindingsTable` to the explicit retained
table cleanup above. Set `DashboardOrigin` to the exact HTTPS frontend origin
when publishing; dev uses `https://ddsw2osqv2rj2.cloudfront.net` with
`EnableLocalDashboard=true` to retain localhost login. See
[dashboard API and recovery](../backend/DASHBOARD.md).

The React dashboard and S3/CloudFront deployment workflow are documented in
[frontend operations](FRONTEND.md). The dev backend now includes the dashboard
allowed-origins contract. The published dashboard is available at
[the dev CloudFront URL](https://ddsw2osqv2rj2.cloudfront.net). The earlier account
verification block was resolved, and the failed stack/empty retained bucket were
removed before successful redeployment. See
[frontend verification](../tasks/frontend-verification.md).

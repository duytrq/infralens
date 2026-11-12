# Kiểm tra hệ thống và cloud — 2026-11-05

Mốc mã nguồn: `1f2c89a`. Đối chiếu README, docs/USER_GUIDE.md, kế hoạch và mã hiện tại; các kế hoạch OAuth CLI/retry upload cũ đã được thay thế theo tasks/todo.md. Kiểm tra AWS chỉ đọc, account `695650811791`, region `ap-southeast-1`, cùng S3/CloudFront toàn cục. Không deploy, sửa dữ liệu hoặc xóa tài nguyên.

## Kết luận

Các khối chức năng chính có trong mã nguồn và các suite kiểm thử đều đạt. Tuy nhiên bản dashboard đang publish chưa có API-key UI, làm đứt luồng onboarding CLI theo tài liệu hiện tại. Hệ thống phù hợp mức dev/demo sau khi đồng bộ frontend; chưa nên coi là hoàn chỉnh cho vận hành lâu dài.

| Chức năng đã nêu | Kết quả đối chiếu |
| --- | --- |
| Security/Trivy, JSON/SARIF, severity, gate, source excerpt | Có implementation và regression tests; lần này không chạy scanner thật |
| Drift refresh-only/import, priority, gate, CloudTrail trace | Có implementation và regression tests; lần này không gọi refresh Terraform/CloudTrail thật |
| CLI config theo repo, project, API-key login/logout, upload | Có implementation và tests; AWS có routes tương ứng |
| Dashboard Cognito, projects/history/findings/download/delete/retry | Có implementation; CloudFront/API config hoạt động; chưa đăng nhập AWS end-to-end mới |
| Drift report/resource/comparison | Có implementation; deployed bundle có comparison |
| Tạo/liệt kê/thu hồi API key trên dashboard | Có trong source, **thiếu trong bundle CloudFront đang phục vụ** |
| Indexing bất đồng bộ và cleanup | Worker/stream đang enabled; cleanup có 168 invocation trong 7 ngày |
| Đóng gói Linux/Windows/Docker | Có workflow; không rebuild wheel/Docker hoặc kiểm tra Windows trong lần audit này |

## Phát hiện cần xử lý

### P1 — Frontend đã publish thiếu API-key UI

CloudFront `/` trả 200 và trỏ tới `/assets/index-DBp6smHl.js`; Last-Modified của HTML là `2026-10-27 10:03:46 UTC`. Đã tải chính bundle này từ bucket frontend: không có `/api-keys`, `/v1/api-keys` hoặc `API keys`. Source hiện tại có route và menu này tại `frontend/src/App.tsx` và `frontend/src/components/Shell.tsx`.

Backend đã cập nhật 03/11, chỉ còn Dashboard Cognito client; endpoint `/v1/config` trả 404 đúng như migration. CLI yêu cầu key do dashboard cấp. Người dùng mới trên website publish vì vậy không thể hoàn tất hướng dẫn tạo key rồi `cloud login`. Cần build/release frontend theo cấu hình deploy và kiểm thử tạo key → CLI login/upload → revoke trên đúng CloudFront origin.

### P1 — Khóa/xóa Cognito user chưa tự vô hiệu API key

`backend/src/infralens_backend/api_keys.py:114` chỉ xác minh bản ghi DynamoDB, hash, định dạng owner và expiry. `handler.py:64` dùng kết quả này trực tiếp. Không có kiểm tra trạng thái user hoặc owner bị khóa. Do đó nếu admin chỉ disable/delete user trên Cognito mà không xóa key riêng, key còn hạn vẫn được chấp nhận. Key không hết hạn cũng được hỗ trợ.

Đây là đường thực thi xác định từ mã, không phải sự cố đã quan sát: kiểm kê hiện tại có 2 key và **0 key thuộc user không còn active**. Cần một quy trình offboarding thu hồi tất cả key hoặc trạng thái owner được authorizer kiểm tra. Không cần gọi Cognito trên mọi request nếu dùng trạng thái owner nhất quán trong DynamoDB.

### P2 — Chưa có cảnh báo vận hành trên cloud

`describe_alarms` tại Singapore trả danh sách metric/composite/log alarms rỗng. Trong 7 ngày, cả bốn Lambda đều không ghi nhận Errors/Throttles; đây là lịch sử tốt, nhưng không có cảnh báo khi indexing/cleanup/API lỗi sau này. Cần alarm cho lỗi/throttle và độ trễ xử lý, kèm đầu nhận thông báo.

### P2 — Chưa bật khả năng phục hồi dữ liệu theo thời điểm

Cả StorageTable và FindingsTable đều có `PointInTimeRecoveryStatus=DISABLED`; bucket reports không bật versioning. Retain/deletion protection không khôi phục item/object bị xóa hoặc sửa nhầm. Chưa kiểm kê backup thủ công/AWS Backup nên không kết luận tuyệt đối là không có bản sao lưu nào. Ưu tiên chính sách phục hồi metadata và report gốc; findings có thể dựng lại. [AWS backup/restore](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Backup-and-Restore.html).

### P2 — CI chưa kiểm tra artifact của API-key authorizer

`.github/workflows/backend.yml:41` chỉ truyền ApiFunction, CleanupFunction, AnalysisFunction vào verify_artifacts.py, thiếu ApiKeyAuthorizerFunction. Hơn nữa script hiện gọi `api_handler` cho mọi artifact, chưa thực thi từng entrypoint cleanup/analysis/authorizer. Đây là khoảng trống kiểm chứng đóng gói, không phải bằng chứng authorizer hiện hỏng. Nên bổ sung artifact và kiểm tra đúng entrypoint.

## Phần chưa hợp lý hoặc nên tinh gọn

- Project chỉ tạo/đọc; đổi tên cùng ID bị 409, chưa có archive/delete project. Đây là thiếu tiện ích vòng đời sử dụng, không phải vi phạm chức năng CRUD đầy đủ đã hứa. Có thể ưu tiên rename/archive sau các lỗi trên.
- Chọn baseline Drift thủ công yêu cầu UUID; nên dùng danh sách các run tương thích để người dùng không phải chép ID.
- Cleanup analysis giữ job của mọi ready run và duyệt lại theo giờ, giới hạn 100 job/invocation (`analysis.py:305`). Chi phí và thời gian quét tăng cùng lịch sử giữ vĩnh viễn; hiện chỉ có 3 job nên chưa là vấn đề tải thực tế.
- Artifacts bucket có 41 object, 433,155,897 byte (~413 MiB), lifecycle chỉ abort multipart; chưa có chính sách dọn gói deploy cũ. Cần giữ các release dùng để rollback rồi mới dọn phần còn lại, không xóa toàn bộ.
- `aws/README.md`, `aws/install`, `aws/THIRD_PARTY_LICENSES` được track nhưng không có executable bundle trong thư mục. Đây là phần bộ cài AWS CLI còn sót, không phải chức năng InfraLens; nên chuyển việc cài AWS CLI sang hướng dẫn vận hành.
- Tài liệu có chỗ lỗi thời: infra/README.md mở đầu nói hai stack nhưng thực tế có ba; backend/DASHBOARD.md vẫn gọi các màn hình đã có là “planned”. Checklist lịch sử không nên dùng làm bằng chứng release hiện tại.

## Kiểm kê AWS thực tế

- `infralens-dev`: UPDATE_COMPLETE; `infralens-dev-artifacts` và `infralens-dev-frontend`: CREATE_COMPLETE.
- Inventory ghi 67 stack-resource entries; xác minh đủ tag trên cả 23 resource hỗ trợ kiểm tra tag bằng tool inventory.
- 4 Lambda; 2 DynamoDB; 3 S3 bucket thuộc InfraLens; frontend CloudFront; 32 API routes sau khi đọc hết phân trang; chỉ một Cognito dashboard client. Không có SQS cũ ở region được kiểm tra.
- Cả ba bucket InfraLens bật đủ bốn cờ Block Public Access. Analysis stream mapping Enabled, LastProcessingResult OK.
- Lambda 7 ngày: API 307 invocation, authorizer 17, analysis 5, cleanup 168; tất cả Errors=0, Throttles=0. Không suy ra toàn bộ request nghiệp vụ đều thành công từ Lambda Errors.
- DynamoDB metadata có 4 project, 3 run, 3 analysis job và 2 cặp bản ghi API key. Không có USER row hoặc API-key owner nằm ngoài tập Cognito user đang enabled tại thời điểm đọc.
- Reports bucket: 3 object/139,368 byte. Frontend: 6 object/885,352 byte. Không có dấu hiệu rác report mồ côi từ các tổng số này, nhưng chưa đối chiếu từng object với run.
- Budget hiện có là budget toàn account 30 USD/tháng; không phải budget InfraLens 5 USD được gợi ý trong tài liệu. Không đánh giá chi phí riêng InfraLens từ budget chung.
- Ngoài InfraLens: bucket `private-devops-26626`; hai EC2 `openstack-lab3` đã stopped, kèm hai EBS gp3 30 GiB. Không có NAT Gateway hoặc Elastic IP tại Singapore. Đây là tài nguyên dự án khác, chưa đủ căn cứ gọi là rác. EBS vẫn có thể phát sinh phí khi EC2 dừng theo [AWS EC2 lifecycle](https://docs.aws.amazon.com/us_en/AWSEC2/latest/UserGuide/ec2-instance-lifecycle.html).

## Kiểm chứng và giới hạn

- CLI: 750 passed, 2 skipped, 17 deselected (các integration gate hiện có).
- Backend: 165 passed. Frontend unit: 15 passed.
- Playwright Chromium: 37 passed, gồm API-key create/show-once/revoke, auth, Security/Drift, pagination và accessibility. Chạy frontend cục bộ với API fixtures, không phải phiên đăng nhập/upload AWS thật. Lần chạy trong sandbox không khởi động được web server; chạy lại ngoài sandbox thành công.
- Frontend production build, ESLint, Ruff, OpenAPI export check, generated TypeScript check và cfn-lint ba template: đạt.
- Read-only HTTP: dashboard và dashboard-config 200; route cũ 404; projects và CLI projects không credential trả 401.
- Không thực hiện deploy, upload report mới, tạo user/key thật hoặc thử vô hiệu user thật. Chưa chạy drift detection của CloudFormation, kiểm kê toàn bộ region/service, hay đo tải.
- Bằng chứng thô cục bộ: `/tmp/infralens-cloud-audit.json`, `/tmp/infralens-cloud-extra.json`, `/tmp/infralens-inventory-audit.json`, `/tmp/infralens-deployed-frontend.js`. Không commit dữ liệu kiểm kê account thô.

Thứ tự xử lý đề xuất: đồng bộ frontend → offboarding/key revocation → alarm/backup → CI artifact → quản lý project và dọn artifacts có giữ rollback.

## Cập nhật sau audit: frontend đã deploy ngày 05/11

Đã xử lý phát hiện frontend cũ bằng release `20261105T144138Z-1f2c89a34d75`;
CloudFront phục vụ bundle mới có API-key UI, checksum khớp manifest release.
Trong kiểm tra sau deploy phát hiện thêm rewrite `/api-keys` chưa có; đã bổ sung
rewrite và regression test cho `/api-keys`, `/api-keys/`, đồng thời giữ nguyên
403/404 cho đường dẫn không hợp lệ. Cập nhật qua stack frontend.

Live browser smoke đạt 18 check trên CloudFront và localhost với Cognito/API/S3
thật; tài khoản tạm được xóa. Kiểm tra tùy chọn bằng CLI cài trên máy không qua
bước login API key, nên chưa xác nhận lại luồng CLI live trong lần deploy này.
Luồng API-key UI tạo/hiển thị một lần/thu hồi đã đạt Chromium E2E bằng fixtures;
bundle và đường dẫn CloudFront đã được xác minh riêng.

Publish chạy frozen install, generated-contract check, lint/typecheck, 15 unit
test, 37 Chromium E2E, audit và build. Audit không có high/critical; còn 7 moderate
trong chuỗi dev dependency minimatch/typescript-eslint. Không thay đổi lockfile.
Release cũ `20261027T100344Z-d9e3b434ac36` được lưu để rollback.

Bằng chứng mới:
- `infra/deployments/infralens-dev-frontend-api-key-release-verification.json`
- `infra/deployments/infralens-dev-frontend-api-key-browser-verification.json`

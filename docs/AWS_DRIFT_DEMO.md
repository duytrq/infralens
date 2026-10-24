# Demo drift trên AWS

Chương trình này tạo tài nguyên thật, cố ý thay đổi/xóa tài nguyên sandbox,
gọi InfraLens để kiểm tra, rồi dọn sandbox. Đây là chương trình demo riêng;
lệnh `infralens drift` vẫn chỉ tạo plan để đọc kết quả, không apply hạ tầng.

## Trạng thái ngày 22/10/2026

Đã chạy **6/6 tình huống thành công trên AWS thật** tại `ap-southeast-2`, với
Terraform 1.16.5, AWS provider 6.70.0 và profile cục bộ `infralens-sandbox`.
Lần chạy đạt: `8b769c0a794c`. Cả sáu lần kiểm tra giữ nguyên SHA-256 và mtime
của state. Sandbox đã destroy; state rỗng và truy vấn AWS theo tag không còn
VPC, subnet, SG, EBS hoặc instance còn hoạt động của lần chạy.

Bằng chứng cục bộ: `reports/aws-drift/8b769c0a794c/summary.json` cùng sáu báo cáo
JSON. Xem [biên bản kiểm chứng](verification/AWS_DRIFT_2026-10-22.md).
Các lần thử trước gặp khác biệt tag `null` → `{}` của provider và cũng đã cleanup.
Engine hiện chuẩn hóa riêng trường hợp bản đồ tag rỗng này, ghi rõ trong trường
`normalizations`, đồng thời giữ việc phát hiện thay đổi tag thật.

## Tài nguyên của mỗi lần chạy

- Một VPC riêng và một subnet riêng, không dùng default VPC hoặc VPC lab có sẵn.
- Một Security Group, ban đầu không có ingress/egress.
- Một EC2 `t3.micro`, dùng Amazon Linux 2023 x86_64, EBS gp3 8 GiB mã hóa.
- Không public IP, Internet Gateway, NAT Gateway, key pair hoặc IAM instance role.
- IMDSv2 bắt buộc; T3 dùng standard CPU credits.
- Tag `Project=InfraLens`, `Purpose=DriftSandbox` và `RunId` riêng cho lần chạy.

Chương trình cố định workspace `default` và TF_DATA_DIR bên trong thư mục của
lần chạy, không kế thừa workspace/backend metadata của dự án khác trong shell.

Có chi phí EC2/EBS trong thời gian tài nguyên tồn tại. Mặc định chương trình
destroy sandbox trong finally, kể cả khi apply mới tạo được một phần rồi lỗi.
`--keep-resources` chủ động giữ lại để điều tra; khi dùng phải tự dọn sau đó.

## Chuẩn bị

1. Dùng AWS account sandbox có quyền EC2/VPC cần thiết và đã xác thực cục bộ.
   Terraform và boto3 cùng dùng profile/credential chain. Không ghi access key
   vào mã nguồn, báo cáo hoặc tệp Terraform variables.
2. Cài Terraform >=1.4,<2.0. Wheel của InfraLens không bundle Terraform.
3. Cài dependency demo từ repo:

```powershell
cd C:\work\infralens
.\.venv\Scripts\python.exe -m pip install -e '.[aws-demo]'
# Hoặc dùng uv: uv sync --locked --extra aws-demo
```

Extra aws-demo bao gồm boto3[crt] để đọc được profile tạo bởi `aws login`.
Không xuất temporary access key ra terminal hoặc chép credential vào tfvars.

Profile cần quyền đọc STS identity, đọc AMI public parameter SSM (hoặc truyền
`--ami`), EC2 Describe, tạo/tag/xóa VPC, subnet, SG, instance/volume và các thao
tác stop/start/modify instance, authorize/revoke ingress, terminate instance.
Các quyền đọc EC2 còn được dùng để xác nhận cleanup. Không cần quyền đọc
Secrets Manager, CloudTrail hoặc tạo IAM role cho demo này. Tổ chức có SCP,
permission boundary hoặc quy định mã hóa/KMS riêng có thể cần cấu hình thêm.
Danh sách này là mô tả thao tác, không phải policy IAM đã được xác minh đầy đủ.

## Chạy

Thay account ID bằng account sandbox thực tế đã xác nhận qua STS. Region trong
ví dụ dùng cùng khu vực với lab trước nhưng tất cả tài nguyên đều được tạo mới.

```powershell
.\.venv\Scripts\python.exe -m infralens.aws_sandbox `
  --account 123456789012 `
  --region ap-southeast-2 `
  --profile infralens-sandbox `
  --terraform 'C:\tools\terraform\terraform.exe'
```

`123456789012` chỉ là ví dụ. Chương trình gọi STS và từ chối account không khớp
trước khi tạo tài nguyên. Provider Terraform cũng có `allowed_account_ids`.
Template phải nằm ở `examples/aws-drift-sandbox` tính từ CWD, hoặc truyền
`--template` để trỏ đến bản template đã kiểm tra. Không dùng template không tin cậy.

Nếu không truyền `--ami`, chương trình đọc AMI ID từ public SSM parameter:
`/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64` trong
region được chọn. Giá trị này không phải secret và được cố định trong biến cho
toàn bộ lần chạy. Có thể truyền một AMI x86_64 tương thích qua `--ami`.

## Sáu tình huống

| Tình huống | Thao tác | Kết quả mong đợi |
| --- | --- | --- |
| 01-baseline | Apply cấu hình ban đầu | Không drift, exit 0 |
| 02-code-only | Chỉ đổi cấu hình mong muốn sang t3.small | Không drift, EC2 chưa đổi |
| 03-ec2-change | Stop EC2, đổi loại qua API, start lại | instance_type micro → small, exit 1 |
| 04-security-group | Thêm ingress TCP 8080 từ CIDR nội bộ VPC | SG ingress drift, exit 1 |
| 05-code-and-aws | Sửa cấu hình instance, đồng thời thêm ingress trên AWS | Báo drift SG; không báo nhầm instance |
| 06-resource-deleted | Terminate EC2 sandbox qua API | Báo delete trên aws_instance.demo, exit 1 |

Các thay đổi được khôi phục qua API giữa những tình huống cần baseline sạch;
không apply lại để che drift hoặc làm state mới. Delete được thực hiện cuối.
Mỗi check so cả SHA-256 và mtime của state trước/sau. Không thay đổi tài nguyên
lab OpenStack hay tài nguyên có RunId khác.

## Bằng chứng và cleanup

Mỗi lần chạy có thư mục riêng `reports/aws-drift/<RunId>/`, gồm:

- `terraform/`: mã sandbox, variables, provider lock và state riêng của lần chạy.
- `01-baseline.json` đến `06-resource-deleted.json`: báo cáo đã được InfraLens chuẩn hóa.
- `summary.json`: từng tình huống đã đạt, trạng thái tổng và cleanup.

Sau destroy, chương trình xác nhận Terraform state rỗng và truy vấn AWS theo tag
RunId để kiểm tra VPC, subnet, SG, volume và instance còn hoạt động. Cleanup lỗi
hoặc AWS vẫn trả về tài nguyên thì không báo cleanup thành công. AWS có eventual
consistency; có thể cần kiểm tra lại trước khi kết luận đã dọn hoàn toàn.

Nếu máy bị tắt hoặc quy trình cleanup bị ngắt, dùng đúng thư mục của lần chạy:

```powershell
$env:AWS_PROFILE = 'infralens-sandbox'
terraform '-chdir=reports/aws-drift/<RunId>/terraform' destroy -input=false
```

Kiểm tra lại account/region trước khi xác nhận destroy. Không dùng state của lab
khác, không force-unlock khi chưa chắc quy trình cũ đã dừng. Không đưa state hay
báo cáo thật lên Git; thư mục reports đã được ignore.

## Kiểm thử không cần AWS

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_aws_sandbox.py
terraform '-chdir=examples/aws-drift-sandbox' init -backend=false -input=false
terraform '-chdir=examples/aws-drift-sandbox' validate
```

Test SDK dùng botocore Stubber với dữ liệu giả, không gọi API thật. Chúng không
thay thế việc kiểm chứng sáu tình huống với AWS provider.

Tham khảo: [đổi thuộc tính EC2](https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_ModifyInstanceAttribute.html),
[ingress Security Group](https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_AuthorizeSecurityGroupIngress.html),
[AMI public parameters](https://docs.aws.amazon.com/systems-manager/latest/userguide/parameter-store-public-parameters-ami.html).

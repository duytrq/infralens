# Kiểm chứng định vị nguồn — 22/10/2026

Đã bổ sung file/dòng của block resource vào báo cáo drift. Môi trường kiểm thử:
Windows, Terraform 1.16.5, python-hcl2 8.1.4; fixture local_file dùng provider
hashicorp/local 2.5.3. Không tạo hoặc thay đổi tài nguyên AWS cho tính năng này.

## Demo từ checkout

Đã chạy CLI với `examples/drift/plan.json` và mã trong `examples/drift/main.tf`.
Kết quả: aws_instance.demo có source located, dòng 6–9, instance_type thay đổi
và password sensitive vẫn được che. Metadata không chứa source excerpt hoặc
giá trị biểu thức từ file cấu hình.

## Kiểm thử

Kết quả: **353 passed, 9 skipped, 16 deselected** ở suite mặc định;
**4 passed** với Terraform thật. Ruff lint/format, `uv lock --check` đạt.

51 unit test kiểm tra HCL/comment/heredoc, selector có dấu chấm/ngoặc/quote,
module local lồng nhau, metadata module đã init với TF_DATA_DIR tùy chỉnh,
module không tồn tại, JSON object/array, khoảng dòng, override và khai báo trùng.
Có ca parse lỗi, thiếu quyền đọc, dữ liệu quá lớn và cache nhiều instance;
không lộ nội dung lỗi/parser và không đổi kết luận drift khi thiếu vị trí.
Có kiểm tra CLI dùng metadata module từ TF_DATA_DIR tương đối/tuyệt đối,
không ghi đè module/backend metadata qua hardlink hoặc output trong cache.

Suite Terraform thật kiểm tra source của resource local_file bị thay đổi/xóa,
module for_each chứa module count và resource for_each có key chứa quote/ngoặc;
cấu hình `.tf.json` dạng labeled block array cũng được apply trong thư mục tạm
để kiểm chứng drift và vị trí key. Các thao tác apply chỉ dùng tài nguyên local.

Vị trí gắn vào code hiện tại; không xác định dòng thuộc tính phát sinh drift
hoặc chứng nhận code cũ trong imported plan. Override có nhiều vị trí được báo
ambiguous. Các trạng thái và giới hạn đầy đủ nằm ở [hướng dẫn](../SOURCE_LOCATIONS.md).

# Kiểm chứng ưu tiên và hướng dẫn drift — 22/10/2026

Kết quả: **401 passed, 9 skipped, 16 deselected** với suite mặc định;
**4 passed** với Terraform thật. Ruff lint/format đạt. Không tạo/thay đổi tài
nguyên AWS cho tính năng này; các fixture apply chỉ dùng tài nguyên local.

48 kiểm thử riêng xác nhận TCP/UDP/all, IPv4/IPv6, mở rộng protocol/port,
gộp khoảng port, thu hẹp quyền và sửa description. Có kiểm tra dữ liệu lỗi,
sensitive/unknown/absent, tag, resource không hỗ trợ và cách tổng hợp priority.

Test CLI xác nhận imported plan không chạy Terraform/AWS, không đổi nội dung
hoặc mtime state, và priority unknown vẫn tuân thủ fail-on-drift. Metadata review
không sao chép giá trị đầu vào vào hướng dẫn và giữ nguyên source, trace,
resource/attribute counts cùng kết luận drift.

Đã chạy demo `examples/drift-review` với imported plan giả lập. Báo cáo cục bộ
`reports/drift-review-demo.json` có 4 resource, high=2, medium=1, unknown=1;
cả bốn vị trí source được tìm thấy. Exit 1 đúng kỳ vọng khi bật fail-on-drift.

Hai lựa chọn được hiển thị ở cả bảng terminal và JSON: khôi phục cấu hình đã
duyệt hoặc cập nhật code để chấp nhận thay đổi đã duyệt. Chương trình không
thực thi lệnh sửa. Priority là heuristic; giới hạn đầy đủ ở [hướng dẫn](../DRIFT_REVIEW.md).

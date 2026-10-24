# Gate CI drift — 2026-10-23

Phạm vi: gate CLI theo priority, JSON decision, giữ report trước exit finding,
demo offline và workflow GitHub Actions mẫu. Không cấu hình AWS hoặc bật workflow.

## Thay đổi

- `--fail-on-priority high|medium`, chuẩn hóa hoa/thường và khoảng trắng trước
  collection; invalid threshold trả 2 trước engine/output.
- `--fail-on-unknown` độc lập với ngưỡng. Dựa trên priority hiệu lực của resource;
  assessment thiếu/không nhận diện được tính unknown, không copy payload lạ.
- `--fail-on-drift` giữ semantics mọi drift, kết hợp các cờ bằng OR. Finding không
  bị lọc. Match nhiều tiêu chí không nhân đôi matched_count.
- Module thuần `drift_gate.py` trả policy drift-gate-v1, criteria, counts,
  unassessed/matched resources và exit code. Không thay đổi result/assessment.
- Report có thêm gate khi bật cờ; không bật gate giữ nguyên schema. Writer chạy
  trước exit 1, trace lỗi cho incomplete/exit 3; I/O/engine lỗi vẫn là 3.
- Ở bước CLI này backend/API chưa nhận gate criteria. Phần tích hợp tiếp theo
  được ghi riêng tại [Backend/dashboard gate](BACKEND_GATE_2026-10-23.md).

## Kiểm thử tự động

**57 test mới** trong `tests/test_drift_gate.py`: ma trận ngưỡng/unknown/any drift,
criteria OR/deduplicate, assessment thiếu/sai phiên bản/sai kiểu, bảo toàn report,
không echo giá trị thuộc tính, ANSI sanitization, CLI normalization/validation,
import không AWS/Terraform, output trước exit, trace/I/O/engine precedence và help.

Lần chạy toàn bộ cuối bằng `python -m pytest -q`:
**627 passed, 9 skipped, 16 deselected**, 102,11 giây.
Một warning deprecation TestClient/httpx hiện có. Các suite external-tool chưa
được chọn trong lệnh mặc định; không chạy lại Terraform/AWS live trong lượt này.

Một lần chạy trước đó có **626 passed/1 failed** ở bài scanner Trivy hiện có
`test_clean_and_filtered_empty_have_distinct_messages` (scanner trả exit 3).
Test chạy lại riêng đạt, rồi toàn bộ chạy tuần tự đạt 627. Chưa khẳng định nguyên
nhân lỗi gián đoạn của lần đầu; không thay đổi code scanner trong phần gate này.

Ruff check toàn repo và format check **83 file** thành công, uv lock check và
git diff check thành công. Wheel ở
`reports/drift-gate-build/infralens-0.1.0-py3-none-any.whl` build thành công.
Giải nén/import CLI từ wheel riêng: hai cờ mới dùng được, mẫu 4 resource trả 1,
matched_count=3 và vẫn giữ đủ cả 4 resource.

## Demo CLI thật

```powershell
.\.venv\Scripts\python.exe .\examples\ci\demo_gate.py --format json
```

**8/8 scenario hợp lệ** qua các CLI subprocess, dùng synthetic plan và không
bật trace. Temporary inputs được dọn sau khi chạy. Artifact Git ignored:
`reports/drift-gate-demo.json`.

| Scenario | CLI exit | Matched |
| --- | --- | --- |
| clean | 0 | 0 |
| medium_allowed (threshold high) | 0 | 0 |
| medium_blocked (threshold medium) | 1 | 1 |
| unknown_allowed | 0 | 0 |
| unknown_blocked | 1 | 1 |
| high_blocked | 1 | 1 |
| mixed high+unknown | 1 | 3 |
| any_drift_overrides | 1 | 1 |

## Workflow mẫu

`examples/ci/drift-gate.yml` parse thành công bằng PyYAML BaseLoader trong uv
environment tạm, không đổi dependencies/lockfile dự án. Đã kiểm tra workflow_dispatch,
quyền contents read, action SHA, env input quote, giữ failure và chỉ upload
normalized report. Các SHA được đối chiếu tag v7 bằng git ls-remote:

- checkout: `3d3c42e5aac5ba805825da76410c181273ba90b1`
- setup-python: `6d4fd22b20465ccc0f7354476588e8df7c9ca0e0`
- upload-artifact: `cf430e030ddbb5b0abf93d22962f4752f3646cd9`

Trích nguyên run block sang `reports/drift-gate-step.sh`, Bash syntax check đạt.
Chạy nguyên block bằng Git Bash với fixture mixed: **exit 1**, report saved,
matched=3, resources=4. Evidence:
`reports/ci-step/infralens-drift/drift.json` và `reports/ci-step.*.log`.

Chưa chạy GitHub-hosted orchestration hoặc upload artifact lên GitHub. Workflow
vẫn chỉ là ví dụ ngoài `.github/workflows`; chưa commit/push. Plan import chưa
xác minh freshness/coverage; gate passed chỉ phản ánh tiêu chí đã chọn.

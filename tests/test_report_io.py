import os
import stat

import pytest

from infralens.reporting import write_report


def test_atomic_report_replacement_preserves_utf8_and_permissions(tmp_path):
    output = tmp_path / "reports" / "hạ tầng.json"
    write_report(output, '{"message":"hạ tầng"}\n')
    assert output.read_text(encoding="utf-8") == '{"message":"hạ tầng"}\n'
    if os.name != "nt":
        assert stat.S_IMODE(output.stat().st_mode) == 0o600
    write_report(output, "updated")
    assert output.read_text(encoding="utf-8") == "updated"
    assert list(output.parent.iterdir()) == [output]


def test_failed_report_replacement_keeps_old_report_and_removes_temporary(
    tmp_path, monkeypatch
):
    output = tmp_path / "report.json"
    output.write_bytes(b"old report")

    def fail(*args):
        raise PermissionError("destination unavailable")

    monkeypatch.setattr("infralens.reporting.os.replace", fail)
    with pytest.raises(PermissionError):
        write_report(output, "new report")
    assert output.read_bytes() == b"old report"
    assert list(tmp_path.iterdir()) == [output]

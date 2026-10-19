import pytest


@pytest.fixture
def project(tmp_path):
    path = tmp_path / "terraform project"
    path.mkdir()
    (path / "main.tf").write_text('variable "secret" {}\n')
    return path

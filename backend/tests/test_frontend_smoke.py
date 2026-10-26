import importlib.util
from pathlib import Path
from unittest.mock import Mock

import pytest

PATH = Path(__file__).resolve().parents[2] / "infra/frontend_smoke.py"
SPEC = importlib.util.spec_from_file_location("frontend_smoke", PATH)
smoke = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(smoke)


def test_smoke_removes_all_test_accounts_even_if_project_cleanup_fails():
    table = Mock()
    table.query.side_effect = [RuntimeError("Unavailable"), {"Items": []}]
    cognito = Mock()
    users = [{"sub": "a", "username": "test-a"}, {"sub": "b", "username": "test-b"}]
    with pytest.raises(RuntimeError, match="project cleanup"):
        smoke.cleanup_users(cognito, table, "pool", users)
    assert cognito.admin_delete_user.call_count == 2
    assert [
        call.kwargs["Username"] for call in cognito.admin_delete_user.call_args_list
    ] == ["test-a", "test-b"]


def test_smoke_deletes_only_the_test_users_project_keys():
    table = Mock()
    table.query.return_value = {"Items": [{"pk": "USER#a", "sk": "PROJECT#smoke"}]}
    cognito = Mock()
    assert (
        smoke.cleanup_users(
            cognito, table, "pool", [{"sub": "a", "username": "test-a"}]
        )
        == 1
    )
    table.delete_item.assert_called_once_with(
        Key={"pk": "USER#a", "sk": "PROJECT#smoke"}
    )
    cognito.admin_delete_user.assert_called_once_with(
        UserPoolId="pool", Username="test-a"
    )

"""User-level public cloud defaults; credentials are never persisted here."""

import json
import os
from pathlib import Path

from infralens.cloud import identifier
from infralens.cloud_auth import origin
from infralens.errors import InvalidInput
from infralens.reporting import write_report


def config_path():
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData/Roaming")
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "infralens/config.json"


def load():
    path = config_path()
    try:
        with path.open("rb") as stream:
            raw = stream.read(65537)
    except FileNotFoundError:
        return {}
    try:
        if len(raw) > 65536:
            raise ValueError
        data = json.loads(raw.decode("utf-8"))
        if (
            not isinstance(data, dict)
            or set(data) != {"schema_version", "api_url", "project_id"}
            or type(data["schema_version"]) is not int
            or data["schema_version"] != 1
        ):
            raise ValueError
        data["api_url"] = origin(data["api_url"])
        if data["project_id"] is not None:
            identifier(data["project_id"], "project_id")
    except (ValueError, TypeError, InvalidInput, UnicodeError, RecursionError):
        raise InvalidInput(
            "Cloud config is invalid. Fix or remove the config file, "
            "then run 'infralens cloud configure'."
        ) from None
    return data


def save(api_url, project_id=None):
    data = {
        "schema_version": 1,
        "api_url": origin(api_url),
        "project_id": identifier(project_id, "--project")
        if project_id is not None
        else None,
    }
    write_report(config_path(), json.dumps(data, indent=2) + "\n")


def repo_config(root):
    """Find the nearest config from the scan input, stopping at a Git boundary."""
    directory = Path(root).resolve()
    for parent in (directory, *directory.parents):
        file = parent / ".infralens.toml"
        if file.exists() or file.is_symlink():
            try:
                try:
                    import tomllib
                except ImportError:
                    import tomli as tomllib
                with file.open("rb") as stream:
                    raw = stream.read(65537)
                if len(raw) > 65536:
                    raise ValueError
                data = tomllib.loads(raw.decode("utf-8"))
                if set(data) != {"api_url", "project"}:
                    raise ValueError
                return file, {
                    "api_url": origin(data["api_url"]),
                    "project_id": identifier(data["project"], "project"),
                }
            except (ValueError, TypeError, UnicodeError, InvalidInput, RecursionError):
                raise InvalidInput(
                    "Invalid .infralens.toml; expected API URL and project only."
                ) from None
        if (parent / ".git").exists():
            break
    return None, {}


def save_repo(root, api_url, project_id):
    file = Path(root).resolve() / ".infralens.toml"
    api = origin(api_url)
    project = identifier(project_id, "project")
    write_report(
        file, f"api_url = {json.dumps(api)}\nproject = {json.dumps(project)}\n"
    )
    return file


def resolve(api_url=None, project_id=None, *, root=None):
    api = api_url if api_url is not None else os.environ.get("INFRALENS_API_URL")
    project = (
        project_id if project_id is not None else os.environ.get("INFRALENS_PROJECT")
    )
    _, repo = repo_config(root or Path.cwd())
    saved = load() if api is None or project is None else {}
    if api is None:
        api = repo.get("api_url")
    if api is None:
        api = saved.get("api_url")
    if api is None:
        raise InvalidInput(
            "No API URL configured. Run 'infralens cloud configure --api-url URL' "
            "or set INFRALENS_API_URL."
        )
    api = origin(api)
    if project is None and repo.get("api_url") == api:
        project = repo.get("project_id")
    if project is None and saved.get("api_url") == api:
        project = saved.get("project_id")
    return api, identifier(project, "--project") if project is not None else None

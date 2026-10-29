"""Authenticated project operations using the existing private projects API."""

import json
from pathlib import Path
from urllib.parse import urlencode

import typer

from infralens import cloud_config
from infralens.cloud import identifier
from infralens.cloud_auth import access_token, http
from infralens.errors import ExecutionError, InvalidInput
from infralens.reporting import plain


def _project(data, expected=None):
    try:
        if not isinstance(data, dict):
            raise ValueError
        project_id = identifier(data["project_id"], "project_id")
        name = data["name"]
        if expected is not None and project_id != expected:
            raise ValueError
        if not isinstance(name, str) or not name.strip() or len(name) > 120:
            raise ValueError
    except (ValueError, KeyError, TypeError, InvalidInput):
        raise ExecutionError("The service returned invalid project data.") from None
    return data


def _request(api, token, method, path, body=None):
    _, payload = http(
        method,
        api + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        statuses=(200, 201) if method == "PUT" else (200,),
    )
    try:
        return json.loads(payload)
    except (ValueError, UnicodeError, RecursionError):
        raise ExecutionError("The service returned invalid project data.") from None


def create(project_id, name, api_url=None, select=True):
    project_id = identifier(project_id, "project_id")
    name = name.strip()
    if not name or len(name) > 120 or any(not c.isprintable() for c in name):
        raise InvalidInput("--name must contain 1-120 printable characters.")
    api, _ = cloud_config.resolve(api_url)
    data = _project(
        _request(
            api, access_token(api), "PUT", f"/v1/projects/{project_id}", {"name": name}
        ),
        project_id,
    )
    typer.echo(f"Project ready: {project_id} | {plain(data['name'])}")
    if select:
        select_project(api, project_id)
        typer.echo(f"Selected project: {project_id}")


def use(project_id, api_url=None):
    project_id = identifier(project_id, "project_id")
    api, _ = cloud_config.resolve(api_url)
    _project(
        _request(api, access_token(api), "GET", f"/v1/projects/{project_id}"),
        project_id,
    )
    select_project(api, project_id)
    typer.echo(f"Selected project: {project_id}")


def list_projects(api_url=None, *, collect=False):
    api, selected = cloud_config.resolve(api_url)
    token = access_token(api)
    cursor = None
    seen = set()
    count = 0
    projects = []
    if not collect:
        typer.echo("PROJECT ID | NAME | SELECTED")
    for _ in range(100):
        query = {"limit": 100}
        if cursor is not None:
            query["cursor"] = cursor
        data = _request(api, token, "GET", "/v1/projects?" + urlencode(query))
        if (
            not isinstance(data, dict)
            or not isinstance(data.get("items"), list)
            or len(data["items"]) > 100
            or "next_cursor" not in data
        ):
            raise ExecutionError("The service returned invalid project data.")
        for item in data["items"]:
            project = _project(item)
            marker = "*" if project["project_id"] == selected else ""
            projects.append(project)
            if not collect:
                typer.echo(
                    f"{project['project_id']} | {plain(project['name'])} | {marker}"
                )
            count += 1
        cursor = data.get("next_cursor")
        if cursor is None:
            if count == 0 and not collect:
                typer.echo(
                    "No projects yet. Create one with "
                    "'infralens cloud project create ID'."
                )
            return projects
        if (
            not isinstance(cursor, str)
            or not cursor
            or len(cursor) > 16384
            or cursor in seen
        ):
            raise ExecutionError("The service returned an invalid project cursor.")
        seen.add(cursor)
    raise ExecutionError(
        "Project listing exceeded its page limit. "
        "Use the dashboard to view more projects."
    )


def select_project(api, project_id):
    existing, _ = cloud_config.repo_config(Path.cwd())
    root = existing.parent if existing else Path.cwd()
    file = root / ".infralens.toml"
    if file.is_symlink():
        raise InvalidInput("Repo config must not be a symbolic link.")
    cloud_config.save_repo(root, api, project_id)

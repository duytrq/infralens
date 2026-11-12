"""Authenticated project operations using the existing private projects API."""

import json
import os
import re
import subprocess
from pathlib import Path
from urllib.parse import urlencode

import typer

from infralens import cloud_auth, cloud_config
from infralens.cloud import identifier
from infralens.cloud_auth import access_token, http
from infralens.errors import ExecutionError, InvalidInput
from infralens.reporting import plain


def auto_project(api, root):
    """Bind on first upload; ask before reusing any existing project ID."""
    directory = Path(root).resolve()
    existing, binding = cloud_config.repo_config(directory)
    if existing is not None:
        if binding["api_url"] == api:
            return binding["project_id"]
        raise InvalidInput(
            "This repo is bound to a different API. Use --project for this run "
            "or 'infralens cloud project use ID --api-url URL' to rebind it."
        )
    try:
        result = subprocess.run(
            ["git", "-C", str(directory), "rev-parse", "--show-toplevel"],
            env={k: v for k, v in os.environ.items() if not k.startswith("GIT_")},
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
        git_root = Path(result.stdout.strip()).resolve()
        directory.relative_to(git_root)
    except (OSError, subprocess.SubprocessError, ValueError):
        raise InvalidInput(
            "No project bound to this directory and no usable Git repo found. "
            "Run 'infralens cloud setup' or pass --project explicitly."
        ) from None
    name = plain(git_root.name)[:120] or "Git project"
    project_id = re.sub(r"[^a-z0-9]+", "-", name.lower())[:64].strip("-") or "repo"
    token = access_token(api)
    while True:
        data, created = _prepare_project(api, token, project_id, name)
        if created:
            break
        if not cloud_auth.interactive_input():
            raise InvalidInput(
                f"Project '{project_id}' already exists. Run with --project "
                "to explicitly reuse it, commit a repo binding, or use "
                "'infralens cloud project create ID --name NAME' to create another."
            )
        typer.echo(
            f"Project ID already exists: {project_id} | {plain(data['name'])}",
            err=True,
        )
        if typer.confirm("Use this existing project?", default=False, err=True):
            break
        project_id = identifier(typer.prompt("New project ID", err=True), "Project ID")
    file = cloud_config.save_repo(git_root, api, project_id)
    typer.echo(f"Project ready: {project_id} | {plain(data['name'])}", err=True)
    typer.echo(f"Repo binding saved: {file}", err=True)
    return project_id


def _prepare_project(api, token, project_id, name):
    path = f"/v1/projects/{project_id}"
    status, data = _request(
        api, token, "GET", path, statuses=(200, 404), include_status=True
    )
    if status == 200:
        return _project(data, project_id), False
    status, data = _request(
        api,
        token,
        "PUT",
        path,
        {"name": name},
        statuses=(200, 201, 409),
        include_status=True,
    )
    # Another client may create the ID between GET and PUT. Never silently reuse it.
    if status == 409:
        data = _request(api, token, "GET", path)
    return _project(data, project_id), status == 201


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


def _request(
    api, token, method, path, body=None, *, statuses=None, include_status=False
):
    from infralens.cloud_api_key import route

    status, payload = http(
        method,
        api + route(token, path),
        data=json.dumps(body).encode() if body is not None else None,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        statuses=statuses or ((200, 201) if method == "PUT" else (200,)),
    )
    try:
        data = json.loads(payload)
        return (status, data) if include_status else data
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

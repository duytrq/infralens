"""Interactive onboarding, with no prompts in automated commands."""

import os
from pathlib import Path

import typer

from infralens import cloud_auth, cloud_config, cloud_projects
from infralens.errors import InvalidInput
from infralens.reporting import plain


def interactive():
    if not cloud_auth.interactive_input():
        raise InvalidInput(
            "Interactive terminal required; supply explicit flags/IDs in CI."
        )


def project_details(project_id=None, name=None):
    if project_id is None or name is None:
        if not cloud_auth.interactive_input():
            raise InvalidInput("Supply PROJECT_ID and --name in noninteractive mode.")
        if project_id is None:
            project_id = typer.prompt("New project ID")
        if name is None:
            name = typer.prompt("Display name", default=project_id)
    return project_id, name


def choose_project(api):
    interactive()
    projects = cloud_projects.list_projects(api, collect=True)
    for i, project in enumerate(projects, 1):
        typer.echo(f"{i}. {project['project_id']} | {plain(project['name'])}")
    typer.echo("0. Create a project")
    _, current = cloud_config.resolve(api)
    default = next(
        (i for i, p in enumerate(projects, 1) if p["project_id"] == current),
        1 if projects else 0,
    )
    selected = typer.prompt("Project number", type=int, default=default)
    if not 0 <= selected <= len(projects):
        raise InvalidInput("Choose one of the displayed project numbers.")
    if selected:
        return projects[selected - 1]["project_id"]
    project_id, name = project_details()
    cloud_projects.create(project_id, name, api, select=False)
    return project_id


def setup(api_url=None):
    from infralens import cloud_auth

    interactive()
    if api_url is None:
        _, repo = cloud_config.repo_config(Path.cwd())
        saved = cloud_config.load()
        api_url = (
            os.environ.get("INFRALENS_API_URL")
            or repo.get("api_url")
            or saved.get("api_url")
        )
        if api_url is None:
            api_url = typer.prompt("API URL")
    api = cloud_auth.origin(api_url)
    cloud_auth.access_token(api)
    project = choose_project(api)
    cloud_projects.use(project, api)
    typer.echo("Setup complete. Run 'infralens scan --upload'.")

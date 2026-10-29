"""Interactive onboarding, with no prompts in automated commands."""

import sys
from pathlib import Path

import typer

from infralens import cloud_config, cloud_projects
from infralens.errors import InvalidInput
from infralens.reporting import plain


def interactive():
    if not sys.stdin.isatty():
        raise InvalidInput(
            "Interactive terminal required; supply explicit flags/IDs in CI."
        )


def choose_project(api):
    interactive()
    projects = cloud_projects.list_projects(api, collect=True)
    for i, project in enumerate(projects, 1):
        typer.echo(f"{i}. {project['project_id']} | {plain(project['name'])}")
    typer.echo("0. Create a project")
    selected = typer.prompt("Project number", type=int, default=1 if projects else 0)
    if not 0 <= selected <= len(projects):
        raise InvalidInput("Choose one of the displayed project numbers.")
    if selected:
        return projects[selected - 1]["project_id"]
    project_id = typer.prompt("New project ID")
    name = typer.prompt("Display name", default=project_id)
    cloud_projects.create(project_id, name, api, select=False)
    return project_id


def setup(api_url=None, local=False):
    from infralens import cloud_auth

    interactive()
    if api_url is None:
        _, repo = cloud_config.repo_config(Path.cwd())
        saved = cloud_config.load()
        api_url = typer.prompt(
            "API URL", default=repo.get("api_url") or saved.get("api_url")
        )
    api = cloud_auth.origin(api_url)
    cloud_auth.access_token(api)
    project = choose_project(api)
    cloud_projects.use(project, api, local=local)
    typer.echo("Setup complete. Run 'infralens scan --upload'.")

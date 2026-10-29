"""Command declarations and process entry point."""

import os
import signal
import sys
from importlib.metadata import version
from pathlib import Path
from typing import Annotated

import typer

from infralens.errors import ExitCode, InvalidInput, command_errors, report_unexpected
from infralens.handlers import handle_drift, handle_scan
from infralens.logging import configure_logging, logger
from infralens.options import (
    DRIFT_PRIORITIES,
    SEVERITIES,
    DriftFormat,
    DriftOptions,
    ScanFormat,
    ScanOptions,
    UploadOptions,
)
from infralens.reporting import color_enabled
from infralens.validation import (
    drift_output_path,
    drift_priority_threshold,
    failure_threshold,
    optional_text,
    readable_file,
    scan_directory,
    scan_output_path,
    severity_filter,
    terraform_directory,
    trace_lookback,
    variable_files,
)

app = typer.Typer(
    help="Scan Terraform security and inspect infrastructure drift.",
    add_completion=False,
    invoke_without_command=True,
    no_args_is_help=False,
    rich_markup_mode=None,
    pretty_exceptions_enable=False,
    pretty_exceptions_show_locals=False,
)
cloud_app = typer.Typer(
    help="Configure cloud connection and manage projects.", no_args_is_help=True
)
project_app = typer.Typer(
    help="Create, list and select your projects.", no_args_is_help=True
)
app.add_typer(cloud_app, name="cloud")
cloud_app.add_typer(project_app, name="project")
configure_app = typer.Typer(
    help="Save API settings or list current configuration.",
    invoke_without_command=True,
    no_args_is_help=False,
)
cloud_app.add_typer(configure_app, name="configure")


def show_version(value: bool) -> None:
    if value:
        typer.echo(f"infralens {version('infralens')}")
        raise typer.Exit()


@app.callback()
def root(
    ctx: typer.Context,
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            callback=show_version,
            is_eager=True,
            help="Show the installed version and exit.",
        ),
    ] = False,
    verbose: Annotated[
        bool, typer.Option("--verbose", help="Log diagnostic steps to stderr.")
    ] = False,
    no_color: Annotated[
        bool, typer.Option("--no-color", help="Disable ANSI color output.")
    ] = False,
) -> None:
    # Plain help/errors avoid ANSI even before eager --help is processed.
    ctx.color = False
    ctx.obj = {"color": color_enabled(no_color)}
    configure_logging(verbose)
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())


ProjectPath = Annotated[Path, typer.Argument(help="Terraform project directory.")]
ReportOutput = Annotated[Path | None, typer.Option(help="Output path relative to CWD.")]
EngineTimeout = Annotated[int, typer.Option(min=1, help="Engine timeout in seconds.")]
UploadReport = Annotated[
    bool, typer.Option(help="Upload JSON to the InfraLens dashboard.")
]
CloudProject = Annotated[
    str | None,
    typer.Option(
        help="Explicit project; otherwise INFRALENS_PROJECT or this repo binding."
    ),
]
CloudApiUrl = Annotated[
    str | None,
    typer.Option(
        help="API override; otherwise INFRALENS_API_URL or saved configuration."
    ),
]


@configure_app.callback()
def configure_cloud(
    ctx: typer.Context,
    api_url: Annotated[
        str | None, typer.Option(help="HTTPS API origin to save.")
    ] = None,
):
    """Save the API URL once. No credentials are stored."""
    with command_errors():
        if ctx.invoked_subcommand is not None:
            if api_url is not None:
                raise InvalidInput(
                    "Use --api-url to save settings, or 'configure list' to view them."
                )
            return
        if api_url is None:
            raise InvalidInput(
                "Supply --api-url URL or run 'infralens cloud configure list'."
            )
        from infralens import cloud_config
        from infralens.cloud_auth import origin

        api = origin(api_url)
        cloud_config.save(api)
        typer.echo(f"API URL saved: {api}")


@cloud_app.command("setup")
def cloud_setup(api_url: CloudApiUrl = None):
    """Sign in and bind this repo to a cloud project."""
    with command_errors():
        from infralens.cloud_workflow import setup

        setup(api_url)


@cloud_app.command("login")
def cloud_login(api_url: CloudApiUrl = None):
    """Sign in once through the browser and save your Cognito session."""
    with command_errors():
        from infralens import cloud_auth, cloud_config, cloud_session

        if not cloud_auth.interactive_input():
            raise InvalidInput("Login requires an interactive terminal.")
        api, _ = cloud_config.resolve(api_url)
        cloud_session.sign_in(api)


@cloud_app.command("logout")
def cloud_logout(api_url: CloudApiUrl = None):
    """Remove this API's saved session and request token revocation."""
    with command_errors():
        from infralens import cloud_config, cloud_session

        api, _ = cloud_config.resolve(api_url)
        cloud_session.logout(api)


@cloud_app.command("status")
def cloud_status():
    """Show public settings without signing in."""
    with command_errors():
        from infralens import cloud_config
        from infralens.reporting import plain

        saved = cloud_config.load()
        repo_file, repo = cloud_config.repo_config(Path.cwd())
        api, project = (
            cloud_config.resolve()
            if repo.get("api_url")
            or saved.get("api_url")
            or os.environ.get("INFRALENS_API_URL")
            else (None, None)
        )
        typer.echo(f"API URL: {api or 'not configured'}")
        typer.echo(f"Project: {project or 'not selected'}")
        typer.echo(f"Repo config: {plain(str(repo_file)) if repo_file else 'none'}")
        typer.echo("Project priority: flags > environment > repo binding")
        typer.echo("API priority: flags > environment > repo > saved API URL")
        api_source = (
            "environment"
            if os.environ.get("INFRALENS_API_URL") is not None
            else ("repo" if repo.get("api_url") else "user config")
        )
        project_source = (
            "environment"
            if os.environ.get("INFRALENS_PROJECT") is not None
            else ("repo" if project and repo.get("api_url") == api else "not bound")
        )
        typer.echo(f"Sources: API={api_source}; project={project_source}")
        typer.echo(f"Config: {plain(str(cloud_config.config_path()))}")
        import time

        from infralens import cloud_session

        if os.environ.get("INFRALENS_ACCESS_TOKEN") is not None:
            state = "environment access token (not saved or refreshed)"
        else:
            session = cloud_session.read(api) if api else None
            state = (
                "not signed in; run 'infralens cloud login'"
                if session is None
                else "saved session; token valid locally (revocation not checked)"
                if session["expires_at"] > time.time() + 60
                else "saved session; refresh needed on next cloud command"
            )
        typer.echo(f"Auth: {state}")


@configure_app.command("list")
def list_configuration():
    """Show the effective API, project and auth state without exposing tokens."""
    cloud_status()


@project_app.command("create")
def create_project(
    project_id: Annotated[str | None, typer.Argument()] = None,
    name: Annotated[
        str | None,
        typer.Option(
            help="Display name; prompts when omitted on an interactive terminal."
        ),
    ] = None,
    api_url: CloudApiUrl = None,
    select: Annotated[
        bool, typer.Option(help="Bind this repo to the project after creation.")
    ] = True,
):
    """Create a project and bind this repo for subsequent uploads."""
    with command_errors():
        from infralens.cloud_projects import create
        from infralens.cloud_workflow import project_details

        project_id, name = project_details(project_id, name)
        create(project_id, name, api_url, select)


@project_app.command("list")
def list_projects(api_url: CloudApiUrl = None):
    """List projects visible to your signed-in account."""
    with command_errors():
        from infralens.cloud_projects import list_projects as list_cloud_projects

        list_cloud_projects(api_url)


@project_app.command("use")
def use_project(
    project_id: Annotated[str | None, typer.Argument()] = None,
    api_url: CloudApiUrl = None,
):
    """Bind this repo to an existing project for subsequent uploads."""
    with command_errors():
        from infralens.cloud_config import resolve
        from infralens.cloud_projects import use
        from infralens.cloud_workflow import choose_project

        api, _ = resolve(api_url)
        use(project_id if project_id is not None else choose_project(api), api)


def upload_defaults(upload, format, output, kind, enum):
    from datetime import datetime, timezone
    from uuid import uuid4

    if format is None:
        format = enum.json if upload else enum.table
    if upload and output is None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        output = Path(".infralens/reports") / f"{kind}-{stamp}-{uuid4().hex[:8]}.json"
    return format, output


def _upload_options(
    upload: bool,
    report_format: str,
    output: Path | None,
    project: str | None,
    api_url: str | None,
    *,
    scope: str | None = None,
    require_scope: bool = False,
    root: Path | None = None,
) -> UploadOptions | None:
    if not upload:
        if any(value is not None for value in (project, api_url, scope)):
            flags = (
                "--project, --scope and --api-url"
                if require_scope
                else "--project and --api-url"
            )
            raise InvalidInput(f"{flags} require --upload.")
        return None
    if report_format != "json" or output is None:
        raise InvalidInput("--upload requires --format json and --output.")
    from infralens.cloud import identifier
    from infralens.cloud_config import resolve

    api_url, project = resolve(api_url, project, root=root)
    if project is None:
        raise InvalidInput(
            "No project bound to this repo. Run 'infralens cloud setup' or "
            "pass --project explicitly for this run."
        )
    if require_scope and scope is None:
        raise InvalidInput(
            "Drift upload requires --scope, e.g. --scope dev-default "
            "for this account/workspace/environment."
        )
    options = UploadOptions(
        api_url,
        project,
        identifier(scope, "--scope") if require_scope else None,
    )
    return options


@app.command()
def scan(
    ctx: typer.Context,
    path: ProjectPath = Path("."),
    format: Annotated[
        ScanFormat, typer.Option("--format", help="Report format.")
    ] = None,
    output: ReportOutput = None,
    fail_on: Annotated[
        str | None,
        typer.Option(
            help="Inclusive LOW|MEDIUM|HIGH|CRITICAL threshold; ignores --severity."
        ),
    ] = None,
    timeout: EngineTimeout = 300,
    upload: UploadReport = False,
    project: CloudProject = None,
    api_url: CloudApiUrl = None,
    severity: Annotated[
        str,
        typer.Option(help="Comma-separated report severities; upload JSON keeps all."),
    ] = ",".join(SEVERITIES),
) -> None:
    """Scan Terraform misconfigurations using Trivy 0.76.x."""
    with command_errors():
        format, output = upload_defaults(upload, format, output, "security", ScanFormat)
        selected = severity_filter(severity)
        threshold = failure_threshold(fail_on)
        directory, inputs = scan_directory(path)
        destination = scan_output_path(output, inputs)
        cloud_options = _upload_options(
            upload, format.value, destination, project, api_url, root=directory
        )
        logger.debug("Scan validation complete")
        handle_scan(
            ScanOptions(
                directory,
                selected,
                format.value,
                destination,
                threshold,
                timeout,
                upload=cloud_options,
                color=ctx.find_root().obj["color"],
            )
        )


@app.command()
def drift(
    ctx: typer.Context,
    path: ProjectPath = Path("."),
    format: Annotated[
        DriftFormat, typer.Option("--format", help="Report format.")
    ] = None,
    output: ReportOutput = None,
    fail_on_priority: Annotated[
        str | None,
        typer.Option(
            "--fail-on",
            "--fail-on-priority",
            help="Inclusive MEDIUM|HIGH review-priority threshold.",
        ),
    ] = None,
    timeout: EngineTimeout = 300,
    upload: UploadReport = False,
    project: CloudProject = None,
    api_url: CloudApiUrl = None,
    severity: Annotated[
        str,
        typer.Option(
            help="Displayed priorities HIGH,MEDIUM,UNKNOWN; JSON/gates keep all."
        ),
    ] = ",".join(DRIFT_PRIORITIES),
    scope: Annotated[
        str | None,
        typer.Option(
            help="Stable account/workspace/environment ID; requires --upload."
        ),
    ] = None,
    var_file: Annotated[
        list[Path] | None,
        typer.Option("--var-file", help="Repeatable variable file, relative to PATH."),
    ] = None,
    profile: Annotated[str | None, typer.Option(help="AWS profile name.")] = None,
    region: Annotated[str | None, typer.Option(help="AWS region name.")] = None,
    trace: Annotated[
        bool, typer.Option("--trace", help="Look up related AWS CloudTrail events.")
    ] = False,
    lookback_days: Annotated[
        int | None,
        typer.Option(
            min=1,
            max=90,
            help="Lookback in days (1-90); requires --trace (default: 7).",
        ),
    ] = None,
    fail_on_drift: Annotated[
        bool, typer.Option("--fail-on-drift", help="Exit 1 when drift is detected.")
    ] = False,
    fail_on_unknown: Annotated[
        bool,
        typer.Option(
            "--fail-on-unknown", help="Exit 1 for unknown or unassessed priority."
        ),
    ] = False,
    plan_json: Annotated[
        Path | None,
        typer.Option(help="Read plan JSON without Terraform; --trace still calls AWS."),
    ] = None,
) -> None:
    """Detect managed resource drift using a Terraform refresh-only plan."""
    with command_errors():
        format, output = upload_defaults(upload, format, output, "drift", DriftFormat)
        selected = severity_filter(severity)
        if any(level not in DRIFT_PRIORITIES for level in selected):
            raise InvalidInput(
                "--severity: Drift priorities are HIGH, MEDIUM and UNKNOWN."
            )
        days = trace_lookback(trace, lookback_days)
        priority = drift_priority_threshold(fail_on_priority)
        profile = optional_text(profile, "--profile")
        region = optional_text(region, "--region")
        directory, inputs = terraform_directory(path)
        variables = variable_files(var_file or [], directory)
        imported = (
            readable_file(plan_json, "--plan-json") if plan_json is not None else None
        )
        protected = inputs + variables + ((imported,) if imported is not None else ())
        destination = drift_output_path(output, directory, protected)
        cloud_options = _upload_options(
            upload,
            format.value,
            destination,
            project,
            api_url,
            scope=scope,
            require_scope=True,
            root=directory,
        )
        logger.debug("Drift validation complete")
        handle_drift(
            DriftOptions(
                directory,
                variables,
                format.value,
                destination,
                profile,
                region,
                trace,
                days,
                fail_on_drift,
                timeout,
                imported,
                fail_on_priority=priority,
                fail_on_unknown=fail_on_unknown,
                color=ctx.find_root().obj["color"],
                severity=selected,
                upload=cloud_options,
            )
        )


def main() -> None:
    if os.name == "nt":
        for stream in (sys.stdout, sys.stderr):
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8")

        def interrupt(signum, frame):
            raise KeyboardInterrupt

        signal.signal(signal.SIGBREAK, interrupt)
    try:
        app()
    except KeyboardInterrupt:
        raise SystemExit(ExitCode.interrupted) from None
    except Exception as exc:
        report_unexpected(exc)
        raise SystemExit(ExitCode.execution_error) from None

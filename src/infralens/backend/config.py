"""Operator-owned project registry; HTTP callers cannot choose filesystem paths."""

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from infralens.errors import InvalidInput
from infralens.validation import drift_output_path, readable_file, terraform_directory


@dataclass(frozen=True)
class Project:
    id: str
    name: str
    path: Path
    workspace: str = "default"
    profile: str | None = None
    region: str | None = None
    var_files: tuple[Path, ...] = ()
    data_dir: Path | None = None
    allow_refresh: bool = True
    allow_import: bool = True
    allow_trace: bool = False
    max_timeout: int = 300

    def scope_key(self):
        values = {
            "id": self.id,
            "path": str(self.path),
            "workspace": self.workspace,
            "profile": self.profile,
            "region": self.region,
            "var_files": [str(p) for p in self.var_files],
            "data_dir": str(self.data_dir or self.path / ".terraform"),
        }
        return hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()


@dataclass(frozen=True)
class Settings:
    projects: dict[str, Project]
    database: Path
    api_token: str = field(repr=False)
    max_pending: int = 100
    max_body_bytes: int = 2 * 1024 * 1024
    cors_origins: tuple[str, ...] = ()

    def validate(self):
        if not re.fullmatch(r"[A-Za-z0-9_-]{24,256}", self.api_token):
            raise ValueError("Configure a 24-256 character API token.")
        if not self.projects or not 1 <= self.max_pending <= 1000:
            raise ValueError("Invalid backend settings.")
        if not 1024 <= self.max_body_bytes <= 8 * 1024 * 1024:
            raise ValueError("Invalid body limit.")
        database = self.database.resolve()
        for project in self.projects.values():
            drift_output_path(database, project.path, project.var_files)
            data = (project.data_dir or project.path / ".terraform").resolve()
            if database.is_relative_to(data):
                raise ValueError("Database must be outside Terraform data directories.")
            for relative in ("terraform.tfstate", "modules/modules.json"):
                metadata = data / relative
                if (
                    database.exists()
                    and metadata.is_file()
                    and database.samefile(metadata)
                ):
                    raise ValueError("Database overlaps Terraform metadata.")


def load_projects(path: Path) -> dict[str, Project]:
    """Read a trusted local JSON registry, resolving paths relative to that file."""
    allowed = set(Project.__dataclass_fields__)
    try:
        config = json.loads(path.read_text(encoding="utf-8-sig"))
        if set(config) != {"projects"} or not isinstance(config["projects"], list):
            raise ValueError
        projects = {}
        for item in config["projects"]:
            if not isinstance(item, dict) or set(item) - allowed:
                raise ValueError
            identity, name = item["id"], item["name"]
            if not isinstance(identity, str) or not re.fullmatch(
                r"[a-z0-9_-]{1,64}", identity
            ):
                raise ValueError
            if (
                identity in projects
                or not isinstance(name, str)
                or not 1 <= len(name) <= 100
            ):
                raise ValueError
            directory, _ = terraform_directory(path.parent / item["path"])
            values = {
                k: v
                for k, v in item.items()
                if k not in ("path", "var_files", "data_dir")
            }
            if not re.fullmatch(
                r"[A-Za-z0-9_-]{1,90}", values.get("workspace", "default")
            ):
                raise ValueError
            for key in ("allow_refresh", "allow_import", "allow_trace"):
                if key in values and type(values[key]) is not bool:
                    raise ValueError
            timeout = values.get("max_timeout", 300)
            if type(timeout) is not int or not 1 <= timeout <= 600:
                raise ValueError
            for key in ("profile", "region"):
                if key in values and values[key] is not None:
                    if not isinstance(values[key], str) or not values[key].strip():
                        raise ValueError
                    values[key] = values[key].strip()
            variables = item.get("var_files", [])
            if not isinstance(variables, list) or any(
                not isinstance(p, str) for p in variables
            ):
                raise ValueError
            variables = tuple(
                readable_file(directory / p, "var_files") for p in variables
            )
            data = item.get("data_dir")
            data = (
                (directory / data).resolve()
                if data is not None
                else directory / ".terraform"
            )
            projects[identity] = Project(
                path=directory, var_files=variables, data_dir=data, **values
            )
        if not projects:
            raise ValueError
        return projects
    except (KeyError, TypeError, ValueError, OSError, InvalidInput):
        raise ValueError(
            "Invalid project registry; check its schema and paths."
        ) from None

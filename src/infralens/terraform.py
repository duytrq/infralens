"""Terraform refresh-only plans using the shared cancellable process runner."""

import json
import os
import re
import shutil
import tempfile
from pathlib import Path

from infralens.drift import DriftResult, parse_plan
from infralens.errors import ExecutionError
from infralens.logging import logger
from infralens.options import DriftOptions
from infralens.process import run_process


def _environment() -> dict[str, str]:
    if os.name != "nt":
        return dict(os.environ)
    # Python uppercases os.environ keys on Windows. Terraform enumerates TF_VAR_*
    # and treats the suffix as a case-sensitive HCL variable name. Preserve the
    # original environment block rather than changing TF_VAR_name to TF_VAR_NAME.
    import ctypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetEnvironmentStringsW.restype = ctypes.c_void_p
    kernel.FreeEnvironmentStringsW.argtypes = [ctypes.c_void_p]
    block = kernel.GetEnvironmentStringsW()
    if not block:
        raise ExecutionError("Could not read the process environment for Terraform.")
    env = {}
    try:
        cursor = block
        while entry := ctypes.wstring_at(cursor):
            if not entry.startswith("="):
                key, value = entry.split("=", 1)
                env[key] = value
            cursor += len(entry.encode("utf-16-le", errors="surrogatepass")) + 2
    finally:
        kernel.FreeEnvironmentStringsW(block)
    return env


def terraform_environment(options: DriftOptions) -> dict[str, str]:
    # Inherited CLI arguments could introduce -target, -refresh=false, another
    # state or -out. Logging can persist plaintext secrets. Preserve provider,
    # backend, workspace, proxy and TF_VAR_* credential/variable configuration.
    overrides = {"TF_INPUT": "0", "TF_IN_AUTOMATION": "1", "CHECKPOINT_DISABLE": "1"}
    if options.profile is not None:
        overrides.update(
            AWS_PROFILE=options.profile, AWS_DEFAULT_PROFILE=options.profile
        )
    if options.region is not None:
        overrides.update(AWS_REGION=options.region, AWS_DEFAULT_REGION=options.region)
    if options.workspace is not None:
        overrides["TF_WORKSPACE"] = options.workspace
    if options.data_dir is not None:
        overrides["TF_DATA_DIR"] = str(options.data_dir)
    env = {
        key: value
        for key, value in _environment().items()
        if not key.upper().startswith(("TF_CLI_ARGS", "TF_LOG"))
        and key.upper() not in overrides
    }
    env.update(overrides)
    return env


class Terraform:
    def __init__(self, options: DriftOptions):
        self.options = options
        binary = shutil.which("terraform")
        if binary is None:
            raise ExecutionError(
                "Terraform >=1.1,<2 was not found on PATH. Install Terraform "
                "and run terraform init in the project first."
            )
        self.binary = str(Path(binary).resolve())
        self.env = terraform_environment(options)
        result = self._run(["version", "-json"], timeout=10)
        try:
            raw = json.loads(result.stdout)
            version = raw["terraform_version"]
            match = re.fullmatch(r"1\.(\d+)\.\d+", version)
            if result.returncode != 0 or match is None or int(match[1]) < 1:
                raise ValueError
        except (ValueError, TypeError, KeyError):
            raise ExecutionError(
                "Unsupported Terraform version. Use a stable Terraform >=1.1,<2."
            ) from None
        self.version = version
        logger.debug("Terraform %s discovered on PATH", self.version)

    def _run(self, args: list[str], *, timeout: int):
        return run_process(
            [self.binary, *args],
            cwd=self.options.path,
            timeout=timeout,
            env=self.env,
            cancel=self.options.cancel,
        )

    def drift(self) -> DriftResult:
        with tempfile.TemporaryDirectory(prefix="infralens-drift-") as directory:
            plan = Path(directory) / "refresh.tfplan"
            arguments = [
                "plan",
                "-refresh-only",
                "-input=false",
                "-no-color",
                "-detailed-exitcode",
                "-lock-timeout=10s",
                f"-out={plan}",
                *(f"-var-file={path}" for path in self.options.var_files),
            ]
            logger.debug("Creating refresh-only plan (state lock enabled)")
            result = self._run(arguments, timeout=self.options.timeout)
            if result.returncode not in (0, 2):
                raise ExecutionError(
                    "Terraform refresh-only plan failed. Run terraform init, check "
                    "variables, workspace, backend and provider credentials, then "
                    "run terraform plan -refresh-only directly for diagnostics."
                )
            logger.debug("Reading temporary Terraform plan as JSON")
            result = self._run(["show", "-json", str(plan)], timeout=60)
            if result.returncode != 0:
                raise ExecutionError("Terraform could not read its saved plan as JSON.")
            parsed = parse_plan(result.stdout, input_mode="refresh_only")
            if parsed.terraform_version != self.version:
                raise ExecutionError(
                    "Terraform version changed while reading the plan."
                )
            return parsed

"""Explicit bundle builds; ordinary source/development builds stay lightweight."""

import json
import os
import runpy
from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class CustomBuildHook(BuildHookInterface):
    def initialize(self, version, build_data):
        if self.target_name != "wheel" or version == "editable":
            return
        target = os.environ.get("INFRALENS_BUNDLE_PLATFORM")
        if not target:
            return
        root = Path(self.root)
        helper = runpy.run_path(str(root / "scripts" / "bundle_trivy.py"))
        staged = root / "build" / "trivy" / target
        manifest = helper["validate_stage"](staged, target)
        build_data["pure_python"] = False
        build_data["tag"] = f"py3-none-{target}"
        marker = root / "build" / "trivy" / f"{target}.json"
        marker.write_text(json.dumps(manifest) + "\n", encoding="utf-8")
        build_data["force_include"][str(marker)] = "infralens/_bundle.json"
        build_data["force_include"][str(root / "vendor" / "README.md")] = (
            "infralens/_vendor/trivy/README.md"
        )
        for name in (
            helper["configuration"](target)[1]["executable"],
            "LICENSE",
            "manifest.json",
        ):
            build_data["force_include"][str(staged / name)] = (
                f"infralens/_vendor/trivy/{name}"
            )

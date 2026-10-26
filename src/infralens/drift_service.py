"""Shared drift collection for CLI and background backend workers."""

import os

from infralens.drift import DriftResult, parse_plan
from infralens.drift_review import enrich_review
from infralens.errors import ExecutionCancelled, ExecutionError
from infralens.options import DriftOptions
from infralens.source_locations import enrich_source_locations
from infralens.terraform import Terraform


def collect_drift(options: DriftOptions, imported: DriftResult | None = None):
    def checkpoint():
        if options.cancel is not None and options.cancel.is_set():
            raise ExecutionCancelled("Execution cancelled.")

    checkpoint()
    if imported is not None:
        result = imported
    elif options.plan_json is not None:
        try:
            payload = options.plan_json.read_text(encoding="utf-8-sig")
        except UnicodeError:
            raise ExecutionError("--plan-json: expected a UTF-8 JSON file.") from None
        result = parse_plan(payload)
    else:
        result = Terraform(options).drift()
    checkpoint()
    result = enrich_source_locations(
        result,
        options.path,
        str(options.data_dir)
        if options.data_dir is not None
        else os.environ.get("TF_DATA_DIR"),
    )
    checkpoint()
    if options.trace:
        from infralens.cloudtrail import enrich_trace

        result = enrich_trace(result, options)
    checkpoint()
    return enrich_review(result)

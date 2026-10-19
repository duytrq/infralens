"""Command boundaries; engine integration is intentionally not implemented."""

from infralens.errors import FeatureUnavailable
from infralens.options import DriftOptions, ScanOptions


def handle_scan(options: ScanOptions) -> None:
    raise FeatureUnavailable("Scan engine is not implemented.")


def handle_drift(options: DriftOptions) -> None:
    if options.trace:
        raise FeatureUnavailable("CloudTrail trace is not supported yet.")
    raise FeatureUnavailable("Drift engine is not implemented.")

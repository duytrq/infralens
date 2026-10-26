"""Compare drift findings without copying secret values or source/actor metadata."""

import json

from infralens_backend.drift_schemas import COMPARISON_STATUSES, NETWORK_FIELDS

NETWORK_RULE_FIELDS = NETWORK_FIELDS

_NOTE = (
    "No longer reported does not prove repair: state, configuration or provider "
    "coverage may have changed. Imported plans have unverified coverage/freshness."
)


def _resource_change(old, new):
    before = {tuple(item["path"]): item for item in old["attributes"]}
    after = {tuple(item["path"]): item for item in new["attributes"]}
    changed = set(before) ^ set(after)
    uncertain = False
    structural = (
        old["actions"] != new["actions"] or old["resource_type"] != new["resource_type"]
    )
    for path in set(before) & set(after):
        for side in ("before", "after"):
            left, right = before[path][side], after[path][side]
            if left["status"] in ("sensitive", "unknown") or right["status"] in (
                "sensitive",
                "unknown",
            ):
                uncertain = True
            elif json.dumps(left, sort_keys=True) != json.dumps(right, sort_keys=True):
                changed.add(path)
    if (
        old["resource_type"] in NETWORK_RULE_FIELDS
        or new["resource_type"] in NETWORK_RULE_FIELDS
    ) and new["actions"] != ["delete"]:
        left_context, right_context = (
            old.get("network_context"),
            new.get("network_context"),
        )
        if (
            not left_context
            or not right_context
            or left_context.get("version") != "security-group-rule-v1"
            or right_context.get("version") != "security-group-rule-v1"
        ):
            uncertain = True
        else:
            fields = set(NETWORK_RULE_FIELDS.get(old["resource_type"], ()))
            fields.update(NETWORK_RULE_FIELDS.get(new["resource_type"], ()))
            for side in ("before", "after"):
                for field in fields:
                    left = left_context.get(side, {}).get(field, {})
                    right = right_context.get(side, {}).get(field, {})
                    if left.get("status") in (
                        None,
                        "sensitive",
                        "unknown",
                    ) or right.get("status") in (None, "sensitive", "unknown"):
                        uncertain = True
                    elif json.dumps(left, sort_keys=True) != json.dumps(
                        right, sort_keys=True
                    ):
                        changed.add((field,))
    status = (
        "changed"
        if structural or changed
        else "indeterminate"
        if uncertain
        else "unchanged"
    )
    return status, [list(path) for path in sorted(changed)]


def compare_runs(current, baseline):
    result = {
        "current_run_id": current["id"],
        "baseline_run_id": None,
        "status": "baseline_missing",
        "resources": [],
        "summary": dict.fromkeys(COMPARISON_STATUSES, 0),
        "notes": [_NOTE],
    }
    if baseline is None:
        return result
    result.update(status="compared", baseline_run_id=baseline["id"])
    old = {r["address"]: r for r in baseline["report_json"]["resources"]}
    new = {r["address"]: r for r in current["report_json"]["resources"]}
    counts = {
        key: 0
        for key in (
            "new",
            "no_longer_reported",
            "changed",
            "unchanged",
            "indeterminate",
        )
    }
    for address in sorted(set(old) | set(new)):
        paths = []
        if address not in old:
            status = "new"
        elif address not in new:
            status = "no_longer_reported"
        else:
            status, paths = _resource_change(old[address], new[address])
        counts[status] += 1
        result["resources"].append(
            {"address": address, "status": status, "changed_paths": paths}
        )
    result["summary"] = counts
    return result

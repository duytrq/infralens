import type { DriftResource, DriftValue } from "../api/types";

export function valueText(value: DriftValue): string {
  return value.status === "known"
    ? JSON.stringify(value.value, null, 2)
    : `[${value.status}]`;
}

export function effectivePriority(resource: DriftResource) {
  return resource.assessment?.policy === "builtin-review-v2"
    ? resource.assessment.priority
    : "unknown";
}

import type { components } from "./schema";

export type DashboardConfig = components["schemas"]["DashboardConfig"];
export type Project = components["schemas"]["Project"];
export type Run = components["schemas"]["Run"];
export type Finding = components["schemas"]["Finding"];
export type FindingSummary = components["schemas"]["FindingSummary"];
export type Severity = Finding["severity"];
export type FindingCounts = Run["result"]["findings"];
export type Page<T> = { items: T[]; next_cursor: string | null };
export type Query = Record<string, string | number | null | undefined>;
export const severities: Severity[] = [
  "CRITICAL",
  "HIGH",
  "MEDIUM",
  "LOW",
  "UNKNOWN",
];

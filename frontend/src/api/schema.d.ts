// Generated from contracts/openapi.json. Do not edit.
export interface paths {
    "/v1/config": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["config"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/dashboard-config": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["dashboardConfig"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/projects": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["listProjects"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/projects/{project_id}": {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: string;
            };
            cookie?: never;
        };
        get: operations["getProject"];
        put: operations["createProject"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/runs": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["listRuns"];
        put?: never;
        post: operations["registerRun"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/runs/{run_id}": {
        parameters: {
            query?: never;
            header?: never;
            path: {
                run_id: string;
            };
            cookie?: never;
        };
        get: operations["getRun"];
        put?: never;
        post?: never;
        delete: operations["deleteRun"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/runs/{run_id}/complete": {
        parameters: {
            query?: never;
            header?: never;
            path: {
                run_id: string;
            };
            cookie?: never;
        };
        get?: never;
        put?: never;
        post: operations["completeRun"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/runs/{run_id}/artifacts/json": {
        parameters: {
            query?: never;
            header?: never;
            path: {
                run_id: string;
            };
            cookie?: never;
        };
        get: operations["downloadReport"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/runs/{run_id}/findings": {
        parameters: {
            query?: never;
            header?: never;
            path: {
                run_id: string;
            };
            cookie?: never;
        };
        get: operations["listFindings"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/runs/{run_id}/findings/{finding_id}": {
        parameters: {
            query?: never;
            header?: never;
            path: {
                run_id: string;
                finding_id: string;
            };
            cookie?: never;
        };
        get: operations["getFinding"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/runs/{run_id}/analysis/retry": {
        parameters: {
            query?: never;
            header?: never;
            path: {
                run_id: string;
            };
            cookie?: never;
        };
        get?: never;
        put?: never;
        post: operations["retryAnalysis"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/runs/{run_id}/drift/report": {
        parameters: {
            query?: never;
            header?: never;
            path: {
                run_id: string;
            };
            cookie?: never;
        };
        get: operations["getDriftReport"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/runs/{run_id}/drift/comparison": {
        parameters: {
            query?: never;
            header?: never;
            path: {
                run_id: string;
            };
            cookie?: never;
        };
        get: operations["compareDrift"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
}
export type webhooks = Record<string, never>;
export interface components {
    schemas: {
        ProjectInput: {
            name: string;
        };
        RunInput: {
            /** @constant */
            schema_version: 1;
            /** Format: uuid */
            run_id: string;
            project_id: string;
            /** @constant */
            run_type: "security_scan";
            /** Format: date-time */
            started_at: string;
            /** Format: date-time */
            finished_at: string;
            duration_ms: number;
            source: {
                relative_path: string;
                git?: {
                    commit: string;
                    branch: string | null;
                    dirty: boolean;
                };
            };
            tool: {
                infralens_version: string;
                /** @constant */
                engine: "trivy";
                engine_version: string;
                checks_version?: string;
            };
            scan_options: {
                /** @enum {unknown} */
                fail_on: null | "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
                severity: ("UNKNOWN" | "LOW" | "MEDIUM" | "HIGH" | "CRITICAL")[];
                ignore_sha256: string | null;
            };
            result: {
                /** @constant */
                scan_status: "completed";
                /** @enum {unknown} */
                threshold_status: "passed" | "failed" | "not_evaluated";
                findings: {
                    total: number;
                    by_severity: {
                        UNKNOWN: number;
                        LOW: number;
                        MEDIUM: number;
                        HIGH: number;
                        CRITICAL: number;
                    };
                };
                warnings: string[];
            };
            artifact: {
                /** @constant */
                format: "json";
                /** @constant */
                content_type: "application/json";
                size_bytes: number;
                sha256: string;
                /** @constant */
                schema_version: 2;
            };
        } | {
            /** @constant */
            schema_version: 1;
            /** Format: uuid */
            run_id: string;
            project_id: string;
            /** @constant */
            run_type: "drift";
            /** Format: date-time */
            started_at: string;
            /** Format: date-time */
            finished_at: string;
            duration_ms: number;
            source: {
                relative_path: string;
                git?: {
                    commit: string;
                    branch: string | null;
                    dirty: boolean;
                };
            };
            tool: {
                infralens_version: string;
                /** @constant */
                engine: "terraform";
                engine_version: string;
            };
            result: {
                /** @enum {unknown} */
                collection_status: "completed" | "partial";
                has_drift: boolean;
                summary: {
                    resources: number;
                    attributes: number;
                };
                priority_counts: {
                    high: number;
                    medium: number;
                    unknown: number;
                };
                /** @enum {unknown} */
                gate_status: "disabled" | "passed" | "failed" | "incomplete";
                /** @enum {unknown} */
                trace_status: "disabled" | "not_needed" | "partial" | "complete" | "error";
            };
            artifact: {
                /** @constant */
                format: "json";
                /** @constant */
                content_type: "application/json";
                size_bytes: number;
                sha256: string;
                /** @constant */
                schema_version: "1.0";
            };
            scope: string;
            drift_options: {
                /** @enum {unknown} */
                input_mode: "refresh_only" | "imported_plan";
                trace: boolean;
                lookback_days: number | null;
                gate: {
                    any_drift: boolean;
                    /** @enum {unknown} */
                    minimum_priority: null | "high" | "medium";
                    unknown_priority: boolean;
                };
            };
        };
        Project: {
            name: string;
            project_id: string;
            /** Format: date-time */
            created_at: string;
            latest_scan?: {
                /** Format: uuid */
                run_id: string;
                /** Format: date-time */
                started_at: string;
                /** Format: date-time */
                finished_at: string;
                result: {
                    /** @constant */
                    scan_status: "completed";
                    /** @enum {unknown} */
                    threshold_status: "passed" | "failed" | "not_evaluated";
                    findings: {
                        total: number;
                        by_severity: {
                            UNKNOWN: number;
                            LOW: number;
                            MEDIUM: number;
                            HIGH: number;
                            CRITICAL: number;
                        };
                    };
                    warnings: string[];
                };
            } | null;
            latest_drift?: {
                /** Format: uuid */
                run_id: string;
                /** Format: date-time */
                started_at: string;
                /** Format: date-time */
                finished_at: string;
                scope: string;
                result: {
                    /** @enum {unknown} */
                    collection_status: "completed" | "partial";
                    has_drift: boolean;
                    summary: {
                        resources: number;
                        attributes: number;
                    };
                    priority_counts: {
                        high: number;
                        medium: number;
                        unknown: number;
                    };
                    /** @enum {unknown} */
                    gate_status: "disabled" | "passed" | "failed" | "incomplete";
                    /** @enum {unknown} */
                    trace_status: "disabled" | "not_needed" | "partial" | "complete" | "error";
                };
                /** @enum {unknown} */
                input_mode: "refresh_only" | "imported_plan";
            } | null;
        };
        Run: {
            /** @constant */
            schema_version: 1;
            /** Format: uuid */
            run_id: string;
            project_id: string;
            /** @constant */
            run_type: "security_scan";
            /** Format: date-time */
            started_at: string;
            /** Format: date-time */
            finished_at: string;
            duration_ms: number;
            source: {
                relative_path: string;
                git?: {
                    commit: string;
                    branch: string | null;
                    dirty: boolean;
                };
            };
            tool: {
                infralens_version: string;
                /** @constant */
                engine: "trivy";
                engine_version: string;
                checks_version?: string;
            };
            scan_options: {
                /** @enum {unknown} */
                fail_on: null | "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
                severity: ("UNKNOWN" | "LOW" | "MEDIUM" | "HIGH" | "CRITICAL")[];
                ignore_sha256: string | null;
            };
            result: {
                /** @constant */
                scan_status: "completed";
                /** @enum {unknown} */
                threshold_status: "passed" | "failed" | "not_evaluated";
                findings: {
                    total: number;
                    by_severity: {
                        UNKNOWN: number;
                        LOW: number;
                        MEDIUM: number;
                        HIGH: number;
                        CRITICAL: number;
                    };
                };
                warnings: string[];
            };
            artifact: {
                /** @constant */
                format: "json";
                /** @constant */
                content_type: "application/json";
                size_bytes: number;
                sha256: string;
                /** @constant */
                schema_version: 2;
            };
            /** Format: date-time */
            received_at: string;
            uploaded_at: string | null;
            /** @enum {unknown} */
            upload_status: "pending" | "ready";
            analysis?: {
                /** @enum {unknown} */
                status: "pending" | "ready" | "failed";
                version: number;
                /** Format: uuid */
                build_id: string;
                /** Format: date-time */
                requested_at: string;
                completed_at: string | null;
                findings: {
                    total: number;
                    by_severity: {
                        UNKNOWN: number;
                        LOW: number;
                        MEDIUM: number;
                        HIGH: number;
                        CRITICAL: number;
                    };
                } | null;
                counts_match: boolean | null;
                error_code: string | null;
            };
        } | {
            /** @constant */
            schema_version: 1;
            /** Format: uuid */
            run_id: string;
            project_id: string;
            /** @constant */
            run_type: "drift";
            /** Format: date-time */
            started_at: string;
            /** Format: date-time */
            finished_at: string;
            duration_ms: number;
            source: {
                relative_path: string;
                git?: {
                    commit: string;
                    branch: string | null;
                    dirty: boolean;
                };
            };
            tool: {
                infralens_version: string;
                /** @constant */
                engine: "terraform";
                engine_version: string;
            };
            result: {
                /** @enum {unknown} */
                collection_status: "completed" | "partial";
                has_drift: boolean;
                summary: {
                    resources: number;
                    attributes: number;
                };
                priority_counts: {
                    high: number;
                    medium: number;
                    unknown: number;
                };
                /** @enum {unknown} */
                gate_status: "disabled" | "passed" | "failed" | "incomplete";
                /** @enum {unknown} */
                trace_status: "disabled" | "not_needed" | "partial" | "complete" | "error";
            };
            artifact: {
                /** @constant */
                format: "json";
                /** @constant */
                content_type: "application/json";
                size_bytes: number;
                sha256: string;
                /** @constant */
                schema_version: "1.0";
            };
            scope: string;
            drift_options: {
                /** @enum {unknown} */
                input_mode: "refresh_only" | "imported_plan";
                trace: boolean;
                lookback_days: number | null;
                gate: {
                    any_drift: boolean;
                    /** @enum {unknown} */
                    minimum_priority: null | "high" | "medium";
                    unknown_priority: boolean;
                };
            };
            /** Format: date-time */
            received_at: string;
            uploaded_at: string | null;
            /** @enum {unknown} */
            upload_status: "pending" | "ready";
        };
        SecurityRun: {
            /** @constant */
            schema_version: 1;
            /** Format: uuid */
            run_id: string;
            project_id: string;
            /** @constant */
            run_type: "security_scan";
            /** Format: date-time */
            started_at: string;
            /** Format: date-time */
            finished_at: string;
            duration_ms: number;
            source: {
                relative_path: string;
                git?: {
                    commit: string;
                    branch: string | null;
                    dirty: boolean;
                };
            };
            tool: {
                infralens_version: string;
                /** @constant */
                engine: "trivy";
                engine_version: string;
                checks_version?: string;
            };
            scan_options: {
                /** @enum {unknown} */
                fail_on: null | "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
                severity: ("UNKNOWN" | "LOW" | "MEDIUM" | "HIGH" | "CRITICAL")[];
                ignore_sha256: string | null;
            };
            result: {
                /** @constant */
                scan_status: "completed";
                /** @enum {unknown} */
                threshold_status: "passed" | "failed" | "not_evaluated";
                findings: {
                    total: number;
                    by_severity: {
                        UNKNOWN: number;
                        LOW: number;
                        MEDIUM: number;
                        HIGH: number;
                        CRITICAL: number;
                    };
                };
                warnings: string[];
            };
            artifact: {
                /** @constant */
                format: "json";
                /** @constant */
                content_type: "application/json";
                size_bytes: number;
                sha256: string;
                /** @constant */
                schema_version: 2;
            };
            /** Format: date-time */
            received_at: string;
            uploaded_at: string | null;
            /** @enum {unknown} */
            upload_status: "pending" | "ready";
            analysis?: {
                /** @enum {unknown} */
                status: "pending" | "ready" | "failed";
                version: number;
                /** Format: uuid */
                build_id: string;
                /** Format: date-time */
                requested_at: string;
                completed_at: string | null;
                findings: {
                    total: number;
                    by_severity: {
                        UNKNOWN: number;
                        LOW: number;
                        MEDIUM: number;
                        HIGH: number;
                        CRITICAL: number;
                    };
                } | null;
                counts_match: boolean | null;
                error_code: string | null;
            };
        };
        DriftRun: {
            /** @constant */
            schema_version: 1;
            /** Format: uuid */
            run_id: string;
            project_id: string;
            /** @constant */
            run_type: "drift";
            /** Format: date-time */
            started_at: string;
            /** Format: date-time */
            finished_at: string;
            duration_ms: number;
            source: {
                relative_path: string;
                git?: {
                    commit: string;
                    branch: string | null;
                    dirty: boolean;
                };
            };
            tool: {
                infralens_version: string;
                /** @constant */
                engine: "terraform";
                engine_version: string;
            };
            result: {
                /** @enum {unknown} */
                collection_status: "completed" | "partial";
                has_drift: boolean;
                summary: {
                    resources: number;
                    attributes: number;
                };
                priority_counts: {
                    high: number;
                    medium: number;
                    unknown: number;
                };
                /** @enum {unknown} */
                gate_status: "disabled" | "passed" | "failed" | "incomplete";
                /** @enum {unknown} */
                trace_status: "disabled" | "not_needed" | "partial" | "complete" | "error";
            };
            artifact: {
                /** @constant */
                format: "json";
                /** @constant */
                content_type: "application/json";
                size_bytes: number;
                sha256: string;
                /** @constant */
                schema_version: "1.0";
            };
            scope: string;
            drift_options: {
                /** @enum {unknown} */
                input_mode: "refresh_only" | "imported_plan";
                trace: boolean;
                lookback_days: number | null;
                gate: {
                    any_drift: boolean;
                    /** @enum {unknown} */
                    minimum_priority: null | "high" | "medium";
                    unknown_priority: boolean;
                };
            };
            /** Format: date-time */
            received_at: string;
            uploaded_at: string | null;
            /** @enum {unknown} */
            upload_status: "pending" | "ready";
        };
        DriftReport: {
            /** @constant */
            schema_version: "1.0";
            /** @constant */
            kind: "drift";
            terraform_version: string;
            /** @enum {unknown} */
            input_mode: "refresh_only" | "imported_plan";
            /** Format: date-time */
            checked_at: string;
            has_drift: boolean;
            summary: {
                resources: number;
                attributes: number;
            };
            resources: {
                address: string;
                resource_type: string;
                /** @enum {unknown} */
                actions: [
                    "update"
                ] | [
                    "delete"
                ];
                attributes: {
                    path: string[];
                    before: {
                        /** @constant */
                        status: "known";
                        value: unknown;
                        /** @enum {unknown} */
                        source?: "saved" | "observed";
                    } | {
                        /** @enum {unknown} */
                        status: "sensitive" | "unknown" | "absent";
                    };
                    after: {
                        /** @constant */
                        status: "known";
                        value: unknown;
                        /** @enum {unknown} */
                        source?: "saved" | "observed";
                    } | {
                        /** @enum {unknown} */
                        status: "sensitive" | "unknown" | "absent";
                    };
                }[];
                identifiers: {
                    id?: {
                        /** @constant */
                        status: "known";
                        value: unknown;
                        /** @enum {unknown} */
                        source?: "saved" | "observed";
                    } | {
                        /** @enum {unknown} */
                        status: "sensitive" | "unknown" | "absent";
                    };
                    arn?: {
                        /** @constant */
                        status: "known";
                        value: unknown;
                        /** @enum {unknown} */
                        source?: "saved" | "observed";
                    } | {
                        /** @enum {unknown} */
                        status: "sensitive" | "unknown" | "absent";
                    };
                    security_group_id?: {
                        /** @constant */
                        status: "known";
                        value: unknown;
                        /** @enum {unknown} */
                        source?: "saved" | "observed";
                    } | {
                        /** @enum {unknown} */
                        status: "sensitive" | "unknown" | "absent";
                    };
                    security_group_rule_id?: {
                        /** @constant */
                        status: "known";
                        value: unknown;
                        /** @enum {unknown} */
                        source?: "saved" | "observed";
                    } | {
                        /** @enum {unknown} */
                        status: "sensitive" | "unknown" | "absent";
                    };
                };
                source?: {
                    /** @enum {unknown} */
                    status: "located" | "ambiguous" | "unavailable";
                    /** @constant */
                    context: "current_configuration";
                    block_address?: string;
                    reason?: string;
                    locations?: {
                        file: string;
                        start_line: number;
                        end_line: number;
                        /** @enum {unknown} */
                        syntax: "hcl" | "json";
                    }[];
                };
                assessment?: {
                    policy: string;
                    /** @enum {unknown} */
                    priority: "high" | "medium" | "unknown";
                    signals: {
                        code: string;
                        /** @enum {unknown} */
                        priority: "high" | "medium" | "unknown";
                        description: string;
                        paths: string[][];
                    }[];
                    guidance: {
                        review_steps: string[];
                        choices: {
                            id: string;
                            title: string;
                            steps: string[];
                        }[];
                    };
                };
                trace?: {
                    /** @enum {unknown} */
                    status: "matched" | "no_events" | "partial" | "skipped" | "error";
                    events: {
                        event_id: string;
                        event_name: string;
                        event_source: string;
                        /** Format: date-time */
                        event_time: string;
                        region: string;
                        actor: {
                            type?: string;
                            arn?: string;
                            userName?: string;
                            invokedBy?: string;
                            session_issuer_arn?: string;
                        };
                        matched_attributes: string[];
                        /** @constant */
                        relation: "candidate";
                    }[];
                    reason?: string;
                    pages_scanned?: number;
                    truncated?: boolean;
                    malformed_events?: number;
                    unsupported_attributes?: string[];
                    /** @constant */
                    correlation?: "exact_rule_id";
                    /** @constant */
                    lookup_scope?: "parent_security_group";
                    unresolved_rule_events?: number;
                };
                network_context?: {
                    /** @constant */
                    version: "security-group-rule-v1";
                    before: {
                        cidr_blocks?: {
                            /** @constant */
                            status: "known";
                            value: unknown;
                            /** @enum {unknown} */
                            source?: "saved" | "observed";
                        } | {
                            /** @enum {unknown} */
                            status: "sensitive" | "unknown" | "absent";
                        };
                        cidr_ipv4?: {
                            /** @constant */
                            status: "known";
                            value: unknown;
                            /** @enum {unknown} */
                            source?: "saved" | "observed";
                        } | {
                            /** @enum {unknown} */
                            status: "sensitive" | "unknown" | "absent";
                        };
                        cidr_ipv6?: {
                            /** @constant */
                            status: "known";
                            value: unknown;
                            /** @enum {unknown} */
                            source?: "saved" | "observed";
                        } | {
                            /** @enum {unknown} */
                            status: "sensitive" | "unknown" | "absent";
                        };
                        from_port?: {
                            /** @constant */
                            status: "known";
                            value: unknown;
                            /** @enum {unknown} */
                            source?: "saved" | "observed";
                        } | {
                            /** @enum {unknown} */
                            status: "sensitive" | "unknown" | "absent";
                        };
                        ip_protocol?: {
                            /** @constant */
                            status: "known";
                            value: unknown;
                            /** @enum {unknown} */
                            source?: "saved" | "observed";
                        } | {
                            /** @enum {unknown} */
                            status: "sensitive" | "unknown" | "absent";
                        };
                        ipv6_cidr_blocks?: {
                            /** @constant */
                            status: "known";
                            value: unknown;
                            /** @enum {unknown} */
                            source?: "saved" | "observed";
                        } | {
                            /** @enum {unknown} */
                            status: "sensitive" | "unknown" | "absent";
                        };
                        prefix_list_id?: {
                            /** @constant */
                            status: "known";
                            value: unknown;
                            /** @enum {unknown} */
                            source?: "saved" | "observed";
                        } | {
                            /** @enum {unknown} */
                            status: "sensitive" | "unknown" | "absent";
                        };
                        prefix_list_ids?: {
                            /** @constant */
                            status: "known";
                            value: unknown;
                            /** @enum {unknown} */
                            source?: "saved" | "observed";
                        } | {
                            /** @enum {unknown} */
                            status: "sensitive" | "unknown" | "absent";
                        };
                        protocol?: {
                            /** @constant */
                            status: "known";
                            value: unknown;
                            /** @enum {unknown} */
                            source?: "saved" | "observed";
                        } | {
                            /** @enum {unknown} */
                            status: "sensitive" | "unknown" | "absent";
                        };
                        referenced_security_group_id?: {
                            /** @constant */
                            status: "known";
                            value: unknown;
                            /** @enum {unknown} */
                            source?: "saved" | "observed";
                        } | {
                            /** @enum {unknown} */
                            status: "sensitive" | "unknown" | "absent";
                        };
                        region?: {
                            /** @constant */
                            status: "known";
                            value: unknown;
                            /** @enum {unknown} */
                            source?: "saved" | "observed";
                        } | {
                            /** @enum {unknown} */
                            status: "sensitive" | "unknown" | "absent";
                        };
                        security_group_id?: {
                            /** @constant */
                            status: "known";
                            value: unknown;
                            /** @enum {unknown} */
                            source?: "saved" | "observed";
                        } | {
                            /** @enum {unknown} */
                            status: "sensitive" | "unknown" | "absent";
                        };
                        self?: {
                            /** @constant */
                            status: "known";
                            value: unknown;
                            /** @enum {unknown} */
                            source?: "saved" | "observed";
                        } | {
                            /** @enum {unknown} */
                            status: "sensitive" | "unknown" | "absent";
                        };
                        source_security_group_id?: {
                            /** @constant */
                            status: "known";
                            value: unknown;
                            /** @enum {unknown} */
                            source?: "saved" | "observed";
                        } | {
                            /** @enum {unknown} */
                            status: "sensitive" | "unknown" | "absent";
                        };
                        to_port?: {
                            /** @constant */
                            status: "known";
                            value: unknown;
                            /** @enum {unknown} */
                            source?: "saved" | "observed";
                        } | {
                            /** @enum {unknown} */
                            status: "sensitive" | "unknown" | "absent";
                        };
                        type?: {
                            /** @constant */
                            status: "known";
                            value: unknown;
                            /** @enum {unknown} */
                            source?: "saved" | "observed";
                        } | {
                            /** @enum {unknown} */
                            status: "sensitive" | "unknown" | "absent";
                        };
                    };
                    after: {
                        cidr_blocks?: {
                            /** @constant */
                            status: "known";
                            value: unknown;
                            /** @enum {unknown} */
                            source?: "saved" | "observed";
                        } | {
                            /** @enum {unknown} */
                            status: "sensitive" | "unknown" | "absent";
                        };
                        cidr_ipv4?: {
                            /** @constant */
                            status: "known";
                            value: unknown;
                            /** @enum {unknown} */
                            source?: "saved" | "observed";
                        } | {
                            /** @enum {unknown} */
                            status: "sensitive" | "unknown" | "absent";
                        };
                        cidr_ipv6?: {
                            /** @constant */
                            status: "known";
                            value: unknown;
                            /** @enum {unknown} */
                            source?: "saved" | "observed";
                        } | {
                            /** @enum {unknown} */
                            status: "sensitive" | "unknown" | "absent";
                        };
                        from_port?: {
                            /** @constant */
                            status: "known";
                            value: unknown;
                            /** @enum {unknown} */
                            source?: "saved" | "observed";
                        } | {
                            /** @enum {unknown} */
                            status: "sensitive" | "unknown" | "absent";
                        };
                        ip_protocol?: {
                            /** @constant */
                            status: "known";
                            value: unknown;
                            /** @enum {unknown} */
                            source?: "saved" | "observed";
                        } | {
                            /** @enum {unknown} */
                            status: "sensitive" | "unknown" | "absent";
                        };
                        ipv6_cidr_blocks?: {
                            /** @constant */
                            status: "known";
                            value: unknown;
                            /** @enum {unknown} */
                            source?: "saved" | "observed";
                        } | {
                            /** @enum {unknown} */
                            status: "sensitive" | "unknown" | "absent";
                        };
                        prefix_list_id?: {
                            /** @constant */
                            status: "known";
                            value: unknown;
                            /** @enum {unknown} */
                            source?: "saved" | "observed";
                        } | {
                            /** @enum {unknown} */
                            status: "sensitive" | "unknown" | "absent";
                        };
                        prefix_list_ids?: {
                            /** @constant */
                            status: "known";
                            value: unknown;
                            /** @enum {unknown} */
                            source?: "saved" | "observed";
                        } | {
                            /** @enum {unknown} */
                            status: "sensitive" | "unknown" | "absent";
                        };
                        protocol?: {
                            /** @constant */
                            status: "known";
                            value: unknown;
                            /** @enum {unknown} */
                            source?: "saved" | "observed";
                        } | {
                            /** @enum {unknown} */
                            status: "sensitive" | "unknown" | "absent";
                        };
                        referenced_security_group_id?: {
                            /** @constant */
                            status: "known";
                            value: unknown;
                            /** @enum {unknown} */
                            source?: "saved" | "observed";
                        } | {
                            /** @enum {unknown} */
                            status: "sensitive" | "unknown" | "absent";
                        };
                        region?: {
                            /** @constant */
                            status: "known";
                            value: unknown;
                            /** @enum {unknown} */
                            source?: "saved" | "observed";
                        } | {
                            /** @enum {unknown} */
                            status: "sensitive" | "unknown" | "absent";
                        };
                        security_group_id?: {
                            /** @constant */
                            status: "known";
                            value: unknown;
                            /** @enum {unknown} */
                            source?: "saved" | "observed";
                        } | {
                            /** @enum {unknown} */
                            status: "sensitive" | "unknown" | "absent";
                        };
                        self?: {
                            /** @constant */
                            status: "known";
                            value: unknown;
                            /** @enum {unknown} */
                            source?: "saved" | "observed";
                        } | {
                            /** @enum {unknown} */
                            status: "sensitive" | "unknown" | "absent";
                        };
                        source_security_group_id?: {
                            /** @constant */
                            status: "known";
                            value: unknown;
                            /** @enum {unknown} */
                            source?: "saved" | "observed";
                        } | {
                            /** @enum {unknown} */
                            status: "sensitive" | "unknown" | "absent";
                        };
                        to_port?: {
                            /** @constant */
                            status: "known";
                            value: unknown;
                            /** @enum {unknown} */
                            source?: "saved" | "observed";
                        } | {
                            /** @enum {unknown} */
                            status: "sensitive" | "unknown" | "absent";
                        };
                        type?: {
                            /** @constant */
                            status: "known";
                            value: unknown;
                            /** @enum {unknown} */
                            source?: "saved" | "observed";
                        } | {
                            /** @enum {unknown} */
                            status: "sensitive" | "unknown" | "absent";
                        };
                    };
                };
            }[];
            normalizations: {
                address: string;
                path: (string | number)[];
                reason: string;
            }[];
            notes: string[];
            trace?: {
                /** @enum {unknown} */
                status: "not_needed" | "partial" | "complete" | "error";
                has_errors: boolean;
                message?: string;
                /** Format: date-time */
                start_time?: string;
                /** Format: date-time */
                end_time?: string;
                max_resources?: number;
                max_pages_per_resource?: number;
                account_id?: string;
                region?: string;
            };
            gate?: {
                /** @constant */
                policy: "drift-gate-v1";
                /** @constant */
                review_policy: "builtin-review-v2";
                /** @enum {unknown} */
                status: "passed" | "failed" | "incomplete";
                /** @enum {unknown} */
                exit_code: 0 | 1 | 3;
                criteria: {
                    any_drift: boolean;
                    /** @enum {unknown} */
                    minimum_priority: null | "high" | "medium";
                    unknown_priority: boolean;
                };
                priority_counts: {
                    high: number;
                    medium: number;
                    unknown: number;
                };
                unassessed_resources: number;
                matched_count: number;
                matched_resources: {
                    address: string;
                    /** @enum {unknown} */
                    priority: "high" | "medium" | "unknown";
                    reasons: ("any_drift" | "priority_threshold" | "unknown_priority")[];
                }[];
                reason_codes: string[];
            };
            review_summary?: {
                policy: string;
                priority_counts: {
                    high: number;
                    medium: number;
                    unknown: number;
                };
            };
        };
        DriftComparison: {
            current_run_id: string;
            baseline_run_id: string | null;
            /** @enum {unknown} */
            status: "baseline_missing" | "compared";
            resources: {
                address: string;
                /** @enum {unknown} */
                status: "new" | "no_longer_reported" | "changed" | "unchanged" | "indeterminate";
                changed_paths: string[][];
            }[];
            summary: {
                new: number;
                no_longer_reported: number;
                changed: number;
                unchanged: number;
                indeterminate: number;
            };
            notes: string[];
            next_cursor: string | null;
        };
        Analysis: {
            /** @enum {unknown} */
            status: "pending" | "ready" | "failed";
            version: number;
            /** Format: uuid */
            build_id: string;
            /** Format: date-time */
            requested_at: string;
            completed_at: string | null;
            findings: {
                total: number;
                by_severity: {
                    UNKNOWN: number;
                    LOW: number;
                    MEDIUM: number;
                    HIGH: number;
                    CRITICAL: number;
                };
            } | null;
            counts_match: boolean | null;
            error_code: string | null;
        };
        Finding: {
            finding_id: string;
            rule_id: string;
            /** @enum {unknown} */
            severity: "UNKNOWN" | "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
            title: string;
            file: string | null;
            resource: string | null;
            start_line: number | null;
            end_line: number | null;
            truncated_fields: string[];
            message: string;
            description: string;
            resolution: string;
            references: string[];
            code: {
                number: number;
                content: string;
                is_cause: boolean;
            }[];
        };
        FindingSummary: {
            finding_id: string;
            rule_id: string;
            /** @enum {unknown} */
            severity: "UNKNOWN" | "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
            title: string;
            file: string | null;
            resource: string | null;
            start_line: number | null;
            end_line: number | null;
            truncated_fields: string[];
        };
        FindingPage: {
            items: components["schemas"]["FindingSummary"][];
            next_cursor: string | null;
        };
        ProjectPage: {
            items: components["schemas"]["Project"][];
            next_cursor: string | null;
        };
        RunPage: {
            items: components["schemas"]["Run"][];
            next_cursor: string | null;
        };
        Upload: {
            /** Format: uri */
            url: string;
            /** @constant */
            method: "PUT";
            /** Format: date-time */
            expires_at: string;
            headers: {
                [key: string]: string;
            };
        };
        Registration: {
            run: components["schemas"]["Run"];
            upload: components["schemas"]["Upload"] | null;
        };
        Download: {
            /** Format: uri */
            url: string;
            /** Format: date-time */
            expires_at: string;
        };
        Deletion: {
            run_id: string;
            /** @constant */
            upload_status: "deleting";
            /** Format: date-time */
            delete_after: string;
        };
        Error: {
            error: {
                code: string;
                message: string;
            };
        };
        GatewayError: {
            error: {
                code: string;
                message: string;
            };
        } | {
            message: string;
        };
        Config: {
            /** @constant */
            schema_version: 1;
            /** @constant */
            api_version: "v1";
            auth: {
                issuer: string;
                client_id: string;
                authorization_endpoint: string;
                token_endpoint: string;
                revocation_endpoint: string;
                callback_url: string;
                scopes: string[];
                /** @constant */
                pkce_method: "S256";
            };
            upload: {
                /** @constant */
                formats: [
                    "json"
                ];
                max_report_bytes: number;
                max_drift_report_bytes: number;
                url_expires_seconds: number;
            };
        };
        DashboardConfig: {
            /** @constant */
            schema_version: 1;
            /** @constant */
            api_version: "v1";
            auth: {
                issuer: string;
                client_id: string;
                authorization_endpoint: string;
                token_endpoint: string;
                revocation_endpoint: string;
                callback_url: string;
                scopes: string[];
                /** @constant */
                pkce_method: "S256";
                logout_url: string;
                logout_endpoint: string;
                allowed_origins: string[];
            };
            upload: {
                /** @constant */
                formats: [
                    "json"
                ];
                max_report_bytes: number;
                max_drift_report_bytes: number;
                url_expires_seconds: number;
            };
        };
    };
    responses: never;
    parameters: never;
    requestBodies: never;
    headers: never;
    pathItems: never;
}
export type $defs = Record<string, never>;
export interface operations {
    config: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Success */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Config"];
                };
            };
            /** @description Invalid JSON */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Invalid or missing access token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
            /** @description Access token has insufficient scopes */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
            /** @description Resource not found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Conflict; retry or check upload state */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Metadata exceeds 64 KiB */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
            /** @description Unsupported media type */
            415: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Invalid metadata or query */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Throttled */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
            /** @description Internal error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
            /** @description Gateway integration failed */
            502: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
            /** @description Dependency unavailable; retry later */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Gateway integration timed out */
            504: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
        };
    };
    dashboardConfig: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Success */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DashboardConfig"];
                };
            };
            /** @description Invalid JSON */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Invalid or missing access token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
            /** @description Access token has insufficient scopes */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
            /** @description Resource not found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Conflict; retry or check upload state */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Metadata exceeds 64 KiB */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
            /** @description Unsupported media type */
            415: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Invalid metadata or query */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Throttled */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
            /** @description Internal error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
            /** @description Gateway integration failed */
            502: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
            /** @description Dependency unavailable; retry later */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Gateway integration timed out */
            504: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
        };
    };
    listProjects: {
        parameters: {
            query?: {
                limit?: number;
                cursor?: string;
                include?: "latest_scan" | "latest_drift" | "latest_scan,latest_drift" | "latest_drift,latest_scan";
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Success */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProjectPage"];
                };
            };
            /** @description Invalid JSON */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Invalid or missing access token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
            /** @description Access token has insufficient scopes */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
            /** @description Resource not found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Conflict; retry or check upload state */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Metadata exceeds 64 KiB */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
            /** @description Unsupported media type */
            415: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Invalid metadata or query */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Throttled */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
            /** @description Internal error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
            /** @description Gateway integration failed */
            502: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
            /** @description Dependency unavailable; retry later */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Gateway integration timed out */
            504: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
        };
    };
    getProject: {
        parameters: {
            query?: {
                include?: "latest_scan" | "latest_drift" | "latest_scan,latest_drift" | "latest_drift,latest_scan";
            };
            header?: never;
            path: {
                project_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Success */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Project"];
                };
            };
            /** @description Invalid JSON */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Invalid or missing access token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
            /** @description Access token has insufficient scopes */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
            /** @description Resource not found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Conflict; retry or check upload state */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Metadata exceeds 64 KiB */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
            /** @description Unsupported media type */
            415: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Invalid metadata or query */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Throttled */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
            /** @description Internal error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
            /** @description Gateway integration failed */
            502: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
            /** @description Dependency unavailable; retry later */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Gateway integration timed out */
            504: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
        };
    };
    createProject: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                project_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ProjectInput"];
            };
        };
        responses: {
            /** @description Success */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Project"];
                };
            };
            /** @description Success */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Project"];
                };
            };
            /** @description Invalid JSON */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Invalid or missing access token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
            /** @description Access token has insufficient scopes */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
            /** @description Resource not found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Conflict; retry or check upload state */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Metadata exceeds 64 KiB */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
            /** @description Unsupported media type */
            415: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Invalid metadata or query */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Throttled */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
            /** @description Internal error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
            /** @description Gateway integration failed */
            502: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
            /** @description Dependency unavailable; retry later */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Gateway integration timed out */
            504: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
        };
    };
    listRuns: {
        parameters: {
            query?: {
                limit?: number;
                cursor?: string;
                project_id?: string;
                from?: string;
                to?: string;
                run_type?: "security_scan" | "drift";
                scope?: string;
                gate_status?: "disabled" | "passed" | "failed" | "incomplete";
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Success */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RunPage"];
                };
            };
            /** @description Invalid JSON */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Invalid or missing access token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
            /** @description Access token has insufficient scopes */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
            /** @description Resource not found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Conflict; retry or check upload state */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Metadata exceeds 64 KiB */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
            /** @description Unsupported media type */
            415: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Invalid metadata or query */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Throttled */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
            /** @description Internal error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
            /** @description Gateway integration failed */
            502: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
            /** @description Dependency unavailable; retry later */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Gateway integration timed out */
            504: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
        };
    };
    registerRun: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RunInput"];
            };
        };
        responses: {
            /** @description Success */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Registration"];
                };
            };
            /** @description Success */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Registration"];
                };
            };
            /** @description Invalid JSON */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Invalid or missing access token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
            /** @description Access token has insufficient scopes */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
            /** @description Resource not found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Conflict; retry or check upload state */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Metadata exceeds 64 KiB */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
            /** @description Unsupported media type */
            415: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Invalid metadata or query */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Throttled */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
            /** @description Internal error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
            /** @description Gateway integration failed */
            502: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
            /** @description Dependency unavailable; retry later */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Gateway integration timed out */
            504: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
        };
    };
    getRun: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                run_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Success */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Run"];
                };
            };
            /** @description Invalid JSON */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Invalid or missing access token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
            /** @description Access token has insufficient scopes */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
            /** @description Resource not found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Conflict; retry or check upload state */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Metadata exceeds 64 KiB */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
            /** @description Unsupported media type */
            415: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Invalid metadata or query */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Throttled */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
            /** @description Internal error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
            /** @description Gateway integration failed */
            502: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
            /** @description Dependency unavailable; retry later */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Gateway integration timed out */
            504: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
        };
    };
    deleteRun: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                run_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Success */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Deletion"];
                };
            };
            /** @description Deleted */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Invalid JSON */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Invalid or missing access token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
            /** @description Access token has insufficient scopes */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
            /** @description Resource not found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Conflict; retry or check upload state */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Metadata exceeds 64 KiB */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
            /** @description Unsupported media type */
            415: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Invalid metadata or query */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Throttled */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
            /** @description Internal error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
            /** @description Gateway integration failed */
            502: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
            /** @description Dependency unavailable; retry later */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Gateway integration timed out */
            504: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
        };
    };
    completeRun: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                run_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Success */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Run"];
                };
            };
            /** @description Invalid JSON */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Invalid or missing access token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
            /** @description Access token has insufficient scopes */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
            /** @description Resource not found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Conflict; retry or check upload state */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Metadata exceeds 64 KiB */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
            /** @description Unsupported media type */
            415: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Invalid metadata or query */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Throttled */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
            /** @description Internal error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
            /** @description Gateway integration failed */
            502: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
            /** @description Dependency unavailable; retry later */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Gateway integration timed out */
            504: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
        };
    };
    downloadReport: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                run_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Success */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Download"];
                };
            };
            /** @description Invalid JSON */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Invalid or missing access token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
            /** @description Access token has insufficient scopes */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
            /** @description Resource not found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Conflict; retry or check upload state */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Metadata exceeds 64 KiB */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
            /** @description Unsupported media type */
            415: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Invalid metadata or query */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Throttled */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
            /** @description Internal error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
            /** @description Gateway integration failed */
            502: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
            /** @description Dependency unavailable; retry later */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Gateway integration timed out */
            504: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
        };
    };
    listFindings: {
        parameters: {
            query?: {
                limit?: number;
                cursor?: string;
                severity?: "UNKNOWN" | "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
                rule_id?: string;
                file?: string;
            };
            header?: never;
            path: {
                run_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Success */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["FindingPage"];
                };
            };
            /** @description Invalid JSON */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Invalid or missing access token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
            /** @description Access token has insufficient scopes */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
            /** @description Resource not found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Conflict; retry or check upload state */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Metadata exceeds 64 KiB */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
            /** @description Unsupported media type */
            415: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Invalid metadata or query */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Throttled */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
            /** @description Internal error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
            /** @description Gateway integration failed */
            502: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
            /** @description Dependency unavailable; retry later */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Gateway integration timed out */
            504: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
        };
    };
    getFinding: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                run_id: string;
                finding_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Success */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Finding"];
                };
            };
            /** @description Invalid JSON */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Invalid or missing access token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
            /** @description Access token has insufficient scopes */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
            /** @description Resource not found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Conflict; retry or check upload state */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Metadata exceeds 64 KiB */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
            /** @description Unsupported media type */
            415: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Invalid metadata or query */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Throttled */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
            /** @description Internal error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
            /** @description Gateway integration failed */
            502: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
            /** @description Dependency unavailable; retry later */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Gateway integration timed out */
            504: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
        };
    };
    retryAnalysis: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                run_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Success */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Run"];
                };
            };
            /** @description Success */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Run"];
                };
            };
            /** @description Invalid JSON */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Invalid or missing access token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
            /** @description Access token has insufficient scopes */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
            /** @description Resource not found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Conflict; retry or check upload state */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Metadata exceeds 64 KiB */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
            /** @description Unsupported media type */
            415: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Invalid metadata or query */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Throttled */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
            /** @description Internal error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
            /** @description Gateway integration failed */
            502: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
            /** @description Dependency unavailable; retry later */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Gateway integration timed out */
            504: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
        };
    };
    getDriftReport: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                run_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Success */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DriftReport"];
                };
            };
            /** @description Invalid JSON */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Invalid or missing access token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
            /** @description Access token has insufficient scopes */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
            /** @description Resource not found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Conflict; retry or check upload state */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Metadata exceeds 64 KiB */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
            /** @description Unsupported media type */
            415: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Invalid metadata or query */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Throttled */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
            /** @description Internal error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
            /** @description Gateway integration failed */
            502: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
            /** @description Dependency unavailable; retry later */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Gateway integration timed out */
            504: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
        };
    };
    compareDrift: {
        parameters: {
            query?: {
                limit?: number;
                cursor?: string;
                baseline_id?: string;
            };
            header?: never;
            path: {
                run_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Success */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DriftComparison"];
                };
            };
            /** @description Invalid JSON */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Invalid or missing access token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
            /** @description Access token has insufficient scopes */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
            /** @description Resource not found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Conflict; retry or check upload state */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Metadata exceeds 64 KiB */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
            /** @description Unsupported media type */
            415: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Invalid metadata or query */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Throttled */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
            /** @description Internal error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
            /** @description Gateway integration failed */
            502: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
            /** @description Dependency unavailable; retry later */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Gateway integration timed out */
            504: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayError"];
                };
            };
        };
    };
}

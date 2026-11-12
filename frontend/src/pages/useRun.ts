import { useQuery } from "@tanstack/react-query";
import { useSession } from "../auth/AuthProvider";
import type { Run } from "../api/types";
import { analysisPolling } from "./scan-state";

export function useRun(runId: string) {
  const { api, user } = useSession();
  return useQuery({
    queryKey: ["user", user.profile.sub, "run", runId],
    queryFn: ({ signal }) =>
      api.request<Run>(`/v1/runs/${encodeURIComponent(runId)}`, { signal }),
    refetchInterval: (query) =>
      analysisPolling(
        query.state.data,
        Math.max(0, query.state.dataUpdateCount - 1),
      ),
    refetchIntervalInBackground: false,
  });
}

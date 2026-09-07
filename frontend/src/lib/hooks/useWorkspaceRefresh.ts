import { useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { onWorkspaceChanged } from "@/lib/workspaceEvents";

/**
 * Bridges the legacy `workspace:refresh` window event (fired by the chat after
 * it creates/edits workspace entities) into TanStack Query cache invalidation.
 *
 * Mounted once in `AppLayout`, which is the parent of every route. It used to
 * be mounted per page, on the three list pages — and the pages that host a
 * chat were not among them, so the entity the agent had just written was
 * invisible on the very page the consultant was looking at.
 */
export function useWorkspaceRefresh(): void {
  const queryClient = useQueryClient();

  useEffect(() => {
    return onWorkspaceChanged(() => {
      void queryClient.invalidateQueries({ queryKey: ["projects"] });
      void queryClient.invalidateQueries({ queryKey: ["clients"] });
    });
  }, [queryClient]);
}

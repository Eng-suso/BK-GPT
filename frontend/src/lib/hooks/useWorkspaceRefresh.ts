import { useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { onWorkspaceChanged } from "@/lib/workspaceEvents";

/**
 * Bridges the legacy `workspace:refresh` window event (fired by the chat after
 * it creates/edits workspace entities) into TanStack Query cache invalidation.
 * Mount once near the workspace routes.
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

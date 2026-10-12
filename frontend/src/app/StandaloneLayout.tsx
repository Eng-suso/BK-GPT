import { Suspense } from "react";
import { Outlet, useLocation } from "react-router-dom";

import { ErrorBoundary } from "@/components/feedback";
import { Skeleton } from "@/ui/skeleton";

/**
 * Pagine senza barra laterale ne' barra in alto: quelle che leggono persone
 * fuori dallo studio di consulenza, come il cruscotto del responsabile del
 * processo. La navigazione di DeliR li' non serve e non deve vedersi.
 */
export function StandaloneLayout(): React.JSX.Element {
  const location = useLocation();
  return (
    <ErrorBoundary resetKey={location.pathname}>
      <Suspense fallback={<div className="mx-auto flex max-w-3xl flex-col gap-4 px-6 py-10"><Skeleton className="h-8 w-72" /><Skeleton className="h-40 w-full" /></div>}>
        <Outlet />
      </Suspense>
    </ErrorBoundary>
  );
}

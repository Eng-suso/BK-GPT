import React from "react";
import { QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "react-router-dom";
import { I18nextProvider } from "react-i18next";

import { router } from "@/app/router";
import { PeriodProvider } from "@/features/period/PeriodContext";
import { i18n } from "@/lib/i18n";
import { queryClient } from "@/lib/query";

export const AppProviders: React.FC = () => {
  return (
    <QueryClientProvider client={queryClient}>
      <I18nextProvider i18n={i18n}>
        <PeriodProvider>
          <RouterProvider router={router} />
        </PeriodProvider>
      </I18nextProvider>
    </QueryClientProvider>
  );
};

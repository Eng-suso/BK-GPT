import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { Slot } from "radix-ui";
import { cn } from "@/lib/utils";

/** Shared material, independent of layout, padding and domain content. */
export const surfaceVariants = cva("ui-surface", {
  variants: {
    variant: {
      panel: "ui-surface-panel",
      inset: "ui-surface-inset",
      chrome: "ui-surface-chrome",
      rail: "ui-surface-rail",
      toolbar: "ui-surface-toolbar",
      floating: "ui-surface-floating",
      framed: "ui-surface-framed",
    },
  },
  defaultVariants: { variant: "panel" },
});

export function Surface({
  asChild = false,
  variant,
  className,
  ...props
}: React.ComponentProps<"div"> & VariantProps<typeof surfaceVariants> & { asChild?: boolean }) {
  const Comp = asChild ? Slot.Root : "div";
  return <Comp data-slot="surface" className={cn(surfaceVariants({ variant }), className)} {...props} />;
}

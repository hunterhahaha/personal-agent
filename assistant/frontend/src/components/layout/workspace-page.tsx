import type React from "react";
import { cn } from "@/lib/utils";

type WorkspacePageProps = React.ComponentProps<"div"> & {
  constrained?: boolean;
};

export function WorkspacePage({
  className,
  constrained = true,
  ...props
}: WorkspacePageProps) {
  return (
    <div
      className={cn(
        "min-h-full px-4 py-6 sm:px-6 lg:px-10 lg:py-10",
        constrained && "mx-auto w-full max-w-[1200px]",
        className
      )}
      {...props}
    />
  );
}

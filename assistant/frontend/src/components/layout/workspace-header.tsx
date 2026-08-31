import type React from "react";
import { cn } from "@/lib/utils";

interface WorkspaceHeaderProps extends React.ComponentProps<"header"> {
  title: string;
  description?: string;
  actions?: React.ReactNode;
}

export function WorkspaceHeader({
  title,
  description,
  actions,
  className,
  ...props
}: WorkspaceHeaderProps) {
  return (
    <header
      className={cn(
        "mb-6 flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between",
        className
      )}
      {...props}
    >
      <div className="min-w-0">
        <h1 className="truncate text-[28px] font-semibold leading-9 tracking-normal text-foreground sm:text-[32px] sm:leading-10">
          {title}
        </h1>
        {description && (
          <p className="mt-1 max-w-2xl text-sm leading-6 text-muted-foreground">
            {description}
          </p>
        )}
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </header>
  );
}

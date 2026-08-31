import { type ReactNode } from "react";
import { LucideIcon } from "lucide-react";

interface PageHeaderProps {
  icon: LucideIcon;
  title: string;
  description: string;
  children?: ReactNode;
}

export function PageHeader({ icon: Icon, title, description, children }: PageHeaderProps) {
  return (
    <div className="mb-5 flex flex-col gap-3 border-b border-border pb-5 sm:flex-row sm:items-start sm:justify-between">
      <div className="flex min-w-0 items-start gap-3">
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary/10">
          <Icon className="h-4 w-4 text-primary" />
        </div>
        <div className="min-w-0">
          <h1 className="text-xl font-semibold tracking-normal">{title}</h1>
          <p className="max-w-[72ch] text-sm leading-6 text-muted-foreground">
            {description}
          </p>
        </div>
      </div>
      {children && <div className="shrink-0 sm:pt-0.5">{children}</div>}
    </div>
  );
}

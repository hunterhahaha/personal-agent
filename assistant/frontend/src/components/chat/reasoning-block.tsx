"use client";

import { ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";

interface ReasoningBlockProps {
  content: string;
  defaultOpen?: boolean;
  label?: string;
}

/**
 * Collapsible block for displaying LLM reasoning/thinking content.
 * Default state: collapsed.
 */
export function ReasoningBlock({
  content,
  defaultOpen = false,
  label = "查看思考",
}: ReasoningBlockProps) {
  return (
    <details
      className="group my-1 text-xs text-muted-foreground"
      open={defaultOpen}
    >
      <summary className="flex cursor-pointer list-none items-center gap-2 py-1 transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
        <ChevronRight
          className={cn(
            "h-3.5 w-3.5 shrink-0 transition-transform group-open:rotate-90",
          )}
        />
        <span className="font-medium">{label}</span>
      </summary>
      <div className="mt-1 whitespace-pre-wrap border-l border-border/70 pl-5 leading-relaxed text-muted-foreground">
        {content}
      </div>
    </details>
  );
}

"use client";

import { FolderOpen, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface WorkspaceSelectorProps {
  workspaceRoot: string | null;
  disabled?: boolean;
  readOnly?: boolean;
  onSelect: () => void;
  onClear: () => void;
}

function workspaceLabel(path: string | null): string {
  if (!path) return "选择工作区";
  const parts = path.split(/[\\/]+/).filter(Boolean);
  return parts.at(-1) || path;
}

export function WorkspaceSelector({
  workspaceRoot,
  disabled = false,
  readOnly = false,
  onSelect,
  onClear,
}: WorkspaceSelectorProps) {
  const label = workspaceLabel(workspaceRoot);

  return (
    <div className="flex w-full min-w-0 max-w-full items-center gap-1 md:w-auto">
      <Button
        type="button"
        variant="outline"
        size="lg"
        disabled={disabled || readOnly}
        onClick={onSelect}
        title={workspaceRoot || "选择工作区"}
        className={cn(
          "w-full max-w-[128px] justify-start gap-2 px-2.5 text-xs text-muted-foreground md:w-auto md:max-w-[280px]",
          readOnly && "opacity-80"
        )}
      >
        <FolderOpen className="h-3.5 w-3.5" />
        <span className="truncate">{label}</span>
      </Button>
      {workspaceRoot && !readOnly && (
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          disabled={disabled}
          onClick={onClear}
          aria-label="清除工作区"
          title="清除工作区"
          className="text-muted-foreground"
        >
          <X className="h-3.5 w-3.5" />
        </Button>
      )}
    </div>
  );
}

"use client";

import { useEffect, useState } from "react";
import { modelsApi, type ModelConfig } from "@/lib/api-client";

interface ModelSelectorProps {
  selectedModelId: string | null;
  disabled: boolean;
  onChange: (modelId: string | null) => void;
  onModelsLoaded?: (models: ModelConfig[]) => void;
}

export default function ModelSelector({
  selectedModelId,
  disabled,
  onChange,
  onModelsLoaded,
}: ModelSelectorProps) {
  const [models, setModels] = useState<ModelConfig[]>([]);

  useEffect(() => {
    modelsApi.list().then(({ data }) => {
      setModels(data);
      onModelsLoaded?.(data);
    }).catch(() => {});
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const activeModel = models.find((m) => m.uid === selectedModelId)
    ?? models.find((m) => m.is_active);

  return (
    <div className="relative">
      <select
        value={selectedModelId ?? activeModel?.uid ?? ""}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value || null)}
        className="h-9 w-full min-w-[116px] max-w-[132px] truncate rounded-md border border-input bg-background px-2 text-xs text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring disabled:opacity-50 md:min-w-[148px] md:max-w-[180px]"
        title={activeModel?.name ?? "选择模型"}
      >
        {models.length === 0 && (
          <option value="">选择模型</option>
        )}
        {models.map((m) => (
          <option key={m.uid} value={m.uid}>
            {m.name}
          </option>
        ))}
      </select>
    </div>
  );
}

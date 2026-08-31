import { useCallback, useEffect, useState } from "react";

interface ListApi<T> {
  list: (params?: { skip?: number; limit?: number }) => Promise<{ data: T[] }>;
  toggle: (id: string) => Promise<unknown>;
}

export function useEntityList<T>(api: ListApi<T>) {
  const [items, setItems] = useState<T[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const { data } = await api.list();
      setItems(data);
    } catch {
      setError("加载失败");
    } finally {
      setLoading(false);
    }
  }, [api]);

  const toggleEnabled = useCallback(
    async (id: string) => {
      try {
        await api.toggle(id);
        await load();
      } catch {
        setError("切换失败");
      }
    },
    [api, load]
  );

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- async data fetch on mount
    load();
  }, [load]);

  return { items, loading, error, load, toggleEnabled, setError };
}

"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { callTool } from "@/lib/api";
import {
  groupByProvider,
  parseModels,
  type ModelChoice,
  type ProviderGroup,
} from "@/lib/model-catalog";

interface ModelCatalog {
  models: ModelChoice[];
  groups: ProviderGroup[];
  loading: boolean;
  error: string | null;
  /** Re-read the catalog; `live` re-fetches the provider list, bypassing the cache. */
  refresh: (live?: boolean) => void;
}

/**
 * Read the safe mixed-provider chat-model catalog via the delegated
 * ``agent_list_models`` MCP tool. An unavailable catalog is a truthful
 * error (degraded state) — never a fabricated empty list — so the picker
 * can say so instead of silently offering nothing.
 */
export function useModelCatalog(): ModelCatalog {
  const [models, setModels] = useState<ModelChoice[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async (live = false) => {
    setLoading(true);
    try {
      setModels(parseModels(await callTool("agent_list_models", live ? { refresh: true } : {})));
      setError(null);
    } catch {
      setModels([]);
      setError("Model catalog unavailable");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const groups = useMemo(() => groupByProvider(models), [models]);
  return { models, groups, loading, error, refresh };
}

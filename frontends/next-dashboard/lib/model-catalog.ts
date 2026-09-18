import { unwrapToolData } from "@/lib/tool-result-data";

/**
 * A non-secret chat-model choice, mirroring the llm_gateway
 * ``ChatModelDescriptor`` delegated through the agent brick's safe catalog.
 * Endpoints and credential-env names are never projected to the client.
 */
/**
 * A non-secret chat-model choice, mirroring the llm_gateway
 * ``ChatModelDescriptor`` delegated through the agent brick's safe catalog.
 * Endpoints and credential-env names are never projected to the client.
 * ``promptUsdPerToken``/``completionUsdPerToken`` are OpenRouter's own public
 * per-token USD pricing when the catalog has it — undefined for providers
 * with no comparable public pricing source (Bedrock, Ollama, openai-compat).
 */
export interface ModelChoice {
  model_id: string;
  provider: string;
  model: string;
  promptUsdPerToken?: number;
  completionUsdPerToken?: number;
}

export interface ProviderGroup {
  provider: string;
  models: ModelChoice[];
}

/** Unwrap + validate the ``agent_list_models`` ToolResult. */
export function parseModels(raw: unknown): ModelChoice[] {
  const data = unwrapToolData(raw);
  const obj = (data && typeof data === "object" ? data : {}) as Record<string, unknown>;
  const rows = Array.isArray(obj.models) ? obj.models : [];
  return rows
    .filter((row): row is Record<string, unknown> => Boolean(row && typeof row === "object"))
    .filter((row) => typeof row.model_id === "string" && typeof row.provider === "string")
    .map((row) => ({
      model_id: row.model_id as string,
      provider: row.provider as string,
      model: typeof row.model === "string" ? row.model : (row.model_id as string),
      ...(typeof row.prompt_usd_per_token === "number" ? { promptUsdPerToken: row.prompt_usd_per_token } : {}),
      ...(typeof row.completion_usd_per_token === "number"
        ? { completionUsdPerToken: row.completion_usd_per_token } : {}),
    }));
}

/**
 * Group choices by provider WITHOUT assuming one catalog shape — mixed
 * Bedrock, OpenRouter, Ollama, and openai-compat entries each fall into
 * their own group in first-seen order.
 */
export function groupByProvider(models: ModelChoice[]): ProviderGroup[] {
  const groups: ProviderGroup[] = [];
  const index = new Map<string, ProviderGroup>();
  for (const choice of models) {
    let group = index.get(choice.provider);
    if (!group) {
      group = { provider: choice.provider, models: [] };
      index.set(choice.provider, group);
      groups.push(group);
    }
    group.models.push(choice);
  }
  return groups;
}

/** Blended per-token cost used to rank "cheapest" — 3:1 completion:prompt
 * weighting approximates a typical chat turn's token mix; not a bill. */
function blendedCost(model: ModelChoice): number | null {
  if (model.promptUsdPerToken === undefined || model.completionUsdPerToken === undefined) return null;
  return model.promptUsdPerToken + model.completionUsdPerToken * 3;
}

/** The model_id of the priced model with the lowest blended cost, if any priced model exists. */
export function cheapestModelId(models: ModelChoice[]): string | null {
  let best: { id: string; cost: number } | null = null;
  for (const model of models) {
    const cost = blendedCost(model);
    if (cost === null) continue;
    if (best === null || cost < best.cost) best = { id: model.model_id, cost };
  }
  return best?.id ?? null;
}

/** Human-readable per-million-token price, e.g. "$0.20/M in · $0.80/M out". */
export function formatPricing(model: ModelChoice): string | null {
  if (model.promptUsdPerToken === undefined || model.completionUsdPerToken === undefined) return null;
  const perMillion = (usdPerToken: number) => {
    const value = usdPerToken * 1_000_000;
    return value === 0 ? "free" : `$${value < 0.01 ? value.toFixed(4) : value.toFixed(2)}/M`;
  };
  return `${perMillion(model.promptUsdPerToken)} in · ${perMillion(model.completionUsdPerToken)} out`;
}

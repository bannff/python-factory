import { describe, expect, it } from "vitest";
import { cheapestModelId, formatPricing, groupByProvider, parseModels } from "../model-catalog";

describe("parseModels pricing extraction", () => {
  it("carries pricing when both fields are numbers", () => {
    const models = parseModels({ ok: true, data: { count: 1, models: [
      { model_id: "openrouter/x", provider: "openrouter", model: "x",
        prompt_usd_per_token: 0.0000002, completion_usd_per_token: 0.0000008 },
    ] } });
    expect(models[0].promptUsdPerToken).toBe(0.0000002);
    expect(models[0].completionUsdPerToken).toBe(0.0000008);
  });

  it("omits pricing fields entirely when the server sends null (non-OpenRouter provider)", () => {
    const models = parseModels({ ok: true, data: { count: 1, models: [
      { model_id: "anthropic.claude", provider: "bedrock", model: "anthropic.claude",
        prompt_usd_per_token: null, completion_usd_per_token: null },
    ] } });
    expect(models[0].promptUsdPerToken).toBeUndefined();
    expect(models[0].completionUsdPerToken).toBeUndefined();
  });
});

describe("cheapestModelId", () => {
  it("picks the lowest blended cost among priced models", () => {
    const models = parseModels({ ok: true, data: { count: 2, models: [
      { model_id: "openrouter/expensive", provider: "openrouter", model: "expensive",
        prompt_usd_per_token: 0.00001, completion_usd_per_token: 0.00005 },
      { model_id: "openrouter/cheap", provider: "openrouter", model: "cheap",
        prompt_usd_per_token: 0.0000001, completion_usd_per_token: 0.0000004 },
    ] } });
    expect(cheapestModelId(models)).toBe("openrouter/cheap");
  });

  it("returns null when nothing has pricing", () => {
    const models = parseModels({ ok: true, data: { count: 1, models: [
      { model_id: "anthropic.claude", provider: "bedrock", model: "anthropic.claude" },
    ] } });
    expect(cheapestModelId(models)).toBeNull();
  });

  it("ignores unpriced entries when ranking priced ones", () => {
    const models = parseModels({ ok: true, data: { count: 2, models: [
      { model_id: "anthropic.claude", provider: "bedrock", model: "anthropic.claude" },
      { model_id: "openrouter/x", provider: "openrouter", model: "x",
        prompt_usd_per_token: 0.0000001, completion_usd_per_token: 0.0000004 },
    ] } });
    expect(cheapestModelId(models)).toBe("openrouter/x");
  });
});

describe("formatPricing", () => {
  it("formats per-million pricing for both directions", () => {
    const [model] = parseModels({ ok: true, data: { count: 1, models: [
      { model_id: "openrouter/x", provider: "openrouter", model: "x",
        prompt_usd_per_token: 0.0000002, completion_usd_per_token: 0.0000008 },
    ] } });
    expect(formatPricing(model)).toBe("$0.20/M in · $0.80/M out");
  });

  it("returns null when pricing is absent", () => {
    const [model] = parseModels({ ok: true, data: { count: 1, models: [
      { model_id: "anthropic.claude", provider: "bedrock", model: "anthropic.claude" },
    ] } });
    expect(formatPricing(model)).toBeNull();
  });

  it("labels a genuinely free model rather than showing $0.00", () => {
    const [model] = parseModels({ ok: true, data: { count: 1, models: [
      { model_id: "openrouter/free-model", provider: "openrouter", model: "free-model",
        prompt_usd_per_token: 0, completion_usd_per_token: 0 },
    ] } });
    expect(formatPricing(model)).toBe("free in · free out");
  });
});

describe("groupByProvider keeps pricing on each choice", () => {
  it("preserves pricing fields through grouping", () => {
    const models = parseModels({ ok: true, data: { count: 1, models: [
      { model_id: "openrouter/x", provider: "openrouter", model: "x",
        prompt_usd_per_token: 0.0000002, completion_usd_per_token: 0.0000008 },
    ] } });
    const [group] = groupByProvider(models);
    expect(group.models[0].promptUsdPerToken).toBe(0.0000002);
  });
});

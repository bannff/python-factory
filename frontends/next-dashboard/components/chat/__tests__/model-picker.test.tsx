import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

const mocks = vi.hoisted(() => ({
  core: { properties: {} as Record<string, unknown>, setProperties: vi.fn() },
  agent: { threadId: "t1" },
  catalog: {
    groups: [
      { provider: "bedrock", models: [{ model_id: "anthropic.claude", provider: "bedrock", model: "claude" }] },
      { provider: "openrouter", models: [{ model_id: "openrouter/x/y", provider: "openrouter", model: "x/y" }] },
    ],
    models: [], loading: false, error: null as string | null, refresh: vi.fn(),
  },
  preferences: { plainDiffs: false, hiddenModels: [] as string[], revision: 0 },
  sessions: [{ session_id: "s1", thread_id: "t1", title: "T", agent_id: "a", model: "anthropic.claude", updated_at: "", archived_at: null, revision: 4, crew_id: "", memory_scope: "" }],
  refresh: vi.fn(),
  callTool: vi.fn(),
}));

vi.mock("@copilotkit/react-core/v2", () => ({
  useAgent: () => ({ agent: mocks.agent }),
  useCopilotKit: () => ({ copilotkit: mocks.core }),
  UseAgentUpdate: { OnMessagesChanged: "messages" },
}));
vi.mock("@/lib/hooks/use-model-catalog", () => ({ useModelCatalog: () => mocks.catalog }));
vi.mock("@/components/settings/use-chat-preferences", () => ({
  useChatPreferences: () => ({ preferences: mocks.preferences, loading: false, error: null, refresh: vi.fn() }),
}));
vi.mock("@/lib/hooks/use-session-list", () => ({ useSessionList: () => ({ sessions: mocks.sessions, loading: false, error: null, refresh: mocks.refresh }) }));
vi.mock("@/lib/api", () => ({ callTool: (...args: unknown[]) => mocks.callTool(...args) }));

import { ModelPicker } from "../model-picker";

beforeEach(() => {
  mocks.core.properties = {};
  mocks.core.setProperties.mockReset();
  mocks.callTool.mockReset().mockResolvedValue({});
  mocks.refresh.mockReset();
  mocks.catalog.error = null;
  mocks.catalog.refresh.mockReset();
  mocks.catalog.groups = [
    { provider: "bedrock", models: [{ model_id: "anthropic.claude", provider: "bedrock", model: "claude" }] },
    { provider: "openrouter", models: [{ model_id: "openrouter/x/y", provider: "openrouter", model: "x/y" }] },
  ];
  mocks.preferences.hiddenModels = [];
  mocks.agent.threadId = "t1";
  mocks.sessions = [{ session_id: "s1", thread_id: "t1", title: "T", agent_id: "a", model: "anthropic.claude", updated_at: "", archived_at: null, revision: 4, crew_id: "", memory_scope: "" }];
});

describe("ModelPicker", () => {
  it("groups choices by provider", () => {
    render(<ModelPicker agentId="companion_x" />);
    fireEvent.click(screen.getByTitle("Choose the chat model"));
    expect(screen.getByText("bedrock")).toBeTruthy();
    expect(screen.getByText("openrouter")).toBeTruthy();
    expect(screen.getByText("claude")).toBeTruthy();
    expect(screen.getByText("claude").closest("button")?.getAttribute("aria-selected")).toBe("true");
    expect(screen.getByText("x/y").closest("button")?.getAttribute("aria-selected")).toBe("false");
  });

  it("persists to the active session via CAS before merging properties", async () => {
    mocks.core.properties = { existing: "keep" };
    render(<ModelPicker agentId="companion_x" />);
    fireEvent.click(screen.getByTitle("Choose the chat model"));
    fireEvent.click(screen.getByText("x/y"));
    await waitFor(() => expect(mocks.callTool).toHaveBeenCalledWith("session_set_model", {
      session_id: "s1", model: "openrouter/x/y", expected_revision: 4,
    }));
    expect(mocks.core.setProperties).toHaveBeenCalledWith({ existing: "keep", companion_x_model: "openrouter/x/y" });
    expect(mocks.refresh).toHaveBeenCalled();
  });

  it("only sets the next-session hint when there is no persisted session", async () => {
    mocks.agent.threadId = "unsaved";
    render(<ModelPicker agentId="companion_x" />);
    fireEvent.click(screen.getByTitle("Choose the chat model"));
    fireEvent.click(screen.getByText("claude"));
    await waitFor(() => expect(screen.getByText("Applies to your next session.")).toBeTruthy());
    expect(mocks.core.setProperties).toHaveBeenCalledWith({ companion_x_model: "anthropic.claude" });
    expect(mocks.callTool).not.toHaveBeenCalled();
  });

  it("omits models hidden by Chat Settings", () => {
    mocks.preferences.hiddenModels = ["openrouter/x/y"];
    render(<ModelPicker agentId="companion_x" />);
    fireEvent.click(screen.getByTitle("Choose the chat model"));
    expect(screen.getByText("claude")).toBeTruthy();
    expect(screen.queryByText("x/y")).toBeNull();
    expect(screen.queryByText("openrouter")).toBeNull();
  });

  it("shows a truthful degraded state when the catalog is unavailable", () => {
    mocks.catalog.error = "Model catalog unavailable";
    render(<ModelPicker agentId="companion_x" />);
    fireEvent.click(screen.getByTitle("Choose the chat model"));
    expect(screen.getByText("Model catalog unavailable")).toBeTruthy();
  });

  it("searches a large live catalog and can force a provider refresh", () => {
    const many = Array.from({ length: 30 }, (_, i) => ({
      model_id: `openrouter/vendor${i % 3}/model-${i}`, provider: "openrouter", model: `vendor${i % 3}/model-${i}`,
    }));
    mocks.catalog.groups = [{ provider: "openrouter", models: many }];
    render(<ModelPicker agentId="companion_x" />);
    fireEvent.click(screen.getByTitle("Choose the chat model"));
    expect(screen.getAllByRole("option")).toHaveLength(30);
    fireEvent.change(screen.getByPlaceholderText("Search 30 models"), { target: { value: "model-1" } });
    const options = screen.getAllByRole("option").map((el) => el.getAttribute("title"));
    expect(options.every((id) => id?.includes("model-1"))).toBe(true);
    expect(options.length).toBe(11);
    fireEvent.click(screen.getByRole("button", { name: "Refresh model catalog" }));
    expect(mocks.catalog.refresh).toHaveBeenCalledWith(true);
  });

  it("shows per-token pricing and flags the cheapest priced model", () => {
    mocks.catalog.groups = [{ provider: "openrouter", models: [
      { model_id: "openrouter/expensive", provider: "openrouter", model: "expensive",
        promptUsdPerToken: 0.00001, completionUsdPerToken: 0.00005 },
      { model_id: "openrouter/cheap", provider: "openrouter", model: "cheap",
        promptUsdPerToken: 0.0000001, completionUsdPerToken: 0.0000004 },
    ] }];
    render(<ModelPicker agentId="companion_x" />);
    fireEvent.click(screen.getByTitle("Choose the chat model"));
    expect(screen.getByText("$10.00/M in · $50.00/M out")).toBeTruthy();
    const cheapButton = screen.getByText("cheap").closest("button");
    expect(cheapButton?.textContent).toContain("cheapest");
    const expensiveButton = screen.getByText("expensive").closest("button");
    expect(expensiveButton?.textContent).not.toContain("cheapest");
  });
});

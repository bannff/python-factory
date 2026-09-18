import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

const mocks = vi.hoisted(() => ({
  available: vi.fn(), refresh: vi.fn(), listIds: vi.fn(), read: vi.fn(), save: vi.fn(), remove: vi.fn(),
  forkAvailable: vi.fn(), fork: vi.fn(), reset: vi.fn(),
  personas: [
    { id: "builtin", name: "Built in", description: "Core", model: "openrouter/a" },
    { id: "user-one", name: "User one", description: "Custom", model: "openrouter/b" },
  ],
}));
vi.mock("@/lib/hooks/use-mcp-connection", () => ({ useMcpConnection: () => ({ ready: true }) }));
vi.mock("@/lib/hooks/use-personas", () => ({ usePersonas: () => ({
  personas: mocks.personas, loading: false, error: null, refresh: mocks.refresh,
}) }));
vi.mock("../agent-template-api", () => ({
  personaAuthoringAvailable: (...args: unknown[]) => mocks.available(...args),
  personaForkAvailable: (...args: unknown[]) => mocks.forkAvailable(...args),
  listUserTemplateIds: (...args: unknown[]) => mocks.listIds(...args),
  readUserTemplate: (...args: unknown[]) => mocks.read(...args),
  saveUserTemplate: (...args: unknown[]) => mocks.save(...args),
  deleteUserTemplate: (...args: unknown[]) => mocks.remove(...args),
  forkTemplate: (...args: unknown[]) => mocks.fork(...args),
  resetTemplate: (...args: unknown[]) => mocks.reset(...args),
}));

import AgentTemplatesView from "../agent-templates-view";

beforeEach(() => {
  mocks.available.mockReset().mockResolvedValue(true);
  mocks.forkAvailable.mockReset().mockResolvedValue(true);
  mocks.fork.mockReset().mockResolvedValue("builtin-fork");
  mocks.reset.mockReset().mockResolvedValue(undefined);
  mocks.refresh.mockReset(); mocks.save.mockReset().mockResolvedValue(undefined);
  mocks.remove.mockReset().mockResolvedValue(undefined);
  mocks.listIds.mockReset().mockResolvedValue(["user-one"]);
  mocks.read.mockReset().mockResolvedValue({ id: "user-one", name: "User one",
    description: "Custom", model: "openrouter/b", system_prompt: "Help", tools: [], skills: [] });
});

describe("AgentTemplatesView", () => {
  it("keeps built-ins visible and read-only", async () => {
    render(<AgentTemplatesView />);
    await waitFor(() => expect(screen.getByText("Built-in")).toBeTruthy());
    fireEvent.click(screen.getByRole("button", { name: /Built in/ }));
    expect(screen.getByText(/Built-in templates are read-only/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Delete" })).toBeNull();
  });

  it("loads, updates, and deletes a user template", async () => {
    render(<AgentTemplatesView />);
    await waitFor(() => expect(screen.getByText("User template")).toBeTruthy());
    fireEvent.click(screen.getByRole("button", { name: /User one/ }));
    await waitFor(() => expect(mocks.read).toHaveBeenCalledWith("user-one"));
    fireEvent.change(screen.getByLabelText("Description"), { target: { value: "Updated" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(mocks.save).toHaveBeenCalledWith(expect.objectContaining({
      id: "user-one", description: "Updated", system_prompt: "Help",
    })));
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    await waitFor(() => expect(mocks.remove).toHaveBeenCalledWith("user-one"));
  });

  it("creates a new user template", async () => {
    render(<AgentTemplatesView />);
    fireEvent.click(await screen.findByRole("button", { name: "New agent template" }));
    fireEvent.change(screen.getByLabelText("ID"), { target: { value: "new-agent" } });
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "New agent" } });
    fireEvent.change(screen.getByLabelText("System prompt"), { target: { value: "Be helpful" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(mocks.save).toHaveBeenCalledWith(expect.objectContaining({
      id: "new-agent", name: "New agent", system_prompt: "Be helpful",
    })));
  });

  it("keeps registry reads available when authoring is operator-disabled", async () => {
    mocks.available.mockResolvedValue(false);
    render(<AgentTemplatesView />);
    await waitFor(() => expect(screen.getByText("Persona authoring disabled")).toBeTruthy());
    expect(screen.getByText("Built in")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "New agent template" })).toBeNull();
  });

  it("row 33 (feature-map): forks a built-in into an editable copy", async () => {
    render(<AgentTemplatesView />);
    await waitFor(() => expect(screen.getByText("Built-in")).toBeTruthy());
    fireEvent.click(screen.getByRole("button", { name: /Built in/ }));
    fireEvent.click(await screen.findByRole("button", { name: "Fork this template" }));
    await waitFor(() => expect(mocks.fork).toHaveBeenCalledWith("builtin", "builtin-fork"));
  });

  it("row 33 (feature-map): resets a forked template's local edits", async () => {
    render(<AgentTemplatesView />);
    await waitFor(() => expect(screen.getByText("User template")).toBeTruthy());
    fireEvent.click(screen.getByRole("button", { name: /User one/ }));
    await waitFor(() => expect(mocks.read).toHaveBeenCalledWith("user-one"));
    fireEvent.click(screen.getByRole("button", { name: "Reset" }));
    await waitFor(() => expect(mocks.reset).toHaveBeenCalledWith("user-one"));
  });
});

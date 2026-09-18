import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

const mocks = vi.hoisted(() => ({ list: vi.fn(), read: vi.fn(), add: vi.fn(), remove: vi.fn(), available: vi.fn() }));
vi.mock("@/lib/hooks/use-mcp-connection", () => ({
  useMcpConnection: () => ({ ready: true, status: "connected" }),
}));
vi.mock("../skills-api", () => ({
  listSkills: (...args: unknown[]) => mocks.list(...args),
  readSkill: (...args: unknown[]) => mocks.read(...args),
  addSkill: (...args: unknown[]) => mocks.add(...args),
  deleteSkill: (...args: unknown[]) => mocks.remove(...args),
  skillAuthoringAvailable: (...args: unknown[]) => mocks.available(...args),
}));

import SkillsView from "../skills-view";

beforeEach(() => {
  mocks.list.mockReset().mockResolvedValue([{ id: "review", name: "Review", description: "Check evidence" }]);
  mocks.read.mockReset().mockResolvedValue({ id: "review", name: "Review", description: "Check evidence", body: "Read the diff." });
  mocks.add.mockReset().mockResolvedValue({ id: "new-skill", name: "New Skill", description: "Added" });
  mocks.remove.mockReset().mockResolvedValue(undefined);
  mocks.available.mockReset().mockResolvedValue(true);
});

describe("SkillsView", () => {
  it("lists, filters, and reads skill instructions", async () => {
    render(<SkillsView />);
    fireEvent.click(await screen.findByRole("button", { name: /Review/ }));
    expect(await screen.findByText("Read the diff.")).toBeTruthy();
    expect(mocks.read).toHaveBeenCalledWith("review");
    fireEvent.change(screen.getByLabelText("Search skills"), { target: { value: "missing" } });
    expect(screen.getByText("No matching skills.")).toBeTruthy();
  });

  it("adds a skill when Agent authoring is enabled", async () => {
    mocks.read.mockImplementation(async (id: string) => ({
      id, name: id === "new-skill" ? "New Skill" : "Review", description: "Added", body: "Use evidence.",
    }));
    render(<SkillsView />);
    fireEvent.click(await screen.findByRole("button", { name: "Add skill" }));
    fireEvent.change(screen.getByLabelText("ID"), { target: { value: "new-skill" } });
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "New Skill" } });
    fireEvent.change(screen.getByLabelText("Instructions"), { target: { value: "Use evidence." } });
    fireEvent.click(screen.getAllByRole("button", { name: "Add skill" })[1]);
    await waitFor(() => expect(mocks.add).toHaveBeenCalledWith({
      skillId: "new-skill", name: "New Skill", description: "", body: "Use evidence.",
    }));
    expect(await screen.findByText("Use evidence.")).toBeTruthy();
  });

  it("keeps reads available when authoring is disabled", async () => {
    mocks.available.mockResolvedValue(false);
    render(<SkillsView />);
    expect(await screen.findByText(/Adding skills is disabled/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Add skill" })).toBeNull();
    expect(screen.getByRole("button", { name: /Review/ })).toBeTruthy();
  });

  it("deletes a skill when authoring is enabled and clears the detail pane", async () => {
    render(<SkillsView />);
    fireEvent.click(await screen.findByRole("button", { name: /Review/ }));
    await screen.findByText("Read the diff.");
    fireEvent.click(screen.getByRole("button", { name: "Delete skill" }));
    await waitFor(() => expect(mocks.remove).toHaveBeenCalledWith("review"));
    expect(mocks.list).toHaveBeenCalledTimes(2); // initial load + refresh after delete
  });

  it("hides the Delete control when authoring is disabled", async () => {
    mocks.available.mockResolvedValue(false);
    render(<SkillsView />);
    fireEvent.click(await screen.findByRole("button", { name: /Review/ }));
    await screen.findByText("Read the diff.");
    expect(screen.queryByRole("button", { name: "Delete skill" })).toBeNull();
  });
});

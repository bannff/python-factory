import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
const mocks = vi.hoisted(() => ({ list: vi.fn(), read: vi.fn(), save: vi.fn(), available: vi.fn(), remove: vi.fn() }));
vi.mock("@/lib/hooks/use-mcp-connection", () => ({ useMcpConnection: () => ({ ready: true, status: "connected" }) }));
vi.mock("../steering-api", () => ({
  listSteering: (...args: unknown[]) => mocks.list(...args), readSteering: (...args: unknown[]) => mocks.read(...args),
  saveSteering: (...args: unknown[]) => mocks.save(...args), steeringAuthoringAvailable: (...args: unknown[]) => mocks.available(...args),
  deleteSteering: (...args: unknown[]) => mocks.remove(...args),
}));
import SteeringView from "../steering-view";
const row = { id: "quality", title: "Quality", sha256: "a".repeat(64), content: "# Quality\nRun tests." };
beforeEach(() => { mocks.list.mockReset().mockResolvedValue([row]); mocks.read.mockReset().mockResolvedValue(row);
  mocks.save.mockReset().mockResolvedValue({ ...row, content: "# Quality\nRun all tests.", sha256: "b".repeat(64) });
  mocks.available.mockReset().mockResolvedValue(true); mocks.remove.mockReset().mockResolvedValue(undefined); });
describe("SteeringView", () => {
  it("reads and revision-fences edits", async () => {
    render(<SteeringView />); fireEvent.click(await screen.findByRole("button", { name: /Quality/ }));
    const editor = await screen.findByLabelText("Markdown");
    fireEvent.change(editor, { target: { value: "# Quality\nRun all tests." } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(mocks.save).toHaveBeenCalledWith({ id: "quality", content: "# Quality\nRun all tests.", expectedSha256: "a".repeat(64) }));
  });
  it("creates only when authoring is enabled", async () => {
    render(<SteeringView />); fireEvent.click(await screen.findByRole("button", { name: "New steering document" }));
    fireEvent.change(screen.getByLabelText("ID"), { target: { value: "new-doc" } });
    fireEvent.change(screen.getByLabelText("Markdown"), { target: { value: "# New" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(mocks.save).toHaveBeenCalledWith({ id: "new-doc", content: "# New" }));
  });
  it("deletes an existing document with its current revision", async () => {
    render(<SteeringView />); fireEvent.click(await screen.findByRole("button", { name: /Quality/ }));
    fireEvent.click(await screen.findByRole("button", { name: "Delete steering document" }));
    await waitFor(() => expect(mocks.remove).toHaveBeenCalledWith("quality", "a".repeat(64)));
  });
  it("hides the delete button while creating a new document", async () => {
    render(<SteeringView />); fireEvent.click(await screen.findByRole("button", { name: "New steering document" }));
    expect(screen.queryByRole("button", { name: "Delete steering document" })).toBeNull();
  });
});

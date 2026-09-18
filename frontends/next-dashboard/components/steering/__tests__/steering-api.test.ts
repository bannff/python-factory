import { beforeEach, describe, expect, it, vi } from "vitest";
const mocks = vi.hoisted(() => ({ call: vi.fn(), tools: vi.fn() }));
vi.mock("@/lib/api", () => ({ callTool: mocks.call, listTools: mocks.tools }));
import { deleteSteering, listSteering, readSteering, saveSteering, steeringAuthoringAvailable } from "../steering-api";

beforeEach(() => { mocks.call.mockReset(); mocks.tools.mockReset(); });
describe("Steering MCP API", () => {
  it("lists and reads typed documents", async () => {
    const row = { id: "quality", title: "Quality", sha256: "a".repeat(64) };
    mocks.call.mockResolvedValueOnce({ tool: "agent_list_steering", result: { ok: true, data: { documents: [row] } } })
      .mockResolvedValueOnce({ tool: "agent_read_steering", result: { ok: true, data: { ...row, content: "# Quality" } } });
    await expect(listSteering()).resolves.toEqual([row]);
    await expect(readSteering("quality")).resolves.toEqual({ ...row, content: "# Quality" });
  });
  it("detects authoring and revision-fences updates", async () => {
    mocks.tools.mockResolvedValue({ tools: ["agent_create_steering", "agent_update_steering"], count: 2 });
    await expect(steeringAuthoringAvailable()).resolves.toBe(true);
    const row = { id: "quality", title: "Quality", sha256: "b".repeat(64), content: "updated" };
    mocks.call.mockResolvedValue({ tool: "agent_update_steering", result: { ok: true, data: { document: row } } });
    await saveSteering({ id: "quality", content: "updated", expectedSha256: "a".repeat(64) });
    expect(mocks.call).toHaveBeenCalledWith("agent_update_steering", {
      document_id: "quality", content: "updated", expected_sha256: "a".repeat(64),
    });
  });
  it("deletes with a revision fence and rejects a false server response", async () => {
    mocks.call.mockResolvedValueOnce({ tool: "agent_delete_steering", result: { ok: true, data: { deleted: true, document_id: "quality" } } });
    await expect(deleteSteering("quality", "a".repeat(64))).resolves.toBeUndefined();
    expect(mocks.call).toHaveBeenCalledWith("agent_delete_steering", { document_id: "quality", expected_sha256: "a".repeat(64) });
    mocks.call.mockResolvedValueOnce({ tool: "agent_delete_steering", result: { ok: true, data: { deleted: false } } });
    await expect(deleteSteering("quality", "a".repeat(64))).rejects.toThrow("Steering document was not deleted.");
  });
});

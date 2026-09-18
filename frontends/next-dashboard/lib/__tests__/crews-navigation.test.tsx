import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { ActivityBar } from "@/components/layout/activity-bar";
import { ROUTED_VIEWS, syncCanvasRoute } from "@/lib/canvas-routes";

describe("Crews navigation", () => {
  beforeEach(() => { window.history.pushState({}, "", "/"); });
  afterEach(() => { window.history.pushState({}, "", "/"); });

  it("exposes a Crews entry that switches the view and routes to /crews", () => {
    const onViewChange = vi.fn();
    render(<ActivityBar activeView="welcome" onViewChange={onViewChange} />);
    fireEvent.click(screen.getByTitle("Crews"));
    expect(onViewChange).toHaveBeenCalledWith("crews");
    expect(window.location.pathname).toBe("/crews");
  });

  it("registers /crews as a deep-linkable routed view", () => {
    expect(ROUTED_VIEWS.crews).toBe("/crews");
  });

  it("resets a routed path back to / for non-routed views", () => {
    window.history.pushState({}, "", "/crews");
    syncCanvasRoute("graph");
    expect(window.location.pathname).toBe("/");
  });

  it("pushes the routed path for a routed view", () => {
    syncCanvasRoute("crews");
    expect(window.location.pathname).toBe("/crews");
  });
});

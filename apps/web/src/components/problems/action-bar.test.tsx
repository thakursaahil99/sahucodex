import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ActionBar } from "@/components/problems/action-bar";
import type { AiFeature } from "@/lib/ai/types";

vi.mock("sonner", () => ({ toast: { info: vi.fn() } }));

const onRun = vi.fn();
const onSubmit = vi.fn();
const onAi = vi.fn();

function renderBar(props: Partial<React.ComponentProps<typeof ActionBar>> = {}) {
  return render(
    <ActionBar
      onRun={onRun}
      onSubmit={onSubmit}
      running={false}
      submitting={false}
      onAi={onAi}
      aiBusy={null}
      {...props}
    />,
  );
}

beforeEach(() => {
  onRun.mockReset();
  onSubmit.mockReset();
  onAi.mockReset();
});

describe("ActionBar", () => {
  it("runs and submits", async () => {
    renderBar();
    await userEvent.click(screen.getByRole("button", { name: /Run/ }));
    expect(onRun).toHaveBeenCalledTimes(1);
    await userEvent.click(screen.getByRole("button", { name: /Submit/ }));
    expect(onSubmit).toHaveBeenCalledTimes(1);
  });

  it("disables both actions while a run is in flight", () => {
    renderBar({ running: true });
    expect(screen.getByRole("button", { name: /Run/ })).toBeDisabled();
    expect(screen.getByRole("button", { name: /Submit/ })).toBeDisabled();
  });

  it("disables both actions while a submission is in flight", () => {
    renderBar({ submitting: true });
    expect(screen.getByRole("button", { name: /Run/ })).toBeDisabled();
    expect(screen.getByRole("button", { name: /Submit/ })).toBeDisabled();
  });

  it.each([
    ["AI Hint", "hint"],
    ["AI Review", "review"],
    ["Explain", "explain"],
  ] as Array<[string, AiFeature]>)("%s asks the AI for the matching feature", async (label, feature) => {
    renderBar();
    await userEvent.click(screen.getByRole("button", { name: new RegExp(label) }));
    expect(onAi).toHaveBeenCalledExactlyOnceWith(feature);
  });

  it("makes the other AI actions wait while one request is in flight", () => {
    renderBar({ aiBusy: "review" });
    for (const name of [/AI Hint/, /AI Review/, /Explain/]) {
      expect(screen.getByRole("button", { name })).toBeDisabled();
    }
    expect(screen.getByRole("button", { name: /Run/ })).toBeEnabled(); // judging is unaffected by AI work
  });

  it("explains why the AI is off instead of calling it, when no model is configured", async () => {
    const { toast } = await import("sonner");
    renderBar({ aiUnavailable: "No model chosen (OLLAMA_MODEL)." });
    const hint = screen.getByRole("button", { name: /AI Hint/ });
    expect(hint).toHaveAttribute("aria-disabled", "true");
    expect(hint).toHaveAttribute("title", "No model chosen (OLLAMA_MODEL).");
    await userEvent.click(hint);
    expect(toast.info).toHaveBeenCalledWith("AI Hint isn't set up yet", {
      description: "No model chosen (OLLAMA_MODEL).",
    });
    expect(onAi).not.toHaveBeenCalled();
  });
});

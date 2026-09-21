import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AiResultTab } from "@/components/ai/ai-result";

describe("AiResultTab", () => {
  it("says what it can see before anything has been asked, and that hidden tests are never among it", () => {
    render(<AiResultTab output={null} />);
    expect(screen.getByText("No AI suggestion yet")).toBeInTheDocument();
    expect(screen.getByText(/never hidden tests/)).toBeInTheDocument();
  });

  it("announces progress politely while a slow local model works", () => {
    render(<AiResultTab output={{ status: "loading", feature: "review" }} />);
    expect(screen.getByRole("status")).toHaveTextContent("working on your review");
  });

  it("labels every reply as the AI's suggestion, names the model, and defers to Submit", () => {
    render(
      <AiResultTab
        output={{ status: "ready", feature: "explain", content: "It sums two numbers.", model: "qwen-test" }}
      />,
    );
    expect(screen.getByText("It sums two numbers.")).toBeInTheDocument();
    expect(screen.getByText(/AI explanation/)).toBeInTheDocument();
    expect(screen.getByText(/qwen-test/)).toBeInTheDocument();
    expect(screen.getByText(/a suggestion, not a verdict/)).toBeInTheDocument();
    expect(screen.getByText("Submit")).toBeInTheDocument();
  });

  it("numbers hints", () => {
    render(<AiResultTab output={{ status: "ready", feature: "hint", content: "Nudge.", model: "m", hintNumber: 3 }} />);
    expect(screen.getByText(/AI hint #3/)).toBeInTheDocument();
  });

  it("shows failures as an alert, with no suggestion banner", () => {
    render(<AiResultTab output={{ status: "error", feature: "hint", message: "Model is busy." }} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Model is busy.");
    expect(screen.queryByText(/not a verdict/)).not.toBeInTheDocument();
  });

  it("only offers the chat link when it knows the problem, and encodes the slug", () => {
    const output = { status: "ready", feature: "hint", content: "x", model: "m" } as const;
    const { rerender } = render(<AiResultTab output={output} />);
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
    rerender(<AiResultTab output={output} problemSlug="a b" />);
    expect(screen.getByRole("link", { name: /Continue in chat/ })).toHaveAttribute("href", "/ai?problem=a%20b");
  });
});

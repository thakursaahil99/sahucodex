import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { Markdown } from "@/components/ui/markdown";

describe("Markdown (admin-authored text shown to every learner)", () => {
  it("renders headings, emphasis, lists, code and tables", () => {
    const { container } = render(
      <Markdown>{"## Title\n\nSome **bold** and `code`.\n\n- one\n- two\n\n| a | b |\n|---|---|\n| 1 | 2 |"}</Markdown>,
    );
    expect(screen.getByRole("heading", { name: "Title" })).toBeInTheDocument();
    expect(container.querySelector("strong")).toHaveTextContent("bold");
    expect(container.querySelector("code")).toHaveTextContent("code");
    expect(container.querySelectorAll("li")).toHaveLength(2);
    expect(container.querySelector("table")).not.toBeNull();
  });

  it("does not execute or even create raw HTML elements (XSS)", () => {
    const { container } = render(
      <Markdown>{'<script>window.pwned = 1</script>\n\n<img src=x onerror="window.pwned = 2">\n\n<iframe src="https://evil.example"></iframe>'}</Markdown>,
    );
    expect(container.querySelector("script")).toBeNull();
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("iframe")).toBeNull();
    expect((window as unknown as { pwned?: number }).pwned).toBeUndefined();
  });

  it("drops images entirely (no external requests or tracking pixels)", () => {
    const { container } = render(<Markdown>{"![tracker](https://evil.example/pixel.png)"}</Markdown>);
    expect(container.querySelector("img")).toBeNull();
  });

  it("opens links safely in a new tab", () => {
    render(<Markdown>{"[docs](https://example.com)"}</Markdown>);
    const link = screen.getByRole("link", { name: "docs" });
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
  });

  it("neutralises javascript: links", () => {
    const { container } = render(<Markdown>{"[click](javascript:alert(1))"}</Markdown>);
    const link = container.querySelector("a");
    expect(link?.getAttribute("href") ?? "").not.toMatch(/^javascript:/i);
  });

  describe("code blocks", () => {
    const fenced = "```python\nprint(1)\nprint(2)\n```";

    it("gives each fenced block a Copy button that copies exactly the code", async () => {
      const writeText = vi.fn().mockResolvedValue(undefined);
      Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
      render(<Markdown>{fenced}</Markdown>);

      await userEvent.click(screen.getByRole("button", { name: "Copy code" }));
      expect(writeText).toHaveBeenCalledWith("print(1)\nprint(2)");
      expect(await screen.findByRole("button", { name: "Copied" })).toBeInTheDocument();
    });

    it("does not add a Copy button to inline code", () => {
      render(<Markdown>{"Use `x = 1` here."}</Markdown>);
      expect(screen.queryByRole("button", { name: "Copy code" })).not.toBeInTheDocument();
    });

    it("survives a denied clipboard without crashing or claiming it copied", async () => {
      const writeText = vi.fn().mockRejectedValue(new Error("denied"));
      Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
      render(<Markdown>{fenced}</Markdown>);

      await userEvent.click(screen.getByRole("button", { name: "Copy code" }));
      await waitFor(() => expect(writeText).toHaveBeenCalled());
      expect(screen.queryByRole("button", { name: "Copied" })).not.toBeInTheDocument();
    });
  });
});

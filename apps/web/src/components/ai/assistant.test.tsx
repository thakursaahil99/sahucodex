import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { Assistant } from "@/components/ai/assistant";
import type { ConversationDetail, ConversationSummary, StreamEvent } from "@/lib/ai/types";
import { ApiError } from "@/lib/api/http";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }));
vi.mock("next/link", () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => <a href={href}>{children}</a>,
}));

const mocks = vi.hoisted(() => ({
  useAiStatus: vi.fn(),
  useConversations: vi.fn(),
  useConversation: vi.fn(),
  renameConversation: vi.fn(),
  deleteConversation: vi.fn(),
  streamAi: vi.fn(),
}));

vi.mock("@/lib/ai/api", () => mocks);
vi.mock("@/lib/ai/stream", () => ({ streamAi: mocks.streamAi }));

const summary = (over: Partial<ConversationSummary> = {}): ConversationSummary => ({
  id: "c1",
  title: "How do I start?",
  problem_slug: null,
  created_at: "2026-09-21T10:00:00Z",
  updated_at: "2026-09-21T10:00:00Z",
  ...over,
});

const transcript = (...pairs: Array<["user" | "assistant", string]>): ConversationDetail => ({
  ...summary(),
  messages: pairs.map(([role, content], i) => ({ id: `m${i}`, role, content, created_at: "2026-09-21T10:00:00Z" })),
});

let saved: ConversationDetail | undefined;
let list: ConversationSummary[];

let queryClient: QueryClient;

function renderAssistant(problemSlug?: string) {
  queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <Assistant problemSlug={problemSlug} />
    </QueryClientProvider>,
  );
}

const box = () => screen.getByRole("textbox", { name: "Message SahuCodeX AI" });

beforeEach(() => {
  saved = undefined;
  list = [];
  for (const mock of Object.values(mocks)) mock.mockReset();
  mocks.useAiStatus.mockReturnValue({ isPending: false, data: { configured: true, model: "qwen-test" } });
  mocks.useConversations.mockImplementation(() => ({ data: list }));
  mocks.useConversation.mockImplementation((id: string | null) => ({ isPending: false, data: id ? saved : undefined }));
  mocks.renameConversation.mockResolvedValue(summary());
  mocks.deleteConversation.mockResolvedValue(undefined);
});

describe("Assistant", () => {
  it("explains how to enable the AI, instead of offering a chat that cannot work, when no model is configured", () => {
    mocks.useAiStatus.mockReturnValue({ isPending: false, data: { configured: false, model: null } });
    renderAssistant();
    expect(screen.getByRole("heading", { name: /isn't set up yet/ })).toBeInTheDocument();
    expect(screen.getByText("OLLAMA_MODEL")).toBeInTheDocument();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  });

  it("starts empty, and says the judge — not the AI — decides correctness", () => {
    renderAssistant();
    expect(screen.getByText(/Ask SahuCodeX AI anything about coding/)).toBeInTheDocument();
    expect(screen.getByText(/SahuJudge — not the AI — decides/)).toBeInTheDocument();
    expect(screen.getByText("qwen-test")).toBeInTheDocument();
  });

  it("creates a conversation on the first message, streams the reply in, then shows the saved transcript", async () => {
    let finish: () => void = () => {};
    mocks.streamAi.mockImplementation(async (_path: string, _body: unknown, onEvent: (e: StreamEvent) => void) => {
      onEvent({ type: "start", conversationId: "c1" });
      onEvent({ type: "token", content: "Use a " });
      await new Promise<void>((resolve) => (finish = resolve));
      onEvent({ type: "token", content: "hash map." });
      onEvent({ type: "done" });
      saved = transcript(["user", "How do I start?"], ["assistant", "Use a hash map."]);
      list = [summary()];
    });
    renderAssistant();

    await userEvent.type(box(), "How do I start?{Enter}");

    expect(mocks.streamAi).toHaveBeenCalledWith(
      "/ai/conversations",
      { message: "How do I start?" },
      expect.any(Function),
      expect.any(AbortSignal),
    );
    expect(await screen.findByText("Use a")).toBeInTheDocument(); // partial reply, mid-stream
    expect(screen.getByRole("button", { name: /Stop/ })).toBeInTheDocument();
    expect(box()).toHaveValue("");

    finish();
    expect(await screen.findByText("Use a hash map.")).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole("button", { name: /Stop/ })).not.toBeInTheDocument());
    expect(screen.getAllByText("How do I start?").length).toBeGreaterThan(0);
  });

  it("sends follow-ups to the same conversation", async () => {
    saved = transcript(["user", "First"], ["assistant", "Answer"]);
    list = [summary()];
    mocks.streamAi.mockResolvedValue(undefined);
    renderAssistant();

    await userEvent.click(screen.getByRole("button", { name: "How do I start?" }));
    expect(await screen.findByText("Answer")).toBeInTheDocument();
    await userEvent.type(box(), "And then?{Enter}");

    expect(mocks.streamAi).toHaveBeenCalledWith(
      "/ai/conversations/c1/messages",
      { content: "And then?" },
      expect.any(Function),
      expect.any(AbortSignal),
    );
  });

  it("attaches the problem context when the chat was opened from a problem", async () => {
    mocks.streamAi.mockResolvedValue(undefined);
    renderAssistant("two-sum");
    await userEvent.type(box(), "hint please{Enter}");
    expect(mocks.streamAi).toHaveBeenCalledWith(
      "/ai/conversations",
      { message: "hint please", problem_slug: "two-sum" },
      expect.any(Function),
      expect.any(AbortSignal),
    );
  });

  it("shows the server's error and puts the message back when it was refused, so nothing typed is lost", async () => {
    mocks.streamAi.mockRejectedValue(new ApiError(503, "AI_UNAVAILABLE", "SahuCodeX AI could not answer right now."));
    renderAssistant();
    await userEvent.type(box(), "please help{Enter}");

    expect(await screen.findByRole("alert")).toHaveTextContent("SahuCodeX AI could not answer right now.");
    await waitFor(() => expect(box()).toHaveValue("please help"));
  });

  it("reports a mid-stream failure in place, keeping what arrived", async () => {
    mocks.streamAi.mockImplementation(async (_p: string, _b: unknown, onEvent: (e: StreamEvent) => void) => {
      onEvent({ type: "start", conversationId: "c1" });
      onEvent({ type: "token", content: "Partial " });
      onEvent({ type: "error", code: "AI_UNAVAILABLE", message: "SahuCodeX AI stopped responding. Please retry." });
      saved = transcript(["user", "hi"], ["assistant", "Partial"]);
    });
    renderAssistant();
    await userEvent.type(box(), "hi{Enter}");

    expect(await screen.findByRole("alert")).toHaveTextContent("stopped responding");
    expect(screen.getByText("Partial")).toBeInTheDocument();
  });

  it("stops a reply when asked to", async () => {
    let signal: AbortSignal | undefined;
    mocks.streamAi.mockImplementation(
      (_p: string, _b: unknown, onEvent: (e: StreamEvent) => void, abort: AbortSignal) =>
        new Promise<void>((resolve, reject) => {
          signal = abort;
          onEvent({ type: "start", conversationId: "c1" });
          abort.addEventListener("abort", () => (reject(new DOMException("aborted", "AbortError")), resolve()));
        }),
    );
    renderAssistant();
    await userEvent.type(box(), "long one{Enter}");
    await userEvent.click(await screen.findByRole("button", { name: /Stop/ }));

    expect(signal?.aborted).toBe(true);
    await waitFor(() => expect(screen.queryByRole("button", { name: /Stop/ })).not.toBeInTheDocument());
    expect(screen.queryByRole("alert")).not.toBeInTheDocument(); // stopping is not an error
  });

  it("fills the composer from a quick start without sending anything", async () => {
    renderAssistant();
    await userEvent.click(screen.getByRole("button", { name: /Debug my code/ }));
    expect((box() as HTMLTextAreaElement).value).toContain("Expected output:");
    expect((box() as HTMLTextAreaElement).value).toContain("Actual output or error:");
    expect(mocks.streamAi).not.toHaveBeenCalled();
  });

  it("does not send a blank message", async () => {
    renderAssistant();
    await userEvent.type(box(), "   {Enter}");
    expect(mocks.streamAi).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: /Send/ })).toBeDisabled();
  });

  it("renames a conversation inline", async () => {
    list = [summary()];
    renderAssistant();
    await userEvent.click(screen.getByRole("button", { name: "Rename How do I start?" }));
    const input = screen.getByRole("textbox", { name: "Conversation title" });
    await userEvent.clear(input);
    await userEvent.type(input, "Two pointers{Enter}");
    await waitFor(() => expect(mocks.renameConversation).toHaveBeenCalledWith("c1", "Two pointers"));
  });

  it("refreshes both the list and the open conversation's own title after a rename", async () => {
    list = [summary()];
    saved = transcript(["user", "hi"], ["assistant", "hello"]);
    renderAssistant();
    await userEvent.click(screen.getByRole("button", { name: "How do I start?" })); // open it
    await screen.findByText("hello");
    const invalidate = vi.spyOn(queryClient, "invalidateQueries");

    await userEvent.click(screen.getByRole("button", { name: "Rename How do I start?" }));
    await userEvent.type(screen.getByRole("textbox", { name: "Conversation title" }), "!{Enter}");

    await waitFor(() => expect(invalidate).toHaveBeenCalledWith({ queryKey: ["ai-conversations"] }));
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["ai-conversation", "c1"] });
  });

  it("asks before deleting, and only then deletes", async () => {
    list = [summary()];
    renderAssistant();
    await userEvent.click(screen.getByRole("button", { name: "Delete How do I start?" }));
    expect(mocks.deleteConversation).not.toHaveBeenCalled();

    const dialog = await screen.findByRole("alertdialog");
    await userEvent.click(within(dialog).getByRole("button", { name: "Delete" }));
    await waitFor(() => expect(mocks.deleteConversation).toHaveBeenCalledWith("c1"));
  });

  it("renders model output as inert Markdown, never as HTML", async () => {
    saved = transcript(["user", "hi"], ["assistant", '<img src=x onerror="window.pwned=1"> <script>window.pwned=2</script> **bold**']);
    list = [summary()];
    const { container } = renderAssistant();
    await userEvent.click(screen.getByRole("button", { name: "How do I start?" }));
    expect(await screen.findByText("bold")).toBeInTheDocument();
    expect(container.querySelector("img, script")).toBeNull();
    expect((window as unknown as { pwned?: number }).pwned).toBeUndefined();
  });
});

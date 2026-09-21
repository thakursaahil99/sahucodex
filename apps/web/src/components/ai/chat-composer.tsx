"use client";

import { Bug, Send, Square } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

// Templates, not a separate feature: they just start the message for you. The Debugger is this chat with the
// facts a debugging answer needs (code, input, expected vs actual) laid out to fill in.
const QUICK_STARTS = [
  {
    label: "Debug my code",
    Icon: Bug,
    text: "Help me debug my code.\n\nLanguage: \n\nCode:\n```\n\n```\n\nInput:\n```\n\n```\n\nExpected output:\n```\n\n```\n\nActual output or error:\n```\n\n```\n",
  },
  { label: "Explain an idea", Icon: null, text: "Explain this concept with a small example: " },
  { label: "Compare approaches", Icon: null, text: "Compare these approaches and their complexity: " },
] as const;

interface ChatComposerProps {
  disabled: boolean;
  streaming: boolean;
  onSend: (text: string) => Promise<boolean>;
  onStop: () => void;
}

export function ChatComposer({ disabled, streaming, onSend, onStop }: ChatComposerProps) {
  const [text, setText] = useState("");

  async function submit() {
    const message = text.trim();
    if (!message || disabled || streaming) return;
    setText("");
    // If the server refused the message (rate limit, size, outage), put it back so nothing typed is lost.
    if (!(await onSend(message))) setText((current) => current || message);
  }

  return (
    <form
      className="space-y-2 border-t bg-card p-3"
      onSubmit={(event) => {
        event.preventDefault();
        void submit();
      }}
    >
      <div className="flex flex-wrap gap-1.5" role="group" aria-label="Quick starts">
        {QUICK_STARTS.map(({ label, Icon, text: template }) => (
          <Button
            key={label}
            type="button"
            variant="outline"
            size="sm"
            className="h-7 px-2.5 text-xs"
            disabled={disabled || streaming}
            onClick={() => setText(template)}
          >
            {Icon && <Icon aria-hidden />} {label}
          </Button>
        ))}
      </div>
      <div className="flex items-end gap-2">
        <label className="sr-only" htmlFor="chat-message">
          Message SahuCodeX AI
        </label>
        <Textarea
          id="chat-message"
          value={text}
          onChange={(event) => setText(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              void submit();
            }
          }}
          disabled={disabled}
          maxLength={8000}
          placeholder="Ask about an algorithm, a bug, a concept… (Enter sends, Shift+Enter for a new line)"
          className="max-h-48 min-h-11 resize-y font-mono text-[13px]"
        />
        {streaming ? (
          <Button type="button" variant="outline" onClick={onStop}>
            <Square aria-hidden /> Stop
          </Button>
        ) : (
          <Button type="submit" disabled={disabled || !text.trim()}>
            <Send aria-hidden /> Send
          </Button>
        )}
      </div>
    </form>
  );
}

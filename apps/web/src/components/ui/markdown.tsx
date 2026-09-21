"use client";

import { Check, Copy } from "lucide-react";
import { isValidElement, useState, type ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { cn } from "@/lib/utils";

/** Plain text of a rendered subtree — what a code block's Copy button puts on the clipboard. */
function textOf(node: ReactNode): string {
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(textOf).join("");
  if (isValidElement<{ children?: ReactNode }>(node)) return textOf(node.props.children);
  return "";
}

function CodeBlock({ children }: { children: ReactNode }) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(textOf(children).replace(/\n$/, ""));
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard access can be denied (insecure context, permissions); the code stays selectable by hand.
    }
  }

  return (
    <div className="relative">
      <pre>{children}</pre>
      <button
        type="button"
        onClick={() => void copy()}
        aria-label={copied ? "Copied" : "Copy code"}
        className="absolute top-2 right-2 inline-flex size-7 items-center justify-center rounded-md border bg-card text-muted-foreground opacity-70 transition hover:opacity-100 focus-visible:opacity-100"
      >
        {copied ? <Check className="size-3.5" aria-hidden /> : <Copy className="size-3.5" aria-hidden />}
      </button>
    </div>
  );
}

/**
 * Renders problem statements, editorials and AI replies.
 *
 * Safe by construction: react-markdown does not render raw HTML (no rehype-raw), so `<script>` or `<img onerror>`
 * in an admin-authored statement — or a model's reply — is shown as text, never executed. Images are dropped
 * entirely (they would be an external request and a tracking vector), and links open in a new tab with
 * `noopener noreferrer`. Fenced code blocks get a Copy button.
 */
export function Markdown({ children, className }: { children: string; className?: string }) {
  return (
    <div className={cn("markdown", className)}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          img: () => null,
          pre: ({ children: content }) => <CodeBlock>{content}</CodeBlock>,
          a: ({ href, children: content }) => (
            <a href={href} target="_blank" rel="noopener noreferrer">
              {content}
            </a>
          ),
        }}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}

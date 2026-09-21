"use client";

import { AArrowDown, AArrowUp, Check, RotateCcw, Sparkles, WrapText } from "lucide-react";
import { useTheme } from "next-themes";
import dynamic from "next/dynamic";
import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import type { EditorHandle } from "@/components/problems/code-editor";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Select } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import {
  clampFont,
  clearDraft,
  DEFAULT_PREFS,
  loadDraft,
  loadPrefs,
  saveDraft,
  savePrefs,
  type EditorPrefs,
} from "@/lib/problems/storage";
import type { Language } from "@/lib/problems/types";

// Monaco is heavy and needs `window`: load it only in the browser, and only on this page.
const CodeEditor = dynamic(() => import("@/components/problems/code-editor"), {
  ssr: false,
  loading: () => <Skeleton className="m-3 h-[calc(100%-1.5rem)]" />,
});

interface EditorPaneProps {
  slug: string;
  language: string;
  languages: Language[];
  starterCode: string;
  onLanguageChange: (language: string) => void;
  onRun: () => void;
  /** Reports the current code on every change (including the initial value), so a parent that needs it at the
   * moment Run/Submit is clicked (without re-rendering itself on every keystroke) can keep a ref up to date. */
  onCodeChange?: (code: string) => void;
}

/**
 * Editor toolbar + Monaco + draft handling for ONE (problem, language). The parent gives this component a `key` of
 * `slug:language`, so switching language remounts it and it loads that language's draft (or the starter code).
 */
export function EditorPane({
  slug,
  language,
  languages,
  starterCode,
  onLanguageChange,
  onRun,
  onCodeChange,
}: EditorPaneProps) {
  const { resolvedTheme } = useTheme();
  const [code, setCode] = useState(() => loadDraft(slug, language) ?? starterCode);

  useEffect(() => {
    onCodeChange?.(code);
  }, [code, onCodeChange]);
  const [prefs, setPrefs] = useState<EditorPrefs>(() => (typeof window === "undefined" ? DEFAULT_PREFS : loadPrefs()));
  const [savedAt, setSavedAt] = useState<Date | null>(null);
  const editor = useRef<EditorHandle | null>(null);
  const latest = useRef(code);
  const monacoLanguage = languages.find((l) => l.key === language)?.editor_language ?? language;
  const modified = code !== starterCode;

  const persist = useCallback(() => {
    if (latest.current === starterCode) {
      clearDraft(slug, language); // nothing worth keeping: the starter template is always available
      setSavedAt(null);
      return;
    }
    saveDraft(slug, language, latest.current);
    setSavedAt(new Date());
  }, [slug, language, starterCode]);

  // Autosave shortly after typing stops, and flush on unmount / tab close so nothing typed is lost.
  useEffect(() => {
    latest.current = code;
    const timer = setTimeout(persist, 600);
    return () => clearTimeout(timer);
  }, [code, persist]);

  useEffect(() => {
    const flush = () => persist();
    window.addEventListener("beforeunload", flush);
    return () => {
      window.removeEventListener("beforeunload", flush);
      flush();
    };
  }, [persist]);

  function updatePrefs(changes: Partial<EditorPrefs>) {
    const next = { ...prefs, ...changes, fontSize: clampFont(changes.fontSize ?? prefs.fontSize) };
    setPrefs(next);
    savePrefs(next);
  }

  const handleReady = useCallback((handle: EditorHandle | null) => {
    editor.current = handle;
  }, []);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div
        className="flex flex-wrap items-center gap-2 border-b bg-card px-3 py-2"
        role="toolbar"
        aria-label="Editor tools"
      >
        <label className="sr-only" htmlFor="language">
          Language
        </label>
        <Select id="language" className="h-9 w-44" value={language} onChange={(e) => onLanguageChange(e.target.value)}>
          {languages.map((l) => (
            <option key={l.key} value={l.key}>
              {l.display_name}
            </option>
          ))}
        </Select>

        <div className="flex items-center gap-0.5" role="group" aria-label="Font size">
          <Button
            variant="ghost"
            size="icon"
            className="size-8"
            aria-label="Decrease font size"
            onClick={() => updatePrefs({ fontSize: prefs.fontSize - 1 })}
          >
            <AArrowDown aria-hidden />
          </Button>
          <span className="w-7 text-center text-xs tabular-nums text-muted-foreground" aria-live="polite">
            {prefs.fontSize}
          </span>
          <Button
            variant="ghost"
            size="icon"
            className="size-8"
            aria-label="Increase font size"
            onClick={() => updatePrefs({ fontSize: prefs.fontSize + 1 })}
          >
            <AArrowUp aria-hidden />
          </Button>
        </div>

        <Button
          variant="ghost"
          size="sm"
          aria-pressed={prefs.wordWrap}
          onClick={() => updatePrefs({ wordWrap: !prefs.wordWrap })}
          className={cn(prefs.wordWrap && "bg-muted")}
        >
          <WrapText aria-hidden /> Wrap
        </Button>
        <Button
          variant="ghost"
          size="sm"
          aria-pressed={prefs.minimap}
          onClick={() => updatePrefs({ minimap: !prefs.minimap })}
          className={cn("hidden sm:inline-flex", prefs.minimap && "bg-muted")}
        >
          Minimap
        </Button>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => {
            const result = editor.current?.format();
            toast.success(result === "formatted" ? "Code formatted" : "Whitespace tidied", {
              description:
                result === "formatted"
                  ? undefined
                  : "Python and C++ have no bundled formatter, so only trailing spaces and the final newline are cleaned up.",
            });
          }}
        >
          <Sparkles aria-hidden /> Format
        </Button>
        <ConfirmDialog
          trigger={
            <Button variant="ghost" size="sm" disabled={!modified}>
              <RotateCcw aria-hidden /> Reset
            </Button>
          }
          title="Reset to the starter code?"
          description="Your current code for this language will be replaced and its saved draft deleted. This can't be undone."
          confirmLabel="Reset code"
          destructive
          onConfirm={() => {
            clearDraft(slug, language);
            setCode(starterCode);
            toast.success("Code reset to the starter template");
          }}
        />

        <p className="ml-auto flex items-center gap-1 text-xs text-muted-foreground" role="status">
          {savedAt ? (
            <>
              <Check className="size-3.5 text-success" aria-hidden />
              Draft saved
            </>
          ) : modified ? (
            "Unsaved changes"
          ) : (
            "Starter code"
          )}
        </p>
      </div>

      <div className="min-h-0 flex-1">
        <CodeEditor
          value={code}
          onChange={setCode}
          language={monacoLanguage}
          dark={resolvedTheme !== "light"}
          fontSize={prefs.fontSize}
          // The minimap is wasted space on a phone, so it only shows on wider screens.
          minimap={prefs.minimap && typeof window !== "undefined" && window.innerWidth >= 640}
          wordWrap={prefs.wordWrap}
          onRun={onRun}
          onSave={() => {
            persist();
            toast.success("Draft saved");
          }}
          onReady={handleReady}
        />
      </div>
    </div>
  );
}

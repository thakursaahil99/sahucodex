"use client";

import Editor, { loader, type BeforeMount, type OnMount } from "@monaco-editor/react";
import { useEffect, useRef, useState } from "react";

import { Skeleton } from "@/components/ui/skeleton";
import { normalizeWhitespace } from "@/lib/problems/storage";

// Serve Monaco from our own origin (copied to /monaco by scripts/copy-monaco.mjs) instead of a public CDN:
// it satisfies the Content-Security-Policy, works offline, and adds no third-party dependency.
loader.config({ paths: { vs: "/monaco/vs" } });

export interface EditorHandle {
  /** Formats the document: Monaco's formatter for JavaScript, whitespace clean-up for the rest. */
  format: () => "formatted" | "normalized";
  focus: () => void;
}

export interface CodeEditorProps {
  value: string;
  onChange: (value: string) => void;
  /** Monaco language id (`python`, `cpp`, `javascript`, …). */
  language: string;
  dark: boolean;
  fontSize: number;
  minimap: boolean;
  wordWrap: boolean;
  onRun: () => void;
  onSave: () => void;
  onReady: (handle: EditorHandle | null) => void;
}

const beforeMount: BeforeMount = (monaco) => {
  monaco.editor.defineTheme("sahucodex-dark", {
    base: "vs-dark",
    inherit: true,
    rules: [],
    colors: {
      "editor.background": "#0f1220",
      "editor.lineHighlightBackground": "#151929",
      "editorLineNumber.foreground": "#4b5573",
      "editorLineNumber.activeForeground": "#9aa3c0",
      "editorCursor.foreground": "#4c86ff",
      "editor.selectionBackground": "#2f66ec55",
    },
  });
  monaco.editor.defineTheme("sahucodex-light", {
    base: "vs",
    inherit: true,
    rules: [],
    colors: { "editor.background": "#ffffff", "editor.lineHighlightBackground": "#f3f5fb" },
  });
  // Programs here read stdin via `require("fs")`; the editor's type checker doesn't know Node's globals and would
  // underline them. Keep syntax errors and completions, drop the noisy semantic checks.
  monaco.languages.typescript.javascriptDefaults.setDiagnosticsOptions({
    noSemanticValidation: true,
    noSyntaxValidation: false,
  });
  monaco.languages.typescript.javascriptDefaults.setEagerModelSync(true);
};

export default function CodeEditor(props: CodeEditorProps) {
  const { value, onChange, language, dark, fontSize, minimap, wordWrap, onReady } = props;
  const [failed, setFailed] = useState(false);

  // Keyboard shortcuts are registered once at mount, so they read the latest callbacks through refs.
  const latest = useRef(props);
  useEffect(() => {
    latest.current = props;
  });

  useEffect(() => {
    let cancelled = false;
    loader.init().catch(() => {
      if (!cancelled) setFailed(true);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const onMount: OnMount = (editor, monaco) => {
    editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.Enter, () => latest.current.onRun());
    editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, () => latest.current.onSave());
    onReady({
      focus: () => editor.focus(),
      format: () => {
        if (latest.current.language === "javascript") {
          void editor.getAction("editor.action.formatDocument")?.run();
          return "formatted";
        }
        const model = editor.getModel();
        if (model) {
          // executeEdits keeps the change on the undo stack.
          editor.executeEdits("sahucodex-format", [
            { range: model.getFullModelRange(), text: normalizeWhitespace(model.getValue()) },
          ]);
        }
        return "normalized";
      },
    });
  };

  useEffect(() => () => onReady(null), [onReady]);

  if (failed) {
    return (
      <div className="flex h-full flex-col">
        <p role="alert" className="border-b bg-warning/10 px-3 py-2 text-xs text-warning">
          The code editor failed to load, so a plain text box is shown. Your work is still saved as a draft.
        </p>
        <textarea
          aria-label="Code editor (fallback)"
          spellCheck={false}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="min-h-0 flex-1 resize-none bg-card p-3 font-mono text-sm outline-none"
          style={{ fontSize }}
        />
      </div>
    );
  }

  return (
    <Editor
      height="100%"
      language={language}
      value={value}
      theme={dark ? "sahucodex-dark" : "sahucodex-light"}
      beforeMount={beforeMount}
      onMount={onMount}
      onChange={(next) => onChange(next ?? "")}
      loading={<Skeleton className="m-3 h-[calc(100%-1.5rem)]" />}
      options={{
        fontSize,
        minimap: { enabled: minimap },
        wordWrap: wordWrap ? "on" : "off",
        tabSize: 4,
        insertSpaces: true,
        automaticLayout: true,
        scrollBeyondLastLine: false,
        padding: { top: 12, bottom: 12 },
        fontFamily: 'ui-monospace, "Cascadia Code", "JetBrains Mono", Menlo, Consolas, monospace',
        bracketPairColorization: { enabled: true },
        renderWhitespace: "selection",
        smoothScrolling: true,
        ariaLabel: "Code editor",
        // Suggestions from words already in the file work for every language; IntelliSense is richer for JavaScript.
        wordBasedSuggestions: "currentDocument",
        quickSuggestions: { other: true, comments: false, strings: false },
      }}
    />
  );
}

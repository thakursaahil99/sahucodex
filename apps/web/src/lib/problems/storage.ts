/**
 * Per-browser conveniences: code drafts and editor preferences.
 *
 * localStorage can be missing, full, or throw (private windows, blocked site data), so every access is wrapped and
 * the editor works without it. Nothing sensitive is stored here — only the user's own draft code and UI settings.
 */

const PREFIX = "sahucodex:";

export interface EditorPrefs {
  fontSize: number;
  minimap: boolean;
  wordWrap: boolean;
}

export const DEFAULT_PREFS: EditorPrefs = { fontSize: 14, minimap: true, wordWrap: false };
export const MIN_FONT = 10;
export const MAX_FONT = 28;

export const clampFont = (size: number): number =>
  Math.min(MAX_FONT, Math.max(MIN_FONT, Math.round(Number.isFinite(size) ? size : DEFAULT_PREFS.fontSize)));

function read(key: string): string | null {
  try {
    return window.localStorage.getItem(PREFIX + key);
  } catch {
    return null;
  }
}

function write(key: string, value: string): boolean {
  try {
    window.localStorage.setItem(PREFIX + key, value);
    return true;
  } catch {
    return false;
  }
}

function remove(key: string): void {
  try {
    window.localStorage.removeItem(PREFIX + key);
  } catch {
    /* nothing to clean up */
  }
}

export const loadDraft = (slug: string, language: string): string | null => read(`draft:${slug}:${language}`);
export const saveDraft = (slug: string, language: string, code: string): boolean =>
  write(`draft:${slug}:${language}`, code);
export const clearDraft = (slug: string, language: string): void => remove(`draft:${slug}:${language}`);

export const loadLanguage = (slug: string): string | null => read(`language:${slug}`);
export const saveLanguage = (slug: string, language: string): boolean => write(`language:${slug}`, language);

export function loadPrefs(): EditorPrefs {
  const raw = read("editor-prefs");
  if (!raw) return DEFAULT_PREFS;
  try {
    const parsed = JSON.parse(raw) as Partial<EditorPrefs>;
    return {
      fontSize: clampFont(Number(parsed.fontSize ?? DEFAULT_PREFS.fontSize)),
      minimap: typeof parsed.minimap === "boolean" ? parsed.minimap : DEFAULT_PREFS.minimap,
      wordWrap: typeof parsed.wordWrap === "boolean" ? parsed.wordWrap : DEFAULT_PREFS.wordWrap,
    };
  } catch {
    return DEFAULT_PREFS;
  }
}

export const savePrefs = (prefs: EditorPrefs): boolean => write("editor-prefs", JSON.stringify(prefs));

/**
 * Whitespace-only clean-up for languages without a bundled formatter (Python, C++): trims trailing spaces and
 * guarantees a single final newline. It never re-indents or reorders code, so it cannot change behaviour.
 */
export function normalizeWhitespace(code: string): string {
  const lines = code.replace(/\r\n?/g, "\n").split("\n").map((line) => line.replace(/[ \t]+$/, ""));
  while (lines.length > 1 && lines[lines.length - 1] === "") lines.pop();
  return `${lines.join("\n")}\n`;
}

/**
 * Copies Monaco Editor's runtime files into public/monaco so the editor is served from our own origin.
 *
 * Why: the default loader fetches Monaco from a public CDN, which would (a) break under our Content-Security-Policy,
 * (b) stop working offline / on a private network, and (c) make the app depend on a third party. The copied folder is
 * build output (git-ignored) and is refreshed automatically before `dev` and `build`.
 */
import { cpSync, existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const webRoot = join(here, "..");

/** npm workspaces usually hoist to the repo root, but may leave it in apps/web/node_modules; look upwards. */
function findMonaco() {
  let dir = webRoot;
  for (;;) {
    const candidate = join(dir, "node_modules", "monaco-editor");
    if (existsSync(join(candidate, "package.json"))) return candidate;
    const parent = dirname(dir);
    if (parent === dir) return null;
    dir = parent;
  }
}

const monacoRoot = findMonaco();
if (!monacoRoot) {
  console.error("copy-monaco: monaco-editor is not installed. Run `npm install` at the repository root.");
  process.exit(1);
}

const version = JSON.parse(readFileSync(join(monacoRoot, "package.json"), "utf8")).version;
const target = join(webRoot, "public", "monaco");
const marker = join(target, ".version");

if (existsSync(marker) && readFileSync(marker, "utf8").trim() === version) {
  console.log(`copy-monaco: Monaco ${version} already in public/monaco`);
  process.exit(0);
}

rmSync(target, { recursive: true, force: true });
mkdirSync(target, { recursive: true });
cpSync(join(monacoRoot, "min", "vs"), join(target, "vs"), { recursive: true });
writeFileSync(marker, `${version}\n`);
console.log(`copy-monaco: copied Monaco ${version} to public/monaco`);

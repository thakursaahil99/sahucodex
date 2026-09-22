// Transpiles one TypeScript file to plain JavaScript for the judge's `typescript` LanguageSpec.
// Deliberately no type-checking: `esbuild` strips types without verifying them, which is what a judge wants (fast,
// faithful-to-Node execution) and matches how competitive-programming judges have always treated TS as "JS + types".
// Usage: node esbuild.js <in.ts> <out.js>
"use strict";
const esbuild = require("esbuild");

const [, , inPath, outPath] = process.argv;
if (!inPath || !outPath) {
  process.stderr.write("usage: esbuild.js <in.ts> <out.js>\n");
  process.exit(2);
}

esbuild
  .build({
    entryPoints: [inPath],
    outfile: outPath,
    bundle: false,
    platform: "node",
    format: "cjs",
    target: "node22",
    logLevel: "silent",
  })
  .catch((err) => {
    process.stderr.write(String((err && err.message) || err) + "\n");
    process.exit(1);
  });

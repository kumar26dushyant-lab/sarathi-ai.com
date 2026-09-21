// Lint the JavaScript that lives inside an ops page.
//
// The page is one HTML file with several <script> blocks, and in the browser they share ONE
// global scope - a function written in the first block is callable from the fifth. So they are
// joined into one file before linting, which is the only way `no-undef` gives the right answer:
// linted separately, every cross-block call would look undefined.
//
// Line numbers are mapped back to the HTML file, so a report points at the real line.
//
//   node deploy/verify-page-js.mjs static/nidaan_ops.html [more.html ...]
//
// Exits non-zero if anything is reported. Run it before shipping a page change.

import { readFileSync } from "node:fs";
import { ESLint } from "eslint";

const files = process.argv.slice(2);
if (!files.length) {
  console.error("usage: node deploy/verify-page-js.mjs <page.html> [...]");
  process.exit(2);
}

let problems = 0;

// Names the page's OWN script files hang on window. Discovered rather than listed by hand: a
// hand-kept list rots, and every stale entry is a name the linter stops checking - which is the
// one thing this must not do quietly.
function externalGlobals(html) {
  const found = {};
  const harvest = (code, alsoFunctions) => {
    // `window.foo = ...` really does create a global called foo. no-undef does not know that -
    // it only tracks declarations - so every page using that pattern would report itself broken.
    for (const g of code.matchAll(/\b(?:window|root|globalThis|self)\.([A-Za-z_$][\w$]*)\s*=/g)) {
      found[g[1]] = "readonly";
    }
    // A script file wrapped in an IIFE hands its helpers out under whatever name the wrapper's
    // parameter has, which cannot be matched reliably. Its top-level function declarations are
    // the honest signal that the name exists.
    if (alsoFunctions) {
      for (const g of code.matchAll(/(?:^|\n)\s*(?:async\s+)?function\s+([A-Za-z_$][\w$]*)/g)) {
        found[g[1]] = "readonly";
      }
    }
  };
  harvest(html, false);
  for (const m of html.matchAll(/<script[^>]*\bsrc=["']([^"']+)["']/g)) {
    const path = m[1].split("?")[0].replace(/^\//, "");
    let code;
    try {
      code = readFileSync(path, "utf8");
    } catch {
      console.log(`  (note: ${path} is loaded by the page but not readable from here)`);
      continue;
    }
    harvest(code, true);
  }
  return found;
}

for (const file of files) {
  const src = readFileSync(file, "utf8");
  const eslint = new ESLint({
    overrideConfigFile: "eslint.config.mjs",
    overrideConfig: { languageOptions: { globals: externalGlobals(src) } },
  });

  // Every inline block, in order, with the HTML line each one starts on.
  const blocks = [];
  const re = /<script(?![^>]*\bsrc=)([^>]*)>([\s\S]*?)<\/script>/gi;
  let m;
  while ((m = re.exec(src)) !== null) {
    // A <script> is not always JavaScript. JSON-LD for search engines and HTML templates both
    // live in script tags, and feeding those to a JS parser reports a syntax error that is not
    // one - the fastest way to teach somebody to ignore this check.
    const type = (m[1].match(/\btype\s*=\s*["']([^"']+)["']/) || [])[1] || "";
    if (type && !/^(text\/javascript|application\/javascript|module)$/i.test(type)) continue;
    // A server-side template is not JavaScript until it has been rendered: `bio: {{BIO_JSON}}`
    // is a syntax error here and correct in the file. Reporting it teaches people to ignore
    // this check, which is the one thing it must never do.
    if (/\{\{[A-Z0-9_]+\}\}/.test(m[2])) {
      console.log(`  (skipping a templated script block in ${file} - {{...}} placeholders)`);
      continue;
    }
    blocks.push({ code: m[2], htmlLine: src.slice(0, m.index).split("\n").length });
  }
  if (!blocks.length) {
    console.log(`${file}: no inline script to check`);
    continue;
  }

  // Joined, with a marker line before each block so a reported line can be mapped home.
  const parts = [];
  const index = [];          // {fromLine, htmlLine} for the joined file
  let line = 1;
  for (const b of blocks) {
    const header = `/* block starting at ${file}:${b.htmlLine} */\n`;
    parts.push(header, b.code, "\n");
    index.push({ fromLine: line + 1, htmlLine: b.htmlLine });
    line += 1 + b.code.split("\n").length;
  }

  // Linted as TEXT, not as a temp file on disk: eslint refuses to look at anything outside the
  // project directory, and writing the joined code into the repo to get around that would leave
  // a stray file behind on every run.
  const results = await eslint.lintText(parts.join(""), { filePath: "page-inline.js" });
  const msgs = results.flatMap((r) => r.messages);

  // A line in the joined file -> the line in the HTML it came from.
  const toHtml = (joinedLine) => {
    let best = index[0];
    for (const e of index) if (e.fromLine <= joinedLine) best = e;
    // The block's own first line is `best.htmlLine`, one past its <script> tag.
    const offset = joinedLine - best.fromLine;
    return best.htmlLine + offset;
  };

  if (!msgs.length) {
    console.log(`${file}: ${blocks.length} inline block(s), nothing reported`);
    continue;
  }
  console.log(`\n${file}:`);
  for (const x of msgs) {
    problems++;
    console.log(
      `  line ${String(toHtml(x.line)).padEnd(6)} ${x.ruleId ?? "parse"}  ${x.message}`
    );
  }
}

console.log(`\n${problems} problem(s)`);
process.exit(problems ? 1 : 0);

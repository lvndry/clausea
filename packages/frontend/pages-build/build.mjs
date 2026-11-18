import { spawnSync } from "node:child_process";
import { cp, readFile, readdir, rm, writeFile } from "node:fs/promises";
import { join, relative, sep } from "node:path";
import { fileURLToPath } from "node:url";

const frontend = fileURLToPath(new URL("..", import.meta.url));
// Outside the frontend folder, which cannot be copied into itself.
const scratch = join(frontend, "../../.pages-build");

// Everything that needs a server, an account or a secret stays out of the static site.
const LEFT_OUT = new Set([
  "node_modules",
  ".next",
  "pages-build",
  "out",
  "docs",
  "app/(auth)",
  "app/(dashboard)",
  "app/(site)/bot.html",
  "app/(site)/contact",
  "app/actions",
  "app/api",
  "app/og",
  "app/llms.txt",
  "app/manifest.ts",
  "app/robots.ts",
  "app/sitemap.ts",
  "proxy.ts",
  "instrumentation.ts",
  "instrumentation-client.ts",
  "next.config.mjs",
  "vitest.config.ts",
  "vitest.setup.ts",
  "knip.json",
  "Dockerfile",
]);

function keep(source) {
  const path = relative(frontend, source).split(sep).join("/");
  if (LEFT_OUT.has(path)) return false;
  if (path.startsWith(".env")) return false;
  return !/\.test\.tsx?$/.test(path);
}

function run(command, args) {
  const result = spawnSync(command, args, { cwd: scratch, stdio: "inherit" });
  if (result.status !== 0) process.exit(result.status ?? 1);
}

await rm(scratch, { recursive: true, force: true });
await cp(frontend, scratch, { recursive: true, filter: keep });
await cp(
  join(frontend, "pages-build/next.config.mjs"),
  join(scratch, "next.config.mjs"),
);
await cp(join(frontend, "pages-build/stubs"), join(scratch, "pages-stubs"), {
  recursive: true,
});
// Static versions of the hooks that need the app, laid over the copy at the same paths.
await cp(join(frontend, "pages-build/overrides"), scratch, { recursive: true });

// Turbopack ignores an alias on next/link, so the import is swapped in the copy instead.
for (const entry of await readdir(scratch, { recursive: true })) {
  if (!/\.tsx?$/.test(entry) || entry.startsWith("pages-stubs")) continue;
  const file = join(scratch, entry);
  const source = await readFile(file, "utf8");
  const rewritten = source.replaceAll(
    'from "next/link"',
    'from "@/pages-stubs/link"',
  );
  if (rewritten !== source) await writeFile(file, rewritten);
}

run("bun", ["install", "--frozen-lockfile"]);
run("bunx", ["next", "build"]);

console.log(`Static site written to ${join(scratch, "out")}`);

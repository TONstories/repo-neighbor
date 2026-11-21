import { cp, mkdir, rm, writeFile } from "node:fs/promises";
import { build } from "esbuild";

const directory = ".appwrite-build";
await mkdir(directory, { recursive: true });
await rm(directory + "/dist", { recursive: true, force: true });
await cp("dist", directory + "/dist", { recursive: true });
await writeFile(directory + "/package.json", '{"type":"module","private":true}\n');
await build({
  entryPoints: ["src/appwrite.mjs"], bundle: true, platform: "node",
  target: "node24", format: "esm", outfile: directory + "/main.mjs",
});

import { copyFileSync, existsSync, mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";

const vendors = [
  {
    name: "marked",
    output: "web/static/dist/marked.min.js",
    candidates: [
      "node_modules/marked/marked.min.js",
      "node_modules/marked/lib/marked.umd.js",
    ],
  },
];

for (const vendor of vendors) {
  const source = vendor.candidates.map((path) => resolve(path)).find(existsSync);
  if (!source) {
    const candidates = vendor.candidates.join(", ");
    throw new Error(
      `Cannot find ${vendor.name}. Run npm install first. Tried: ${candidates}`,
    );
  }

  const output = resolve(vendor.output);
  mkdirSync(dirname(output), { recursive: true });
  copyFileSync(source, output);
  console.log(`Copied ${vendor.name} to ${vendor.output}`);
}

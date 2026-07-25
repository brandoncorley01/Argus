/**
 * Lightweight check for founder activity mapping (no Jest in EOC).
 * Run: node scripts/check-activity-feed.mjs
 */
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import ts from "typescript";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(__dirname, "..");

const srcPath = path.join(root, "src/lib/founder/activityFeed.ts");
const source = fs.readFileSync(srcPath, "utf8");
const { outputText } = ts.transpileModule(source, {
  compilerOptions: {
    module: ts.ModuleKind.ESNext,
    target: ts.ScriptTarget.ES2022,
    esModuleInterop: true,
  },
});
const tmp = path.join(root, ".tmp-activityFeed.mjs");
fs.writeFileSync(tmp, outputText);

const mod = await import(pathToFileURL(tmp).href);
fs.unlinkSync(tmp);

const items = mod.buildFounderActivity({
  audits: [
    {
      id: "a1",
      occurred_at: "2026-07-25T12:00:00Z",
      action: "paper.pause_new_entries",
      resource_type: "paper_portfolio",
      resource_id: "11111111-1111-1111-1111-111111111111",
      payload: { active: true },
    },
  ],
  fills: [
    {
      id: "f1",
      symbol: "BTC-USD",
      side: "buy",
      quantity: "1",
      price: "100",
      filled_at: "2026-07-25T12:01:00Z",
    },
  ],
  limit: 10,
});

assert.ok(items.some((i) => String(i.title).includes("Pause new entries")));
assert.ok(items.some((i) => String(i.title).includes("BTC-USD")));
assert.equal(items[0]?.at, "2026-07-25T12:01:00Z");
console.log("activityFeed check ok:", items.length, "items");

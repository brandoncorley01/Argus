import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import ts from "typescript";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(__dirname, "..");
const srcPath = path.join(root, "src/lib/founder/decisionStream.ts");
const source = fs.readFileSync(srcPath, "utf8");
const { outputText } = ts.transpileModule(source, {
  compilerOptions: {
    module: ts.ModuleKind.ESNext,
    target: ts.ScriptTarget.ES2022,
  },
});
const tmp = path.join(root, ".tmp-decisionStream.mjs");
fs.writeFileSync(tmp, outputText);
const mod = await import(pathToFileURL(tmp).href);
fs.unlinkSync(tmp);

const items = mod.buildDecisionStream({
  scanEvents: [
    {
      id: "1",
      occurred_at: "2026-07-25T12:00:00Z",
      symbol: "BTC-USD",
      title: "Entry rejected for BTC-USD",
      detail: "Weak signal",
      outcome: "rejected",
      reason_code: "weak_signal",
      strategy_key: "sma_crossover",
      correlation_id: "abc",
      component: "strategy_evaluator",
    },
  ],
  fills: [],
  limit: 5,
});
assert.equal(items.length, 1);
assert.ok(items[0].event.includes("BTC-USD") || items[0].symbol === "BTC-USD");
assert.equal(items[0].tone, "bad");
console.log("decisionStream check ok");

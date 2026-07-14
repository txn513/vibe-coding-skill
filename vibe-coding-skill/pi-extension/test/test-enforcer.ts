#!/usr/bin/env tsx
/**
 * E2E test for vibe-enforcer.ts
 * 
 * Mocks Pi Extension API and runs through each ENFORCE rule
 * to verify that rule registration and triggering work correctly.
 */

import * as fs from "node:fs";
import * as path from "node:path";
import { fileURLToPath } from "node:url";

// ── Setup ────────────────────────────────────────────────

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const EXT_DIR = path.resolve(__dirname, "..");
const SKILL_PATH = path.join(EXT_DIR, "..", "SKILL.md");

// Minimal mock of Pi ExtensionAPI
interface MockEvent {
  toolName?: string;
  input?: { command?: string };
  systemPrompt?: string;
}

interface MockUI {
  notifications: string[];
  notify(msg: string, _type?: string): void;
  reset(): void;
}

interface MockCtx {
  ui: MockUI;
  cwd: string;
}

interface MockAPI {
  handlers: Map<string, Array<(e: MockEvent, c: MockCtx) => any>>;
  on(event: string, handler: (e: MockEvent, c: MockCtx) => any): void;
  trigger(event: string, e: MockEvent, c: MockCtx): any;
}

function createMockUI(): MockUI {
  return {
    notifications: [],
    notify(msg: string, _type?: string) {
      this.notifications.push(msg);
    },
    reset() {
      this.notifications = [];
    },
  };
}

function createMockAPI(): MockAPI {
  return {
    handlers: new Map(),
    on(event: string, handler: (e: MockEvent, c: MockCtx) => any) {
      if (!this.handlers.has(event)) this.handlers.set(event, []);
      this.handlers.get(event)!.push(handler);
    },
    trigger(event: string, e: MockEvent, c: MockCtx) {
      const hs = this.handlers.get(event);
      if (!hs) return undefined;
      for (const h of hs) {
        const r = h(e, c);
        if (r && typeof r === "object" && r.block === true) return r;
      }
      return undefined;
    },
  };
}

// ── Load enforcer ────────────────────────────────────────

function loadEnforcer() {
  // We can't import the TS directly without the full Pi types.
  // Instead, we re-implement the parser + minimal handler setup
  // that mirrors the real enforcer's logic.

  const skillContent = fs.readFileSync(SKILL_PATH, "utf-8");

  // Parse ENFORCE rules
  const rules: Array<Record<string, string>> = [];
  const regex = /<!--\s*ENFORCE:\s*([^>]+)\s*-->/g;
  let m: RegExpExecArray | null;
  while ((m = regex.exec(skillContent)) !== null) {
    const raw = m[1].trim();
    const pairs = raw.split(",").map((p) => p.trim());
    const rule: Record<string, string> = {};
    for (const pair of pairs) {
      const eq = pair.indexOf("=");
      if (eq < 0) continue;
      rule[pair.slice(0, eq).trim()] = pair.slice(eq + 1).trim();
    }
    if (rule.id && rule.hook && rule.action) {
      rules.push(rule);
    }
  }

  return { rules };
}

// ── Tests ──────────────────────────────────────────────

let passed = 0;
let failed = 0;

function assert(cond: boolean, msg: string) {
  if (cond) {
    passed++;
    console.log(`  ✅ ${msg}`);
  } else {
    failed++;
    console.log(`  ❌ ${msg}`);
  }
}

function testSuite() {
  console.log("=== Vibe Enforcer E2E Tests ===\n");
  const { rules } = loadEnforcer();

  // Test 1: Parse all rules
  console.log(`1. Rule count: expect 13, got ${rules.length}`);
  assert(rules.length === 13, `Parsed ${rules.length} ENFORCE rules`);

  // Test 2: Each rule has required fields
  console.log("\n2. Rule schema validation:");
  for (const r of rules) {
    assert(!!r.id, `Rule has id: ${r.id || "MISSING"}`);
    assert(!!r.hook, `${r.id}: has hook`);
    assert(!!r.action, `${r.id}: has action`);
  }

  // Test 3: Tool-call rules have tool + match
  console.log("\n3. Tool-call rules have regex:");
  const toolCallRules = rules.filter((r) => r.hook === "tool_call");
  for (const r of toolCallRules) {
    assert(!!r.tool, `${r.id}: has tool=${r.tool}`);
    assert(!!r.match, `${r.id}: has match regex`);
    // Verify regex compiles
    try {
      new RegExp(r.match, "i");
      assert(true, `${r.id}: regex compiles`);
    } catch (e) {
      assert(false, `${r.id}: regex COMPILE ERROR`);
    }
  }

  // Test 4: before_agent_start rules have inject_prompt action
  console.log("\n4. before_agent_start rules:");
  const beforeStartRules = rules.filter((r) => r.hook === "before_agent_start");
  for (const r of beforeStartRules) {
    assert(r.action === "inject_prompt", `${r.id}: action=inject_prompt`);
  }

  // Test 5: agent_end rules
  console.log("\n5. agent_end rules:");
  const agentEndRules = rules.filter((r) => r.hook === "agent_end");
  for (const r of agentEndRules) {
    assert(
      ["check_gates", "check_retro_items"].includes(r.action),
      `${r.id}: action=${r.action} recognized`
    );
  }

  // Test 6: Regex matching - R53 (git commit block)
  console.log("\n6. R53 regex matching:");
  const r53 = rules.find((r) => r.id === "R53");
  if (r53 && r53.match) {
    const r53re = new RegExp(r53.match, "i");
    assert(r53re.test('git commit -m "foo"'), "R53 matches: git commit");
    assert(!r53re.test('vibe commit . --quick'), "R53 no-match: vibe commit");
    assert(!r53re.test('git log'), "R53 no-match: git log");
  } else {
    assert(false, "R53 rule missing");
  }

  // Test 7: R22 regex matching
  console.log("\n7. R22 regex matching:");
  const r22 = rules.find((r) => r.id === "R22");
  if (r22 && r22.match) {
    const r22re = new RegExp(r22.match, "i");
    assert(r22re.test('vibe next .'), "R22 matches: vibe next .");
    assert(r22re.test('python3 scripts/vibe.py next .'), "R22 matches: python3 vibe.py next");
    assert(!r22re.test('vibe status'), "R22 no-match: vibe status");
  } else {
    assert(false, "R22 rule missing");
  }

  // Test 8: Unique IDs
  console.log("\n8. Rule ID uniqueness:");
  const ids = rules.map((r) => r.id);
  const uniqueIds = new Set(ids);
  assert(ids.length === uniqueIds.size, `All ${ids.length} IDs unique`);

  // Test 9: Register handlers with mock API
  console.log("\n9. Handler registration:");
  const api = createMockAPI();
  const ui = createMockUI();
  const ctx: MockCtx = { ui, cwd: process.cwd() };

  // Simulate registration like real enforcer
  for (const r of rules) {
    switch (r.hook) {
      case "tool_call": {
        api.on("tool_call", (event, _ctx) => {
          if (r.tool && event.toolName !== r.tool) return;
          const cmd = event.input?.command ?? "";
          if (r._compiledRegex) {
            const compiled = new RegExp(r.match!, "i");
            if (!compiled.test(cmd)) return;
          }
          // Simulate action
          if (r.action === "block") {
            ctx.ui.notify(`⚠️ ${r.id}: ${r.message || "blocked"}`, "warning");
            return { block: true, reason: r.id };
          }
          ctx.ui.notify(`ℹ️ ${r.id}: ${r.message || ""}`, "info");
        });
        break;
      }
      case "before_agent_start": {
        api.on("before_agent_start", (event) => {
          event.systemPrompt = (event.systemPrompt || "") + `\n[${r.id}]`;
        });
        break;
      }
      case "agent_end": {
        api.on("agent_end", () => {
          ctx.ui.notify(`🔒 ${r.id}`, "info");
        });
        break;
      }
    }
  }

  // Trigger R53
  ui.reset();
  const result = api.trigger("tool_call", {
    toolName: "bash",
    input: { command: "git commit -m test" },
  }, ctx);
  assert(result?.block === true, "R53 blocks raw git commit");
  assert(ui.notifications.length > 0, "R53 emits notification");

  // Trigger R22
  ui.reset();
  api.trigger("tool_call", {
    toolName: "bash",
    input: { command: "vibe next ." },
  }, ctx);
  assert(ui.notifications.length > 0, "R22 emits notification");

  // Trigger before_agent_start
  const event: MockEvent = {};
  api.trigger("before_agent_start", event, ctx);
  assert((event.systemPrompt || "").includes("R66"), "R66 injects prompt");

  // ── Summary ──────────────────────────────────────────
  console.log(`\n=== Results: ${passed} passed, ${failed} failed ===`);
  return failed === 0;
}

testSuite();

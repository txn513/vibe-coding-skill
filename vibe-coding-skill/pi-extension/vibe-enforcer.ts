import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import * as fs from "node:fs";
import * as path from "node:path";

interface EnforceRule {
  id: string;
  hook: string;
  action: string;
  tool?: string;
  match?: string;
  message?: string;
  _compiledRegex?: RegExp;
}

function findSkillPath(cwd: string): string | null {
  const candidates: string[] = [];
  candidates.push(path.join(process.env.HOME || "", ".pi", "agent", "skills", "vibe-coding", "SKILL.md"));
  candidates.push(path.join(process.env.HOME || "", ".agents", "skills", "vibe-coding", "SKILL.md"));
  candidates.push(path.join(cwd, ".pi", "skills", "vibe-coding", "SKILL.md"));
  candidates.push(path.join(cwd, ".agents", "skills", "vibe-coding", "SKILL.md"));
  const extDir = __dirname;
  candidates.push(path.join(extDir, "..", "SKILL.md"));

  for (const c of candidates) {
    try { if (fs.existsSync(c)) return c; } catch {}
  }
  return null;
}

function findScriptsDir(skillPath: string): string | null {
  const dir = path.dirname(skillPath);
  const scriptsDir = path.join(dir, "scripts");
  if (fs.existsSync(scriptsDir)) return scriptsDir;
  return null;
}

function findProjectRoot(cwd: string): string {
  // Walk up to find .agents/ directory
  let current = path.resolve(cwd);
  for (let i = 0; i < 10; i++) {
    if (fs.existsSync(path.join(current, ".agents"))) return current;
    const parent = path.dirname(current);
    if (parent === current) break;
    current = parent;
  }
  return cwd;
}

function parseEnforceComments(content: string): EnforceRule[] {
  const rules: EnforceRule[] = [];
  const regex = /<!--\s*ENFORCE:\s*([^>]+)\s*-->/g;
  let m: RegExpExecArray | null;
  while ((m = regex.exec(content)) !== null) {
    const raw = m[1].trim();
    const pairs = raw.split(",").map((p) => p.trim());
    const rule: Partial<EnforceRule> = {};
    for (const pair of pairs) {
      const eq = pair.indexOf("=");
      if (eq < 0) continue;
      const key = pair.slice(0, eq).trim();
      const val = pair.slice(eq + 1).trim();
      (rule as Record<string, string>)[key] = val;
    }
    if (rule.id && rule.hook && rule.action) {
      rules.push(rule as EnforceRule);
    } else {
      console.warn("[vibe-enforcer] Skipped malformed ENFORCE rule:", raw);
    }
  }
  return rules;
}

// ── Real enforcement helpers ─────────────────────────────

function checkReviewerIdentity(projectRoot: string, specName: string): { ok: boolean; detail: string } {
  try {
    const activityFile = path.join(projectRoot, ".agents", "activity.md");
    if (!fs.existsSync(activityFile)) {
      return { ok: true, detail: "No activity.md, skipping identity check" };
    }
    const content = fs.readFileSync(activityFile, "utf-8");

    // Find all entries for this spec
    const specPattern = new RegExp(`- \\*\\*${specName}\\*\\*`, "g");
    const lines = content.split("\n");
    let lastBuilder = "";
    let lastReviewer = "";

    for (const line of lines) {
      if (specPattern.test(line)) {
        const actorMatch = line.match(/Actor:\s*(\S+)/);
        const roleMatch = line.match(/Role:\s*(\S+)/);
        if (actorMatch && roleMatch) {
          const actor = actorMatch[1];
          const role = roleMatch[1];
          if (role === "builder") lastBuilder = actor;
          if (role === "reviewer") lastReviewer = actor;
        }
      }
    }

    if (!lastBuilder || !lastReviewer) {
      return { ok: true, detail: "Missing builder or reviewer record" };
    }

    if (lastBuilder === lastReviewer) {
      return {
        ok: false,
        detail: `Builder (${lastBuilder}) 和 Reviewer (${lastReviewer}) 是同一人，违反身份分离`,
      };
    }

    return { ok: true, detail: `Builder=${lastBuilder}, Reviewer=${lastReviewer}` };
  } catch (e) {
    return { ok: true, detail: `Identity check error: ${e}` };
  }
}

function checkVerifyCommands(projectRoot: string): { ok: boolean; detail: string } {
  try {
    const workflowPath = path.join(projectRoot, ".agents", "workflow.json");
    if (!fs.existsSync(workflowPath)) {
      return { ok: true, detail: "No workflow.json" };
    }
    const workflow = JSON.parse(fs.readFileSync(workflowPath, "utf-8"));
    const commands = workflow?.commands?.verify || [];
    if (commands.length === 0) {
      return { ok: false, detail: "workflow.json 未配置 verify 命令" };
    }
    return { ok: true, detail: `${commands.length} verify commands configured` };
  } catch (e) {
    return { ok: true, detail: `Verify check error: ${e}` };
  }
}

// ── Handlers ─────────────────────────────────────────────

function registerHandlers(
  pi: ExtensionAPI,
  rules: EnforceRule[],
  _scriptsDir: string | null,
  projectRoot: string,
) {
  for (const rule of rules) {
    const id = rule.id;
    const message = rule.message || `${id}: 违反规则`;

    if (rule.match) {
      try { rule._compiledRegex = new RegExp(rule.match, "i"); }
      catch (e) { console.warn(`[vibe-enforcer] Invalid regex for ${id}: ${rule.match}`); }
    }

    switch (rule.hook) {
      case "tool_call": {
        pi.on("tool_call", async (event, ctx) => {
          if (rule.tool && event.toolName !== rule.tool) return;
          const cmd = event.input?.command ?? "";
          if (!rule._compiledRegex || !rule._compiledRegex.test(cmd)) return;

          // ── R53: block raw git commit ──
          if (id === "R53" && rule.action === "block") {
            ctx.ui.notify(`⚠️ ${id}: ${message}`, "warning");
            return { block: true, reason: `${id}: ${message}` };
          }

          // ── R5: reviewer identity check ──
          if (id === "R5" && rule.action === "check_identity") {
            const result = checkReviewerIdentity(projectRoot, "*");
            if (!result.ok) {
              ctx.ui.notify(`⚠️ ${id}: ${result.detail}`, "warning");
              // Advisory only — don't block, just warn
            }
          }

          // ── R4: verify commands configured ──
          if (id === "R4" && rule.action === "verify_commands") {
            const result = checkVerifyCommands(projectRoot);
            if (!result.ok) {
              ctx.ui.notify(`⚠️ ${id}: ${result.detail}`, "warning");
            }
          }

          // ── R10: bug evidence check ──
          if (id === "R10" && rule.action === "check_bug_evidence") {
            // Advisory: prompt agent to check for reproduction evidence
            ctx.ui.notify(`⚠️ ${id}: ${message}`, "warning");
          }

          // ── R22: stage transition gate ──
          if (id === "R22" && rule.action === "check_stage_transition") {
            ctx.ui.notify(`🔒 ${id}: ${message}`, "info");
          }

          // ── R25: retro failure labels ──
          if (id === "R25" && rule.action === "check_failure_labels") {
            ctx.ui.notify(`📝 ${id}: ${message}`, "info");
          }
        });
        break;
      }

      case "before_agent_start": {
        pi.on("before_agent_start", async (event, _ctx) => {
          if (rule.action === "inject_prompt") {
            const injected = `\n\n## AGENT-MANDATORY (${id})\n${message}`;
            event.systemPrompt = (event.systemPrompt || "") + injected;
          }
        });
        break;
      }

      case "agent_end": {
        pi.on("agent_end", async (_event, ctx) => {
          if (rule.action === "check_gates") {
            ctx.ui.notify(`🔒 ${message}`, "info");
          }
          if (rule.action === "require_retro") {
            ctx.ui.notify(`📝 ${message}`, "info");
          }
        });
        break;
      }

      default: {
        console.warn(`[vibe-enforcer] Unknown hook "${rule.hook}" for rule ${id}`);
      }
    }
  }
}

// ── Main ─────────────────────────────────────────────────

export default function (pi: ExtensionAPI) {
  let rules: EnforceRule[] = [];
  let scriptsDir: string | null = null;
  let projectRoot = "";

  pi.on("session_start", async (event, ctx) => {
    const cwd = ctx.cwd || process.cwd();
    projectRoot = findProjectRoot(cwd);

    const skillPath = findSkillPath(cwd);
    if (!skillPath) {
      console.warn("[vibe-enforcer] SKILL.md not found. Searched:");
      console.warn("  ~/.pi/agent/skills/vibe-coding/SKILL.md");
      console.warn("  ~/.agents/skills/vibe-coding/SKILL.md");
      console.warn("  ./.pi/skills/vibe-coding/SKILL.md");
      console.warn("  ./.agents/skills/vibe-coding/SKILL.md");
      console.warn("  <ext>/../SKILL.md");
      return;
    }

    scriptsDir = findScriptsDir(skillPath);
    console.log(`[vibe-enforcer] Skill: ${skillPath}`);
    if (scriptsDir) console.log(`[vibe-enforcer] Scripts: ${scriptsDir}`);

    try {
      const content = fs.readFileSync(skillPath, "utf-8");
      rules = parseEnforceComments(content);
      console.log(`[vibe-enforcer] Loaded ${rules.length} rules:`);
      for (const r of rules) {
        console.log(`  - ${r.id}: ${r.hook}/${r.action}`);
      }
    } catch (e) {
      console.warn("[vibe-enforcer] Parse error:", e);
      return;
    }

    registerHandlers(pi, rules, scriptsDir, projectRoot);
  });
}

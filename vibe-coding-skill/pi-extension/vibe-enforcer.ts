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

function findProjectRoot(cwd: string): string {
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

function checkReviewerIdentity(projectRoot: string, _specName: string): { ok: boolean; detail: string } {
  try {
    const activityFile = path.join(projectRoot, ".agents", "activity.md");
    if (!fs.existsSync(activityFile)) return { ok: true, detail: "No activity.md" };
    const content = fs.readFileSync(activityFile, "utf-8");
    const lines = content.split("\n");
    let lastBuilder = "", lastReviewer = "";
    for (const line of lines) {
      if (line.includes("Actor:")) {
        const actorMatch = line.match(/Actor:\s*(\S+)/);
        const roleMatch = line.match(/Role:\s*(\S+)/);
        if (actorMatch && roleMatch) {
          if (roleMatch[1] === "builder") lastBuilder = actorMatch[1];
          if (roleMatch[1] === "reviewer") lastReviewer = actorMatch[1];
        }
      }
    }
    if (!lastBuilder || !lastReviewer) return { ok: true, detail: "Missing records" };
    if (lastBuilder === lastReviewer) {
      return { ok: false, detail: `Builder (${lastBuilder}) = Reviewer (${lastReviewer})` };
    }
    return { ok: true, detail: `${lastBuilder} != ${lastReviewer}` };
  } catch (e) {
    return { ok: true, detail: `Error: ${e}` };
  }
}

function checkVerifyCommands(projectRoot: string): { ok: boolean; detail: string } {
  try {
    const workflowPath = path.join(projectRoot, ".agents", "workflow.json");
    if (!fs.existsSync(workflowPath)) return { ok: true, detail: "No workflow.json" };
    const workflow = JSON.parse(fs.readFileSync(workflowPath, "utf-8"));
    const commands = workflow?.commands?.verify || [];
    if (commands.length === 0) return { ok: false, detail: "No verify commands" };
    return { ok: true, detail: `${commands.length} commands` };
  } catch (e) {
    return { ok: true, detail: `Error: ${e}` };
  }
}

function checkPerACMapping(projectRoot: string, _specName: string): { ok: boolean; detail: string } {
  try {
    const evidenceDir = path.join(projectRoot, ".agents", "evidence");
    if (!fs.existsSync(evidenceDir)) return { ok: true, detail: "No evidence dir" };
    const files = fs.readdirSync(evidenceDir);
    let missingAC = 0;
    for (const f of files) {
      if (!f.endsWith(".md")) continue;
      const content = fs.readFileSync(path.join(evidenceDir, f), "utf-8");
      if (!content.includes("AC") && !content.includes("Acceptance Criteria")) {
        missingAC++;
      }
    }
    if (missingAC > 0) return { ok: false, detail: `${missingAC} evidence files lack AC mapping` };
    return { ok: true, detail: "All evidence has AC mapping" };
  } catch (e) {
    return { ok: true, detail: `Error: ${e}` };
  }
}

function checkPromptVersion(projectRoot: string, _specName: string): { ok: boolean; detail: string } {
  try {
    const specsDir = path.join(projectRoot, ".agents", "specs");
    if (!fs.existsSync(specsDir)) return { ok: true, detail: "No specs dir" };
    const files = fs.readdirSync(specsDir).filter(f => f.endsWith(".md"));
    let outdated = 0;
    for (const f of files) {
      const content = fs.readFileSync(path.join(specsDir, f), "utf-8");
      if (content.includes("Prompt version") && !content.includes("Prompt version: ")) {
        outdated++;
      }
    }
    if (outdated > 0) return { ok: false, detail: `${outdated} specs lack Prompt version` };
    return { ok: true, detail: "All specs have Prompt version" };
  } catch (e) {
    return { ok: true, detail: `Error: ${e}` };
  }
}

function checkRetroItems(projectRoot: string): { ok: boolean; detail: string } {
  try {
    const retrosDir = path.join(projectRoot, ".agents", "retros");
    if (!fs.existsSync(retrosDir)) return { ok: true, detail: "No retros dir" };
    const files = fs.readdirSync(retrosDir).filter(f => f.endsWith(".md"));
    let openItems = 0;
    for (const f of files) {
      const content = fs.readFileSync(path.join(retrosDir, f), "utf-8");
      const matches = content.match(/- \[ \].*action item/gi);
      if (matches) openItems += matches.length;
    }
    if (openItems > 0) return { ok: false, detail: `${openItems} open action items` };
    return { ok: true, detail: "All action items terminal" };
  } catch (e) {
    return { ok: true, detail: `Error: ${e}` };
  }
}

function checkCallSites(projectRoot: string): { ok: boolean; detail: string } {
  try {
    const workflowPath = path.join(projectRoot, ".agents", "workflow.json");
    if (!fs.existsSync(workflowPath)) return { ok: true, detail: "No workflow.json" };
    const workflow = JSON.parse(fs.readFileSync(workflowPath, "utf-8"));
    const checks = workflow?.commands?.call_site_check || [];
    if (checks.length === 0) return { ok: true, detail: "call_site_check not configured (optional)" };
    return { ok: true, detail: `${checks.length} call-site checks configured` };
  } catch (e) {
    return { ok: true, detail: `Error: ${e}` };
  }
}

// ── Handlers ─────────────────────────────────────────────


function checkOverrideSession(projectRoot: string): { ok: boolean; detail: string } {
  try {
    const sessionFile = process.env.PI_SESSION_FILE || "";
    const sessionId = process.env.PI_SESSION_ID || "";
    let currentSession = "";
    if (sessionFile) {
      const basename = path.basename(sessionFile);
      const parts = basename.split("_");
      if (parts.length >= 2) currentSession = parts[parts.length - 1].replace(".jsonl", "");
    }
    if (!currentSession && sessionId) currentSession = sessionId;
    if (!currentSession) return { ok: true, detail: "No session context, gate skipped" };
    const activityFile = path.join(projectRoot, ".agents", "activity.md");
    if (!fs.existsSync(activityFile)) return { ok: true, detail: "No activity.md" };
    const actContent = fs.readFileSync(activityFile, "utf-8");
    const lines = actContent.split("\n");
    let lastOverrideActor = "";
    for (const line of lines) {
      if (line.includes("override_approver")) {
        const actorMatch = line.match(/Actor:\s*(\S+)/);
        if (actorMatch) lastOverrideActor = actorMatch[1];
      }
    }
    if (!lastOverrideActor) return { ok: true, detail: "No override_approver found" };
    if (lastOverrideActor === currentSession) {
      return { ok: false, detail: "Self-override: actor " + lastOverrideActor + " = current session" };
    }
    return { ok: true, detail: "Override actor " + lastOverrideActor + " != session " + currentSession };
  } catch (e) {
    return { ok: true, detail: "Error: " + e };
  }
}

function registerHandlers(pi: ExtensionAPI, rules: EnforceRule[], projectRoot: string) {
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

          // R53: block raw git commit
          if (id === "R53" && rule.action === "block") {
            ctx.ui.notify(`⚠️ ${id}: ${message}`, "warning");
            return { block: true, reason: `${id}: ${message}` };
          }

          // R4: verify commands check
          if (id === "R4" && rule.action === "verify_commands") {
            const result = checkVerifyCommands(projectRoot);
            if (!result.ok) ctx.ui.notify(`⚠️ ${id}: ${result.detail}`, "warning");
          }

          // R5: reviewer identity
          if (id === "R5" && rule.action === "check_identity") {
            const result = checkReviewerIdentity(projectRoot, "*");
            if (!result.ok) ctx.ui.notify(`⚠️ ${id}: ${result.detail}`, "warning");
          }

          // R10: bug evidence
          if (id === "R10" && rule.action === "check_bug_evidence") {
            ctx.ui.notify(`⚠️ ${id}: ${message}`, "warning");
          }

          // R22: stage transition
          if (id === "R22" && rule.action === "check_stage_transition") {
            ctx.ui.notify(`🔒 ${id}: ${message}`, "info");
          }

          // R25: retro failure labels
          if (id === "R25" && rule.action === "check_failure_labels") {
            ctx.ui.notify(`📝 ${id}: ${message}`, "info");
          }

          // R30: per-AC mapping
          if (id === "R30" && rule.action === "check_per_ac") {
            const result = checkPerACMapping(projectRoot, "*");
            if (!result.ok) ctx.ui.notify(`⚠️ ${id}: ${result.detail}`, "warning");
          }

          // R47: Prompt version
          if (id === "R47" && rule.action === "check_prompt_version") {
            const result = checkPromptVersion(projectRoot, "*");
            if (!result.ok) ctx.ui.notify(`⚠️ ${id}: ${result.detail}`, "warning");
          }

          // R62: call sites
          if (id === "R62" && rule.action === "check_call_sites") {
            const result = checkCallSites(projectRoot);
            if (!result.ok) ctx.ui.notify(`⚠️ ${id}: ${result.detail}`, "warning");
          }

          // R67: override session separation
          if (id === "R67" && rule.action === "check_override_session") {
            const result = checkOverrideSession(projectRoot);
            if (!result.ok) ctx.ui.notify(`⚠️ ${id}: ${result.detail}`, "warning");
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
          // R1: check gates
          if (id === "R1" && rule.action === "check_gates") {
            ctx.ui.notify(`🔒 ${message}`, "info");
          }
          // R60: retro items
          if (id === "R60" && rule.action === "check_retro_items") {
            const result = checkRetroItems(projectRoot);
            if (!result.ok) ctx.ui.notify(`📝 ${id}: ${result.detail}`, "warning");
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
  let projectRoot = "";

  pi.on("session_start", async (event, ctx) => {
    const cwd = ctx.cwd || process.cwd();
    projectRoot = findProjectRoot(cwd);

    const skillPath = findSkillPath(cwd);
    if (!skillPath) {
      console.warn("[vibe-enforcer] SKILL.md not found.");
      return;
    }

    console.log(`[vibe-enforcer] Skill: ${skillPath}`);

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

    registerHandlers(pi, rules, projectRoot);
  });
}

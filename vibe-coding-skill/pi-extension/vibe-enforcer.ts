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
}

function findSkillPath(): string | null {
  const candidates = [
    path.join(process.env.HOME || "", ".pi", "agent", "skills", "vibe-coding", "SKILL.md"),
    path.join(process.env.HOME || "", ".agents", "skills", "vibe-coding", "SKILL.md"),
    path.join(".", ".agents", "skills", "vibe-coding", "SKILL.md"),
  ];
  for (const c of candidates) {
    if (fs.existsSync(c)) return c;
  }
  return null;
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

export default function (pi: ExtensionAPI) {
  const skillPath = findSkillPath();
  if (!skillPath) {
    console.warn("[vibe-enforcer] vibe-coding SKILL.md not found. Skipping.");
    return;
  }

  let rules: EnforceRule[] = [];
  try {
    const content = fs.readFileSync(skillPath, "utf-8");
    rules = parseEnforceComments(content);
    console.log(`[vibe-enforcer] Loaded ${rules.length} enforce rules from ${skillPath}`);
  } catch (e) {
    console.warn("[vibe-enforcer] Failed to parse SKILL.md:", e);
    return;
  }

  for (const rule of rules) {
    const id = rule.id;
    const message = rule.message || `${id}: 违反规则`;

    switch (rule.hook) {
      case "tool_call": {
        pi.on("tool_call", async (event, ctx) => {
          if (rule.tool && event.toolName !== rule.tool) return;
          const cmd = event.input?.command ?? "";
          if (rule.match) {
            const regex = new RegExp(rule.match, "i");
            if (regex.test(cmd)) {
              ctx.ui.notify(`⚠️ ${id}: ${message}`, "warning");
              if (rule.action === "block") {
                return { block: true, reason: `${id}: ${message}` };
              }
            }
          }
        });
        console.log(`[vibe-enforcer] ${id}: tool_call (tool=${rule.tool}, match=${rule.match})`);
        break;
      }

      case "before_agent_start": {
        pi.on("before_agent_start", async (event, _ctx) => {
          if (rule.action === "inject_prompt") {
            const injected = `\n\n## AGENT-MANDATORY (${id})\n${message}`;
            event.systemPrompt = (event.systemPrompt || "") + injected;
          }
        });
        console.log(`[vibe-enforcer] ${id}: before_agent_start inject_prompt`);
        break;
      }

      case "agent_end": {
        pi.on("agent_end", async (_event, ctx) => {
          if (rule.action === "require_retro") {
            ctx.ui.notify(`📝 ${message}`, "info");
          }
          if (rule.action === "check_gates") {
            ctx.ui.notify(`🔒 ${message}`, "info");
          }
        });
        console.log(`[vibe-enforcer] ${id}: agent_end notify`);
        break;
      }

      default: {
        console.warn(`[vibe-enforcer] Unknown hook "${rule.hook}" for rule ${id}`);
      }
    }
  }
}

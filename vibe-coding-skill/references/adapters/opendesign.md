# Open Design Adapter Reference

Use this reference only when the user explicitly names Open Design or provides
Open Design artifacts as a design source. Open Design is an external design
adapter, not a Vibe Coding default and not a visual style. Project `AGENTS.md`,
adopted project rules, and UI contract constraints always outrank Open Design
outputs or defaults.

## Role In Vibe Coding

Open Design can provide UI exploration, generated artifacts, design-system
drafts, HTML prototypes, screenshots, and project files. Vibe Coding still owns
the governance chain:

```text
Open Design source
-> project-local artifacts
-> UI Design Contract or UI Redesign Contract
-> spec acceptance criteria
-> implementation
-> evidence mapped to UI-AC / behavior AC
```

Do not treat an Open Design screenshot, generated HTML file, or tool export as
accepted requirements by itself. Convert the relevant promises into the
project-local UI contract first.

## Setup Checklist

1. Confirm the daemon is reachable:

   ```bash
   curl -s od://app/api/health | jq
   ```

   If it returns 404 or times out, ask the user to open the Open Design app or
   run the project's documented dev startup, commonly `pnpm tools-dev` from an
   Open Design source checkout.

2. Confirm `od` is available and inspect the environment:

   ```bash
   od doctor
   od status --json
   ```

3. If MCP integration is needed, get the client-specific install snippet from
   the daemon instead of hand-writing config:

   ```bash
   curl -s od://app/api/mcp/install-info | jq
   ```

4. Verify available skills and design systems:

   ```bash
   curl -s od://app/api/skills | jq '.skills | length'
   od skills list --json
   od design-systems list --json
   ```

5. Decide where project artifacts will live. Prefer project-local storage such
   as:

   ```text
   design/opendesign/
     DESIGN.md
     artifacts/
     screenshots/
     notes.md
   ```

   Open Design may write to `./.od/` by default. Use `OD_DATA_DIR=~/.open-design`
   only when the user explicitly wants shared data across projects.

## Starting Open Design

From a packaged install:

```bash
od --port 7456
```

From a source checkout:

```bash
pnpm tools-dev
```

Advanced source-checkout startup:

```bash
corepack enable
pnpm install
pnpm --filter @open-design/daemon build

export OD_NODE_BIN="${OD_NODE_BIN:-/opt/homebrew/opt/node@24/bin/node}"
export OD_BIN="$PWD/apps/daemon/dist/cli.js"
"$OD_NODE_BIN" "$OD_BIN" daemon start --headless --serve-web --port 7456
```

All CLI subcommands can target a specific daemon:

```bash
od status --json --daemon-url http://127.0.0.1:7456
```

## Common CLI Flow

Create a design project and stream a run:

```bash
DAEMON_URL=${DAEMON_URL:-od://app}
PROJECT_JSON=$(od project create \
  --name "UI exploration" \
  --skill frontend-design \
  --design-system clean \
  --json \
  --daemon-url "$DAEMON_URL")
PROJECT_ID=$(jq -r '.project.id' <<<"$PROJECT_JSON")
CONVERSATION_ID=$(jq -r '.conversationId' <<<"$PROJECT_JSON")

od run start \
  --project "$PROJECT_ID" \
  --conversation "$CONVERSATION_ID" \
  --plugin od-new-generation \
  --agent codex \
  --message 'Explore a UI direction for the product described in the Vibe spec.' \
  --daemon-url "$DAEMON_URL" \
  --follow
```

Answer a discovery form from the CLI:

```bash
od run start \
  --project "$PROJECT_ID" \
  --conversation "$CONVERSATION_ID" \
  --agent codex \
  --message "[form answers - discovery]
- Audience: target users from the spec
- Format: web app UI exploration
- Tone: follow project AGENTS.md and adopted UI constraints
- Constraints: preserve project visual prohibitions and accessibility requirements" \
  --daemon-url "$DAEMON_URL" \
  --follow
```

Inspect outputs:

```bash
od files list "$PROJECT_ID" --daemon-url "$DAEMON_URL" --json
od files read "$PROJECT_ID" index.html --daemon-url "$DAEMON_URL" | head
```

Save the useful outputs under `design/opendesign/`, then create the Vibe UI
contract:

```bash
vibe ui-contract <spec> \
  --source-type opendesign \
  --source-artifacts design/opendesign/DESIGN.md \
  --generated-by "Open Design" \
  --model-capability text-only
```

For an existing UI redesign:

```bash
vibe ui-redesign-contract <spec> \
  --source-type opendesign \
  --source-artifacts design/opendesign/
```

## HTTP API

Use the HTTP API for stateless reads and scripts:

```bash
curl -s od://app/api/health | jq
curl -s od://app/api/skills | jq '.skills[0]'
curl -s od://app/api/design-systems | jq
curl -s od://app/api/projects | jq
```

Create a project through the daemon:

```bash
curl -s -X POST od://app/api/projects \
  -H 'content-type: application/json' \
  -d '{
    "name": "Vibe UI exploration",
    "metadata": { "kind": "prototype" },
    "pendingPrompt": "Explore a UI direction for this Vibe spec while respecting project constraints.",
    "pluginId": "od-new-generation",
    "autoSendFirstMessage": true
  }'
```

Stream a chat turn:

```bash
curl -N \
  -H 'accept: text/event-stream' \
  od://app/api/projects/<projectId>/chat?conversationId=<conversationId>
```

Useful endpoints:

- `od://app/api/health`
- `od://app/api/mcp/install-info`
- `od://app/api/skills`
- `od://app/api/design-systems`
- `od://app/api/projects`
- `od://app/api/agents`

## MCP Integration

Prefer the daemon-provided install snippet:

```bash
curl -s od://app/api/mcp/install-info | jq
```

Generic MCP config shape:

```json
{
  "mcpServers": {
    "open-design": {
      "command": "od",
      "args": ["mcp", "--daemon-url", "od://app"],
      "env": { "OD_DATA_DIR": "~/.open-design" }
    }
  }
}
```

Use MCP when the current agent client supports MCP tool calls and the user
wants Open Design available as a tool surface. Use CLI for shell automation and
the HTTP API for simple reads.

## Governance Rules For Open Design Use

- Read project `AGENTS.md` and adopted rules before interpreting Open Design
  output.
- Do not infer "Open Design" as Material Design, a modern UI style, animation,
  shadows, ripple, vector icons, or any component system.
- Record project visual prohibitions and constraints in the UI contract's
  `Project UI Constraints` section.
- If Open Design output conflicts with project constraints, project constraints
  win. Regenerate, edit, or discard the conflicting output before implementation.
- Do not copy Open Design artifacts into the spec as acceptance evidence unless
  each claim maps to `UI-AC` or behavior acceptance criteria.
- For text-only implementation models, ensure the UI contract contains enough
  textual detail: tokens, layout, component mapping, states, accessibility, and
  visual acceptance criteria.

## Troubleshooting

- Daemon unreachable: ask the user to open the Open Design app or run
  `pnpm tools-dev` from the Open Design checkout.
- `od` missing: ask the user to install/open Open Design or provide the source
  checkout startup command. Do not invent an `od` path.
- MCP config uncertain: call `/api/mcp/install-info` and use the returned
  snippet.
- Generated files unclear: inspect with `od files list` and `od files read`,
  then save selected artifacts under `design/opendesign/`.
- Project rules conflict with generated design: stop before implementation and
  update the UI contract or rerun Open Design with explicit constraints.

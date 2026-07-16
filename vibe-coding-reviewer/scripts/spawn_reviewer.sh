#!/usr/bin/env bash
# spawn_reviewer.sh — 一键生成 codex exec 独立 reviewer 命令
# Usage: spawn_reviewer.sh <spec-id> [options]
#
# 跨项目通用: 通过 --project-root 参数支持任意 vibe-coding 项目

set -euo pipefail

# --- 默认值 ---
SCRIPT_NAME="$(basename "$0")"
PROJECT_ROOT=""
SPECS_DIR=""
TEMPLATE_PATH=""
COMMIT_HASH="HEAD"
RULES="R5,R8.44,R8.45"
CODEX_CMD="${CODEX_CMD:-codex}"
CODEX_EXTRA_FLAGS="${CODEX_EXTRA_FLAGS:-}"
AGENTS_MD="AGENTS.md"

# --- 工具函数 ---
die() { echo "❌ $SCRIPT_NAME: $*" >&2; exit 1; }
warn() { echo "⚠️  $SCRIPT_NAME: $*" >&2; }

show_help() {
  cat <<'HELP'
Usage: spawn_reviewer.sh <spec-id> [options]

一键生成 codex exec 独立 reviewer 命令，用于 spawn 与 builder 不同身份的 reviewer。

注意: 默认从当前目录推断 --project-root。如果你在 skill 目录跑，
      必须显式传 --project-root 指向项目根。

Options:
  --project-root DIR        项目根目录 (默认: 当前目录)
  --specs-dir DIR           specs 目录 (默认: <project-root>/.agents/specs)
  --template FILE           reviewer prompt 模板路径
                            (默认: <project-root>/.agents/templates/reviewer-prompt.md)
  --commit HASH             要验证的 commit (默认: HEAD)
  --rules RULES             逗号分隔的 R 编号列表 (默认: R5,R8.44,R8.45)
  --codex-cmd CMD           codex CLI 命令 (默认: codex, 环境变量 CODEX_CMD 可覆盖)
  --codex-extra-flags STR   额外 codex 参数 (默认: 空, 环境变量 CODEX_EXTRA_FLAGS 可覆盖)
  --agends-md FILE          AGENTS.md 文件名 (默认: AGENTS.md)
  --help, -h                显示帮助

Examples:
  # 在项目根目录跑 (推荐)
  cd /path/to/project
  bash <skill-path>/scripts/spawn_reviewer.sh my-spec

  # 显式指定项目
  bash <skill-path>/scripts/spawn_reviewer.sh my-spec --project-root /path/to/project

  # 自定义 reviewer 规则
  bash <skill-path>/scripts/spawn_reviewer.sh my-spec --rules R5,R8.44,R8.45,R62

  # 加额外 codex 参数
  bash scripts/spawn_reviewer.sh my-spec --codex-extra-flags "--sandbox read-only"

Environment:
  CODEX_CMD                 覆盖默认的 codex CLI 命令
  CODEX_EXTRA_FLAGS         额外 codex 参数 (如 --sandbox)
HELP
}

# --- 参数解析 ---
while [[ $# -gt 0 ]]; do
  case "$1" in
    --project-root)
      PROJECT_ROOT="$2"; shift 2 ;;
    --specs-dir)
      SPECS_DIR="$2"; shift 2 ;;
    --template)
      TEMPLATE_PATH="$2"; shift 2 ;;
    --commit)
      COMMIT_HASH="$2"; shift 2 ;;
    --rules)
      RULES="$2"; shift 2 ;;
    --codex-cmd)
      CODEX_CMD="$2"; shift 2 ;;
    --codex-extra-flags)
      CODEX_EXTRA_FLAGS="$2"; shift 2 ;;
    --agends-md)
      AGENTS_MD="$2"; shift 2 ;;
    --help|-h)
      show_help; exit 0 ;;
    -*)
      die "未知参数: $1 (用 --help 查看用法)" ;;
    *)
      [[ -z "${SPEC_ID:-}" ]] || die "只接受一个 spec-id"
      SPEC_ID="$1"; shift ;;
  esac
done

[[ -n "${SPEC_ID:-}" ]] || { show_help; exit 1; }

# --- 推导默认值 ---
PROJECT_ROOT="${PROJECT_ROOT:-$(pwd)}"
PROJECT_ROOT="$(cd "$PROJECT_ROOT" && pwd)"
SPECS_DIR="${SPECS_DIR:-$PROJECT_ROOT/.agents/specs}"
TEMPLATE_PATH="${TEMPLATE_PATH:-$PROJECT_ROOT/.agents/templates/reviewer-prompt.md}"

# --- 校验 ---
if ! [[ "$SPEC_ID" =~ ^[a-z0-9-]+$ ]]; then
  die "spec-id 格式不合法: '$SPEC_ID' (要求 ^[a-z0-9-]+\$)"
fi

SPEC_FILE="$SPECS_DIR/$SPEC_ID.md"
[[ -f "$SPEC_FILE" ]] || die "spec 文件不存在: $SPEC_FILE"

[[ -f "$TEMPLATE_PATH" ]] || die "模板文件不存在: $TEMPLATE_PATH"

# --- codex 检测 ---
if ! command -v "$CODEX_CMD" >/dev/null 2>&1; then
  warn "$CODEX_CMD 不在 PATH"
  warn "生成的命令可能无法直接执行，可复制到有 codex 的环境运行"
fi

# --- 生成命令 ---
PROMPT_CMD="sed -e 's|<spec-id>|$SPEC_ID|g' -e 's|<commit-hash>|$COMMIT_HASH|g' -e 's|<rules>|$RULES|g' -e 's|<agends-md-path>|$AGENTS_MD|g' '$TEMPLATE_PATH'"

# 组装 codex exec 命令
echo "# 复制并执行以下命令:" >&2
echo "#" >&2
echo "# 注意: 确保你在项目根目录运行" >&2
echo "#" >&2
if [[ -n "$CODEX_EXTRA_FLAGS" ]]; then
  echo "$CODEX_CMD exec $CODEX_EXTRA_FLAGS --allowedTools \"Read,Bash,Grep\" \"\$($PROMPT_CMD)\"" >&1
else
  echo "$CODEX_CMD exec --allowedTools \"Read,Bash,Grep\" \"\$($PROMPT_CMD)\"" >&1
fi

# --- 无 reviewer / subagent 时的替代方案 ---
echo "#" >&2
echo "# 提示: 如果你没有 codex CLI 或没有可用的 reviewer subagent," >&2
echo "# 可以用 pi agent 替代(单文件模式,不保留 session):" >&2
echo "#" >&2
echo "#   pi --print --no-session --provider minimax-cn --model MiniMax-M3 \\" >&2
echo "#     < $TEMPLATE_PATH \\" >&2
echo "#     > review.md" >&2
echo "#" >&2
echo "# pi agent 会把 prompt 模板内容读入,输出 review 结果到 review.md。" >&2
echo "# 注意: pi agent 的命令格式跟 codex exec 不同,codex 把 prompt 当参数传," >&2
echo "# pi 从 stdin 读。具体用法请查阅 pi agent 文档。" >&2

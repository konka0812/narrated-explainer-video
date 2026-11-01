#!/usr/bin/env bash
set -euo pipefail

# Forward the same Skills CLI options to both installs, e.g. --agent codex --global --yes.
repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"

command -v npx >/dev/null 2>&1 || { printf '%s\n' 'Node.js and npx are required.' >&2; exit 1; }
printf '%s\n' 'Installing narrated-explainer-video...'
npx --yes skills@latest add "$repo_dir" --skill narrated-explainer-video "$@"
printf '%s\n' 'Installing official remotion-best-practices...'
npx --yes skills@latest add remotion-dev/skills --skill remotion-best-practices "$@"
printf '%s\n' 'Both installation commands completed. Confirm that both skills appear in the same agent and scope.'

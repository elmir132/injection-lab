#!/usr/bin/env bash
set -euo pipefail
project_root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$project_root"
if [ -x "$project_root/.venv/bin/python" ]; then
  injection_lab_python="$project_root/.venv/bin/python"
else
  injection_lab_python=python3
fi
"$injection_lab_python" -m compileall -q src tests
"$injection_lab_python" -m pytest
"$injection_lab_python" -m injection_lab.cli --system-prompt-file examples/system_prompt.txt --provider mock


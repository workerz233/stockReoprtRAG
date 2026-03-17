#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONDA_ENV_NAME="${CONDA_ENV_NAME:-learn}"

find_conda_sh() {
  if [[ -n "${CONDA_EXE:-}" ]]; then
    local conda_base
    conda_base="$("$CONDA_EXE" info --base 2>/dev/null || true)"
    if [[ -n "$conda_base" && -f "$conda_base/etc/profile.d/conda.sh" ]]; then
      printf '%s\n' "$conda_base/etc/profile.d/conda.sh"
      return 0
    fi
  fi

  local candidates=(
    "$HOME/miniconda3/etc/profile.d/conda.sh"
    "$HOME/anaconda3/etc/profile.d/conda.sh"
    "/opt/homebrew/Caskroom/miniconda/base/etc/profile.d/conda.sh"
    "/usr/local/Caskroom/miniconda/base/etc/profile.d/conda.sh"
  )

  local candidate
  for candidate in "${candidates[@]}"; do
    if [[ -f "$candidate" ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done

  return 1
}

CONDA_SH="$(find_conda_sh || true)"
if [[ -z "$CONDA_SH" ]]; then
  echo "未找到 conda.sh，请确认 Conda 已安装。" >&2
  exit 1
fi

# shellcheck disable=SC1090
source "$CONDA_SH"
conda activate "$CONDA_ENV_NAME"

if ! command -v python >/dev/null 2>&1; then
  echo "激活环境后未找到 python，请检查 conda 环境: $CONDA_ENV_NAME" >&2
  exit 1
fi

cd "$ROOT_DIR"

echo "使用 conda 环境: $CONDA_ENV_NAME"
echo "项目目录: $ROOT_DIR"
echo "执行评测命令: python -m evals.run_eval $*"

python -m evals.run_eval "$@"

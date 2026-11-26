#!/bin/bash

# Resolve project root from this script location.
# BASH_SOURCE is empty in zsh; use the zsh equivalent there.
if [ -n "$ZSH_VERSION" ]; then
    eval 'SCRIPT_PATH="${(%):-%x}"'
else
    SCRIPT_PATH="${BASH_SOURCE[0]}"
fi
PROJECT_ROOT="$(cd "$(dirname "$SCRIPT_PATH")" && pwd)"
VENV_DIR="$PROJECT_ROOT/.venv"
# Add this line specifically for Zsh themes
export VIRTUAL_ENV_PROMPT="lborg"

# This script is sourced, so use `return` (not `exit` or `set -e`) on failure
# to stop without closing the user's shell.
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$VENV_DIR" --prompt "$VIRTUAL_ENV_PROMPT" \
        || { echo "Failed to create virtual environment." >&2; return 1; }
    source "$VENV_DIR/bin/activate" || return 1
    pip install --upgrade pip || { echo "Failed to upgrade pip." >&2; return 1; }
else
    source "$VENV_DIR/bin/activate" || return 1
fi

pip install -e "${PROJECT_ROOT}[dev,gui]" \
    || { echo "Failed to install the project." >&2; return 1; }

export VIRTUAL_ENV="$VENV_DIR"
export PATH="$VENV_DIR/bin:$PATH"

echo "Environment ($VIRTUAL_ENV_PROMPT) is ready."
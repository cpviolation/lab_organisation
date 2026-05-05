#!/bin/bash

# Resolve project root from this script location.
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$PROJECT_ROOT/.venv"
# Add this line specifically for Zsh themes
export VIRTUAL_ENV_PROMPT="lborg"

if [ ! -d "$VENV_DIR" ]; then
    set -e  # Enable strict error checking for the installation
    
    echo "Creating virtual environment..."
    python3 -m venv "$VENV_DIR" --prompt "$VIRTUAL_ENV_PROMPT"
    source "$VENV_DIR/bin/activate"
    
    pip install --upgrade pip
    pip install -r "$PROJECT_ROOT/requirements.txt"
    
    set +e  # Disable strict error checking after installation is successful
else
    source "$VENV_DIR/bin/activate"
fi

export LBORG="$PROJECT_ROOT"
export VIRTUAL_ENV="$VENV_DIR"
export PATH="$VENV_DIR/bin:$PATH"

echo "Environment ($VIRTUAL_ENV_PROMPT) is ready."
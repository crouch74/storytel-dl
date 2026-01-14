#!/bin/bash
set -e

# Project setup script

echo "🛠️  Setting up Python environment..."

# Create .venv if it doesn't exist
if [ ! -d ".venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv .venv
fi

# Activate venv
source .venv/bin/activate

# Upgrade pip
echo "⬆️  Upgrading pip..."
pip install --upgrade pip

# Install requirements
echo "📥 Installing dependencies..."
pip install -r requirements.txt

echo "✅ Setup complete! You can now run the tool with:"
echo "   source .venv/bin/activate"
echo "   python -m src.main --help"

#!/bin/bash

# Build script for Nuitka compilation and installation
set -e

echo "🚀 Starting build process..."

# Create build virtual environment
echo "📦 Creating build_venv..."
python3 -m venv build_venv

# Activate the virtual environment
echo "🔄 Activating build_venv..."
source build_venv/bin/activate

# Install nuitka and other dependencies
echo "📥 Installing nuitka and dependencies..."
pip install nuitka
pip install -r requirements.txt

# Build with nuitka
echo "🔨 Building with Nuitka..."
python -m nuitka --mode=standalone main.py

# Create bin directory if it doesn't exist
echo "📁 Setting up bin directory..."
mkdir -p bin

# Move the compiled output to bin
echo "📋 Moving output to bin..."
if [ -d "main.dist" ]; then
    cp -r main.dist/* bin/
    # Make the main binary executable if it exists
    if [ -f "bin/main.bin" ]; then
        chmod +x bin/main.bin
        mv bin/main.bin bin/dfu
    elif [ -f "bin/main" ]; then
        chmod +x bin/main
        mv bin/main bin/dfu
    fi
else
    echo "❌ Error: main.dist directory not found after Nuitka build"
    exit 1
fi

# Deactivate virtual environment
deactivate

echo "✅ Build completed successfully!"
echo ""
echo "🔧 To make 'dfu' accessible from anywhere, copy and paste this into your terminal:"
echo ""
echo "export PATH=\"$(pwd)/bin:\$PATH\""
echo ""
echo "💡 To make this permanent, add the above line to your ~/.zshrc file:"
echo "echo 'export PATH=\"$(pwd)/bin:\$PATH\"' >> ~/.zshrc && source ~/.zshrc"
echo ""
echo "🎯 You can now use 'dfu' from anywhere in your terminal!"
echo ""
echo "📝 Usage examples:"
echo "  dfu npm i package-name       # Install npm package (HTTPS proxy)"
echo "  dfu yarn add package-name    # Install yarn package (HTTP proxy - see warning)"
echo "  dfu npm install              # Install all dependencies"
echo "  dfu yarn install             # Install all dependencies"

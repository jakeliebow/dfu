#!/bin/bash

# Build script for dfu - dependency fallback utility
set -e

# Ensure we have a proper PATH
export PATH="/bin:/usr/bin:/usr/local/bin:$PATH"

PROJECT_DIR="$(cd "$(/usr/bin/dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="$HOME/.local/bin"
BUILD_DIR="$PROJECT_DIR/build"
DIST_DIR="$PROJECT_DIR/dist"

echo "Building dfu executable with PyInstaller..."

# Clean previous builds
/bin/rm -rf "$BUILD_DIR" "$DIST_DIR"

# Check if virtual environment exists, create if needed
if [ ! -d "$PROJECT_DIR/venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$PROJECT_DIR/venv"
    source "$PROJECT_DIR/venv/bin/activate"
    pip install -r "$PROJECT_DIR/requirements.txt"
    pip install pyinstaller
else
    source "$PROJECT_DIR/venv/bin/activate"
    # Check if pyinstaller is installed
    if ! pip show pyinstaller > /dev/null 2>&1; then
        echo "Installing PyInstaller..."
        pip install pyinstaller
    fi
fi

# Build the executable
echo "Creating executable..."
pyinstaller \
    --onedir \
    --name dfu \
    --distpath "$DIST_DIR" \
    "$PROJECT_DIR/main.py"

# Create install directory if it doesn't exist
/bin/mkdir -p "$INSTALL_DIR"

# Copy the executable directory to the install directory
/bin/rm -rf "$INSTALL_DIR/dfu"
/bin/cp -r "$DIST_DIR/dfu" "$INSTALL_DIR/"

# Create a wrapper script for easy execution
/bin/cat > "$INSTALL_DIR/dfu-wrapper" << 'EOF'
#!/bin/bash
DIR="$(cd "$(/usr/bin/dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$DIR/dfu/dfu" "$@"
EOF
/bin/chmod +x "$INSTALL_DIR/dfu-wrapper"

# Clean up build artifacts
/bin/rm -rf "$BUILD_DIR" "$DIST_DIR" "$PROJECT_DIR/dfu.spec"

echo "dfu executable installed to $INSTALL_DIR/dfu/"
echo "Wrapper script created at $INSTALL_DIR/dfu-wrapper"
echo ""
echo "Make sure $INSTALL_DIR is in your PATH by adding this to your shell profile:"
echo "export PATH=\"\$HOME/.local/bin:\$PATH\""
echo ""
echo "You can now run: dfu-wrapper"
echo "Or directly: $INSTALL_DIR/dfu/dfu"

#!/bin/bash
# Fix file permissions for Podman rootless containers
#
# This script ensures that files in the project directory have the correct
# permissions for the container user (UID 1000).
#
# Usage:
#   ./fix-permissions.sh

set -e

echo "Fixing file permissions for Podman rootless container..."

# Get current user ID
CURRENT_UID=$(id -u)
CURRENT_GID=$(id -g)

echo "Current user: UID=$CURRENT_UID, GID=$CURRENT_GID"
echo "Container user: UID=1000, GID=1000"

# If current user is UID 1000, permissions should already be fine
if [ "$CURRENT_UID" -eq 1000 ]; then
    echo "✓ Current user is UID 1000 - permissions should be correct"
else
    echo "⚠ Current user is not UID 1000"
    echo "  You may need to adjust ownership or run with sudo/root"
fi

# Ensure directories exist and are writable
echo "Creating necessary directories..."
mkdir -p noteshrinker/media/{pdf,png,books,pictures}
mkdir -p logs

# Make sure Python can write to these directories
chmod -R 755 noteshrinker/media logs 2>/dev/null || true

echo "✓ Directories created and permissions set"

# Make scripts executable
if [ -f "manage.py" ]; then
    chmod +x manage.py
    echo "✓ manage.py is executable"
fi

# For Podman, ensure SELinux contexts are correct (RedHat/Fedora)
if command -v chcon &> /dev/null && getenforce 2>/dev/null | grep -q "Enforcing"; then
    echo "SELinux is enforcing - setting container file context..."
    chcon -R -t container_file_t . 2>/dev/null || true
    echo "✓ SELinux context set"
fi

echo ""
echo "✓ Permission fixes complete!"
echo ""
echo "You can now run:"
echo "  podman compose up"
echo "  or"
echo "  docker compose up"

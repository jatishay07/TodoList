#!/usr/bin/env bash
# TaskTrack — Register daily notification scheduler on macOS via launchd
# Run once after cloning the repo: bash setup_scheduler_mac.sh

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="$(which python3)"
SCRIPT="$REPO_DIR/scheduler.py"
LABEL="com.tasktrack.notifier"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

echo "Configuring TaskTrack launchd agent…"
echo "  Repo:   $REPO_DIR"
echo "  Python: $PYTHON"

cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$LABEL</string>

    <key>ProgramArguments</key>
    <array>
        <string>$PYTHON</string>
        <string>$SCRIPT</string>
    </array>

    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>8</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>

    <key>StandardOutPath</key>
    <string>$REPO_DIR/data/scheduler.log</string>

    <key>StandardErrorPath</key>
    <string>$REPO_DIR/data/scheduler_error.log</string>

    <key>RunAtLoad</key>
    <false/>
</dict>
</plist>
EOF

# Load (or reload) the agent
if launchctl list | grep -q "$LABEL"; then
    launchctl unload "$PLIST" 2>/dev/null || true
fi
launchctl load "$PLIST"

echo "Done! TaskTrack will notify you daily at 8:00 AM."
echo "To remove: launchctl unload '$PLIST' && rm '$PLIST'"

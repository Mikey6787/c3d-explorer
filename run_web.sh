#!/bin/bash
# Convenient one-click launcher for C3D Explorer Web

PORT=8080
DIR="$(cd "$(dirname "$0")/web" && pwd)"

echo "-----------------------------------------------------"
echo "  Starting C3D Explorer Web Server on port $PORT"
echo "  Serving files from: $DIR"
echo "-----------------------------------------------------"

# Automatically open the default browser on macOS
sleep 0.5 && open "http://localhost:$PORT" &

# Run Python's built-in static HTTP server
if command -v /opt/homebrew/bin/python3 &> /dev/null; then
    /opt/homebrew/bin/python3 -m http.server "$PORT" --directory "$DIR"
else
    python3 -m http.server "$PORT" --directory "$DIR"
fi

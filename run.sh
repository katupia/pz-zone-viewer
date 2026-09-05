#!/bin/sh
# Launch PZ Zone Viewer.
dir=$(dirname "$0")
if command -v python3 >/dev/null 2>&1; then
    exec python3 "$dir/main.py" "$@"
fi
exec python "$dir/main.py" "$@"

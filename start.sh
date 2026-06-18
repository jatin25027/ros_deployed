#!/bin/bash
set -e

echo "[STARTUP] Starting Xvfb virtual display on :99..."
Xvfb :99 -screen 0 1920x1080x24 &
sleep 1

echo "[STARTUP] Starting Fluxbox window manager..."
fluxbox -display :99 > /dev/null 2>&1 &

# Force X11 display
unset WAYLAND_DISPLAY
unset XDG_SESSION_TYPE
export DISPLAY=:99

echo "[STARTUP] Starting xpra HTML5 server on port 6080..."
xpra start :99 --bind-ws=0.0.0.0:6080 --html=on --daemon=no --start=fluxbox --sharing=yes --no-mdns --no-pulseaudio --no-notifications &
sleep 2

echo "[STARTUP] Starting Node.js server on port ${PORT:-7860}..."
exec node server.js

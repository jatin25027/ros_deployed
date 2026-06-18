#!/bin/bash
set -e

echo "Starting Xvfb on :99..."
Xvfb :99 -screen 0 1920x1080x24 &
sleep 1

echo "Starting fluxbox window manager..."
fluxbox -display :99 > /dev/null 2>&1 &

unset WAYLAND_DISPLAY
unset XDG_SESSION_TYPE

echo "Starting x11vnc..."
x11vnc -display :99 -nopw -forever -shared -bg

echo "Starting websockify on port 6080..."
websockify 6080 localhost:5900 &

echo "Starting Node server..."
exec node server.js

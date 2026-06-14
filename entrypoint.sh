#!/bin/bash
set -e

echo "[STARTUP] Starting virtual framebuffer Xvfb..."
Xvfb :99 -screen 0 1280x800x24 > /tmp/xvfb.log 2>&1 &
sleep 1

export DISPLAY=:99

echo "[STARTUP] Starting Fluxbox window manager..."
fluxbox > /tmp/fluxbox.log 2>&1 &
sleep 1

echo "[STARTUP] Starting x11vnc server..."
x11vnc -display :99 -forever -shared -nopw -rfbport 5900 > /tmp/x11vnc.log 2>&1 &
sleep 1

echo "[STARTUP] Starting noVNC proxy..."
/usr/share/novnc/utils/novnc_proxy --vnc localhost:5900 --listen 6080 > /tmp/novnc.log 2>&1 &
sleep 1

echo "[STARTUP] Starting Nginx reverse proxy..."
nginx -c /app/nginx.conf -g "daemon off;" &
sleep 1

echo "[STARTUP] Starting Node.js server..."
exec node server.js

#!/bin/bash
# ╔══════════════════════════════════════════════════════════════════╗
# ║         ROS Dashboard — One-Shot Startup Script                 ║
# ║  Run this file and the entire project starts automatically.     ║
# ╚══════════════════════════════════════════════════════════════════╝

set -euo pipefail

# ── Colors ─────────────────────────────────────────────────────────
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BOLD='\033[1m'
RESET='\033[0m'

# ── Helpers ─────────────────────────────────────────────────────────
info()    { echo -e "${CYAN}[INFO]${RESET}  $*"; }
success() { echo -e "${GREEN}[OK]${RESET}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${RESET}  $*"; }
error()   { echo -e "${RED}[ERROR]${RESET} $*"; }
section() { echo -e "\n${BOLD}${CYAN}━━━ $* ━━━${RESET}"; }

# ── Change to the script's own directory so paths are always correct
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ── Banner ───────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}${GREEN}"
echo "  ██████╗  ██████╗ ███████╗    ██████╗  █████╗ ███████╗██╗  ██╗"
echo "  ██╔══██╗██╔═══██╗██╔════╝    ██╔══██╗██╔══██╗██╔════╝██║  ██║"
echo "  ██████╔╝██║   ██║███████╗    ██║  ██║███████║███████╗███████║"
echo "  ██╔══██╗██║   ██║╚════██║    ██║  ██║██╔══██║╚════██║██╔══██║"
echo "  ██║  ██║╚██████╔╝███████║    ██████╔╝██║  ██║███████║██║  ██║"
echo "  ╚═╝  ╚═╝ ╚═════╝ ╚══════╝    ╚═════╝ ╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝"
echo -e "${RESET}"
echo -e "  ${BOLD}ROS 2 Simulation Dashboard — Startup${RESET}"
echo ""

# ═══════════════════════════════════════════════════════════════════
# 1. DEPENDENCY CHECKS
# ═══════════════════════════════════════════════════════════════════
section "Checking Dependencies"

check_cmd() {
  if command -v "$1" &>/dev/null; then
    success "$1 found"
  else
    warn "$1 not found — $2"
  fi
}

check_cmd node      "Install Node.js: https://nodejs.org"
check_cmd npm       "Install npm alongside Node.js"
check_cmd Xvfb      "Install with: sudo apt install xvfb"
check_cmd x11vnc    "Install with: sudo apt install x11vnc"
check_cmd websockify "Install with: sudo apt install websockify"

# Node.js is required — fail fast if missing
if ! command -v node &>/dev/null; then
  error "Node.js is required but not found. Please install it first."
  exit 1
fi

# ── Install npm dependencies if needed ─────────────────────────────
if [ ! -d "node_modules" ]; then
  section "Installing npm Dependencies"
  npm install
  success "npm install complete"
else
  info "node_modules already present — skipping npm install"
fi

# ═══════════════════════════════════════════════════════════════════
# 2. CLEANUP STALE PROCESSES
# ═══════════════════════════════════════════════════════════════════
section "Cleaning Up Stale Processes"

kill_quietly() { pkill -f "$1" 2>/dev/null || true; }

kill_quietly "Xvfb :20"
kill_quietly "x11vnc.*5920"
kill_quietly "websockify.*6080"
kill_quietly "node server.js"
kill_quietly "ros2 run"
kill_quietly "ros2 launch"
kill_quietly "rviz2"

sleep 1
success "Cleanup done"

# ═══════════════════════════════════════════════════════════════════
# 3. DETERMINE PORT
# ═══════════════════════════════════════════════════════════════════
PORT="${PORT:-3000}"
DASHBOARD_URL="http://localhost:${PORT}"

# ═══════════════════════════════════════════════════════════════════
# 4. START THE SERVER
# ═══════════════════════════════════════════════════════════════════
section "Starting ROS Dashboard Server"
info "Server will be available at ${BOLD}${DASHBOARD_URL}${RESET}"
info "Press  Ctrl+C  to stop everything"
echo ""

# ── Trap Ctrl+C for a clean shutdown ──────────────────────────────
cleanup() {
  echo ""
  section "Shutting Down"
  kill_quietly "node server.js"
  kill_quietly "Xvfb :20"
  kill_quietly "x11vnc.*5920"
  kill_quietly "websockify.*6080"
  kill_quietly "ros2 run"
  kill_quietly "ros2 launch"
  kill_quietly "rviz2"
  success "All processes stopped. Goodbye!"
  exit 0
}
trap cleanup SIGINT SIGTERM

# ── Auto-open browser after a short delay (best-effort) ───────────
(
  sleep 3
  if command -v xdg-open &>/dev/null; then
    xdg-open "$DASHBOARD_URL" &>/dev/null &
  elif command -v sensible-browser &>/dev/null; then
    sensible-browser "$DASHBOARD_URL" &>/dev/null &
  fi
) &

# ── Launch server (foreground so logs stream to terminal) ─────────
PORT="${PORT}" node server.js

const express = require('express');
const http = require('http');
const net = require('net');
const socketIO = require('socket.io');
const { spawn, execSync } = require('child_process');
const path = require('path');
const os = require('os');
const fs = require('fs');

const HOME = os.homedir();

const app = express();
const server = http.createServer(app);
const io = socketIO(server, {
  cors: { origin: '*' }
});

// ── Display config ────────────────────────────────────────────────────────────
const VIZ_DISPLAY = ':20';       // Xvfb virtual display for RViz
const VNC_PORT    = 5920;        // x11vnc listens here
const NOVNC_PORT  = 6080;        // websockify WebSocket → VNC bridge

// ── WebSocket proxy: /vnc WebSocket → websockify on :6080 ────────────────────
server.on('upgrade', (req, socket, head) => {
  if (req.url.startsWith('/vnc')) {
    const target = net.createConnection(NOVNC_PORT, '127.0.0.1');
    target.on('connect', () => {
      const rewrittenUrl = req.url.replace(/^\/vnc/, '') || '/';
      let rawRequest = `${req.method} ${rewrittenUrl} HTTP/${req.httpVersion}\r\n`;
      for (const [k, v] of Object.entries(req.headers)) {
        rawRequest += `${k}: ${v}\r\n`;
      }
      rawRequest += `\r\n`;
      target.write(rawRequest);
      if (head && head.length > 0) target.write(head);
      socket.pipe(target);
      target.pipe(socket);
    });
    target.on('error', (e) => { console.error('[VNC-PROXY] error:', e.message); socket.destroy(); });
    socket.on('error', () => target.destroy());
    socket.on('close', () => target.destroy());
  }
});

// ── Serve noVNC static assets (system install OR npm fallback) ───────────────
const NOVNC_SYSTEM = '/usr/share/novnc';
const NOVNC_NPM    = path.join(__dirname, 'node_modules/@novnc/novnc');
const NOVNC_PATH   = fs.existsSync(NOVNC_SYSTEM) ? NOVNC_SYSTEM : NOVNC_NPM;

if (fs.existsSync(NOVNC_PATH)) {
  app.use('/novnc', express.static(NOVNC_PATH));
  console.log('[VNC] Serving noVNC from', NOVNC_PATH);
} else {
  console.warn('[VNC] noVNC not found — install: sudo apt install novnc  OR  npm install');
}

app.use(express.static('public'));
app.use(express.json());

// ── API: expose environment config to frontend ────────────────────────────────
app.get('/api/env', (req, res) => {
  res.json({
    rvizVnc: true
  });
});

const ROS_ROOT = __dirname;

const projectConfigs = {
  ros_2: {
    path: path.join(ROS_ROOT, 'ros_2'),
    name: 'ROS 2 - Robot Proximity Communication',
    color: '#3498db'
  },
  ros_3: {
    path: path.join(ROS_ROOT, 'ros_3'),
    name: 'ROS 3 - 3 Robots Simulation',
    color: '#e74c3c'
  },
  ros_4: {
    path: path.join(ROS_ROOT, 'ros_4'),
    name: 'ROS 4 - Quadcopter Multi-Agent',
    color: '#2ecc71'
  }
};

// Only ONE active process at a time across the entire server
let activeProcess = null;   // { process, projectId, pgid }
let activeSocket = null;

// ── Kill the currently running process (entire process group) ──────────────────
function killActiveProcess(notifySocket, reason) {
  if (!activeProcess) return;

  const { process: proc, projectId, pgid } = activeProcess;
  console.log(`[KILL] Stopping ${projectId} (pgid=${pgid}), reason: ${reason}`);

  try {
    // Kill the whole process group so ros2 children die too
    process.kill(-pgid, 'SIGKILL');
  } catch (e) {
    console.warn(`[KILL] process.kill failed (${e.message}), trying proc.kill()`);
    try { proc.kill('SIGKILL'); } catch (_) {}
  }

  // Also nuke any lingering ros2 daemon / nodes
  cleanupLingeringProcesses();

  activeProcess = null;

  if (notifySocket) {
    notifySocket.emit('output', {
      type: 'info',
      message: `⏹ Process stopped (${reason}).`,
      projectId
    });
    notifySocket.emit('process-stopped', { projectId });
  }
}

// ── Robust cleanup helper ─────────────────────────────────────────────────────
function cleanupLingeringProcesses() {
  const commands = [
    'pkill -9 -f "ros2 run" 2>/dev/null || true',
    'pkill -9 -f "ros2 launch" 2>/dev/null || true',
    'pkill -9 -f "robot_node" 2>/dev/null || true',
    'pkill -9 -f "proximity_monitor" 2>/dev/null || true',
    'pkill -9 -f "graph_visualizer" 2>/dev/null || true',
    'pkill -9 -f "interactive_runner" 2>/dev/null || true',
    'pkill -9 -f "rviz2" 2>/dev/null || true',
    'pkill -9 -f "foxglove_bridge" 2>/dev/null || true',
    'source /opt/ros/humble/setup.bash && ros2 daemon stop 2>/dev/null || true'
  ];
  for (const cmd of commands) {
    try {
      execSync(cmd, { shell: '/bin/bash', stdio: 'ignore' });
    } catch (_) {}
  }
}

// ── ROS environment for child processes ───────────────────────────────────────
function rosEnv(projectId) {
  // Use unique ROS_DOMAIN_ID for each project to isolate network traffic
  const domainId = projectId === 'ros_2' ? '2' : (projectId === 'ros_3' ? '3' : '4');
  return {
    ...process.env,
    PYTHONUNBUFFERED: '1',
    PATH: `/opt/ros/humble/bin:/usr/bin:/bin:${process.env.PATH || ''}`,
    LD_LIBRARY_PATH: `/opt/ros/humble/lib:${process.env.LD_LIBRARY_PATH || ''}`,
    AMENT_PREFIX_PATH: '/opt/ros/humble',
    ROS_DISTRO: 'humble',
    COLCON_HOME: `${HOME}/.colcon`,
    PYTHONPATH: '',
    DISPLAY: VIZ_DISPLAY,
    WAYLAND_DISPLAY: '',          // force X11 mode for RViz
    XDG_SESSION_TYPE: 'x11',
    ROS_DOMAIN_ID: domainId
  };
}

// ── Virtual display stack: Xvfb → x11vnc → websockify ───────────────────────
let xvfbProc = null;
let x11vncProc = null;
let websockifyProc = null;

function startDisplayStack() {
  console.log(`[VIZ] Starting Xvfb on ${VIZ_DISPLAY}...`);

  // Kill any leftover processes from a previous run
  try { execSync(`pkill -f 'Xvfb ${VIZ_DISPLAY}' 2>/dev/null`); } catch (_) {}
  try { execSync(`pkill -f 'x11vnc.*:${VNC_PORT}' 2>/dev/null`); } catch (_) {}
  try { execSync(`pkill -f 'websockify.*${NOVNC_PORT}' 2>/dev/null`); } catch (_) {}

  // 1. Xvfb virtual framebuffer
  xvfbProc = spawn('Xvfb', [VIZ_DISPLAY, '-screen', '0', '1280x800x24', '-ac'], {
    detached: false, stdio: 'ignore'
  });
  xvfbProc.on('error', e => console.error('[VIZ] Xvfb error:', e.message));

  // 2. x11vnc — wait 1.5s for Xvfb to be ready
  setTimeout(() => {
    console.log(`[VIZ] Starting x11vnc on port ${VNC_PORT}...`);
    x11vncProc = spawn('x11vnc', [
      '-display', VIZ_DISPLAY,
      '-nopw', '-localhost',
      '-rfbport', String(VNC_PORT),
      '-shared', '-forever', '-noxdamage'
    ], {
      detached: false,
      stdio: 'ignore',
      env: {
        ...process.env,
        DISPLAY: VIZ_DISPLAY,
        WAYLAND_DISPLAY: '',
        XDG_SESSION_TYPE: 'x11'
      }
    });
    x11vncProc.on('error', e => console.error('[VIZ] x11vnc error:', e.message));

    // 3. websockify — bridge VNC → WebSocket
    setTimeout(() => {
      console.log(`[VIZ] Starting websockify on port ${NOVNC_PORT} → VNC ${VNC_PORT}...`);
      websockifyProc = spawn('websockify', [
        '--web', NOVNC_PATH,
        String(NOVNC_PORT),
        `localhost:${VNC_PORT}`
      ], { detached: false, stdio: 'ignore' });
      websockifyProc.on('error', e => console.error('[VIZ] websockify error:', e.message));
      console.log('[VIZ] Display stack ready.');
    }, 1500);
  }, 1500);
}

startDisplayStack();

// ── Socket connections ─────────────────────────────────────────────────────────
// ── Global cleanup on server startup ───────────────────────────────────────────
console.log('[SYSTEM] Performing initial cleanup of lingering ROS processes...');
cleanupLingeringProcesses();
console.log('[SYSTEM] Cleanup complete.');

io.on('connection', (socket) => {
  console.log('Client connected:', socket.id);
  activeSocket = socket;

  // ── Start (or restart) a project ──────────────────────────────────────────
  socket.on('build-and-run', (projectId) => {
    const config = projectConfigs[projectId];
    if (!config) {
      socket.emit('output', { type: 'error', message: `Unknown project: ${projectId}` });
      return;
    }

    // Stop whatever is already running first
    if (activeProcess) {
      socket.emit('output', {
        type: 'info',
        message: `⏹ Stopping previous project (${activeProcess.projectId}) before starting ${projectId}...`
      });
      killActiveProcess(socket, 'new project started');
      // Brief pause so OS can clean up ports/resources
      setTimeout(() => launchProject(socket, projectId, config), 1500);
    } else {
      launchProject(socket, projectId, config);
    }
  });

  // ── Send stdin to the running process ─────────────────────────────────────
  socket.on('send-input', ({ projectId, input }) => {
    if (activeProcess && activeProcess.projectId === projectId) {
      console.log(`[INPUT → ${projectId}]: ${input}`);
      activeProcess.process.stdin.write(input + '\n');
      socket.emit('output', { type: 'user-input', message: `> ${input}`, projectId });
    } else {
      socket.emit('output', { type: 'error', message: 'No matching running process to send input to.' });
    }
  });

  // ── Stop the running process ───────────────────────────────────────────────
  socket.on('stop-process', (projectId) => {
    if (activeProcess && activeProcess.projectId === projectId) {
      killActiveProcess(socket, 'user requested stop');
    } else {
      socket.emit('output', { type: 'info', message: 'No running process to stop.' });
    }
  });

  // ── Cleanup on disconnect ─────────────────────────────────────────────────
  socket.on('disconnect', () => {
    console.log('Client disconnected:', socket.id);
    // Do not kill the active process on disconnect so that page reloads or multiple tabs
    // don't abort the running simulation.
  });
});

// ── Launch a ROS project ──────────────────────────────────────────────────────
function launchProject(socket, projectId, config) {
  socket.emit('output', { type: 'info', message: `▶ Starting ${config.name}...` });
  socket.emit('output', { type: 'building', message: '🔨 Building project...' });

  const buildScript = `#!/bin/bash
set -e
source /opt/ros/humble/setup.bash
echo "[ROS] ROS_DISTRO=$ROS_DISTRO"
cd "${config.path}"
echo "[BUILD] Building robot_proximity..."
colcon build --packages-select robot_proximity 2>&1
echo "[BUILD] Done. Sourcing install..."
source "${config.path}/install/setup.bash"
echo "[RUN] Launching interactive_runner..."
exec ros2 run robot_proximity interactive_runner
`;

  const child = spawn('bash', ['-c', buildScript], {
    cwd: config.path,
    stdio: ['pipe', 'pipe', 'pipe'],
    detached: true,   // <-- creates a new process group so we can kill -pgid
    env: rosEnv(projectId)
  });

  // Store pgid = child.pid (because detached=true makes child the group leader)
  activeProcess = { process: child, projectId, pgid: child.pid };
  console.log(`[LAUNCH] ${projectId} pid=${child.pid} pgid=${child.pid}`);

  // Notify frontend which project is now active
  socket.emit('project-started', { projectId });

  child.stdout.on('data', (data) => {
    const msg = data.toString();
    console.log(`[${projectId}] ${msg.trim()}`);
    socket.emit('output', { type: 'stdout', message: msg, projectId });
  });

  child.stderr.on('data', (data) => {
    const msg = data.toString();
    // ROS2 uses stderr for INFO logs — don't colour them red
    const msgLower = msg.toLowerCase();
    const isInfo = msgLower.includes('[info]') || msgLower.includes('[launch]');
    console.log(`[${projectId}][ERR] ${msg.trim()}`);
    socket.emit('output', { type: isInfo ? 'stdout' : 'stderr', message: msg, projectId });
  });

  child.on('close', (code) => {
    console.log(`[${projectId}] exited code=${code}`);
    if (activeProcess && activeProcess.projectId === projectId) {
      activeProcess = null;
    }
    socket.emit('output', {
      type: code === 0 ? 'success' : 'info',
      message: `Process ended (exit code ${code}).`,
      projectId
    });
    socket.emit('process-stopped', { projectId });
  });

  child.on('error', (err) => {
    console.error(`[${projectId}] spawn error:`, err);
    socket.emit('output', { type: 'error', message: `Spawn error: ${err.message}`, projectId });
    activeProcess = null;
    socket.emit('process-stopped', { projectId });
  });
}

const PORT = process.env.PORT || 3000;
server.listen(PORT, () => {
  console.log(`ROS Project Runner running on http://localhost:${PORT}`);
});

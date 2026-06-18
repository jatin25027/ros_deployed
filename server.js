const express = require('express');
const http = require('http');
const net = require('net');
const socketIO = require('socket.io');
const { spawn, execSync } = require('child_process');
const path = require('path');
const os = require('os');
const fs = require('fs');

const app = express();
const server = http.createServer(app);
const io = socketIO(server, {
  cors: { origin: '*' }
});

// ── WebSocket proxy: /websockify → websockify on :6080 via raw TCP pipe ──────
// We forward the raw HTTP Upgrade + head bytes to websockify, then pipe both
// directions so websockify handles the WS handshake itself (no re-framing bugs).
const WEBSOCKIFY_PORT = 6080;
server.on('upgrade', (req, socket, head) => {
  if (req.url.startsWith('/websockify')) {
    const target = net.createConnection(WEBSOCKIFY_PORT, '127.0.0.1');

    target.on('connect', () => {
      // Forward the original HTTP Upgrade request to websockify
      let rawRequest = `${req.method} ${req.url} HTTP/${req.httpVersion}\r\n`;
      for (const [k, v] of Object.entries(req.headers)) {
        rawRequest += `${k}: ${v}\r\n`;
      }
      rawRequest += `\r\n`;
      target.write(rawRequest);
      if (head && head.length > 0) target.write(head);

      // Pipe raw bytes both ways
      socket.pipe(target);
      target.pipe(socket);
    });

    target.on('error', (e) => { console.error('[PROXY] target error:', e.message); socket.destroy(); });
    socket.on('error', () => target.destroy());
    socket.on('close', () => target.destroy());
  }
});

app.use(express.static('public'));
// noVNC location varies by distro — try multiple paths
const NOVNC_DIRS = ['/usr/share/novnc', '/usr/share/novnc/core', '/usr/local/share/novnc'];
const novncDir = NOVNC_DIRS.find(d => fs.existsSync(d)) || '/usr/share/novnc';
app.use('/novnc', express.static(novncDir));
app.use(express.json());

// ── API: expose environment config to frontend ────────────────────────────────
app.get('/api/env', (req, res) => {
  res.json({
    rvizVnc: true
  });
});

const HOME = os.homedir();
const DESKTOP_PATH = path.join(HOME, 'Desktop', 'ros_full');
const ROS_ROOT = fs.existsSync(DESKTOP_PATH) ? DESKTOP_PATH : __dirname;

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
    DISPLAY: ':99',
    ROS_DOMAIN_ID: domainId
  };
}

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

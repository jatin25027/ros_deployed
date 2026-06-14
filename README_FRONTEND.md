# ROS Project Runner - Interactive Frontend

A modern web-based frontend for running ROS 2 projects interactively. Select a project card, and the frontend will build and run the project, capturing all terminal output and allowing you to provide interactive input.

## Features

✨ **Three Project Cards** - Easily switch between ros_2, ros_3, and ros_4 projects
📱 **Real-time Output** - Live terminal output displayed in the browser
⌨️ **Interactive Input** - Provide input to interactive prompts directly from the frontend
🔧 **Automatic Build** - Projects are automatically built when selected
📊 **Output Display** - Beautiful terminal-style output screen with syntax highlighting
🎨 **Modern UI** - Gradient backgrounds, smooth animations, responsive design

## Prerequisites

1. **Node.js** (v14 or higher) - [Download here](https://nodejs.org/)
2. **ROS 2 Humble** - Already installed on your system
3. **npm** - Comes with Node.js

## Setup Instructions

### Step 1: Install Node Dependencies

```bash
cd /home/jatin/ros_full
npm install
```

This will install:
- `express` - Web server framework
- `socket.io` - Real-time bidirectional communication
- `nodemon` (dev) - Automatic server restart on file changes

### Step 2: Start the Server

```bash
npm start
```

Or with auto-reload during development:

```bash
npm run dev
```

You should see:
```
Server running on http://localhost:3000
```

### Step 3: Open in Browser

Navigate to: **http://localhost:3000**

## How to Use

### 1. Select a Project
Click on one of the three project cards:
- **ROS 2** - Robot Proximity Communication System
- **ROS 3** - 3 Robots Simulation  
- **ROS 4** - Quadcopter Multi-Agent Simulation

### 2. View Build Output
The terminal will start building the project. You'll see:
- `Building project...` - Compilation in progress
- Build output in real-time
- Once built, the interactive runner will start

### 3. Respond to Prompts
When the interactive runner asks for input:
- **Simulation Mode**: Enter `1` for AUTO or `2` for MANUAL
- **Obstacle Interval**: Enter seconds (e.g., `8` or `0` to disable)
- **Robot Count (AUTO)**: Enter 1-10
- **Waypoints (MANUAL)**: Enter comma-separated node names (e.g., `A1,B2,C3`)

The frontend will validate your input and send it to the running process.

### 4. Monitor Output
- All terminal output appears in the **Output Terminal** section
- Color-coded output:
  - 🟠 Orange = Building/Processing
  - 🔵 Blue = Info messages
  - 🟢 Green = Success/Completion
  - 🔴 Red = Errors
  - 🟡 Yellow = Your input

### 5. Stop Process
Click the **Stop Process** button to terminate the running simulation at any time.

## File Structure

```
ros_full/
├── server.js                 # Node.js backend server
├── package.json              # NPM dependencies
├── public/
│   └── index.html           # Frontend HTML/CSS/JS
└── ros_2/                   # ROS 2 project
└── ros_3/                   # ROS 3 project
└── ros_4/                   # ROS 4 project
```

## Architecture

### Backend (server.js)
- **Express.js** - Serves the frontend and handles HTTP requests
- **Socket.io** - Real-time two-way communication with the browser
- **child_process** - Spawns and manages ROS project processes
- **Node.js Streams** - Captures stdout/stderr from running processes

### Frontend (index.html)
- **Vanilla JavaScript** - No framework dependencies (besides Socket.io client)
- **CSS Grid** - Responsive layout
- **Socket.io Client** - Real-time communication with server
- **Modern CSS** - Gradients, animations, flexbox

## Environment Variables

Optional: Create a `.env` file to customize:

```bash
PORT=3000                    # Server port (default 3000)
NODE_ENV=development         # development or production
```

## Troubleshooting

### "Cannot find module 'express'"
```bash
npm install
```

### Port 3000 already in use
```bash
# Change the port
PORT=3001 npm start
```

### Process won't start
- Ensure `/opt/ros/humble/setup.bash` exists on your system
- Check ROS 2 is properly installed: `source /opt/ros/humble/setup.bash`
- Check project paths exist in `/home/jatin/ros_full/`

### Can't see RViz visualization
- RViz opens in a separate window; check your taskbar
- Ensure X11/WSLg is properly configured if using WSL2

## API Reference

### Socket Events (Frontend → Backend)

```javascript
// Start building and running a project
socket.emit('build-and-run', 'ros_2');

// Send input to running process
socket.emit('send-input', {
  projectId: 'ros_2',
  input: '1'  // User's input
});

// Stop the running process
socket.emit('stop-process', 'ros_2');
```

### Socket Events (Backend → Frontend)

```javascript
// Receive output from process
socket.on('output', (data) => {
  // data = {
  //   type: 'stdout' | 'stderr' | 'info' | 'building' | 'user-input' | 'process-end',
  //   message: 'output text',
  //   projectId: 'ros_2'
  // }
});

// Error occurred
socket.on('error', (message) => {
  console.error(message);
});
```

## Building the Projects Manually

If you want to build projects without the frontend:

### ROS 2
```bash
source /opt/ros/humble/setup.bash
cd ~/ros_full/ros_2
colcon build --packages-select robot_proximity
source install/setup.bash
ros2 run robot_proximity interactive_runner
```

### ROS 3
```bash
source /opt/ros/humble/setup.bash
cd ~/ros_full/ros_3
colcon build --packages-select robot_proximity
source install/setup.bash
ros2 launch robot_proximity temp_interactive.launch.py
```

### ROS 4
```bash
source /opt/ros/humble/setup.bash
cd ~/ros_full/ros_4
colcon build --packages-select robot_proximity
source install/setup.bash
ros2 run robot_proximity interactive_runner
```

## Performance Notes

- **Build Time**: First build (~2-5 minutes), incremental builds (~10-30 seconds)
- **Memory**: Each process uses ~100-300MB
- **Network**: Uses WebSocket for efficient real-time communication
- **CPU**: Minimal when idle; scales with number of robots in simulation

## Known Limitations

1. Only one project can run at a time per client
2. Opening multiple browser tabs will create multiple processes
3. Process output is not persisted after browser close
4. RViz windows open in system display (not in browser)

## Future Enhancements

- [ ] Multiple concurrent projects
- [ ] Process history/logging
- [ ] ROS topic visualization
- [ ] Network bandwidth visualization
- [ ] Preset configurations
- [ ] Export logs to file
- [ ] Collaborative multi-user support

## Support

For issues or questions:
1. Check the troubleshooting section above
2. Review ROS 2 Humble documentation
3. Check process logs in `/home/jatin/ros_full/log/`

---

**Created for ROS 2 Humble | Node.js 14+**

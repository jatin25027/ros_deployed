const io = require('socket.io-client');
const socket = io('https://jatin25027-ros-simulation-dashboard.hf.space', { transports: ['websocket', 'polling'] });

socket.on('connect', () => {
    console.log('Connected to Hugging Face space!');
    socket.emit('build-and-run', 'ros_2');
});

socket.on('output', (data) => {
    console.log(`[OUTPUT] ${data.type}: ${data.message}`);
    if (data.message.includes('Enter choice')) {
        console.log('Sending choice 1');
        socket.emit('send-input', { projectId: 'ros_2', input: '1' });
    }
    if (data.message.includes('Enter number of robots')) {
        console.log('Sending 3 robots');
        socket.emit('send-input', { projectId: 'ros_2', input: '3' });
    }
});

socket.on('disconnect', () => {
    console.log('Disconnected');
});

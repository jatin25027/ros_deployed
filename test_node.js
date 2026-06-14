const { spawn } = require('child_process');
const child = spawn('bash', ['-c', 'source /opt/ros/humble/setup.bash && cd ros_2 && source install/setup.bash && ros2 run robot_proximity interactive_runner'], {
  env: { ...process.env, DISPLAY: '' }
});
child.stdout.on('data', d => console.log('STDOUT:', d.toString()));
child.stderr.on('data', d => console.log('STDERR:', d.toString()));
child.on('close', c => console.log('EXIT:', c));

setTimeout(() => {
    child.stdin.write('1\n');
}, 2000);
setTimeout(() => {
    child.stdin.write('3\n');
}, 4000);

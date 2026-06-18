# ── HuggingFace Spaces Dockerfile ────────────────────────────────────────────
FROM osrf/ros:humble-desktop

# Install NodeJS 20
RUN apt-get update && apt-get install -y curl && \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && \
    rm -rf /var/lib/apt/lists/*

# Create a non-root user (Hugging Face runs with UID 1000)
RUN useradd -m -u 1000 user && \
    mkdir -p /app && \
    chown -R user:user /app

WORKDIR /app

# Switch to the non-root user
USER user

# Copy package files first to cache npm install
COPY --chown=user:user package.json package-lock.json* ./

# Install npm packages
RUN npm ci --only=production || npm install --only=production

# Copy the rest of the project files
COPY --chown=user:user . .

# Setup environment sourcing for ROS 2 inside our shell environment
RUN echo "source /opt/ros/humble/setup.bash" >> /home/user/.bashrc

# Pre-build workspaces
RUN /bin/bash -c "source /opt/ros/humble/setup.bash && \
    cd /app/ros_2 && colcon build --packages-select robot_proximity && \
    cd /app/ros_3 && colcon build --packages-select robot_proximity && \
    cd /app/ros_4 && colcon build --packages-select robot_proximity"

# Set up ROS environment variables for run time
ENV AMENT_PREFIX_PATH=/opt/ros/humble
ENV ROS_DISTRO=humble
ENV PYTHONPATH=/opt/ros/humble/local/lib/python3.10/dist-packages
ENV PORT=7860

EXPOSE 7860

# Directly launch node server
CMD ["node", "server.js"]

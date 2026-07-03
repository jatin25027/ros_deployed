# ── Hugging Face Spaces Dockerfile ───────────────────────────────────────────
# Base: ROS 2 Humble (Ubuntu 22.04)
FROM osrf/ros:humble-desktop

# ── System dependencies ───────────────────────────────────────────────────────
# x11vnc + Xvfb + websockify + novnc for the VNC→WebSocket→browser pipeline
# libgl1-mesa-dri  → software OpenGL so RViz renders without a GPU
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        xvfb \
        x11vnc \
        websockify \
        novnc \
        libgl1-mesa-dri \
        libgles2-mesa \
        mesa-utils \
        net-tools \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# ── Non-root user (Hugging Face runs with UID 1000) ───────────────────────────
RUN useradd -m -u 1000 user && \
    mkdir -p /app && \
    chown -R user:user /app

WORKDIR /app
USER user

# ── npm install (cached layer) ────────────────────────────────────────────────
COPY --chown=user:user package.json package-lock.json* ./
RUN npm ci --only=production 2>/dev/null || npm install --only=production

# ── Copy project ──────────────────────────────────────────────────────────────
COPY --chown=user:user . .

# ── Source ROS 2 in shell ─────────────────────────────────────────────────────
RUN echo "source /opt/ros/humble/setup.bash" >> /home/user/.bashrc

# ── Pre-build all ROS workspaces ──────────────────────────────────────────────
RUN /bin/bash -c "\
    source /opt/ros/humble/setup.bash && \
    cd /app/ros_2 && colcon build --parallel-workers 1 --packages-select robot_proximity && \
    cd /app/ros_3 && colcon build --parallel-workers 1 --packages-select robot_proximity && \
    cd /app/ros_4 && colcon build --parallel-workers 1 --packages-select robot_proximity"

# ── Runtime environment ───────────────────────────────────────────────────────
ENV AMENT_PREFIX_PATH=/opt/ros/humble
ENV ROS_DISTRO=humble
ENV PYTHONPATH=/opt/ros/humble/local/lib/python3.10/dist-packages
ENV PORT=7860
# Virtual display — x11vnc will capture this
ENV DISPLAY=:20
# Force software OpenGL so RViz renders without a GPU
ENV LIBGL_ALWAYS_SOFTWARE=1
ENV MESA_GL_VERSION_OVERRIDE=3.3

EXPOSE 7860

# server.js manages the full display stack (Xvfb → x11vnc → websockify)
CMD ["node", "server.js"]

---
title: ROS Simulation Dashboard
emoji: 🤖
colorFrom: indigo
colorTo: purple
sdk: docker
app_port: 7860
pinned: false
---

# 🤖 ROS Simulation Dashboard

[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/jatin25027/ros_deployed)

A web-based dashboard and interactive simulator built to run multi-agent ROS 2 (Humble) systems.

This repository is configured to deploy directly to Hugging Face Spaces using Docker, launching a clean headless ROS 2 environment. Users can control and monitor multiple ROS 2 project simulations, sending interactive command inputs and viewing live RViz 3D simulation streams directly in the browser!

## Features
- 🔵 **ROS 2** – Robot Proximity Communication (5×4 graph navigation)
- 🔴 **ROS 3** – Grid Simulation (10×8 obstacle grid with BFS rerouting)
- 🟢 **ROS 4** – Multi-Agent Quadcopter (dynamic obstacles, up to 10 agents)
- 🖥️ **Live RViz** – 3D simulation streamed via noVNC directly in the browser

# Docker Monitoring Hub

A centralized monitoring dashboard for managing multiple Docker-based application instances. This application provides a unified view of all running containers on your host, grouped by their project/instance, allowing you to track health, resource usage, and logs from a single interface.

## 🚀 How It Works

This monitoring app runs as a standalone Docker container but has special access to the **host's Docker Daemon** via the Unix socket (`/var/run/docker.sock`).

1.  **Centralized Vision**: Because it connects to the Docker socket, it can "see" every other container running on your machine, regardless of which folder or `docker-compose.yml` file started them.
2.  **Automatic Grouping**: It inspects the `com.docker.compose.project` label on each container (which defaults to the directory name) to automatically group containers into "Instances".
    *   Example: If you have a repo in `folder_A` and another in `folder_B`, the dashboard will show two groups: "Instance: folder_A" and "Instance: folder_B".
3.  **No Configuration Needed**: You don't need to tell this app where your other repositories are. As soon as you start a new stack anywhere on the host, it appears here.

## 🛠 Prerequisites

*   **Docker** and **Docker Compose** installed on the host machine.
*   Permission to access `/var/run/docker.sock` (standard for root/docker group users).

## 📥 Installation & Running

1.  **Navigate to the directory**:
    ```bash
    cd monitor-hub
    ```

2.  **Start the Monitor**:
    ```bash
    docker-compose up --build -d
    ```

3.  **Access the Dashboard**:
    Open your browser and go to:
    `http://<your-server-ip>:8599`

    *(Note: We use port **8599** to avoid conflicts with your existing apps running on 8501-8509).*

## 📊 Dashboard Features

### 1. Global Overview
At the top, you see aggregate metrics:
*   **Total Containers**: Number of containers found on the system.
*   **Running**: How many are currently active.
*   **Active Instances**: Number of distinct projects (directories) detected.

### 2. Instances Overview
This is the main view. Containers are grouped by their **Instance Name** (the folder they run from).
*   Expand an instance to see its specific services (e.g., `workspace`, `gallery`, `video`).
*   Check their Uptime and Status at a glance.

### 3. Container Inspector
Scroll down to the "Container Inspector" section to drill down:
*   **Select a Container**: Pick any container from the dropdown list.
*   **Controls**: Use the **Restart** button to reboot a stuck container.
*   **Live Stats**: View real-time **CPU Usage** and **Memory Usage**.
*   **Logs**: View the last 100 lines of logs for quick debugging.

## 🔧 Troubleshooting

**"Could not connect to Docker Daemon"**
*   Ensure the `volumes` section in `docker-compose.yml` correctly mounts the socket: `- /var/run/docker.sock:/var/run/docker.sock`.
*   Ensure the user running docker has permissions.

**CPU/Memory Stats are empty**
*   Stats collection can take a second to initialize. If using cgroups v2, some metrics might be calculated differently (the app attempts to handle this automatically).

**App not accessible**
*   Check if port **8599** is open on your firewall.

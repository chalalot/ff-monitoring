import streamlit as st
import docker
import pandas as pd
import time
import plotly.express as px
from datetime import datetime

st.set_page_config(page_title="Docker Monitor Hub", layout="wide", page_icon="🐳")

# --- Helper Functions ---

def get_docker_client():
    try:
        client = docker.from_env()
        client.ping()
        return client
    except Exception as e:
        st.error(f"Could not connect to Docker Daemon. Ensure the socket is mounted.\nError: {e}")
        return None

def calculate_cpu_percent(d):
    # CPU usage calculation based on Docker API stats
    # Handle different Docker API versions/cgroup structures
    cpu_usage = d.get("cpu_stats", {}).get("cpu_usage", {})
    precpu_usage = d.get("precpu_stats", {}).get("cpu_usage", {})
    
    # Get CPU count safely
    percpu = cpu_usage.get("percpu_usage", [])
    if percpu:
        cpu_count = len(percpu)
    else:
        # Fallback for cgroup v2 or incomplete stats
        cpu_count = d.get("cpu_stats", {}).get("online_cpus", 1)

    cpu_percent = 0.0
    
    # Calculate deltas with safety checks
    cpu_total = float(cpu_usage.get("total_usage", 0.0))
    precpu_total = float(precpu_usage.get("total_usage", 0.0))
    
    system_cpu = float(d.get("cpu_stats", {}).get("system_cpu_usage", 0.0))
    presystem_cpu = float(d.get("precpu_stats", {}).get("system_cpu_usage", 0.0))
    
    cpu_delta = cpu_total - precpu_total
    system_delta = system_cpu - presystem_cpu

    if system_delta > 0.0 and cpu_delta > 0.0:
        cpu_percent = (cpu_delta / system_delta) * cpu_count * 100.0
    
    return cpu_percent

def format_bytes(size):
    # 2**10 = 1024
    power = 2**10
    n = 0
    power_labels = {0 : '', 1: 'K', 2: 'M', 3: 'G', 4: 'T'}
    while size > power:
        size /= power
        n += 1
    return f"{size:.2f} {power_labels[n]}B"

# --- Main App ---

st.title("🐳 Docker Monitoring Hub")
st.markdown("Monitor all your running application instances in one place.")

client = get_docker_client()

if not client:
    st.stop()

# Auto-Refresh Control
refresh_interval = st.sidebar.slider("Refresh Interval (s)", 2, 60, 5)
if st.sidebar.button("Force Refresh"):
    st.rerun()

# --- Fetch Data ---

containers = client.containers.list(all=True)
data = []

for c in containers:
    # Try to identify project/instance from labels
    labels = c.labels
    project = labels.get('com.docker.compose.project', 'Unknown')
    service = labels.get('com.docker.compose.service', c.name)
    
    # Basic Info
    status = c.status
    state = c.attrs['State']
    started_at = state.get('StartedAt', '')
    if started_at:
        try:
            # Parse ISO format (e.g., 2023-10-27T10:00:00.123456789Z)
            started_dt = datetime.fromisoformat(started_at.replace('Z', '+00:00'))
            uptime = datetime.now(started_dt.tzinfo) - started_dt
            uptime_str = str(uptime).split('.')[0]
        except:
            uptime_str = "N/A"
    else:
        uptime_str = "N/A"

    # Stats (This can be slow if we query all, so maybe optional or on drill-down)
    # For overview, we might skip heavy stats or do them asynchronously?
    # Streamlit runs sequentially. Let's try fetching stats with stream=False for running ones.
    
    cpu_usage = 0.0
    mem_usage = 0.0
    mem_limit = 0.0
    mem_percent = 0.0
    
    if status == 'running':
        try:
            # stats(stream=False) can take time. Let's see if we can get quick snapshot?
            # Actually, standard stats call blocks. 
            # For a dashboard with many containers, this loop will be slow.
            # OPTIMIZATION: Only fetch stats if 'Detailed Stats' is enabled or for specific view.
            # For now, let's just get memory from 'top' or basic inspect? No, top gives processes.
            # We'll skip deep stats in the main table for speed.
            pass 
        except:
            pass
    
    data.append({
        "ID": c.short_id,
        "Name": c.name,
        "Project (Instance)": project,
        "Service": service,
        "Status": status,
        "State": state['Status'], # running, exited, etc.
        "Uptime": uptime_str,
        "Image": c.image.tags[0] if c.image.tags else c.image.id[:12]
    })

df = pd.DataFrame(data)

# --- Dashboard Overview ---

# Metrics
total_containers = len(df)
running_containers = len(df[df['Status'] == 'running'])
projects = df['Project (Instance)'].unique()

m1, m2, m3 = st.columns(3)
m1.metric("Total Containers", total_containers)
m2.metric("Running", running_containers)
m3.metric("Active Instances", len(projects))

st.divider()

# --- Grouped View ---

st.subheader("Instances Overview")

# Group by Project
if not df.empty:
    for project in projects:
        if project == 'Unknown':
            continue
            
        with st.expander(f"📂 Instance: {project}", expanded=True):
            proj_df = df[df['Project (Instance)'] == project]
            
            # Show table
            st.dataframe(
                proj_df[['Service', 'Status', 'Uptime', 'Name', 'ID']],
                use_container_width=True,
                hide_index=True
            )
            
            # Quick Actions (e.g. Restart all in project? Maybe too dangerous for now)
            
else:
    st.info("No containers found.")

# --- Detailed Stats (On Demand) ---

st.divider()
st.subheader("🔍 Container Inspector")

selected_container_name = st.selectbox("Select Container to Inspect", df['Name'].tolist())

if selected_container_name:
    container = client.containers.get(selected_container_name)
    
    c1, c2 = st.columns(2)
    
    with c1:
        st.markdown(f"**Status:** {container.status}")
        st.markdown(f"**Image:** {container.image.tags}")
        st.markdown(f"**ID:** `{container.short_id}`")
        
        if st.button(f"Restart {selected_container_name}"):
            with st.spinner(f"Restarting {selected_container_name}..."):
                container.restart()
            st.success("Restarted!")
            st.rerun()

    with c2:
        # Fetch Real-time Stats Here
        if container.status == 'running':
            with st.spinner("Fetching live stats..."):
                stats = container.stats(stream=False)
                
                # CPU
                cpu = calculate_cpu_percent(stats)
                
                # Memory
                mem_usage = stats['memory_stats']['usage']
                mem_limit = stats['memory_stats']['limit']
                mem_percent = (mem_usage / mem_limit) * 100.0
                
                st.metric("CPU Usage", f"{cpu:.2f}%")
                st.metric("Memory Usage", f"{format_bytes(mem_usage)} / {format_bytes(mem_limit)} ({mem_percent:.1f}%)")
                
                # Network (Rx/Tx)
                networks = stats['networks']
                for net_name, net_data in networks.items():
                    st.text(f"Network ({net_name}): Rx {format_bytes(net_data['rx_bytes'])} / Tx {format_bytes(net_data['tx_bytes'])}")
        else:
            st.warning("Container is not running.")

    # Logs
    with st.expander("View Logs (Last 100 lines)"):
        if container.status == 'running':
            logs = container.logs(tail=100).decode('utf-8')
            st.code(logs)
        else:
            st.info("Container not running, fetching last logs...")
            logs = container.logs(tail=100).decode('utf-8')
            st.code(logs)

# Auto-refresh loop
time.sleep(refresh_interval)
st.rerun()

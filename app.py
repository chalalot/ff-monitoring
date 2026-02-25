import streamlit as st
import docker
import pandas as pd
import time
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

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

def get_container_stats(container):
    try:
        if container.status != 'running':
            return None
        
        # stream=False waits for a sample to calculate CPU. 
        # This is slow, so we run it in parallel threads.
        stats = container.stats(stream=False)
        
        cpu = calculate_cpu_percent(stats)
        mem_usage = stats['memory_stats']['usage']
        mem_limit = stats['memory_stats']['limit']
        mem_percent = (mem_usage / mem_limit) * 100.0
        
        return {
            'id': container.short_id,
            'cpu': cpu,
            'memory_mb': mem_usage / (1024 * 1024),
            'memory_percent': mem_percent,
            'timestamp': datetime.now()
        }
    except Exception as e:
        return None

# --- Main App ---

st.title("🐳 Docker Monitoring Hub")

client = get_docker_client()

if not client:
    st.stop()

# Initialize Session State for History
if 'history' not in st.session_state:
    st.session_state.history = {} # { container_id: { 'cpu': [], 'memory': [], 'timestamps': [] } }

# Sidebar Controls
refresh_interval = st.sidebar.slider("Refresh Interval (s)", 2, 60, 5)
history_window = st.sidebar.slider("History Window (Points)", 10, 100, 30)
auto_refresh = st.sidebar.checkbox("Auto-Refresh", value=True)

if st.sidebar.button("Clear History"):
    st.session_state.history = {}
    st.rerun()

# --- Fetch Data (Parallel) ---

containers = client.containers.list(all=True)
running_containers = [c for c in containers if c.status == 'running']

# Update Stats if Auto-Refresh or Manual
if auto_refresh:
    with ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(get_container_stats, running_containers))
    
    # Update History
    for res in results:
        if res:
            cid = res['id']
            if cid not in st.session_state.history:
                st.session_state.history[cid] = {'cpu': [], 'memory': [], 'timestamps': []}
            
            h = st.session_state.history[cid]
            h['cpu'].append(res['cpu'])
            h['memory'].append(res['memory_mb'])
            h['timestamps'].append(res['timestamp'])
            
            # Trim History
            if len(h['cpu']) > history_window:
                h['cpu'] = h['cpu'][-history_window:]
                h['memory'] = h['memory'][-history_window:]
                h['timestamps'] = h['timestamps'][-history_window:]

# --- Dashboard Rendering ---

# Group Containers by Project
projects = {}
for c in containers:
    labels = c.labels
    project_name = labels.get('com.docker.compose.project', 'Unknown')
    if project_name not in projects:
        projects[project_name] = []
    projects[project_name].append(c)

# Render Grid
for project_name, project_containers in projects.items():
    if project_name == 'Unknown' and not project_containers:
        continue
        
    st.subheader(f"📂 Instance: {project_name}")
    
    # Create columns for grid layout (e.g. 3 cards per row)
    cols = st.columns(3)
    
    for i, c in enumerate(project_containers):
        col = cols[i % 3]
        
        with col:
            with st.container(border=True):
                # Header
                status_color = "🟢" if c.status == 'running' else "cx🔴"
                st.markdown(f"**{status_color} {c.name}**")
                st.caption(f"ID: {c.short_id} | Image: {c.image.tags[0] if c.image.tags else 'N/A'}")
                
                # Stats & Graphs
                if c.status == 'running':
                    cid = c.short_id
                    hist = st.session_state.history.get(cid, {})
                    
                    if hist and hist['cpu']:
                        last_cpu = hist['cpu'][-1]
                        last_mem = hist['memory'][-1]
                        
                        # Metrics Row
                        m1, m2 = st.columns(2)
                        m1.metric("CPU", f"{last_cpu:.1f}%")
                        m2.metric("Mem", f"{last_mem:.0f} MB")
                        
                        # Sparkline Graph (CPU)
                        fig = go.Figure()
                        fig.add_trace(go.Scatter(
                            y=hist['cpu'],
                            mode='lines',
                            fill='tozeroy',
                            line=dict(color='#00CC96', width=2),
                            name='CPU'
                        ))
                        fig.update_layout(
                            height=80,
                            margin=dict(l=0, r=0, t=0, b=0),
                            xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                            yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                            showlegend=False
                        )
                        st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
                        
                        # Sparkline Graph (Memory)
                        fig_mem = go.Figure()
                        fig_mem.add_trace(go.Scatter(
                            y=hist['memory'],
                            mode='lines',
                            fill='tozeroy',
                            line=dict(color='#636EFA', width=2),
                            name='Memory'
                        ))
                        fig_mem.update_layout(
                            height=80,
                            margin=dict(l=0, r=0, t=0, b=0),
                            xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                            yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                            showlegend=False
                        )
                        st.plotly_chart(fig_mem, use_container_width=True, config={'displayModeBar': False})
                        
                    else:
                        st.info("Waiting for data...")
                else:
                    st.warning(f"Status: {c.status}")
                    if st.button("Restart", key=f"restart_{c.short_id}"):
                         c.restart()
                         st.rerun()

    st.divider()

# Auto-refresh Loop
if auto_refresh:
    time.sleep(refresh_interval)
    st.rerun()

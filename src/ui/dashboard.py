import streamlit as st
import psycopg2
import pandas as pd
import time
import os
import json
import sys
import uuid
import threading
import queue
import subprocess
from pathlib import Path
from datetime import datetime, timedelta
import grpc

# Add paths for generated protos
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src" / "orchestrator"))
sys.path.insert(0, str(PROJECT_ROOT / "src" / "memory" / "python"))

try:
    from gladys_orchestrator.generated import memory_pb2, memory_pb2_grpc
    from gladys_orchestrator.generated import executive_pb2, executive_pb2_grpc
    from gladys_orchestrator.generated import orchestrator_pb2, orchestrator_pb2_grpc
    from gladys_orchestrator.generated import common_pb2
    from gladys_orchestrator.generated import types_pb2
except ImportError:
    st.error("Proto stubs not found. Run 'python scripts/proto_gen.py' first.")

# Service Connection Config
ENV_CONFIGS = {
    "Docker": {
        "MEMORY_ADDR": "localhost:50061",
        "SALIENCE_ADDR": "localhost:50062",
        "EXECUTIVE_ADDR": "localhost:50063",
        "ORCHESTRATOR_ADDR": "localhost:50060",
        "DB_PORT": "5433"
    },
    "Local": {
        "MEMORY_ADDR": "localhost:50051",
        "SALIENCE_ADDR": "localhost:50052",
        "EXECUTIVE_ADDR": "localhost:50053",
        "ORCHESTRATOR_ADDR": "localhost:50050",
        "DB_PORT": "5432"
    }
}

# Database Connection Config (Static)
DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_NAME = os.environ.get("DB_NAME", "gladys")
DB_USER = os.environ.get("DB_USER", "gladys")
DB_PASS = os.environ.get("DB_PASS", "gladys")

# Page Config
st.set_page_config(
    page_title="GLADyS Evaluation Dashboard",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Initialize Session State
if "response_history" not in st.session_state:
    st.session_state.response_history = []
if "response_queue" not in st.session_state:
    st.session_state.response_queue = queue.Queue()
if "subscribed" not in st.session_state:
    st.session_state.subscribed = False
if "env_mode" not in st.session_state:
    st.session_state.env_mode = "Docker" # Default
if "grpc_channels" not in st.session_state:
    st.session_state.grpc_channels = {}

# --- gRPC Clients ---

def get_or_create_channel(address: str) -> grpc.Channel:
    """Get cached channel or create new one."""
    if address not in st.session_state.grpc_channels:
        st.session_state.grpc_channels[address] = grpc.insecure_channel(address)
    return st.session_state.grpc_channels[address]

def close_all_channels():
    """Close all cached channels (call on env switch)."""
    if "grpc_channels" in st.session_state:
        for addr, channel in st.session_state.grpc_channels.items():
            try:
                channel.close()
            except Exception as e:
                print(f"Error closing channel for {addr}: {e}")
        st.session_state.grpc_channels = {}

def get_current_config():
    return ENV_CONFIGS[st.session_state.env_mode]

def get_executive_stub():
    conf = get_current_config()
    channel = get_or_create_channel(conf["EXECUTIVE_ADDR"])
    return executive_pb2_grpc.ExecutiveServiceStub(channel)

def get_memory_stub():
    conf = get_current_config()
    channel = get_or_create_channel(conf["MEMORY_ADDR"])
    return memory_pb2_grpc.MemoryStorageStub(channel)

def get_orchestrator_stub():
    conf = get_current_config()
    channel = get_or_create_channel(conf["ORCHESTRATOR_ADDR"])
    return orchestrator_pb2_grpc.OrchestratorServiceStub(channel)

def get_salience_stub():
    conf = get_current_config()
    channel = get_or_create_channel(conf["SALIENCE_ADDR"])
    return memory_pb2_grpc.SalienceGatewayStub(channel)

def send_event_to_orchestrator(event):
    """Send single event via streaming RPC, get response."""
    try:
        orch_stub = get_orchestrator_stub()
        def event_generator():
            yield event
        # Get first (only) response from stream
        for ack in orch_stub.PublishEvents(event_generator()):
            return ack
    except Exception as e:
        st.error(f"Orchestrator Error: {e}")
    return None

# --- Service Control Functions ---

def run_service_command(command: str, service: str = "all", extra_args: list = None):
    """Run a service management command via the scripts.

    Returns (success: bool, output: str)
    """
    env_mode = st.session_state.env_mode.lower()
    script = PROJECT_ROOT / "scripts" / f"{env_mode}.py"

    cmd = ["python", str(script), command, service]
    if extra_args:
        cmd.extend(extra_args)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            encoding="utf-8",
            cwd=str(PROJECT_ROOT)
        )
        output = result.stdout + result.stderr
        return result.returncode == 0, output
    except subprocess.TimeoutExpired:
        return False, "Command timed out after 120 seconds"
    except Exception as e:
        return False, str(e)

def response_subscriber_thread(q, orchestrator_addr):
    """Background thread to subscribe to responses."""
    try:
        # Create a dedicated channel for the thread and ensure it's closed on exit
        with grpc.insecure_channel(orchestrator_addr) as channel:
            orch_stub = orchestrator_pb2_grpc.OrchestratorServiceStub(channel)
            
            # Using a unique ID for the dashboard
            subscriber_id = f"dashboard-{uuid.uuid4().hex[:8]}"
            req = orchestrator_pb2.SubscribeResponsesRequest(
                subscriber_id=subscriber_id,
                include_immediate=True
            )
            responses = orch_stub.SubscribeResponses(req)
            for resp in responses:
                q.put(resp)
    except Exception as e:
        print(f"Subscription error: {e}")

# Start subscription thread only once
# Note: If environment switches, we might need to restart this thread.
# For simplicity, we stick to the initial environment for the background thread
# or require a full app restart.
if not st.session_state.subscribed:
    conf = get_current_config()
    thread = threading.Thread(
        target=response_subscriber_thread, 
        args=(st.session_state.response_queue, conf["ORCHESTRATOR_ADDR"]), 
        daemon=True
    )
    thread.start()
    st.session_state.subscribed = True

def process_queue():
    """Move messages from queue to session state history."""
    new_items = False
    while not st.session_state.response_queue.empty():
        try:
            resp = st.session_state.response_queue.get_nowait()
            st.session_state.response_history.insert(0, resp)
            # Keep last 50
            if len(st.session_state.response_history) > 50:
                st.session_state.response_history.pop()
            new_items = True
        except queue.Empty:
            break
    return new_items

# --- Database Functions ---

@st.cache_resource
def get_db_connection(host, port, dbname, user, password):
    try:
        conn = psycopg2.connect(
            host=host,
            port=port,
            database=dbname,
            user=user,
            password=password
        )
        return conn
    except Exception as e:
        st.error(f"Failed to connect to database at {host}:{port}")
        st.error(e)
        return None

def fetch_data(query, params=None):
    conf = get_current_config()
    conn = get_db_connection(
        DB_HOST, 
        conf["DB_PORT"], 
        DB_NAME, 
        DB_USER, 
        DB_PASS
    )
    if not conn:
        return pd.DataFrame()
    
    # Check if connection is alive, reconnect if needed
    if conn.closed:
        st.cache_resource.clear()
        conn = get_db_connection(
            DB_HOST, 
            conf["DB_PORT"], 
            DB_NAME, 
            DB_USER, 
            DB_PASS
        )

    try:
        # Use pandas for easier data handling
        df = pd.read_sql_query(query, conn, params=params)
        return df
    except Exception as e:
        st.error(f"Query failed: {e}")
        return pd.DataFrame()

# --- Components ---

def render_sidebar():
    """Minimal sidebar: environment, service health, controls."""
    st.sidebar.title("GLADyS")

    # Initialize session state
    if "confirm_stop_all" not in st.session_state:
        st.session_state.confirm_stop_all = False
    if "last_cmd_output" not in st.session_state:
        st.session_state.last_cmd_output = ""
    if "time_range" not in st.session_state:
        st.session_state.time_range = "All Time"

    # Environment Switcher (no "Mode" label)
    env_mode = st.sidebar.radio(
        "Environment",
        ["Docker", "Local"],
        index=0 if st.session_state.env_mode == "Docker" else 1,
        horizontal=True,
        label_visibility="collapsed"
    )

    if env_mode != st.session_state.env_mode:
        close_all_channels()
        st.session_state.env_mode = env_mode
        st.cache_resource.clear()
        st.rerun()

    # Refresh button
    if st.sidebar.button("🔄 Refresh", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    st.sidebar.markdown("---")

    # Compact Service Health (one line per service)
    st.sidebar.caption("**Services**")

    services = [
        ("memory-py", "memory-python", get_memory_stub),
        ("memory-rs", "memory-rust", get_salience_stub),
        ("orchestrator", "orchestrator", get_orchestrator_stub),
        ("executive", "executive", get_executive_stub),
    ]

    # Build status and track selected service
    if "selected_service" not in st.session_state:
        st.session_state.selected_service = "all"

    service_statuses = {}
    for display_name, cmd_name, stub_fn in services:
        status_icon = "⚫"
        try:
            stub = stub_fn()
            resp = stub.GetHealth(types_pb2.GetHealthRequest(), timeout=2)
            if resp.status == types_pb2.HEALTH_STATUS_HEALTHY:
                status_icon = "🟢"
            elif resp.status == types_pb2.HEALTH_STATUS_DEGRADED:
                status_icon = "🟡"
            else:
                status_icon = "🔴"
        except Exception:
            status_icon = "⚫"
        service_statuses[cmd_name] = status_icon

    # Check database
    current_conf = get_current_config()
    try:
        conn = get_db_connection(DB_HOST, current_conf["DB_PORT"], DB_NAME, DB_USER, DB_PASS)
        db_icon = "🟢" if conn else "🔴"
    except:
        db_icon = "⚫"

    # Service selection with radio buttons (compact)
    service_options = ["all"] + [s[1] for s in services]
    service_labels = {
        "all": "All Services",
        "memory-python": f"{service_statuses['memory-python']} memory-py",
        "memory-rust": f"{service_statuses['memory-rust']} memory-rs",
        "orchestrator": f"{service_statuses['orchestrator']} orchestrator",
        "executive": f"{service_statuses['executive']} executive",
    }

    selected = st.sidebar.radio(
        "Select service",
        service_options,
        format_func=lambda x: service_labels.get(x, x),
        label_visibility="collapsed",
        key="svc_radio"
    )
    st.session_state.selected_service = selected

    # Database status (not selectable for actions)
    st.sidebar.caption(f"{db_icon} database")

    # Action buttons (vertical layout)
    st.sidebar.markdown("---")

    target = st.session_state.selected_service

    if st.sidebar.button("▶️ Start", key="btn_start", use_container_width=True):
        with st.spinner(f"Starting {target}..."):
            success, output = run_service_command("start", target)
        st.session_state.last_cmd_output = output
        st.toast(f"Started {target}" if success else "Start failed", icon="✅" if success else "❌")
        st.rerun()

    if st.sidebar.button("🔄 Restart", key="btn_restart", use_container_width=True):
        with st.spinner(f"Restarting {target}..."):
            success, output = run_service_command("restart", target)
        st.session_state.last_cmd_output = output
        st.toast(f"Restarted {target}" if success else "Restart failed", icon="✅" if success else "❌")
        st.rerun()

    # Stop with confirmation for "all"
    if target == "all":
        if not st.session_state.confirm_stop_all:
            if st.sidebar.button("🟥 Stop", key="btn_stop", use_container_width=True):
                st.session_state.confirm_stop_all = True
                st.rerun()
        else:
            st.sidebar.warning("Stop ALL?")
            c1, c2 = st.sidebar.columns(2)
            if c1.button("Yes", key="confirm_stop"):
                with st.spinner("Stopping..."):
                    success, output = run_service_command("stop", "all")
                st.session_state.confirm_stop_all = False
                st.session_state.last_cmd_output = output
                st.toast("Stopped all" if success else "Failed", icon="✅" if success else "❌")
                st.rerun()
            if c2.button("No", key="cancel_stop"):
                st.session_state.confirm_stop_all = False
                st.rerun()
    else:
        if st.sidebar.button("🟥 Stop", key="btn_stop", use_container_width=True):
            with st.spinner(f"Stopping {target}..."):
                success, output = run_service_command("stop", target)
            st.session_state.last_cmd_output = output
            st.toast(f"Stopped {target}" if success else "Failed", icon="✅" if success else "❌")
            st.rerun()

    return st.session_state.time_range


def render_settings_tab():
    """Settings & Diagnostics tab - moved from sidebar."""
    st.header("⚙️ Settings & Diagnostics")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Filters")
        time_range = st.selectbox(
            "Time Range",
            ["Last Hour", "Last 24 Hours", "All Time"],
            index=["Last Hour", "Last 24 Hours", "All Time"].index(st.session_state.time_range),
            key="time_range_select"
        )
        if time_range != st.session_state.time_range:
            st.session_state.time_range = time_range
            st.rerun()

        st.markdown("---")
        st.subheader("Testing Tools")
        if st.button("🗑️ Clear Local History", use_container_width=True):
            st.session_state.response_history = []
            st.toast("History cleared", icon="✅")
            st.rerun()

        if st.button("🚽 Flush Accumulator", use_container_width=True):
            try:
                orch_stub = get_orchestrator_stub()
                resp = orch_stub.FlushMoment(orchestrator_pb2.FlushMomentRequest(reason="Manual flush from UI"))
                if resp.moment_sent:
                    st.success(f"Flushed {resp.events_flushed} events")
                else:
                    st.info("Accumulator empty")
            except Exception as e:
                st.error(f"Flush failed: {e}")

    with col2:
        st.subheader("Database Operations")

        # Initialize confirmation state
        if "confirm_clean_db" not in st.session_state:
            st.session_state.confirm_clean_db = False

        if st.button("📦 Run Migrations", use_container_width=True):
            with st.spinner("Running migrations..."):
                success, output = run_service_command("migrate")
            st.session_state.last_cmd_output = output
            st.toast("Migrations complete" if success else "Migration failed", icon="✅" if success else "❌")

        clean_target = st.selectbox(
            "Clean target",
            ["heuristics", "events", "all"],
            key="clean_target"
        )

        if not st.session_state.confirm_clean_db:
            if st.button("🗑️ Clean Database", use_container_width=True, type="secondary"):
                st.session_state.confirm_clean_db = True
                st.rerun()
        else:
            st.error(f"DELETE all {clean_target} data?")
            c1, c2 = st.columns(2)
            if c1.button("Yes, Delete", type="primary", key="confirm_delete"):
                with st.spinner(f"Cleaning {clean_target}..."):
                    success, output = run_service_command("clean", clean_target)
                st.session_state.confirm_clean_db = False
                st.session_state.last_cmd_output = output
                st.toast(f"Cleaned {clean_target}" if success else "Clean failed", icon="✅" if success else "❌")
                st.rerun()
            if c2.button("Cancel", key="cancel_clean"):
                st.session_state.confirm_clean_db = False
                st.rerun()

        st.markdown("---")
        st.subheader("Connection Info")
        current_conf = get_current_config()
        conn_data = [
            {"Service": "Orchestrator", "Address": current_conf["ORCHESTRATOR_ADDR"]},
            {"Service": "Memory (Python)", "Address": current_conf["MEMORY_ADDR"]},
            {"Service": "Salience (Rust)", "Address": current_conf["SALIENCE_ADDR"]},
            {"Service": "Executive", "Address": current_conf["EXECUTIVE_ADDR"]},
            {"Service": "Database", "Address": f"localhost:{current_conf['DB_PORT']}"},
        ]
        st.dataframe(conn_data, use_container_width=True, hide_index=True)

    # Command output log
    st.markdown("---")
    st.subheader("Command Log")
    if st.session_state.last_cmd_output:
        st.code(st.session_state.last_cmd_output, language="text")
    else:
        st.caption("No commands executed yet.")

def render_stats_summary(time_filter_clause, params):
    # Queries
    events_query = f"SELECT COUNT(*) FROM episodic_events WHERE archived = false {time_filter_clause}"
    heuristics_query = "SELECT COUNT(*), AVG(confidence) FROM heuristics WHERE frozen = false"
    llm_calls_query = f"SELECT COUNT(*) FROM episodic_events WHERE response_id IS NOT NULL {time_filter_clause}"

    # Fetch
    events_df = fetch_data(events_query, params)
    total_events = events_df.iloc[0, 0] if not events_df.empty else 0
    
    heuristics_df = fetch_data(heuristics_query)
    total_heuristics = heuristics_df.iloc[0, 0] if not heuristics_df.empty else 0
    avg_confidence = heuristics_df.iloc[0, 1] if not heuristics_df.empty and not pd.isna(heuristics_df.iloc[0, 1]) else 0.0
    
    llm_df = fetch_data(llm_calls_query, params)
    llm_calls = llm_df.iloc[0, 0] if not llm_df.empty else 0
    
    fast_path_events = total_events - llm_calls
    hit_rate = (fast_path_events / total_events * 100) if total_events > 0 else 0

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Events", total_events)
    col2.metric("Active Heuristics", total_heuristics, f"Avg Conf: {avg_confidence:.2f}")
    col3.metric("LLM Calls", llm_calls)
    col4.metric("Fast Path (Est)", fast_path_events, f"{hit_rate:.1f}% Rate")

def render_event_simulator():
    st.header("🧪 Interaction Lab")
    
    with st.expander("Quick Load Presets", expanded=False):
        presets = {
            "Oven Timer": ("kitchen", "Oven timer expired."),
            "Low Health": ("minecraft", "Player health is 10% after arrow hit."),
            "Smart Home": ("smart_home", "Temperature rose 5 degrees in 10 minutes."),
            "Creeper": ("minecraft", "Creeper hissed nearby!")
        }
        cols = st.columns(len(presets))
        for i, (name, val) in enumerate(presets.items()):
            if cols[i].button(name):
                st.session_state.sim_source_select = val[0]
                st.session_state.sim_text = val[1]

    with st.form("event_form", clear_on_submit=False):
        st.write("Source Mode:")
        source_mode = st.radio("Source Mode", ["Preset", "Custom"], horizontal=True, label_visibility="collapsed")
        
        c1, c2 = st.columns([1, 3]) # Wider ratio for better text space
        
        with c1:
            if source_mode == "Preset":
                source = st.selectbox("Source", ["minecraft", "kitchen", "smart_home", "work", "health"], key="sim_source_select")
            else:
                source = st.text_input("Source", value="email", key="sim_source_custom")
        
        with c2:
            raw_text = st.text_input("Event Text", placeholder="Describe what happened...", key="sim_text")
            
        st.write("Salience Override:")
        force_salience = st.radio(
            "Salience Override", 
            ["Let system evaluate", "Force HIGH (Immediate)", "Force LOW (Accumulated)"],
            horizontal=True,
            label_visibility="collapsed"
        )
            
        submit = st.form_submit_button("🚀 Process Event", use_container_width=True)

    if submit:
        if not raw_text:
            st.warning("Please enter event text.")
        else:
            try:
                event_id = str(uuid.uuid4())
                
                # Build Event
                event = common_pb2.Event(
                    id=event_id,
                    source=source,
                    raw_text=raw_text,
                )
                
                # Apply salience override if selected
                if force_salience == "Force HIGH (Immediate)":
                    event.salience.novelty = 0.9
                elif force_salience == "Force LOW (Accumulated)":
                    event.salience.novelty = 0.1
                
                with st.spinner("GLADyS is thinking..."):
                    # Route through Orchestrator (handles heuristics + LLM + storage)
                    ack = send_event_to_orchestrator(event)
                
                if ack and ack.accepted:
                    st.session_state.last_event_id = event_id
                    st.session_state.last_response_id = ack.response_id
                    
                    # Store response text (use heuristic action if raw text is empty but heuristic matched)
                    if ack.response_text:
                        st.session_state.last_response_text = ack.response_text
                    elif ack.matched_heuristic_id:
                        # Fetch heuristic details to show the action message
                        try:
                            # We don't have a direct 'GetHeuristic' RPC in the proto imported, 
                            # but we can query the DB directly since this is a dashboard.
                            # Querying DB is faster and we already have db functions.
                            # But we need to use the docker DB connection.
                            h_query = "SELECT action FROM heuristics WHERE id = %s"
                            h_df = fetch_data(h_query, (ack.matched_heuristic_id,))
                            
                            if not h_df.empty:
                                action_json = h_df.iloc[0, 0]
                                # Check if it's a dict (jsonb) or string
                                if isinstance(action_json, str):
                                    try:
                                        action = json.loads(action_json)
                                    except:
                                        action = {"raw": action_json}
                                else:
                                    action = action_json
                                
                                # Extract message
                                msg = action.get("message") or action.get("text") or action.get("response")
                                if msg:
                                    st.session_state.last_response_text = f"{msg} (via Heuristic)"
                                else:
                                    st.session_state.last_response_text = f"Action: {json.dumps(action)}"
                            else:
                                st.session_state.last_response_text = f"⚡ Heuristic {ack.matched_heuristic_id[:8]} (Details not found)"
                        except Exception as ex:
                            st.session_state.last_response_text = f"⚡ Heuristic {ack.matched_heuristic_id[:8]}"
                    elif force_salience == "Force LOW (Accumulated)":
                        st.session_state.last_response_text = "(Waiting in Accumulator...)"
                    else:
                        st.session_state.last_response_text = "(No immediate response)"

                    st.session_state.last_pred_success = ack.predicted_success
                    st.session_state.last_pred_conf = ack.prediction_confidence
                    st.session_state.last_routing_info = {
                        "heuristic_id": ack.matched_heuristic_id,
                        "llm_routed": ack.routed_to_llm,
                        "routing_path": ack.routing_path if hasattr(ack, 'routing_path') else 0
                    }
                    
                    # INJECT into history so it appears in the stream immediately
                    # Only if it's NOT an accumulated event (those come via stream later)
                    if force_salience != "Force LOW (Accumulated)":
                        # Create a pseudo-response object matching the structure expected by render_response_history
                        class PseudoResp:
                            def __init__(self, ack, eid):
                                self.event_id = eid
                                self.response_id = ack.response_id
                                self.response_text = ack.response_text or f"⚡ Heuristic {ack.matched_heuristic_id[:8]}"
                                self.predicted_success = ack.predicted_success
                                self.prediction_confidence = ack.prediction_confidence
                                self.routing_path = 1 if ack.matched_heuristic_id else (1 if ack.routed_to_llm else 0) # Assume IMMEDIATE/Fast if we got an ack
                                self.matched_heuristic_id = ack.matched_heuristic_id
                                self.event_timestamp_ms = int(time.time() * 1000)
                                self.response_timestamp_ms = int(time.time() * 1000)
                        
                        st.session_state.response_history.insert(0, PseudoResp(ack, event_id))
                        if len(st.session_state.response_history) > 50:
                            st.session_state.response_history.pop()
                        
                else:
                    st.error(f"Event rejected: {ack.error_message if ack else 'No response from Orchestrator'}")
            except Exception as e:
                st.error(f"Failed to process event: {e}")

    # Persistent Results Area
    if "last_response_text" in st.session_state:
        st.markdown("### Latest Request Result")
        
        # 1. Routing Info
        info = st.session_state.get("last_routing_info", {})
        if info.get("heuristic_id"):
            st.info(f"⚡ **Fast Path (Heuristic Match)**\n\nID: `{info['heuristic_id']}`")
        elif info.get("llm_routed"):
            st.info("🧠 **Slow Path (LLM Reasoning)**")
        elif force_salience == "Force LOW (Accumulated)":
            st.warning("⏳ **Accumulated Path**\n\nEvent is waiting in moment buffer. Use 'Flush Accumulator' to process.")
        
        # 2. Response & Feedback
        c1, c2 = st.columns([2, 1])
        
        with c1:
            st.success(f"**GLADyS Says:**\n\n{st.session_state.last_response_text}")
            if "last_response_id" in st.session_state and st.session_state.last_response_id:
                st.caption(f"Response ID: {st.session_state.last_response_id}")
        
        with c2:
            st.write("**Feedback**")
            f1, f2 = st.columns(2)
            # Enable feedback only if we have a response
            feedback_disabled = not st.session_state.get("last_response_id")
            if f1.button("👍 Good", use_container_width=True, disabled=feedback_disabled):
                send_feedback(st.session_state.last_event_id, st.session_state.last_response_id, True)
            if f2.button("👎 Bad", use_container_width=True, disabled=feedback_disabled):
                send_feedback(st.session_state.last_event_id, st.session_state.last_response_id, False)
            
            # Show prediction if available
            pred_val = st.session_state.get("last_pred_success", 0)
            if pred_val and not pd.isna(pred_val) and 0 <= pred_val <= 1:
                st.progress(pred_val, text=f"Pred. Success: {pred_val:.2f}")

def send_feedback(event_id, response_id, positive):
    try:
        exec_stub = get_executive_stub()
        req = executive_pb2.ProvideFeedbackRequest(
            event_id=event_id,
            response_id=response_id,
            positive=positive
        )
        resp = exec_stub.ProvideFeedback(req)
        if resp.accepted:
            st.toast(f"Feedback recorded! {'Heuristic created.' if resp.created_heuristic_id else ''}", icon="✅")
            if resp.created_heuristic_id:
                st.session_state.last_created_h = resp.created_heuristic_id
        else:
            st.error(f"Feedback failed: {resp.error_message}")
    except Exception as e:
        st.error(f"gRPC Error: {e}")

def render_memory_console():
    st.header("🧠 Memory Console")
    
    tab_query, tab_inject = st.tabs(["Similarity Probe", "Manual Inject"])
    
    with tab_query:
        st.subheader("Test Retrieval")
        query_text = st.text_input("Query Text", placeholder="Type something to see what GLADyS remembers...")
        if st.button("🔍 Probe Memory"):
            try:
                mem_stub = get_memory_stub()
                req = memory_pb2.QueryMatchingHeuristicsRequest(
                    event_text=query_text,
                    min_confidence=0.0,
                    limit=5
                )
                resp = mem_stub.QueryMatchingHeuristics(req)
                if resp.matches:
                    for m in resp.matches:
                        st.write(f"**Match (Score: {m.score:.2f})**: {m.heuristic.name}")
                        st.json(m.heuristic.effects_json)
                else:
                    st.info("No matches found.")
            except Exception as e:
                st.error(f"Search failed: {e}")

    with tab_inject:
        st.subheader("Create Heuristic")
        with st.form("manual_h"):
            name = st.text_input("Name", value="Manual: ")
            cond = st.text_input("Condition Text")
            action = st.text_area("Action (JSON)", value='{"type": "suggestion", "message": ""}')
            conf = st.slider("Initial Confidence", 0.0, 1.0, 0.8)
            source = st.selectbox("Origin", ["user", "built_in", "learned"])
            
            if st.form_submit_button("📥 Store in Memory"):
                try:
                    mem_stub = get_memory_stub()
                    h = memory_pb2.Heuristic(
                        id=str(uuid.uuid4()),
                        name=name,
                        condition_text=cond,
                        effects_json=action,
                        confidence=conf,
                        origin=source,
                        created_at_ms=int(time.time() * 1000)
                    )
                    resp = mem_stub.StoreHeuristic(memory_pb2.StoreHeuristicRequest(
                        heuristic=h,
                        generate_embedding=True
                    ))
                    if resp.success:
                        st.success(f"Heuristic stored: {resp.heuristic_id}")
                    else:
                        st.error(f"Failed: {resp.error}")
                except Exception as e:
                    st.error(f"gRPC Error: {e}")

def render_response_history():
    st.subheader("🛰️ Live Response Stream")
    
    if process_queue():
        # Small hack to trigger UI refresh when background items arrive if auto-refresh is off
        pass

    if not st.session_state.response_history:
        st.info("Waiting for responses...")
        return

    # Prepare data for display
    history_data = []
    for resp in st.session_state.response_history:
        latency = resp.response_timestamp_ms - resp.event_timestamp_ms if resp.event_timestamp_ms > 0 else 0
        
        path_str = "Unknown"
        if resp.routing_path == 1: path_str = "IMMEDIATE"
        elif resp.routing_path == 2: path_str = "ACCUMULATED"
        
        history_data.append({
            "Time": datetime.fromtimestamp(resp.response_timestamp_ms / 1000).strftime("%H:%M:%S"),
            "Event ID": resp.event_id[:8],
            "Path": path_str,
            "Heuristic": resp.matched_heuristic_id[:8] if resp.matched_heuristic_id else "-",
            "Response": resp.response_text,
            "Latency": f"{latency}ms"
        })
    
    st.table(history_data)

def render_recent_events(time_filter_clause, params):
    st.subheader("Recent System Activity")

    query = f"""
        SELECT
            id,
            timestamp,
            source,
            raw_text,
            salience,
            predicted_success,
            prediction_confidence,
            response_id
        FROM episodic_events
        WHERE archived = false {time_filter_clause}
        ORDER BY timestamp DESC
        LIMIT 20
    """
    df = fetch_data(query, params)

    if df.empty:
        st.info("No events found in database.")
        return

    # Initialize expanded rows state
    if "expanded_events" not in st.session_state:
        st.session_state.expanded_events = set()

    # Column header row
    h0, h1, h2, h3, h4 = st.columns([0.5, 1.2, 1.5, 5.5, 0.8])
    h0.caption("")
    h1.caption("**Time**")
    h2.caption("**Source**")
    h3.caption("**Event**")
    h4.caption("**Path**")

    # Render each row with expandable details
    for idx, row in df.iterrows():
        event_id = str(row['id'])
        is_expanded = event_id in st.session_state.expanded_events

        # Format display values
        time_str = row['timestamp'].strftime("%H:%M:%S") if hasattr(row['timestamp'], 'strftime') else str(row['timestamp'])[:8]
        preview = row['raw_text'][:70] + "..." if len(row['raw_text']) > 70 else row['raw_text']
        path_icon = "🧠" if row['response_id'] else "⚡"
        source_str = (row['source'][:10] if row['source'] else "-")
        toggle_label = "➖" if is_expanded else "➕"

        # Main row with columns
        c0, c1, c2, c3, c4 = st.columns([0.5, 1.2, 1.5, 5.5, 0.8])
        if c0.button(toggle_label, key=f"toggle_{event_id}", help="Expand/collapse"):
            if is_expanded:
                st.session_state.expanded_events.discard(event_id)
            else:
                st.session_state.expanded_events.add(event_id)
            st.rerun()

        c1.write(time_str)
        c2.write(source_str)
        c3.write(preview)
        c4.write(path_icon)

        # Expanded detail row (columnar layout with subtle background)
        if is_expanded:
            # Parse salience
            sal = row['salience']
            if isinstance(sal, str):
                try:
                    sal = json.loads(sal)
                except:
                    sal = {}

            # Build metadata values
            threat_val = f"{sal.get('threat', 0):.2f}" if sal else "-"
            opp_val = f"{sal.get('opportunity', 0):.2f}" if sal else "-"
            nov_val = f"{sal.get('novelty', 0):.2f}" if sal else "-"

            pred_val = row['predicted_success']
            pred_str = f"{pred_val:.2f}" if pred_val is not None and not pd.isna(pred_val) and 0 <= pred_val <= 1 else "-"

            path_str = f"LLM: {row['response_id'][:8]}" if row['response_id'] else "Heuristic"

            # Escape HTML in raw_text
            raw_escaped = row['raw_text'].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br/>")

            # Render as styled HTML table with dark background for contrast
            st.markdown(f"""
            <div style="background: #262730; padding: 8px 12px; margin: 4px 0 8px 0; border-radius: 4px; border-left: 3px solid #4a90d9;">
                <div style="margin-bottom: 8px; font-family: monospace; white-space: pre-wrap; color: #fafafa;">{raw_escaped}</div>
                <table style="width: 100%; font-size: 0.9em; color: #fafafa;">
                    <tr style="color: #a0a0a0; font-weight: bold;">
                        <td>Event ID</td>
                        <td>Threat</td>
                        <td>Opportunity</td>
                        <td>Novelty</td>
                        <td>Pred. Success</td>
                        <td>Response Path</td>
                    </tr>
                    <tr>
                        <td><code style="color: #79c0ff;">{event_id[:8]}</code></td>
                        <td>{threat_val}</td>
                        <td>{opp_val}</td>
                        <td>{nov_val}</td>
                        <td>{pred_str}</td>
                        <td>{path_str}</td>
                    </tr>
                </table>
            </div>
            """, unsafe_allow_html=True)

        # Row separator
        st.divider()


def render_heuristics():
    st.subheader("Learned Knowledge Base (Heuristics)")

    query = """
        SELECT
            id,
            name,
            condition,
            confidence,
            fire_count,
            success_count,
            origin,
            frozen
        FROM heuristics
        ORDER BY confidence DESC
    """
    df = fetch_data(query)

    if df.empty:
        st.info("No heuristics learned yet.")
        return

    # Helper to stringify JSON for display
    def format_cond(val):
        if isinstance(val, dict):
            return json.dumps(val)
        return str(val)

    df['condition'] = df['condition'].apply(format_cond)

    # Show dataframe with multi-row selection for bulk operations
    event = st.dataframe(
        df,
        column_config={
            "id": None,  # Hide ID column
            "name": "Rule Name",
            "condition": st.column_config.TextColumn("Condition Pattern", width="large"),
            "confidence": st.column_config.ProgressColumn("Confidence", min_value=0, max_value=1, format="%.2f"),
            "fire_count": "Fired",
            "success_count": "Succeeded",
            "origin": "Origin",
            "frozen": "Frozen"
        },
        use_container_width=True,
        hide_index=True,
        selection_mode="multi-row",
        on_select="rerun",
        key="heuristics_table"
    )

    # Handle selection and delete (supports multi-select)
    if event and event.selection and event.selection.rows:
        selected_indices = event.selection.rows
        selected_rows = df.iloc[selected_indices]
        selected_count = len(selected_indices)

        col1, col2 = st.columns([3, 1])
        with col1:
            if selected_count == 1:
                st.info(f"Selected: **{selected_rows.iloc[0]['name']}**")
            else:
                names = ", ".join(selected_rows['name'].head(3).tolist())
                if selected_count > 3:
                    names += f" (+{selected_count - 3} more)"
                st.info(f"Selected {selected_count} heuristics: **{names}**")
        with col2:
            btn_label = f"🗑️ Delete ({selected_count})" if selected_count > 1 else "🗑️ Delete"
            if st.button(btn_label, type="secondary", use_container_width=True):
                try:
                    conf = get_current_config()
                    conn = get_db_connection(DB_HOST, conf["DB_PORT"], DB_NAME, DB_USER, DB_PASS)
                    if conn:
                        cur = conn.cursor()
                        ids_to_delete = [str(row['id']) for _, row in selected_rows.iterrows()]
                        cur.execute(
                            "DELETE FROM heuristics WHERE id = ANY(%s::uuid[])",
                            (ids_to_delete,)
                        )
                        conn.commit()
                        cur.close()
                        if selected_count == 1:
                            st.success(f"Deleted: {selected_rows.iloc[0]['name']}")
                        else:
                            st.success(f"Deleted {selected_count} heuristics")
                        st.rerun()
                    else:
                        st.error("Failed to connect to database")
                except Exception as e:
                    st.error(f"Delete failed: {e}")

# --- Cache Inspector ---

def render_cache_tab():
    st.header("Cache Inspector")
    st.caption("View and manage the Rust salience gateway LRU cache.")

    try:
        stub = get_salience_stub()

        # Get cache stats
        stats_resp = stub.GetCacheStats(memory_pb2.GetCacheStatsRequest(), timeout=5)

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Cache Size", f"{stats_resp.current_size} / {stats_resp.max_capacity}")
        col2.metric("Hit Rate", f"{stats_resp.hit_rate:.1%}")
        col3.metric("Total Hits", stats_resp.total_hits)
        col4.metric("Total Misses", stats_resp.total_misses)

        st.markdown("---")

        # Flush button
        if st.button("Flush Cache", type="secondary"):
            try:
                stub.FlushCache(memory_pb2.FlushCacheRequest(), timeout=5)
                st.success("Cache flushed!")
                st.rerun()
            except Exception as e:
                st.error(f"Flush failed: {e}")

        st.markdown("---")

        # List cached heuristics
        st.subheader("Cached Heuristics")
        list_resp = stub.ListCachedHeuristics(memory_pb2.ListCachedHeuristicsRequest(), timeout=5)

        if list_resp.heuristics:
            import time
            now = int(time.time())
            cache_data = []
            for h in list_resp.heuristics:
                last_hit_ago = f"{now - h.last_hit_unix}s ago" if h.last_hit_unix > 0 else "-"
                cache_data.append({
                    "ID": h.heuristic_id[:8] if h.heuristic_id else "-",
                    "Name": h.name or "-",
                    "Hits": h.hit_count,
                    "Last Hit": last_hit_ago,
                })
            st.dataframe(cache_data, use_container_width=True, hide_index=True)
        else:
            st.info("Cache is empty.")

    except Exception as e:
        st.error(f"Failed to connect to SalienceGateway: {e}")
        st.caption("Make sure the Rust service (memory-rust) is running.")


# --- Flight Recorder ---

def render_flight_recorder():
    st.header("Flight Recorder")
    st.caption("Track heuristic fires and their outcomes for learning loop debugging.")

    # Filter
    outcome_filter = st.selectbox(
        "Filter by outcome",
        ["All", "Pending", "Success", "Failure"],
        index=0
    )

    # Build query
    where_clause = ""
    if outcome_filter == "Pending":
        where_clause = "WHERE hf.outcome IS NULL"
    elif outcome_filter == "Success":
        where_clause = "WHERE hf.outcome = 'success'"
    elif outcome_filter == "Failure":
        where_clause = "WHERE hf.outcome = 'failure'"

    query = f"""
        SELECT
            hf.fired_at,
            h.name as heuristic_name,
            hf.event_id,
            hf.outcome,
            hf.feedback_source,
            hf.heuristic_id
        FROM heuristic_fires hf
        LEFT JOIN heuristics h ON hf.heuristic_id = h.id
        {where_clause}
        ORDER BY hf.fired_at DESC
        LIMIT 25
    """

    df = fetch_data(query)

    if df.empty:
        st.info("No heuristic fires recorded yet.")
        return

    st.dataframe(
        df,
        column_config={
            "fired_at": st.column_config.DatetimeColumn("Time", format="HH:mm:ss"),
            "heuristic_name": "Heuristic",
            "event_id": st.column_config.TextColumn("Event ID", width="medium"),
            "outcome": "Outcome",
            "feedback_source": "Feedback Source",
            "heuristic_id": None,  # Hide
        },
        use_container_width=True,
        hide_index=True
    )


# --- Main App ---

def main():
    time_range = render_sidebar()
    
    # Time filter logic
    if time_range == "Last Hour":
        time_filter = "AND timestamp > NOW() - INTERVAL '1 hour'"
        params = ()
    elif time_range == "Last 24 Hours":
        time_filter = "AND timestamp > NOW() - INTERVAL '24 hours'"
        params = ()
    else:
        time_filter = ""
        params = ()

    st.title("🧠 GLADyS Lab Bench")
    render_stats_summary(time_filter, params)
    st.markdown("---")

    tab_lab, tab_memory, tab_events, tab_cache, tab_recorder, tab_settings = st.tabs([
        "🔬 Laboratory",
        "🧠 Memory",
        "📜 Event Log",
        "💾 Cache",
        "🎯 Flight Recorder",
        "⚙️ Settings"
    ])

    with tab_lab:
        render_event_simulator()
        st.markdown("---")
        render_response_history()
        st.markdown("---")
        render_heuristics()

    with tab_memory:
        render_memory_console()

    with tab_events:
        render_recent_events(time_filter, params)

    with tab_cache:
        render_cache_tab()

    with tab_recorder:
        render_flight_recorder()

    with tab_settings:
        render_settings_tab()

if __name__ == "__main__":
    main()

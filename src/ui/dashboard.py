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
except ImportError:
    st.error("Proto stubs not found. Run 'python scripts/proto_sync.py' first.")

# Service Connection Config
ENV_CONFIGS = {
    "Docker": {
        "MEMORY_ADDR": "localhost:50061",
        "EXECUTIVE_ADDR": "localhost:50063",
        "ORCHESTRATOR_ADDR": "localhost:50060",
        "DB_PORT": "5433"
    },
    "Local": {
        "MEMORY_ADDR": "localhost:50051",
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

# --- gRPC Clients ---

def get_current_config():
    return ENV_CONFIGS[st.session_state.env_mode]

def get_executive_stub():
    conf = get_current_config()
    channel = grpc.insecure_channel(conf["EXECUTIVE_ADDR"])
    return executive_pb2_grpc.ExecutiveServiceStub(channel)

def get_memory_stub():
    conf = get_current_config()
    channel = grpc.insecure_channel(conf["MEMORY_ADDR"])
    return memory_pb2_grpc.MemoryStorageStub(channel)

def get_orchestrator_stub():
    conf = get_current_config()
    channel = grpc.insecure_channel(conf["ORCHESTRATOR_ADDR"])
    return orchestrator_pb2_grpc.OrchestratorServiceStub(channel)

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

def response_subscriber_thread(q, orchestrator_addr):
    """Background thread to subscribe to responses."""
    try:
        # Create a dedicated channel for the thread
        channel = grpc.insecure_channel(orchestrator_addr)
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
    st.sidebar.title("GLADyS Control")
    
    # Environment Switcher
    st.sidebar.subheader("Environment")
    env_mode = st.sidebar.radio(
        "Mode", 
        ["Docker", "Local"], 
        index=0 if st.session_state.env_mode == "Docker" else 1,
        horizontal=True
    )
    
    # If mode changed, update state and clear cache
    if env_mode != st.session_state.env_mode:
        st.session_state.env_mode = env_mode
        st.cache_resource.clear()
        st.rerun()

    current_conf = get_current_config()
    st.sidebar.caption(f"Orchestrator: {current_conf['ORCHESTRATOR_ADDR']}")
    st.sidebar.caption(f"DB Port: {current_conf['DB_PORT']}")

    if st.sidebar.button("🔄 Refresh Dashboard"):
        st.cache_data.clear()
        st.rerun()
    
    auto_refresh = st.sidebar.toggle("Auto-refresh (2s)", value=False)
    if auto_refresh:
        time.sleep(2)
        st.rerun()

    st.sidebar.markdown("---")
    st.sidebar.subheader("Filters")
    time_range = st.sidebar.selectbox(
        "Time Range",
        ["Last Hour", "Last 24 Hours", "All Time"],
        index=2 # Default to All Time to avoid timezone confusion
    )
    
    st.sidebar.markdown("---")
    st.sidebar.subheader("Testing Tools")
    if st.sidebar.button("🗑️ Clear Local History"):
        st.session_state.response_history = []
        st.rerun()
        
    if st.sidebar.button("🚽 Flush Accumulator"):
        try:
            orch_stub = get_orchestrator_stub()
            resp = orch_stub.FlushMoment(orchestrator_pb2.FlushMomentRequest(reason="Manual flush from UI"))
            if resp.moment_sent:
                st.sidebar.success(f"Flushed {resp.events_flushed} events")
            else:
                st.sidebar.info("Accumulator empty")
        except Exception as e:
            st.sidebar.error(f"Flush failed: {e}")

    st.sidebar.markdown("---")
    st.sidebar.subheader("Connection Status")
    
    # Simple connection probes
    try:
        conn = get_db_connection(
            DB_HOST, 
            current_conf["DB_PORT"], 
            DB_NAME, 
            DB_USER, 
            DB_PASS
        )
        if conn:
            st.sidebar.success(f"DB: Connected ({current_conf['DB_PORT']})")
    except:
        st.sidebar.error("DB: Disconnected")
        
    return time_range

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
            if st.session_state.get("last_pred_success", 0) > 0:
                st.progress(st.session_state.last_pred_success, text=f"Pred. Success: {st.session_state.last_pred_success:.2f}")

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
    st.subheader("Recent System Activity (DB)")
    
    query = f"""
        SELECT 
            timestamp, 
            source, 
            raw_text, 
            predicted_success, 
            prediction_confidence, 
            response_id
        FROM episodic_events 
        WHERE archived = false {time_filter_clause}
        ORDER BY timestamp DESC 
        LIMIT 10
    """
    df = fetch_data(query, params)
    
    if df.empty:
        st.info("No events found in database.")
        return

    # Formatting
    st.dataframe(
        df,
        column_config={
            "timestamp": st.column_config.DatetimeColumn("Time", format="HH:mm:ss"),
            "source": "Source",
            "raw_text": st.column_config.TextColumn("Event", width="medium"),
            "predicted_success": st.column_config.ProgressColumn("Pred. Success", min_value=0, max_value=1, format="%.2f"),
            "prediction_confidence": st.column_config.NumberColumn("Pred. Conf", format="%.2f"),
            "response_id": "LLM ID"
        },
        use_container_width=True,
        hide_index=True
    )

def render_heuristics():
    st.subheader("Learned Knowledge Base (Heuristics)")
    
    query = """
        SELECT 
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
    # Check if condition is dict or string
    def format_cond(val):
        if isinstance(val, dict):
            return json.dumps(val)
        return str(val)

    df['condition'] = df['condition'].apply(format_cond)

    # Style confidence
    def highlight_confidence(val):
        color = 'red' if val < 0.3 else 'orange' if val < 0.7 else 'green'
        return f'color: {color}; font-weight: bold'

    st.dataframe(
        df.style.map(highlight_confidence, subset=['confidence']),
        column_config={
            "name": "Rule Name",
            "condition": "Condition Pattern",
            "confidence": st.column_config.ProgressColumn("Confidence", min_value=0, max_value=1, format="%.2f"),
            "fire_count": "Fired",
            "success_count": "Succeeded",
            "origin": "Origin",
            "frozen": "Frozen"
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

    tab_lab, tab_events = st.tabs(["🔬 Laboratory", "📜 Event Log"])
    
    with tab_lab:
        col_l, col_r = st.columns([2, 1])
        with col_l:
            render_event_simulator()
            st.markdown("---")
            render_response_history()
        with col_r:
            render_memory_console()
            
    with tab_events:
        render_recent_events(time_filter, params)
    
    st.markdown("---")
    render_heuristics()

if __name__ == "__main__":
    main()

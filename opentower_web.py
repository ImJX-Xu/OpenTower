import streamlit as st
import os
import sys
from pathlib import Path
import json

# Add runtime directory to sys.path
repo_root = Path(__file__).resolve().parent
sys.path.append(str(repo_root / "runtime"))

from opentower_cli.runtime_service import load_runtime_bundle, dispatch_and_maybe_execute
from opentower_cli.workflow_executor import resolve_confirmation

st.set_page_config(page_title="OpenTower Linux Ops", page_icon="🏗️", layout="wide")

st.title("🏗️ OpenTower Linux Ops - Web Terminal")
st.markdown("---")

# Sidebar for configuration
with st.sidebar:
    st.header("Settings")
    auth_path = repo_root / "auth.json"
    if auth_path.exists():
        st.success("✅ auth.json found")
        with open(auth_path, "r") as f:
            auth_data = json.load(f)
            st.code(json.dumps(auth_data, indent=2), language="json")
    else:
        st.warning("⚠️ auth.json missing")

    st.markdown("---")
    st.markdown("### Supported Commands")
    st.info("- 查看磁盘使用情况\n- 搜索包含 'database' 的文件\n- 检查 80 端口占用\n- 创建用户 dev01")

# Main interface
objective = st.text_input("Enter your request in natural language:", placeholder="e.g., 查看磁盘使用情况")

if st.button("Execute", type="primary"):
    if not objective:
        st.error("Please enter an objective.")
    else:
        with st.status("Executing Multi-Agent Workflow...") as status:
            progress_container = st.empty()
            
            def progress_callback(event):
                event_name = event.get("event")
                if event_name == "turn_started":
                    agent = event.get("agent_id")
                    idx = event.get("turn_index")
                    total = event.get("turn_count")
                    progress_container.markdown(f"**[{idx}/{total}]** Working with agent: `{agent}`...")
                elif event_name == "workflow_completed":
                    status.update(label="Workflow Completed!", state="complete", expanded=False)

            try:
                bundle = dispatch_and_maybe_execute(
                    root=repo_root,
                    objective=objective,
                    execute=True,
                    progress_callback=progress_callback
                )
                
                exec_res = bundle.execution_result
                if exec_res:
                    if exec_res.status == "pending_confirmation":
                        st.warning("⚠️ High Risk Operation Detected! Confirmation Required.")
                        st.markdown(f"**Confirmation ID:** `{exec_res.confirmation_id}`")
                        st.markdown(exec_res.final_output)
                        
                        # Confirmation buttons
                        col1, col2 = st.columns(2)
                        with col1:
                            if st.button("Approve (Yes)"):
                                res = resolve_confirmation(repo_root, exec_res.confirmation_id, "yes", "User approved via Web UI")
                                st.success("Operation Executed!")
                                st.markdown(res.final_output)
                        with col2:
                            if st.button("Reject (No)"):
                                res = resolve_confirmation(repo_root, exec_res.confirmation_id, "no")
                                st.info("Operation Cancelled.")
                                st.markdown(res.final_output)
                    else:
                        st.success("✅ Execution Finished")
                        st.markdown("### Final Output")
                        st.markdown(exec_res.final_output)
                        
                        with st.expander("View Logs"):
                            st.json(bundle.dispatch_result.__dict__)
                            
            except Exception as e:
                st.error(f"Error: {str(e)}")

st.markdown("---")
st.caption("OpenTower Linux Ops - AI Hackathon 2026")

import json
import sys
from pathlib import Path

import streamlit as st

# Add runtime directory to sys.path
repo_root = Path(__file__).resolve().parent
sys.path.append(str(repo_root / "runtime"))

from opentower_cli.runtime_service import dispatch_and_maybe_execute
from opentower_cli.workflow_executor import resolve_confirmation


st.set_page_config(page_title="OpenTower Linux Ops", layout="wide")

st.title("OpenTower Linux Ops Web Terminal")
st.markdown("---")

# Sidebar for configuration
with st.sidebar:
    st.header("Settings")
    auth_path = repo_root / "auth.json"
    if auth_path.exists():
        st.success("auth.json found")
        with open(auth_path, "r") as f:
            auth_data = json.load(f)
            st.code(json.dumps(auth_data, indent=2), language="json")
    else:
        st.warning("auth.json missing")

    st.markdown("---")
    st.markdown("### Example Requests")
    st.info(
        "- show disk usage\n"
        "- find nginx config files\n"
        "- check sshd service status\n"
        "- show cpu usage\n"
        "- tail the latest syslog log"
    )

# Main interface
objective = st.text_input("Enter a Linux ops request:", placeholder="e.g. show cpu usage")

if st.button("Execute", type="primary"):
    if not objective:
        st.error("Please enter an objective.")
    else:
        with st.status("Executing workflow...") as status:
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
                    progress_callback=progress_callback,
                )

                dispatch_res = bundle.dispatch_result
                exec_res = bundle.execution_result
                if dispatch_res.resolution_status != "supported":
                    status.update(label="Request Not Supported", state="complete", expanded=False)
                    st.warning("Request is outside the current implemented Linux ops scope.")
                    st.caption(f"resolution_source: {dispatch_res.resolution_source}")
                    if dispatch_res.resolution_reason:
                        st.caption(f"resolution_reason: {dispatch_res.resolution_reason}")
                    if dispatch_res.user_message:
                        st.markdown(dispatch_res.user_message)
                    with st.expander("View Logs"):
                        st.json(dispatch_res.__dict__)
                elif exec_res:
                    if exec_res.status == "pending_confirmation":
                        st.warning("High-risk operation detected. Confirmation required.")
                        st.markdown(f"**Confirmation ID:** `{exec_res.confirmation_id}`")
                        st.markdown(exec_res.final_output)

                        col1, col2 = st.columns(2)
                        with col1:
                            if st.button("Approve (Yes)"):
                                res = resolve_confirmation(repo_root, exec_res.confirmation_id, "yes", "User approved via Web UI")
                                st.success("Operation executed.")
                                st.markdown(res.final_output)
                        with col2:
                            if st.button("Reject (No)"):
                                res = resolve_confirmation(repo_root, exec_res.confirmation_id, "no")
                                st.info("Operation cancelled.")
                                st.markdown(res.final_output)
                    else:
                        st.success("Execution finished.")
                        st.markdown("### Final Output")
                        st.markdown(exec_res.final_output)
                        st.caption(f"resolution_source: {dispatch_res.resolution_source}")
                        if dispatch_res.resolution_reason:
                            st.caption(f"resolution_reason: {dispatch_res.resolution_reason}")

                        with st.expander("View Logs"):
                            st.json(dispatch_res.__dict__)
                else:
                    status.update(label="Request Finished", state="complete", expanded=False)
                    st.info("Request completed without execution output.")

            except Exception as e:
                status.update(label="Execution Failed", state="error", expanded=True)
                st.error(f"Error: {str(e)}")

st.markdown("---")
st.caption("OpenTower Linux Ops")

import streamlit as st
import requests
import json

# --- Configuration ---
API_URL = "http://localhost:8090"
st.set_page_config(layout="wide")


# --- Helper Functions ---
@st.cache_data(ttl=60)
def get_job_ids():
    """Fetches available job IDs from the backend."""
    try:
        response = requests.get(f"{API_URL}/jobs/")
        if response.status_code == 200:
            return response.json()
        st.sidebar.error("Could not fetch job list.")
        return []
    except requests.exceptions.ConnectionError:
        st.sidebar.error("Backend connection failed.")
        return []


@st.cache_data(ttl=60)
def get_jd_text(job_id):
    """Fetches the full text of a specific job description."""
    if not job_id:
        return None
    try:
        response = requests.get(f"{API_URL}/job/{job_id}")
        if response.status_code == 200:
            return response.json().get("jd_text")
        return None
    except requests.exceptions.ConnectionError:
        return None


# --- UI ---
st.title("🤖 Automated Resume Relevance Check System")
st.markdown(
    "An AI-powered tool to score resumes against job descriptions and provide actionable feedback."
)

menu = ["Manage Job Descriptions", "Analyze Resume", "View All Results"]
choice = st.sidebar.selectbox("Navigation", menu)

# --- Page 1: Manage Job Descriptions ---
if choice == "Manage Job Descriptions":
    st.header("Manage Job Descriptions (JDs)")

    tab1, tab2 = st.tabs(["➕ Create New JD", "✏️ View, Update & Delete JDs"])

    # Tab for creating a new JD
    with tab1:
        st.subheader("Upload a New Job Description")
        with st.form("jd_form"):
            job_id = st.text_input("Enter a Unique Job ID", help="e.g., 'SWE-001'")
            jd_file = st.file_uploader("Upload JD File", type=["pdf", "docx", "txt"])
            submitted = st.form_submit_button("Upload JD")

            if submitted:
                if job_id and jd_file:
                    with st.spinner("Processing JD..."):
                        files = {
                            "file": (jd_file.name, jd_file.getvalue(), jd_file.type)
                        }
                        data = {"job_id": job_id}
                        try:
                            response = requests.post(
                                f"{API_URL}/upload_jd/", files=files, data=data
                            )
                            if response.status_code == 200:
                                st.success(response.json().get("message"))
                                st.cache_data.clear()
                            else:
                                st.error(
                                    f"Error: {response.json().get('error', 'Unknown error')}"
                                )
                        except requests.exceptions.ConnectionError:
                            st.error(
                                "Connection Error: Could not connect to the backend."
                            )
                else:
                    st.warning("Please provide a Job ID and upload a file.")

    # Tab for managing existing JDs
    with tab2:
        st.subheader("Manage Existing Job Descriptions")
        all_jobs = get_job_ids()
        if not all_jobs:
            st.info(
                "No job descriptions have been uploaded yet. Go to the 'Create New JD' tab to add one."
            )
        else:
            selected_job_id = st.selectbox(
                "Select a Job ID to manage", options=[""] + all_jobs, index=0
            )

            if selected_job_id:
                current_jd_text = get_jd_text(selected_job_id)
                if current_jd_text:
                    with st.form("update_form"):
                        st.write(f"**Editing Job ID:** `{selected_job_id}`")
                        edited_text = st.text_area(
                            "Job Description Text", value=current_jd_text, height=400
                        )
                        update_button = st.form_submit_button(
                            "💾 Update Job Description"
                        )

                        if update_button:
                            with st.spinner("Updating JD..."):
                                try:
                                    payload = {"jd_text": edited_text}
                                    response = requests.put(
                                        f"{API_URL}/job/{selected_job_id}", json=payload
                                    )
                                    if response.status_code == 200:
                                        st.success(response.json().get("message"))
                                        st.cache_data.clear()
                                    else:
                                        st.error(
                                            f"Error: {response.json().get('error')}"
                                        )
                                except requests.exceptions.ConnectionError:
                                    st.error(
                                        "Connection Error: Could not connect to the backend."
                                    )

                    st.markdown("---")
                    st.error("🚨 Danger Zone")

                    if st.button(f"Delete Job ID: {selected_job_id}"):
                        st.session_state["confirm_delete"] = selected_job_id

                    if (
                        "confirm_delete" in st.session_state
                        and st.session_state["confirm_delete"] == selected_job_id
                    ):
                        st.warning(
                            f"**Are you absolutely sure you want to delete `{selected_job_id}`?** This will also delete all associated application results and cannot be undone."
                        )
                        col1, col2 = st.columns([1, 4])
                        with col1:
                            if st.button("✔️ Yes, I am sure, DELETE"):
                                with st.spinner("Deleting JD..."):
                                    try:
                                        response = requests.delete(
                                            f"{API_URL}/job/{selected_job_id}"
                                        )
                                        if response.status_code == 200:
                                            st.success(response.json().get("message"))
                                            st.cache_data.clear()
                                            st.session_state["confirm_delete"] = None
                                            st.rerun()
                                        else:
                                            st.error(
                                                f"Error: {response.json().get('error')}"
                                            )
                                    except requests.exceptions.ConnectionError:
                                        st.error("Connection Error.")
                        with col2:
                            if st.button("✖️ Cancel"):
                                st.session_state["confirm_delete"] = None
                                st.rerun()

# --- Page 2: Analyze Resume ---
elif choice == "Analyze Resume":
    st.header("Step 2: Upload and Analyze a Resume")
    available_jobs = get_job_ids()
    if not available_jobs:
        st.warning(
            "No jobs found. Please go to 'Manage Job Descriptions' to add a job."
        )
    else:
        job_id_to_apply = st.selectbox(
            "Select the Job to Apply For", options=available_jobs
        )
        if job_id_to_apply:
            with st.expander("Click to Preview Selected Job Description"):
                jd_text = get_jd_text(job_id_to_apply)
                if jd_text:
                    st.markdown(
                        f"<pre style='white-space: pre-wrap;...'>{jd_text}</pre>",
                        unsafe_allow_html=True,
                    )
                else:
                    st.warning("Could not load job description preview.")
        with st.form("resume_form"):
            student_id = st.text_input("Enter Student ID or Name")
            resume_file = st.file_uploader(
                "Upload Resume File", type=["pdf", "docx", "txt"]
            )
            submitted = st.form_submit_button("Analyze Resume")
            if submitted:
                if student_id and job_id_to_apply and resume_file:
                    with st.spinner("Analyzing resume..."):
                        files = {
                            "file": (
                                resume_file.name,
                                resume_file.getvalue(),
                                resume_file.type,
                            )
                        }
                        data = {"student_id": student_id, "job_id": job_id_to_apply}
                        try:
                            response = requests.post(
                                f"{API_URL}/upload_resume/", files=files, data=data
                            )
                            if response.status_code == 200:
                                res = response.json()
                                st.success("Analysis Complete!")
                                st.subheader(
                                    f"Analysis for {res.get('student_id')} against Job ID {res.get('job_id')}"
                                )
                                score, verdict = (
                                    res.get("score", 0),
                                    res.get("verdict", "N/A"),
                                )
                                color = (
                                    "green"
                                    if score >= 75
                                    else "orange"
                                    if score >= 50
                                    else "red"
                                )
                                st.metric(label="Relevance Score", value=f"{score}/100")
                                st.markdown(
                                    f"**Verdict:** <span style='color:{color};...'>{verdict}</span>",
                                    unsafe_allow_html=True,
                                )
                                st.info(
                                    f"**💡 AI Feedback:**\n\n{res.get('feedback', 'No feedback.')}"
                                )
                                missing = res.get("missing_skills", [])
                                if missing:
                                    st.warning(
                                        "**Areas for Improvement (Missing Skills):**"
                                    )
                                    st.markdown("- " + "\n- ".join(missing))
                            else:
                                st.error(
                                    f"Error: {response.json().get('error', 'Failed to process resume.')}"
                                )
                        except requests.exceptions.ConnectionError:
                            st.error(
                                "Connection Error: Could not connect to the backend."
                            )
                else:
                    st.warning("Please fill in all fields and upload a resume.")

# --- Page 3: View All Results ---
elif choice == "View All Results":
    st.header("View All Submission Results")
    job_id_filter = st.text_input("Filter by Job ID (Optional)")
    if st.button("Fetch Results"):
        with st.spinner("Fetching results..."):
            params = {"job_id": job_id_filter} if job_id_filter else {}
            try:
                response = requests.get(f"{API_URL}/results/", params=params)
                if response.status_code == 200:
                    data = response.json()
                    if data:
                        st.success(f"Found {len(data)} results.")
                        for result in data:
                            with st.expander(
                                f"**{result['student_id']}** applied for **{result['job_id']}** | Score: {result['score']}"
                            ):
                                st.markdown(f"**Verdict:** {result['verdict']}")
                                st.markdown(
                                    f"**Feedback:** {result.get('feedback', 'N/A')}"
                                )
                                missing_skills = result.get("missing_skills", [])
                                if missing_skills:
                                    st.markdown("**Missing Skills:**")
                                    st.markdown("- " + "\n- ".join(missing_skills))
                                else:
                                    st.markdown("**Missing Skills:** None identified.")
                                st.write(
                                    f"<small>Analyzed on: {result.get('timestamp')}</small>",
                                    unsafe_allow_html=True,
                                )
                    else:
                        st.info("No results found for the given criteria.")
                else:
                    st.error("Failed to fetch results from the server.")
            except requests.exceptions.ConnectionError:
                st.error("Connection Error: Could not connect to the backend.")

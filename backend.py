import os
import tempfile
import json
import sqlite3
import re
from flask import Flask, request, jsonify
from flask_cors import CORS
import docx2txt
import fitz  # PyMuPDF
import google.generativeai as genai
import logging
from werkzeug.datastructures import FileStorage

# --- Flask App Setup ---
app = Flask(__name__)
CORS(app)  # Enable CORS for all routes and origins
logging.basicConfig(level=logging.DEBUG)

# --- Database Setup ---
DATABASE = "resume_analyzer.db"


def get_db():
    """Opens a new database connection if there is none yet for the current application context."""
    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row  # This enables name-based access to columns
    return db


def init_db():
    """Initializes the database schema."""
    with app.app_context():
        db = get_db()
        db.cursor().executescript("""
        CREATE TABLE IF NOT EXISTS job_descriptions (
            job_id TEXT PRIMARY KEY,
            jd_text TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT NOT NULL,
            job_id TEXT NOT NULL,
            score INTEGER,
            verdict TEXT,
            missing_skills TEXT,
            feedback TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (job_id) REFERENCES job_descriptions (job_id)
        );
        """)
        db.commit()


@app.cli.command("init-db")
def init_db_command():
    """Command to initialize the database."""
    init_db()
    print("Initialized the database.")


# Initialize DB at startup
init_db()


# --- Text Extraction Functions ---
def extract_text_from_pdf(file_path):
    doc = fitz.open(file_path)
    text = ""
    for page in doc:
        text += page.get_text()
    return text


def extract_text_from_docx(file_path):
    return docx2txt.process(file_path)


def extract_text(file: FileStorage):
    suffix = os.path.splitext(file.filename)[1].lower()
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(file.read())
        tmp_path = tmp.name

    text = ""
    if suffix == ".pdf":
        text = extract_text_from_pdf(tmp_path)
    elif suffix == ".docx":
        text = extract_text_from_docx(tmp_path)
    else:
        with open(tmp_path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()

    os.unlink(tmp_path)
    return text.lower()


# --- Improved Gemini & Scoring Functions ---
def calculate_hard_match_score(jd_text, resume_text):
    keywords = [
        "python",
        "java",
        "c++",
        "sql",
        "javascript",
        "react",
        "angular",
        "vue",
        "machine learning",
        "data science",
        "artificial intelligence",
        "aws",
        "azure",
        "gcp",
        "docker",
        "kubernetes",
        "api",
        "git",
        "agile",
        "scrum",
    ]
    jd_words = set(re.findall(r"\b\w+\b", jd_text))
    resume_words = set(re.findall(r"\b\w+\b", resume_text))
    relevant_keywords = [k for k in keywords if k in jd_words]
    if not relevant_keywords:
        return 50
    matched_keywords = [k for k in relevant_keywords if k in resume_words]
    return (
        int((len(matched_keywords) / len(relevant_keywords)) * 100)
        if relevant_keywords
        else 0
    )


def analyze_with_gemini(jd_text, resume_text):
    app.logger.debug("FUNCTION CALLED: analyze_with_gemini")
    try:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY environment variable not set.")
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-1.5-flash")
        prompt = f"""
        As an expert technical recruiter, analyze the provided job description (JD) and resume.
        Provide your analysis in a structured JSON format.

        Job Description:\n---\n{jd_text}\n---\nResume:\n---\n{resume_text}\n---

        Based on the comparison, provide the following in a JSON object:
        1. "semantic_score": An integer relevance score from 0 to 100 based on contextual and semantic fit.
        2. "verdict": A verdict of "High", "Medium", or "Low".
        3. "missing_skills": A list of key skills, tools, or experiences mentioned in the JD that are missing from the resume.
        4. "feedback": A paragraph of constructive feedback for the candidate on how to improve their resume for this specific job.
    
        Your response MUST be a valid JSON object only.
        """
        response = model.generate_content(prompt)
        cleaned_response = (
            response.text.strip().replace("```json", "").replace("```", "").strip()
        )
        return json.loads(cleaned_response)
    except Exception as e:
        app.logger.error(f"An error occurred in Gemini analysis: {e}")
        return {
            "semantic_score": 0,
            "verdict": "Error",
            "missing_skills": [],
            "feedback": "Could not analyze the resume due to an API or parsing error.",
        }


# --- Flask Endpoints ---
@app.route("/upload_jd/", methods=["POST"])
def upload_jd():
    job_id = request.form.get("job_id")
    file = request.files.get("file")
    if not job_id or not file:
        return jsonify({"error": "Missing job_id or file"}), 400
    text = extract_text(file)
    db = get_db()
    try:
        db.execute(
            "INSERT OR REPLACE INTO job_descriptions (job_id, jd_text) VALUES (?, ?)",
            (job_id, text),
        )
        db.commit()
    except sqlite3.Error as e:
        db.rollback()
        return jsonify({"error": f"Database error: {e}"}), 500
    finally:
        db.close()
    return jsonify({"message": f"JD '{file.filename}' uploaded for job_id '{job_id}'"})


@app.route("/upload_resume/", methods=["POST"])
def upload_resume():
    student_id, job_id, file = (
        request.form.get("student_id"),
        request.form.get("job_id"),
        request.files.get("file"),
    )
    if not all([student_id, job_id, file]):
        return jsonify({"error": "Missing student_id, job_id, or file"}), 400
    db = get_db()
    jd_row = db.execute(
        "SELECT jd_text FROM job_descriptions WHERE job_id = ?", (job_id,)
    ).fetchone()
    if not jd_row:
        db.close()
        return jsonify({"error": "Job ID not found"}), 404

    jd_text, resume_text = jd_row["jd_text"], extract_text(file)
    hard_match_score = calculate_hard_match_score(jd_text, resume_text)
    gemini_analysis = analyze_with_gemini(jd_text, resume_text)
    semantic_score = gemini_analysis.get("semantic_score", 0)
    final_score = int((0.4 * hard_match_score) + (0.6 * semantic_score))

    result_data = {
        "student_id": student_id,
        "job_id": job_id,
        "score": final_score,
        "verdict": gemini_analysis.get("verdict"),
        "missing_skills": gemini_analysis.get("missing_skills", []),
        "feedback": gemini_analysis.get("feedback"),
    }

    try:
        missing_skills_str = json.dumps(result_data["missing_skills"])
        db.execute(
            "INSERT INTO results (student_id, job_id, score, verdict, missing_skills, feedback) VALUES (?, ?, ?, ?, ?, ?)",
            (
                student_id,
                job_id,
                final_score,
                result_data["verdict"],
                missing_skills_str,
                result_data["feedback"],
            ),
        )
        db.commit()
    except sqlite3.Error as e:
        db.rollback()
        app.logger.error(f"Database error on insert: {e}")
    finally:
        db.close()
    return jsonify(result_data)


@app.route("/jobs/", methods=["GET"])
def get_jobs():
    db = get_db()
    try:
        cursor = db.execute("SELECT job_id FROM job_descriptions ORDER BY job_id ASC")
        return jsonify([row["job_id"] for row in cursor.fetchall()])
    except sqlite3.Error as e:
        app.logger.error(f"Database error on fetching jobs: {e}")
        return jsonify({"error": f"Database error: {e}"}), 500
    finally:
        db.close()


@app.route("/job/<string:job_id>", methods=["GET"])
def get_job_details(job_id):
    db = get_db()
    try:
        jd_row = db.execute(
            "SELECT jd_text FROM job_descriptions WHERE job_id = ?", (job_id,)
        ).fetchone()
        if jd_row:
            return jsonify({"job_id": job_id, "jd_text": jd_row["jd_text"]})
        else:
            return jsonify({"error": "Job ID not found"}), 404
    except sqlite3.Error as e:
        app.logger.error(f"Database error on fetching job details: {e}")
        return jsonify({"error": f"Database error: {e}"}), 500
    finally:
        db.close()


@app.route("/job/<string:job_id>", methods=["PUT"])
def update_job(job_id):
    """Updates the text for an existing job description."""
    data = request.get_json()
    new_text = data.get("jd_text")
    if not new_text:
        return jsonify({"error": "Missing jd_text in request body"}), 400
    db = get_db()
    try:
        cursor = db.execute(
            "UPDATE job_descriptions SET jd_text = ? WHERE job_id = ?",
            (new_text.lower(), job_id),
        )
        if cursor.rowcount == 0:
            return jsonify({"error": "Job ID not found"}), 404
        db.commit()
        return jsonify({"message": f"Job ID '{job_id}' was successfully updated."})
    except sqlite3.Error as e:
        db.rollback()
        app.logger.error(f"Database error on updating job: {e}")
        return jsonify({"error": f"Database error: {e}"}), 500
    finally:
        db.close()


@app.route("/job/<string:job_id>", methods=["DELETE"])
def delete_job(job_id):
    """Deletes a job description and all associated results."""
    db = get_db()
    try:
        cursor = db.execute(
            "SELECT job_id FROM job_descriptions WHERE job_id = ?", (job_id,)
        )
        if cursor.fetchone() is None:
            return jsonify({"error": "Job ID not found"}), 404
        db.execute("DELETE FROM results WHERE job_id = ?", (job_id,))
        db.execute("DELETE FROM job_descriptions WHERE job_id = ?", (job_id,))
        db.commit()
        return jsonify(
            {
                "message": f"Job ID '{job_id}' and all associated results have been deleted."
            }
        )
    except sqlite3.Error as e:
        db.rollback()
        app.logger.error(f"Database error on deleting job: {e}")
        return jsonify({"error": f"Database error: {e}"}), 500
    finally:
        db.close()


@app.route("/results/", methods=["GET"])
def get_results():
    job_id = request.args.get("job_id")
    db = get_db()
    cursor = (
        db.execute(
            "SELECT * FROM results WHERE job_id = ? ORDER BY score DESC", (job_id,)
        )
        if job_id
        else db.execute("SELECT * FROM results ORDER BY timestamp DESC")
    )
    results = [dict(row) for row in cursor.fetchall()]
    db.close()
    for result in results:
        if result.get("missing_skills"):
            result["missing_skills"] = json.loads(result["missing_skills"])
    return jsonify(results)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8090, debug=True)

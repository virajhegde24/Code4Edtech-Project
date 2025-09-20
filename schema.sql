
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
        
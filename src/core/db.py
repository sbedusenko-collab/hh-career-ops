"""
SQLite хранилище для вакансий и результатов оценки.
"""

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from src.api.vacancies import Vacancy
from src.core.scorer import EvaluationResult


class VacancyDB:
    def __init__(self, db_path: str = "data/vacancies.db"):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.path = db_path
        self._init_schema()

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_schema(self):
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS vacancies (
                    id            TEXT PRIMARY KEY,
                    title         TEXT,
                    company       TEXT,
                    company_id    TEXT,
                    area          TEXT,
                    url           TEXT,
                    salary_from   INTEGER,
                    salary_to     INTEGER,
                    salary_cur    TEXT,
                    salary_gross  INTEGER,
                    employment    TEXT,
                    schedule      TEXT,
                    experience    TEXT,
                    published_at  TEXT,
                    description   TEXT,
                    key_skills    TEXT,   -- JSON array
                    has_test      INTEGER,
                    raw           TEXT,   -- JSON полные данные
                    saved_at      TEXT DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS evaluations (
                    vacancy_id          TEXT PRIMARY KEY REFERENCES vacancies(id),
                    total_score         REAL,
                    grade               TEXT,
                    summary             TEXT,
                    dealbreaker         INTEGER,
                    dealbreaker_reason  TEXT,
                    criteria            TEXT,  -- JSON
                    evaluated_at        TEXT DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS applications (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    vacancy_id      TEXT REFERENCES vacancies(id),
                    resume_id       TEXT,
                    message         TEXT,
                    applied_at      TEXT DEFAULT (datetime('now')),
                    status          TEXT DEFAULT 'sent'
                );

                CREATE INDEX IF NOT EXISTS idx_eval_score ON evaluations(total_score DESC);
                CREATE INDEX IF NOT EXISTS idx_eval_grade ON evaluations(grade);
            """)

    def exists(self, vacancy_id: str) -> bool:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT 1 FROM evaluations WHERE vacancy_id = ?", (vacancy_id,)
            ).fetchone()
            return row is not None

    def save(self, result: EvaluationResult, vacancy: Vacancy) -> None:
        with self._conn() as conn:
            salary = vacancy.salary
            conn.execute("""
                INSERT OR REPLACE INTO vacancies
                (id, title, company, company_id, area, url,
                 salary_from, salary_to, salary_cur, salary_gross,
                 employment, schedule, experience, published_at,
                 description, key_skills, has_test, raw)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                vacancy.id, vacancy.title, vacancy.company, vacancy.company_id,
                vacancy.area, vacancy.url,
                salary.from_ if salary else None,
                salary.to if salary else None,
                salary.currency if salary else None,
                int(salary.gross) if salary else None,
                vacancy.employment, vacancy.schedule, vacancy.experience,
                vacancy.published_at, vacancy.description,
                json.dumps(vacancy.key_skills, ensure_ascii=False),
                int(vacancy.has_test),
                json.dumps(vacancy.raw, ensure_ascii=False),
            ))

            conn.execute("""
                INSERT OR REPLACE INTO evaluations
                (vacancy_id, total_score, grade, summary,
                 dealbreaker, dealbreaker_reason, criteria)
                VALUES (?,?,?,?,?,?,?)
            """, (
                result.vacancy_id, result.total_score, result.grade,
                result.summary, int(result.dealbreaker_hit),
                result.dealbreaker_reason,
                json.dumps(
                    [{"name": c.name, "score": c.score, "grade": c.grade,
                      "reasoning": c.reasoning, "weight": c.weight}
                     for c in result.criteria],
                    ensure_ascii=False,
                ),
            ))

    def save_application(self, vacancy_id: str, resume_id: str, message: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO applications (vacancy_id, resume_id, message) VALUES (?,?,?)",
                (vacancy_id, resume_id, message),
            )

    def get_top(self, limit: int = 20, min_grade: str = "C") -> list[dict]:
        """Топ вакансий по оценке."""
        grade_order = {"A": 5, "B": 4, "C": 3, "D": 2, "F": 1}
        min_score = {5: 4.5, 4: 3.5, 3: 2.5, 2: 1.5, 1: 1.0}[grade_order.get(min_grade, 3)]

        with self._conn() as conn:
            rows = conn.execute("""
                SELECT v.id, v.title, v.company, v.area, v.url,
                       v.salary_from, v.salary_to, v.salary_cur, v.salary_gross,
                       v.schedule, v.published_at,
                       e.total_score, e.grade, e.summary, e.dealbreaker
                FROM vacancies v
                JOIN evaluations e ON v.id = e.vacancy_id
                WHERE e.total_score >= ? AND e.dealbreaker = 0
                ORDER BY e.total_score DESC
                LIMIT ?
            """, (min_score, limit)).fetchall()
            return [dict(r) for r in rows]

    def get_stats(self) -> dict:
        with self._conn() as conn:
            total = conn.execute("SELECT COUNT(*) FROM evaluations").fetchone()[0]
            by_grade = dict(conn.execute(
                "SELECT grade, COUNT(*) FROM evaluations GROUP BY grade"
            ).fetchall())
            applied = conn.execute("SELECT COUNT(*) FROM applications").fetchone()[0]
            return {"total": total, "by_grade": by_grade, "applied": applied}

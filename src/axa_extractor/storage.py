import os
import sqlite3
from typing import Dict, Any, Optional


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT,
    form_type TEXT,
    submission_date TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS fields (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER,
    name TEXT,
    value TEXT,
    confidence REAL,
    source TEXT,
    FOREIGN KEY(document_id) REFERENCES documents(id)
);
"""


class Storage:
    def __init__(self, db_path: str = "data/extractions.db") -> None:
        self.db_path = db_path
        self._persistent = False
        self._conn: Optional[sqlite3.Connection] = None

        dirname = os.path.dirname(db_path)
        if db_path == ":memory:":
            # Keep a persistent in-memory connection so schema persists across calls
            self._conn = sqlite3.connect(db_path)
            self._persistent = True
        elif db_path.startswith("file::memory:"):
            self._conn = sqlite3.connect(db_path, uri=True)
            self._persistent = True
        else:
            if dirname:
                os.makedirs(dirname, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        if self._conn is not None:
            return self._conn
        return sqlite3.connect(self.db_path)

    def _init_db(self) -> None:
        con = self._connect()
        con.executescript(SCHEMA_SQL)

    def save_extraction(self, filename: str, result: Dict[str, Any]) -> int:
        fields = result.get("fields", {})
        form_type = (fields.get("form_type", {}) or {}).get("value") if isinstance(fields.get("form_type"), dict) else None
        submission_date = (fields.get("submission_date", {}) or {}).get("value") if isinstance(fields.get("submission_date"), dict) else None
        con = self._connect()
        cur = con.cursor()
        cur.execute("INSERT INTO documents(filename, form_type, submission_date) VALUES(?,?,?)", (filename, form_type, submission_date))
        doc_id = cur.lastrowid
        for name, fv in fields.items():
            if isinstance(fv, dict):
                value = fv.get("value")
                confidence = float(fv.get("confidence", 0.0))
                source = fv.get("source", "text")
            else:
                value = None
                confidence = 0.0
                source = "text"
            cur.execute(
                "INSERT INTO fields(document_id, name, value, confidence, source) VALUES(?,?,?,?,?)",
                (doc_id, name, value, confidence, source),
            )
        con.commit()
        if not self._persistent:
            con.close()
        return int(doc_id)

    def get_document(self, document_id: int) -> Optional[Dict[str, Any]]:
        con = self._connect()
        cur = con.cursor()
        cur.execute("SELECT id, filename, form_type, submission_date, created_at FROM documents WHERE id=?", (document_id,))
        row = cur.fetchone()
        if not row:
            if not self._persistent:
                con.close()
            return None
        cur.execute("SELECT name, value, confidence, source FROM fields WHERE document_id=?", (document_id,))
        fields = cur.fetchall()
        result = {
            "id": row[0],
            "filename": row[1],
            "form_type": row[2],
            "submission_date": row[3],
            "created_at": row[4],
            "fields": [
                {"name": f[0], "value": f[1], "confidence": f[2], "source": f[3]} for f in fields
            ],
        }
        if not self._persistent:
            con.close()
        return result

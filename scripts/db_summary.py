import sqlite3
from pathlib import Path


def main(db_path: str = "data/extractions.db") -> None:
    con = sqlite3.connect(db_path)
    cur = con.cursor()
    q = (
        "SELECT d.id, d.filename, "
        "SUM(CASE WHEN f.value IS NOT NULL AND TRIM(f.value)<>'' THEN 1 ELSE 0 END) AS filled, "
        "COUNT(f.id) AS total "
        "FROM documents d LEFT JOIN fields f ON f.document_id = d.id "
        "GROUP BY d.id, d.filename ORDER BY d.id DESC LIMIT 20"
    )
    rows = list(cur.execute(q))
    for doc_id, fn, filled, total in rows:
        filled = filled or 0
        total = total or 0
        ratio = (filled / total) if total else 0.0
        print(f"doc_id={doc_id:>3} filled={filled:>2}/{total:<2} ratio={ratio:.2f}  filename={fn}")
    con.close()


if __name__ == "__main__":
    main()


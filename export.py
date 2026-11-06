import json
import os
import sqlite3


def export_to_json(db_path='perfumes.sqlite', json_path='perfumes.json'):
    # sqlite3.connect() silently creates an empty file when the path is wrong.
    if not os.path.exists(db_path):
        raise SystemExit(f"Missing {db_path}. Run perfumes_scraper.py first.")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM perfumes")
    rows = cursor.fetchall()
    col_names = [description[0] for description in cursor.description]
    conn.close()

    # Convert each row into a dictionary {column: value}
    data = [dict(zip(col_names, row)) for row in rows]

    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"✅ Exported {len(data)} perfumes to {json_path}")


if __name__ == "__main__":
    export_to_json()

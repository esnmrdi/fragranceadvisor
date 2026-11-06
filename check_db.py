import os
import sqlite3


def print_sample_rows(db_path='perfumes.sqlite', limit=10):
    # sqlite3.connect() silently creates an empty file when the path is wrong.
    if not os.path.exists(db_path):
        raise SystemExit(f"Missing {db_path}. Run perfumes_scraper.py first.")

    conn = sqlite3.connect(db_path)
    for row in conn.execute("SELECT * FROM perfumes LIMIT ?", (limit,)):
        print(row)
    conn.close()


if __name__ == "__main__":
    print_sample_rows()

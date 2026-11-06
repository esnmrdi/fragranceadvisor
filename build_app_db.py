# build_app_db.py
import json
import os
import sqlite3
from pathlib import Path

DB = "app.db"
DATA = "perfumes_clean.json"   # output of clean.py

def main():
    if not Path(DATA).exists():
        raise SystemExit(f"Missing {DATA}. Run clean.py first.")

    # Also clear SQLite sidecar files: a stale -wal/-shm from an older WAL-mode build could
    # otherwise be applied to the new database.
    for path in (DB, DB + "-wal", DB + "-shm"):
        if os.path.exists(path):
            os.remove(path)

    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    # One-shot build into a fresh file: a failed run is simply re-run from scratch, so skip the
    # journal. Deliberately not WAL: that mode is stored in the file header, and a WAL-mode
    # app.db can't be opened from read-only locations (bundled assets, read-only mounts).
    cur.executescript("""
    PRAGMA journal_mode=OFF;
    PRAGMA synchronous=OFF;
    PRAGMA temp_store=MEMORY;
    """)

    # Schema (no sillage)
    cur.executescript("""
    CREATE TABLE perfumes(
      id TEXT PRIMARY KEY,
      brand TEXT NOT NULL,
      name TEXT NOT NULL,
      image TEXT,                  -- optional image/filename/url
      year INTEGER,
      slug TEXT NOT NULL UNIQUE,
      popularity INTEGER DEFAULT 0
    );

    CREATE TABLE notes(
      perfume_id TEXT NOT NULL,
      kind TEXT CHECK(kind IN ('top','middle','base')) NOT NULL,
      note TEXT NOT NULL,
      PRIMARY KEY (perfume_id, kind, note),
      FOREIGN KEY (perfume_id) REFERENCES perfumes(id) ON DELETE CASCADE
    );

    CREATE TABLE accords(
      perfume_id TEXT NOT NULL,
      accord TEXT NOT NULL,
      rank INTEGER,                -- preserves order from JSON
      PRIMARY KEY (perfume_id, accord),
      FOREIGN KEY (perfume_id) REFERENCES perfumes(id) ON DELETE CASCADE
    );

    -- Full-text search across brand, name, and combined notes/accords
    CREATE VIRTUAL TABLE perfume_fts USING fts5(
      brand, name, notes,
      content='',
      tokenize='porter'
    );

    CREATE INDEX idx_perfumes_brand ON perfumes(brand);
    CREATE INDEX idx_perfumes_year  ON perfumes(year);
    CREATE INDEX idx_notes_note     ON notes(note);
    CREATE INDEX idx_accords_accord ON accords(accord);
    """)

    with open(DATA, encoding="utf-8") as f:
        data = json.load(f)

    perf_rows, note_rows, acc_rows, fts_rows = [], [], [], []
    for rowid, p in enumerate(data, start=1):
        image = p.get("image")
        # Explicit rowid: perfume_fts is contentless, so search hits join back via perfume_fts.rowid = perfumes.rowid
        perf_rows.append((
            rowid, p["id"], p["brand"], p["name"], image, p.get("year"), p["slug"], p.get("popularity", 0)
        ))

        all_notes = []
        for kind in ("top", "middle", "base"):
            for n in p.get("notes", {}).get(kind, []):
                note_rows.append((p["id"], kind, n))
                all_notes.append(n)

        # main_accords (ordered)
        for idx, a in enumerate(p.get("main_accords", []), start=1):
            acc_rows.append((p["id"], a, idx))

        # FTS text: brand, name, notes + accords
        fts_rows.append((
            rowid, p["brand"], p["name"], " ".join(all_notes + p.get("main_accords", []))
        ))

    with conn:
        cur.executemany(
            "INSERT INTO perfumes(rowid,id,brand,name,image,year,slug,popularity) VALUES (?,?,?,?,?,?,?,?)",
            perf_rows
        )
        cur.executemany(
            "INSERT INTO notes(perfume_id,kind,note) VALUES (?,?,?)",
            note_rows
        )
        cur.executemany(
            "INSERT INTO accords(perfume_id,accord,rank) VALUES (?,?,?)",
            acc_rows
        )
        cur.executemany(
            "INSERT INTO perfume_fts(rowid,brand,name,notes) VALUES (?,?,?,?)",
            fts_rows
        )

    conn.close()
    print(f"✅ Built {DB} with {len(perf_rows)} perfumes")

if __name__ == "__main__":
    main()

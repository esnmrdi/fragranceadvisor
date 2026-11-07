"""SQLite helpers for scraper data and URL-based progress tracking."""

import sqlite3


class _TableDB:
    """A SQLite file holding one scraper table and its completed URL ledger."""

    table = None
    columns = ()

    def __init__(self, db_name):
        self.db_name = db_name
        self.conn = sqlite3.connect(db_name)

    def setup(self):
        definitions = ", ".join("{} TEXT".format(column) for column in self.columns)
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS {} ({})".format(self.table, definitions)
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS scrape_progress (
                url TEXT PRIMARY KEY,
                completed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        self.conn.commit()

    def add_record(self, args):
        """Insert a data row (legacy helper; new scrapers should use add_record_for_url)."""
        self.conn.execute(
            "INSERT INTO {} ({}) VALUES ({})".format(
                self.table, ", ".join(self.columns), ", ".join("?" * len(self.columns))
            ),
            args,
        )
        self.conn.commit()

    def add_record_for_url(self, url, args):
        """Atomically save a scraped record and mark its source URL complete."""
        with self.conn:
            self.conn.execute(
                "INSERT INTO {} ({}) VALUES ({})".format(
                    self.table,
                    ", ".join(self.columns),
                    ", ".join("?" * len(self.columns)),
                ),
                args,
            )
            self.conn.execute(
                "INSERT OR REPLACE INTO scrape_progress (url) VALUES (?)",
                (url,),
            )

    def completed_urls(self):
        """Return every source URL already committed to this database."""
        rows = self.conn.execute("SELECT url FROM scrape_progress")
        return {row[0] for row in rows}

    def migrate_legacy_progress(self, manifest_urls):
        """
        Map legacy row-count progress to the original manifest order once.

        Older scraper versions processed URLs sequentially but did not store them.
        This migration preserves that behavior for existing databases.
        """
        tracked = self.conn.execute(
            "SELECT COUNT(*) FROM scrape_progress"
        ).fetchone()[0]
        if tracked:
            return 0

        existing_records = self.number_of_records()
        if not existing_records:
            return 0
        if existing_records > len(manifest_urls):
            raise RuntimeError(
                "{} contains {} records but the current manifest has only {} URLs. "
                "Cannot safely migrate legacy progress; restore the original manifest "
                "or reconcile the database before continuing.".format(
                    self.db_name, existing_records, len(manifest_urls)
                )
            )

        legacy_urls = list(dict.fromkeys(manifest_urls))[:existing_records]
        with self.conn:
            self.conn.executemany(
                "INSERT OR IGNORE INTO scrape_progress (url) VALUES (?)",
                ((url,) for url in legacy_urls),
            )
        print(
            "Migrated {} legacy records to URL-based progress using the first {} "
            "manifest entries. Verify that the manifest order has not changed.".format(
                len(legacy_urls), existing_records
            ),
            flush=True,
        )
        return len(legacy_urls)

    def number_of_records(self):
        return self.conn.execute("SELECT COUNT(*) FROM {}".format(self.table)).fetchone()[0]

    def close(self):
        self.conn.close()


class PerfumesDBHelper(_TableDB):
    table = "perfumes"
    columns = (
        "brand", "perfume", "launch_year", "main_accords", "notes", "longevity", "sillage",
    )


class NotesDBHelper(_TableDB):
    table = "notes"
    columns = ("note", "images")

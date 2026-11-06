"""SQLite helpers for the databases the scrapers append to."""

import sqlite3


class _TableDB:
    """A SQLite file holding one all-TEXT table that scrapers append rows to."""

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
        self.conn.commit()

    def add_record(self, args):
        self.conn.execute(
            "INSERT INTO {} ({}) VALUES ({})".format(
                self.table, ", ".join(self.columns), ", ".join("?" * len(self.columns))
            ),
            args,
        )
        self.conn.commit()

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

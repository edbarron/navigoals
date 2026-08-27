import sqlite3
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SCHEMA_PATH = os.path.join(BASE_DIR, "schema.sql")


def initialize_database(db_name="navigoals.db", schema_path=SCHEMA_PATH):
    """Create the database and apply schema.sql (the single source of truth)."""
    try:
        with open(schema_path, "r", encoding="utf-8") as f:
            schema = f.read()
    except OSError as e:
        print(f"Could not read schema file '{schema_path}': {e}")
        return

    try:
        # Connect to the database (it will be created if it doesn't exist)
        with sqlite3.connect(db_name) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.executescript(schema)
        print(f"Database '{db_name}' created and initialized successfully.")
    except sqlite3.Error as e:
        print(f"An error occurred while initializing the database: {e}")


if __name__ == "__main__":
    initialize_database()
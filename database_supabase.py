
import os
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from dotenv import load_dotenv


# Project folder
BASE_DIR = Path(__file__).resolve().parent

# Load environment variables from the project's .env file
load_dotenv(BASE_DIR / ".env")


def get_db():
    """
    Connect to the TessOS Supabase PostgreSQL database.
    Returns rows as dictionaries so existing templates
    can access values using row['column_name'].
    """

    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        raise RuntimeError(
            "DATABASE_URL is missing. Check the project's .env file."
        )

    return psycopg.connect(
        database_url,
        row_factory=dict_row,
        connect_timeout=10
    )


def test_connection():
    """
    Test the Supabase database connection.
    """

    with get_db() as db:
        result = db.execute(
            "SELECT current_database() AS database_name"
        ).fetchone()

        return result["database_name"]


if __name__ == "__main__":
    try:
        database_name = test_connection()
        print("SUCCESS: Connected to Supabase.")
        print(f"Database: {database_name}")

    except Exception as error:
        print("DATABASE CONNECTION FAILED.")
        print(error)

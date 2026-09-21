import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from uuid import uuid4


def run_alembic(api_dir: Path, database_url: str, *args: str) -> None:
    environment = {**os.environ, "DATABASE_URL": database_url, "APP_ENV": "test"}
    subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=api_dir,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )


def test_phase_4_migration_preserves_existing_records_and_backfills_chat(tmp_path: Path) -> None:
    api_dir = Path(__file__).parents[1]
    database_path = tmp_path / "phase2.db"
    database_url = f"sqlite+pysqlite:///{database_path}"
    run_alembic(api_dir, database_url, "upgrade", "20260917_0002")

    user_id = str(uuid4())
    profile_id = str(uuid4())
    membership_id = str(uuid4())
    checkin_id = str(uuid4())
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "INSERT INTO users (id, email, display_name, created_at) "
            "VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
            (user_id, "subject@example.com", "Subject"),
        )
        connection.execute(
            "INSERT INTO care_profiles (id, name, created_by_id, created_at) "
            "VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
            (profile_id, "Subject", user_id),
        )
        connection.execute(
            "INSERT INTO care_memberships "
            "(id, care_profile_id, user_id, role, created_at) "
            "VALUES (?, ?, ?, 'cared_person', CURRENT_TIMESTAMP)",
            (membership_id, profile_id, user_id),
        )
        connection.execute(
            "INSERT INTO wellbeing_checkins "
            "(id, care_profile_id, reported_by_user_id, score, occurred_at, "
            "created_at, updated_at) VALUES "
            "(?, ?, ?, 64, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
            (checkin_id, profile_id, user_id),
        )

    run_alembic(api_dir, database_url, "upgrade", "head")
    with sqlite3.connect(database_path) as connection:
        profile = connection.execute(
            "SELECT subject_user_id, timezone FROM care_profiles WHERE id = ?", (profile_id,)
        ).fetchone()
        score = connection.execute(
            "SELECT score FROM wellbeing_checkins WHERE id = ?", (checkin_id,)
        ).fetchone()
        room_count = connection.execute(
            "SELECT COUNT(*) FROM chat_rooms WHERE care_profile_id = ?", (profile_id,)
        ).fetchone()
    assert profile == (user_id, "UTC")
    assert score == (64,)
    assert room_count == (1,)

    run_alembic(api_dir, database_url, "downgrade", "20260917_0002")
    with sqlite3.connect(database_path) as connection:
        assert connection.execute(
            "SELECT score FROM wellbeing_checkins WHERE id = ?", (checkin_id,)
        ).fetchone() == (64,)
    run_alembic(api_dir, database_url, "upgrade", "head")

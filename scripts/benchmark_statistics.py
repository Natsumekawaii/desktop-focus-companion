"""Repeatable SQLite query/read benchmark using synthetic, temporary records."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import median
from tempfile import TemporaryDirectory
from time import perf_counter

from app.data.database import Database
from app.data.focus_item_repository import FocusItemRepository
from app.data.focus_session_repository import FocusSessionRepository
from app.statistics import StatisticsPeriod, StatisticsService


class CountingRepository(FocusSessionRepository):
    reads = 0

    def list_sessions(self, *args, **kwargs):
        self.reads += 1
        return super().list_sessions(*args, **kwargs)


def benchmark(count: int) -> dict:
    with TemporaryDirectory(prefix="focus-benchmark-") as temporary:
        database = Database(Path(temporary) / "synthetic.sqlite3")
        database.initialize()
        item = FocusItemRepository(database).create("Synthetic benchmark")
        epoch = datetime(2026, 1, 1, tzinfo=timezone.utc)
        with database.connect() as connection:
            connection.executemany(
                "INSERT INTO focus_sessions (focus_item_id,focus_item_name,start_time,end_time,"
                "duration_seconds,created_at,updated_at,mode,source,note) VALUES (?,?,?,?,?,?,?,?,?,?)",
                [
                    (
                        item.id,
                        item.name,
                        (epoch + timedelta(minutes=i * 10)).isoformat(),
                        (epoch + timedelta(minutes=i * 10 + 5)).isoformat(),
                        300,
                        epoch.isoformat(),
                        epoch.isoformat(),
                        "stopwatch",
                        "timer",
                        "",
                    )
                    for i in range(count)
                ],
            )
        repository = CountingRepository(database)
        service = StatisticsService(repository, timezone.utc)

        def old_metrics():
            totals = tuple(service.focus_item_totals(StatisticsPeriod.ALL_TIME))
            latest = {}
            for session in repository.list_sessions():
                latest.setdefault(session.focus_item_id, session.start_time)
            return totals, tuple(latest.items())

        def new_metrics():
            snapshot = service.focus_item_metrics()
            return snapshot.totals, snapshot.last_records

        def old_progress():
            return service.totals_by_date(), service.total_focus_time()

        def new_progress():
            snapshot = service.progress_snapshot()
            return snapshot.daily_totals, snapshot.total_seconds

        assert old_metrics() == new_metrics()
        assert old_progress() == new_progress()
        results = {"records": count, "equivalent": True}
        for label, operation in [
            ("old_metrics", old_metrics),
            ("new_metrics", new_metrics),
            ("old_progress", old_progress),
            ("new_progress", new_progress),
        ]:
            samples = []
            for _ in range(3):
                repository.reads = 0
                started = perf_counter()
                operation()
                samples.append(perf_counter() - started)
            results[label] = {
                "median_seconds": median(samples),
                "queries": repository.reads,
            }
        return results


def main() -> None:
    results = [benchmark(count) for count in (1000, 10000, 50000)]
    output = (
        Path(__file__).resolve().parents[1] / "artifacts" / "statistics-benchmark.json"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()

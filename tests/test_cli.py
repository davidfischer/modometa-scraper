import io
import logging
import sys
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from src.cli import LevelFilter
from src.cli import main
from src.cli import setup_logging


def test_level_filter():
    f = LevelFilter(logging.WARNING)
    info_record = logging.LogRecord("test", logging.INFO, "path", 1, "msg", (), None)
    warn_record = logging.LogRecord("test", logging.WARNING, "path", 1, "msg", (), None)
    assert not f.filter(info_record)
    assert f.filter(warn_record)


def test_setup_logging_levels(tmp_path, monkeypatch):
    log_file = tmp_path / "test.log"
    fake_stdout = io.StringIO()
    monkeypatch.setattr(sys, "stdout", fake_stdout)

    setup_logging(verbose=False, log_file=str(log_file))

    logger = logging.getLogger("test_logger")
    logger.info("This is an info message")
    logger.warning("This is a warning message")

    stdout_output = fake_stdout.getvalue()
    assert "This is an info message" not in stdout_output
    assert "This is a warning message" in stdout_output

    assert log_file.exists()
    log_file_content = log_file.read_text(encoding="utf-8")
    assert "This is an info message" in log_file_content
    assert "This is a warning message" in log_file_content


def test_setup_logging_verbose(tmp_path, monkeypatch):
    log_file = tmp_path / "test_verbose.log"
    fake_stdout = io.StringIO()
    monkeypatch.setattr(sys, "stdout", fake_stdout)

    setup_logging(verbose=True, log_file=str(log_file))

    logger = logging.getLogger("test_logger_verbose")
    logger.debug("This is a debug message")

    stdout_output = fake_stdout.getvalue()
    assert "This is a debug message" in stdout_output

    assert log_file.exists()
    log_file_content = log_file.read_text(encoding="utf-8")
    assert "This is a debug message" in log_file_content


def test_main_exits_nonzero_when_no_decks_created_or_updated(monkeypatch):
    monkeypatch.setattr("sys.argv", ["main.py"])
    fake_stats = {
        "total_found": 1,
        "created": 0,
        "updated": 0,
        "skipped": 1,
        "failed": 0,
        "failed_events": [],
    }
    with patch("src.cli.MTGOSyncEngine") as mock_engine_cls:
        mock_engine = MagicMock()
        mock_engine.sync.return_value = fake_stats
        mock_engine_cls.return_value = mock_engine

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 1


def test_main_succeeds_when_decks_created(monkeypatch):
    monkeypatch.setattr("sys.argv", ["main.py"])
    fake_stats = {
        "total_found": 1,
        "created": 1,
        "updated": 0,
        "skipped": 0,
        "failed": 0,
        "failed_events": [],
    }
    with patch("src.cli.MTGOSyncEngine") as mock_engine_cls:
        mock_engine = MagicMock()
        mock_engine.sync.return_value = fake_stats
        mock_engine_cls.return_value = mock_engine

        main()


def test_main_succeeds_when_decks_updated(monkeypatch):
    monkeypatch.setattr("sys.argv", ["main.py"])
    fake_stats = {
        "total_found": 1,
        "created": 0,
        "updated": 1,
        "skipped": 0,
        "failed": 0,
        "failed_events": [],
    }
    with patch("src.cli.MTGOSyncEngine") as mock_engine_cls:
        mock_engine = MagicMock()
        mock_engine.sync.return_value = fake_stats
        mock_engine_cls.return_value = mock_engine

        main()


def test_main_saves_datestamped_failed_events(tmp_path, monkeypatch):
    failed_file = tmp_path / "failed_events.json"
    log_file = tmp_path / "test.log"
    monkeypatch.setattr(
        "sys.argv",
        [
            "main.py",
            "--failed-file",
            str(failed_file),
            "--log-file",
            str(log_file),
        ],
    )
    mock_tournament = MagicMock()
    mock_tournament.to_failed_dict.return_value = {
        "name": "Failed Event",
        "uri": "https://www.mtgo.com/failed",
        "failure_reason": "HTTP 500",
    }
    mock_tournament.name = "Failed Event"
    mock_tournament.uri = "https://www.mtgo.com/failed"
    mock_tournament.date = None
    mock_tournament.failure_reason = "HTTP 500"

    fake_stats = {
        "total_found": 1,
        "created": 0,
        "updated": 0,
        "skipped": 0,
        "failed": 1,
        "failed_events": [mock_tournament],
    }

    with patch("src.cli.MTGOSyncEngine") as mock_engine_cls:
        mock_engine = MagicMock()
        mock_engine.sync.return_value = fake_stats
        mock_engine_cls.return_value = mock_engine

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 1

    assert failed_file.exists()
    timestamped_files = [
        f
        for f in tmp_path.glob("failed_events_*.json")
        if f.name != "failed_events.json"
    ]
    assert len(timestamped_files) == 1
    assert timestamped_files[0].read_text(encoding="utf-8") == failed_file.read_text(
        encoding="utf-8"
    )

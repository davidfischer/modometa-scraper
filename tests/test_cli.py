import io
import logging
import sys

from src.cli import LevelFilter
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

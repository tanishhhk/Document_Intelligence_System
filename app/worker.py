"""Run document processing in its own process.

    python -m app.worker

Use this with INGESTION_WORKER_ENABLED=false on the API processes when you
want processing separated from request handling. Several workers can run
at once; each document is claimed by one of them.
"""
import logging
import signal
import threading

from app.config import settings
from app.database import SessionLocal
from app.logging_config import configure_logging
from app.services.ingestion import IngestionWorker


def main() -> None:
    configure_logging(settings.log_level, settings.log_format)
    stopped = threading.Event()
    for name in ("SIGINT", "SIGTERM"):
        if hasattr(signal, name):
            signal.signal(getattr(signal, name), lambda *_: stopped.set())

    worker = IngestionWorker(SessionLocal, settings.upload_dir)
    worker.start()
    logging.getLogger(__name__).info("Ingestion worker started.")
    while not stopped.wait(1.0):  # A timeout keeps Ctrl+C responsive on Windows.
        pass
    worker.stop()


if __name__ == "__main__":
    main()

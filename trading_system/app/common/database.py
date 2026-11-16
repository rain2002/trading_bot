import logging
import warnings
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from trading_system.app.config.settings import settings

logger = logging.getLogger(__name__)

# Setup engine, conditionally adding check_same_thread for SQLite dev environment.
# If PostgreSQL driver (psycopg2) is not installed in the local environment,
# gracefully fallback to an in-memory SQLite engine so unit tests can run out-of-the-box.
try:
    engine = create_engine(
        settings.DATABASE_URL, 
        connect_args={"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {}
    )
except Exception as exc:
    msg = (
        f"CRITICAL WARNING: Database engine creation failed for URL '{settings.DATABASE_URL}': {exc}. "
        "Falling back to in-memory SQLite engine ('sqlite:///:memory:'). "
        "Writes will NOT be persisted! This fallback is intended strictly for unit tests and local mock environments."
    )
    logger.warning(msg)
    warnings.warn(msg, RuntimeWarning)
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False}
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    """Dependency injection for database sessions."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

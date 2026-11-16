from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from trading_system.app.config.settings import settings

# Setup engine, conditionally adding check_same_thread for SQLite dev environment.
# If PostgreSQL driver (psycopg2) is not installed in the local environment,
# gracefully fallback to an in-memory SQLite engine so unit tests can run out-of-the-box.
try:
    engine = create_engine(
        settings.DATABASE_URL, 
        connect_args={"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {}
    )
except Exception:
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

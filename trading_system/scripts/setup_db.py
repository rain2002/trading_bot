import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from trading_system.app.common.database import engine, Base
# Import core to ensure models are registered with Base
import trading_system.app.models.core

from trading_system.app.config.settings import settings

def setup_database():
    print("="*50)
    print(">>> INITIALIZING V2 POSTGRESQL DATABASE SCHEMA <<<")
    print("="*50)
    
    # Extract connection info to create database if it doesn't exist
    try:
        import psycopg2
        from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
        from urllib.parse import urlparse, unquote
        
        # Parse connection string (e.g., postgresql+psycopg2://user:pass@host:port/dbname)
        db_url = settings.DATABASE_URL.replace("+psycopg2", "")
        parsed = urlparse(db_url)
        db_name = parsed.path.lstrip('/')
        
        # Connect to default 'postgres' database to create the new one
        conn = psycopg2.connect(
            dbname='postgres',
            user=unquote(parsed.username) if parsed.username else None,
            password=unquote(parsed.password) if parsed.password else None,
            host=parsed.hostname,
            port=parsed.port
        )
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cursor = conn.cursor()
        
        # Check if database exists
        cursor.execute(f"SELECT 1 FROM pg_catalog.pg_database WHERE datname = '{db_name}'")
        exists = cursor.fetchone()
        
        if not exists:
            print(f"Creating database '{db_name}'...")
            cursor.execute(f"CREATE DATABASE {db_name}")
            print(f"Database '{db_name}' created.")
            
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Warning during DB creation step: {e}")

    try:
        # Create all tables explicitly based on the models
        Base.metadata.create_all(bind=engine)
        print("SUCCESS: All database tables created successfully.")
        print("The V2 Experiment Registry and Order schemas are ready.")
    except Exception as e:
        print(f"ERROR connecting to database: {e}")
        print("\nDid you remember to start PostgreSQL?")
        print("Run 'docker-compose up -d' if you are using Docker.")

if __name__ == "__main__":
    setup_database()

import os
import logging
import urllib.parse
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Support either full DATABASE_URL or individual SQL Server environment variables
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    sql_host = os.getenv("SQL_SERVER_HOST")
    sql_user = os.getenv("SQL_SERVER_USER")
    sql_pass = os.getenv("SQL_SERVER_PASSWORD")
    sql_db = os.getenv("SQL_SERVER_DB", "redsea_db")
    sql_driver = os.getenv("SQL_SERVER_DRIVER", "ODBC Driver 17 for SQL Server")
    sql_trusted = os.getenv("SQL_SERVER_TRUSTED_CONNECTION", "").lower() in ("yes", "true", "1")

    if sql_host:
        if sql_trusted:
            # Windows Authentication (no username/password needed)
            params = urllib.parse.quote_plus(
                f"DRIVER={{{sql_driver}}};SERVER={sql_host};DATABASE={sql_db};"
                f"Trusted_Connection=yes;TrustServerCertificate=yes;"
            )
        elif sql_user and sql_pass:
            # SQL Server Authentication
            params = urllib.parse.quote_plus(
                f"DRIVER={{{sql_driver}}};SERVER={sql_host};DATABASE={sql_db};"
                f"UID={sql_user};PWD={sql_pass};TrustServerCertificate=yes;"
            )
        else:
            params = None

        if params:
            DATABASE_URL = f"mssql+pyodbc:///?odbc_connect={params}"
        else:
            logger.warning("SQL Server configured but missing credentials — falling back to SQLite")
            DATABASE_URL = "sqlite:///./redsea.db"
    else:
        DATABASE_URL = "sqlite:///./redsea.db"

# Build engine based on dialect
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False}
    )
    logger.info("Database: SQLite (development)")
elif DATABASE_URL.startswith("mssql"):
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
        pool_recycle=3600,         # Prevent connection timeout after 1 hour idle
        echo=os.getenv("SQL_ECHO", "false").lower() == "true",
    )
    logger.info(f"Database: SQL Server ({os.getenv('SQL_SERVER_HOST')})")
else:
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

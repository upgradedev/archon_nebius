import os
import logging
import psycopg2

logger = logging.getLogger(__name__)

def get_db_connection():
    """Get a direct connection to the PostgreSQL database."""
    url = os.environ.get("DATABASE_URL")
    if url:
        logger.info("Connecting to database using DATABASE_URL")
        return psycopg2.connect(url, connect_timeout=10)

    host = os.environ.get("POSTGRES_HOST")
    port = os.environ.get("POSTGRES_PORT", "5432")
    db = os.environ.get("POSTGRES_DB")
    user = os.environ.get("POSTGRES_USER")
    password = os.environ.get("POSTGRES_PASSWORD")

    if not host or not db or not user:
        raise ValueError("PostgreSQL database environment variables are not set")

    logger.info("Connecting to database at %s:%s/%s", host, port, db)
    return psycopg2.connect(
        host=host,
        port=port,
        database=db,
        user=user,
        password=password,
        connect_timeout=10
    )

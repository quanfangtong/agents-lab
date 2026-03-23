"""Database connection management."""

import os
from typing import Optional
from contextlib import contextmanager
import pymysql
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from dotenv import load_dotenv
from loguru import logger

# Load environment variables
load_dotenv()


class DatabaseConnection:
    """Manages database connections for multiple databases."""

    def __init__(self):
        """Initialize database connection parameters from environment."""
        self.host = os.getenv("DB_HOST")
        self.port = int(os.getenv("DB_PORT", 3306))
        self.username = os.getenv("DB_USERNAME")
        self.password = os.getenv("DB_PASSWORD")

        self.databases = {
            "basics": os.getenv("DB_BASICS", "qft_basics"),
            "lease": os.getenv("DB_LEASE", "qft_lease"),
            "finance": os.getenv("DB_FINANCE", "qft_finance"),
        }

        self._engines: dict[str, Engine] = {}
        logger.info(f"Initialized DatabaseConnection for host: {self.host}")

    def get_engine(self, db_name: str) -> Engine:
        """
        Get SQLAlchemy engine for a specific database.

        Args:
            db_name: Database name (basics, lease, or finance)

        Returns:
            SQLAlchemy Engine instance
        """
        if db_name not in self.databases:
            raise ValueError(f"Unknown database: {db_name}. Available: {list(self.databases.keys())}")

        if db_name not in self._engines:
            database = self.databases[db_name]
            connection_string = (
                f"mysql+pymysql://{self.username}:{self.password}"
                f"@{self.host}:{self.port}/{database}"
            )
            self._engines[db_name] = create_engine(
                connection_string,
                pool_pre_ping=True,
                pool_recycle=3600,
                echo=False,
            )
            logger.info(f"Created engine for database: {database}")

        return self._engines[db_name]

    @contextmanager
    def get_connection(self, db_name: str):
        """
        Context manager for database connections.

        Args:
            db_name: Database name (basics, lease, or finance)

        Yields:
            Database connection
        """
        engine = self.get_engine(db_name)
        conn = engine.connect()
        try:
            yield conn
        finally:
            conn.close()

    def execute_query(self, db_name: str, query: str, params: Optional[dict] = None):
        """
        Execute a SQL query and return results.

        Args:
            db_name: Database name
            query: SQL query string
            params: Optional query parameters

        Returns:
            Query results
        """
        with self.get_connection(db_name) as conn:
            result = conn.execute(text(query), params or {})
            return result.fetchall()

    def close_all(self):
        """Close all database connections."""
        for name, engine in self._engines.items():
            engine.dispose()
            logger.info(f"Closed engine for database: {name}")
        self._engines.clear()


# Global instance
_db_connection: Optional[DatabaseConnection] = None


def get_db_connection() -> DatabaseConnection:
    """Get or create global database connection instance."""
    global _db_connection
    if _db_connection is None:
        _db_connection = DatabaseConnection()
    return _db_connection

"""Database schema inspection utilities."""

from typing import List, Dict, Any
from sqlalchemy import inspect, text
from loguru import logger
import pandas as pd

from .connection import DatabaseConnection


class DatabaseInspector:
    """Inspect database schema and metadata."""

    def __init__(self, db_connection: DatabaseConnection):
        """
        Initialize database inspector.

        Args:
            db_connection: DatabaseConnection instance
        """
        self.db_connection = db_connection

    def get_tables(self, db_name: str) -> List[str]:
        """
        Get all table names in a database.

        Args:
            db_name: Database name

        Returns:
            List of table names
        """
        engine = self.db_connection.get_engine(db_name)
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        logger.info(f"Found {len(tables)} tables in {db_name}")
        return tables

    def get_table_schema(self, db_name: str, table_name: str) -> Dict[str, Any]:
        """
        Get detailed schema information for a table.

        Args:
            db_name: Database name
            table_name: Table name

        Returns:
            Dictionary with table schema details
        """
        engine = self.db_connection.get_engine(db_name)
        inspector = inspect(engine)

        columns = inspector.get_columns(table_name)
        pk = inspector.get_pk_constraint(table_name)
        indexes = inspector.get_indexes(table_name)
        foreign_keys = inspector.get_foreign_keys(table_name)

        schema = {
            "table_name": table_name,
            "columns": columns,
            "primary_key": pk,
            "indexes": indexes,
            "foreign_keys": foreign_keys,
        }

        logger.info(f"Retrieved schema for {db_name}.{table_name}: {len(columns)} columns")
        return schema

    def get_column_info(self, db_name: str, table_name: str) -> pd.DataFrame:
        """
        Get column information as a DataFrame.

        Args:
            db_name: Database name
            table_name: Table name

        Returns:
            DataFrame with column information
        """
        schema = self.get_table_schema(db_name, table_name)
        columns_data = []

        for col in schema["columns"]:
            columns_data.append({
                "column_name": col["name"],
                "type": str(col["type"]),
                "nullable": col.get("nullable", True),
                "default": col.get("default"),
                "autoincrement": col.get("autoincrement", False),
            })

        return pd.DataFrame(columns_data)

    def get_sample_data(self, db_name: str, table_name: str, limit: int = 10) -> pd.DataFrame:
        """
        Get sample data from a table.

        Args:
            db_name: Database name
            table_name: Table name
            limit: Number of rows to fetch

        Returns:
            DataFrame with sample data
        """
        query = f"SELECT * FROM {table_name} LIMIT {limit}"
        with self.db_connection.get_connection(db_name) as conn:
            df = pd.read_sql(query, conn)

        logger.info(f"Fetched {len(df)} sample rows from {db_name}.{table_name}")
        return df

    def get_table_stats(self, db_name: str, table_name: str) -> Dict[str, Any]:
        """
        Get basic statistics for a table.

        Args:
            db_name: Database name
            table_name: Table name

        Returns:
            Dictionary with table statistics
        """
        with self.db_connection.get_connection(db_name) as conn:
            # Get row count
            count_query = text(f"SELECT COUNT(*) as count FROM {table_name}")
            count_result = conn.execute(count_query).fetchone()
            row_count = count_result[0] if count_result else 0

            # Get table size
            size_query = text(f"""
                SELECT
                    ROUND(((data_length + index_length) / 1024 / 1024), 2) AS size_mb
                FROM information_schema.TABLES
                WHERE table_schema = DATABASE()
                AND table_name = '{table_name}'
            """)
            size_result = conn.execute(size_query).fetchone()
            size_mb = size_result[0] if size_result else 0

        stats = {
            "table_name": table_name,
            "row_count": row_count,
            "size_mb": size_mb,
        }

        logger.info(f"Stats for {db_name}.{table_name}: {row_count} rows, {size_mb} MB")
        return stats

    def export_schema_summary(self, db_name: str, output_file: str):
        """
        Export a summary of all tables in a database to a file.

        Args:
            db_name: Database name
            output_file: Output file path (CSV or JSON)
        """
        tables = self.get_tables(db_name)
        summaries = []

        for table in tables:
            try:
                stats = self.get_table_stats(db_name, table)
                schema = self.get_table_schema(db_name, table)

                summaries.append({
                    "table_name": table,
                    "row_count": stats["row_count"],
                    "size_mb": stats["size_mb"],
                    "column_count": len(schema["columns"]),
                    "has_primary_key": bool(schema["primary_key"]["constrained_columns"]),
                    "foreign_key_count": len(schema["foreign_keys"]),
                })
            except Exception as e:
                logger.warning(f"Failed to get stats for {table}: {e}")

        df = pd.DataFrame(summaries)

        if output_file.endswith(".csv"):
            df.to_csv(output_file, index=False)
        elif output_file.endswith(".json"):
            df.to_json(output_file, orient="records", indent=2)
        else:
            raise ValueError("Output file must be .csv or .json")

        logger.info(f"Exported schema summary to {output_file}")

#!/usr/bin/env python3
"""
Explore database schema and generate metadata.

This script connects to the databases and generates:
- Schema summaries for all tables
- Sample data exports
- Statistical information
"""

import sys
import os
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from common.database import get_db_connection, DatabaseInspector
from common.utils import setup_logger
from loguru import logger


def main():
    """Main exploration function."""
    setup_logger(level="INFO")

    logger.info("Starting database exploration...")

    # Initialize database connection
    db_conn = get_db_connection()
    inspector = DatabaseInspector(db_conn)

    # Create output directory
    output_dir = Path("data/schema")
    output_dir.mkdir(parents=True, exist_ok=True)

    # Explore each database
    databases = ["basics", "lease", "finance"]

    for db_name in databases:
        logger.info(f"\n{'=' * 60}")
        logger.info(f"Exploring database: {db_name}")
        logger.info(f"{'=' * 60}\n")

        try:
            # Get all tables
            tables = inspector.get_tables(db_name)
            logger.info(f"Found {len(tables)} tables in {db_name}")

            # Export schema summary
            summary_file = output_dir / f"{db_name}_summary.csv"
            inspector.export_schema_summary(db_name, str(summary_file))

            # Print top 5 tables by row count
            logger.info(f"\nTop tables in {db_name}:")
            table_stats = []
            for table in tables[:10]:  # Limit to first 10 tables
                try:
                    stats = inspector.get_table_stats(db_name, table)
                    table_stats.append(stats)
                except Exception as e:
                    logger.warning(f"Failed to get stats for {table}: {e}")

            # Sort by row count
            table_stats.sort(key=lambda x: x["row_count"], reverse=True)

            for stats in table_stats[:5]:
                logger.info(
                    f"  - {stats['table_name']}: {stats['row_count']:,} rows, "
                    f"{stats['size_mb']:.2f} MB"
                )

        except Exception as e:
            logger.error(f"Error exploring {db_name}: {e}")

    logger.info(f"\n{'=' * 60}")
    logger.info("Database exploration completed!")
    logger.info(f"Schema summaries saved to: {output_dir}")
    logger.info(f"{'=' * 60}")

    # Close connections
    db_conn.close_all()


if __name__ == "__main__":
    main()

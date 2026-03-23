#!/usr/bin/env python3
"""Test database and LLM connections."""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from common.database import get_db_connection
from loguru import logger


def test_database_connection():
    """Test database connectivity."""
    logger.info("Testing database connections...")

    db_conn = get_db_connection()
    databases = ["basics", "lease", "finance"]

    for db_name in databases:
        try:
            logger.info(f"\nTesting {db_name} database...")

            # Test connection
            with db_conn.get_connection(db_name) as conn:
                result = conn.execute(text("SELECT 1 as test")).fetchone()
                logger.success(f"✓ {db_name}: Connection successful (test query returned: {result[0]})")

                # Get table count
                result = conn.execute(
                    text("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = DATABASE()")
                ).fetchone()
                table_count = result[0]
                logger.info(f"  Tables in {db_name}: {table_count}")

        except Exception as e:
            logger.error(f"✗ {db_name}: Connection failed - {e}")
            return False

    db_conn.close_all()
    return True


def main():
    """Main test function."""
    logger.info("=" * 60)
    logger.info("Starting connection tests...")
    logger.info("=" * 60)

    # Test database
    db_success = test_database_connection()

    logger.info("\n" + "=" * 60)
    if db_success:
        logger.success("All tests passed!")
    else:
        logger.error("Some tests failed!")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()

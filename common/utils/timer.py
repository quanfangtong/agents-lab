"""Timer utility for performance measurement."""

import time
from typing import Optional
from loguru import logger


class Timer:
    """Context manager for timing code execution."""

    def __init__(self, name: str = "Operation", verbose: bool = True):
        """
        Initialize timer.

        Args:
            name: Name of the operation being timed
            verbose: Whether to log timing information
        """
        self.name = name
        self.verbose = verbose
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None
        self.elapsed: Optional[float] = None

    def __enter__(self):
        """Start the timer."""
        self.start_time = time.time()
        if self.verbose:
            logger.info(f"{self.name} started")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Stop the timer and log elapsed time."""
        self.end_time = time.time()
        self.elapsed = self.end_time - self.start_time

        if self.verbose:
            logger.info(f"{self.name} completed in {self.elapsed:.2f}s")

    def get_elapsed(self) -> float:
        """Get elapsed time in seconds."""
        if self.elapsed is None:
            raise RuntimeError("Timer has not been run yet")
        return self.elapsed

"""
Robust Connection Manager with exponential backoff and circuit breaker pattern
"""

import time
import random
import logging
from typing import Callable, Optional, Any
from enum import Enum

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """Circuit breaker states"""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Too many failures, fail fast
    HALF_OPEN = "half_open"  # Testing if service recovered


class ConnectionManager:
    """
    Manages connections with exponential backoff, jitter, and circuit breaker pattern.

    Features:
    - Exponential backoff with configurable parameters
    - Jitter to prevent thundering herd
    - Circuit breaker to fail fast during outages
    - Automatic retry with configurable limits

    Example:
        manager = ConnectionManager(base_delay=1, max_delay=60)
        client = manager.connect_with_retry(mqtt.Client().connect, 'localhost', 1883)
    """

    def __init__(
        self,
        max_retries: Optional[int] = None,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        failure_threshold: int = 5,
        success_threshold: int = 3,
        timeout: int = 60,
    ):
        """
        Initialize connection manager.

        Args:
            max_retries: Maximum retry attempts (None for infinite)
            base_delay: Initial retry delay in seconds
            max_delay: Maximum retry delay in seconds
            failure_threshold: Failures before opening circuit breaker
            success_threshold: Successes before closing circuit breaker
            timeout: Circuit breaker timeout in seconds
        """
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.failure_threshold = failure_threshold
        self.success_threshold = success_threshold
        self.circuit_timeout = timeout

        # State tracking
        self.retry_count = 0
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = 0
        self.circuit_state = CircuitState.CLOSED

    def connect_with_retry(self, connect_func: Callable, *args, **kwargs) -> Any:
        """
        Attempt connection with retry logic and circuit breaker.

        Args:
            connect_func: Function to call for connection
            *args: Positional arguments for connect_func
            **kwargs: Keyword arguments for connect_func

        Returns:
            Result of successful connection

        Raises:
            Exception: If all retries exhausted or circuit breaker is open
        """
        # Check circuit breaker state
        self._check_circuit_breaker()

        while self.max_retries is None or self.retry_count < self.max_retries:
            try:
                # Attempt connection
                logger.debug(f"Connection attempt {self.retry_count + 1}")
                result = connect_func(*args, **kwargs)

                # Success - reset counters
                self._record_success()
                logger.info("Connection successful")
                return result

            except Exception as e:
                self._record_failure(e)

                # Check if we should continue retrying
                if (
                    self.max_retries is not None
                    and self.retry_count >= self.max_retries
                ):
                    logger.error(f"Connection failed after {self.max_retries} attempts")
                    raise

                # Calculate backoff with jitter
                delay = self._calculate_backoff()
                logger.debug(
                    f"Connection attempt {self.retry_count} failed: {e}. "
                    f"Circuit state: {self.circuit_state.value}. "
                    f"Retrying in {delay:.1f}s"
                )

                time.sleep(delay)

        raise Exception(f"Failed to connect after {self.max_retries} attempts")

    def _check_circuit_breaker(self):
        """Check and update circuit breaker state"""
        if self.circuit_state == CircuitState.OPEN:
            # Check if timeout has elapsed
            if time.time() - self.last_failure_time < self.circuit_timeout:
                raise Exception(
                    f"Circuit breaker OPEN - too many recent failures. "
                    f"Will retry in {self.circuit_timeout - (time.time() - self.last_failure_time):.0f}s"
                )
            else:
                # Timeout elapsed, try half-open
                logger.info("Circuit breaker entering HALF_OPEN state")
                self.circuit_state = CircuitState.HALF_OPEN
                self.retry_count = 0  # Reset retry counter

    def _record_success(self):
        """Record successful connection"""
        self.retry_count = 0
        self.failure_count = 0
        self.success_count += 1

        # Close circuit breaker after consecutive successes
        if self.circuit_state == CircuitState.HALF_OPEN:
            if self.success_count >= self.success_threshold:
                logger.info("Circuit breaker entering CLOSED state")
                self.circuit_state = CircuitState.CLOSED

        # Reset success counter if already closed
        if self.circuit_state == CircuitState.CLOSED:
            self.success_count = 0

    def _record_failure(self, error: Exception):
        """Record failed connection attempt"""
        self.retry_count += 1
        self.failure_count += 1
        self.last_failure_time = time.time()
        self.success_count = 0

        # Open circuit breaker after too many failures
        if self.failure_count >= self.failure_threshold:
            if self.circuit_state != CircuitState.OPEN:
                logger.debug(
                    f"Circuit breaker entering OPEN state after {self.failure_count} failures"
                )
                self.circuit_state = CircuitState.OPEN

    def _calculate_backoff(self) -> float:
        """
        Calculate backoff delay with exponential backoff and jitter.

        Returns:
            Delay in seconds
        """
        # Exponential backoff: base_delay * 2^retry_count
        exponential_delay = self.base_delay * (2**self.retry_count)

        # Cap at max_delay
        capped_delay = min(exponential_delay, self.max_delay)

        # Add jitter (±10% random variation)
        jitter = random.uniform(-0.1, 0.1) * capped_delay

        return capped_delay + jitter

    def reset(self):
        """Reset connection manager state"""
        self.retry_count = 0
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = 0
        self.circuit_state = CircuitState.CLOSED
        logger.info("Connection manager state reset")

    def get_state(self) -> dict:
        """Get current state of connection manager"""
        return {
            "circuit_state": self.circuit_state.value,
            "retry_count": self.retry_count,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "last_failure_time": self.last_failure_time,
            "time_since_failure": (
                time.time() - self.last_failure_time if self.last_failure_time else None
            ),
        }

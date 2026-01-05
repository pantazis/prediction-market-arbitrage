"""
Thread-safe control queue for queueing actions from handlers.

Handlers are pure functions that queue actions; the bot loop consumes
and executes them with proper error handling and state management.
"""
import asyncio
import logging
from typing import List, Optional
from datetime import datetime, timedelta
from .actions import Action, ActionType

logger = logging.getLogger(__name__)


class ControlQueue:
    """Thread-safe, async-safe queue for bot actions."""
    
    def __init__(self, max_size: int = 1000):
        """
        Initialize the control queue.
        
        Args:
            max_size: Maximum number of queued actions before blocking
        """
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=max_size)
        self.max_size = max_size
        self.processed_count = 0
        self.dropped_count = 0
        self._lock = asyncio.Lock()
    
    async def enqueue(self, action: Action, timeout_sec: float = 5.0) -> bool:
        """
        Enqueue an action for the bot loop to process.
        
        Args:
            action: The action to enqueue
            timeout_sec: Timeout for queue operations
            
        Returns:
            True if successfully enqueued, False if queue full/timeout
        """
        try:
            async with asyncio.timeout(timeout_sec):
                self.queue.put_nowait(action)
                logger.debug(
                    f"Action queued",
                    extra={
                        "action_type": action.action_type.value,
                        "user_id": action.user_id,
                        "queue_size": self.queue.qsize(),
                    },
                )
                return True
        except asyncio.QueueFull:
            logger.warning(f"Control queue full, dropping action: {action.action_type}")
            self.dropped_count += 1
            return False
        except asyncio.TimeoutError:
            logger.warning(f"Timeout enqueuing action: {action.action_type}")
            self.dropped_count += 1
            return False
        except Exception as e:
            logger.error(f"Error enqueuing action: {e}")
            return False
    
    async def dequeue(self, timeout_sec: Optional[float] = None) -> Optional[Action]:
        """
        Dequeue the next action (blocks if queue empty).
        
        Args:
            timeout_sec: Timeout waiting for action. None = indefinite.
            
        Returns:
            Action if available, None if timeout
        """
        try:
            if timeout_sec is None:
                action = await self.queue.get()
            else:
                action = await asyncio.wait_for(
                    self.queue.get(),
                    timeout=timeout_sec
                )
            self.processed_count += 1
            return action
        except asyncio.TimeoutError:
            return None
        except Exception as e:
            logger.error(f"Error dequeueing action: {e}")
            return None
    
    async def mark_processed(self, action: Action):
        """Mark an action as processed (optional, for rate limiting tracking)."""
        self.queue.task_done()
    
    def size(self) -> int:
        """Current queue size."""
        return self.queue.qsize()
    
    def is_empty(self) -> bool:
        """Check if queue is empty."""
        return self.queue.empty()
    
    async def clear(self):
        """Clear all pending actions."""
        while not self.queue.empty():
            try:
                self.queue.get_nowait()
            except asyncio.QueueEmpty:
                break
    
    async def drain(self) -> List[Action]:
        """Get all pending actions without waiting."""
        actions = []
        while not self.queue.empty():
            try:
                actions.append(self.queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        return actions
    
    def stats(self) -> dict:
        """Get queue statistics."""
        return {
            "queue_size": self.queue.qsize(),
            "max_size": self.max_size,
            "processed_count": self.processed_count,
            "dropped_count": self.dropped_count,
            "utilization_pct": (self.queue.qsize() / self.max_size) * 100,
        }

"""Content-based deduplication cache."""

import time
from typing import Dict, Tuple
import structlog

logger = structlog.get_logger()


class DeduplicationCache:
    """In-memory cache for content-based deduplication with TTL."""
    
    def __init__(self, ttl_seconds: int = 300):  # 5 minutes default
        """Initialize deduplication cache.
        
        Args:
            ttl_seconds: Time-to-live for cache entries in seconds
        """
        self.ttl_seconds = ttl_seconds
        self._cache: Dict[str, Tuple[float, str]] = {}  # hash -> (timestamp, description)
        
    def is_duplicate(self, content_hash: str, description: str = "") -> bool:
        """Check if content hash was recently processed.
        
        Args:
            content_hash: Hash of the content to check
            description: Optional description for logging
            
        Returns:
            True if this is a duplicate within the TTL window
        """
        current_time = time.time()
        
        # Clean expired entries
        self._cleanup_expired(current_time)
        
        if content_hash in self._cache:
            cached_time, cached_desc = self._cache[content_hash]
            age_seconds = current_time - cached_time
            
            logger.info("Duplicate content detected",
                       content_hash=content_hash,
                       age_seconds=round(age_seconds, 1),
                       ttl_seconds=self.ttl_seconds,
                       description=description,
                       cached_description=cached_desc,
                       is_duplicate=True)
            return True
        
        # Not a duplicate - add to cache
        self._cache[content_hash] = (current_time, description)
        
        logger.info("New content hash cached",
                   content_hash=content_hash,
                   cache_size=len(self._cache),
                   description=description,
                   is_duplicate=False)
        
        return False
    
    def _cleanup_expired(self, current_time: float) -> None:
        """Remove expired entries from cache."""
        expired_keys = [
            key for key, (timestamp, _) in self._cache.items()
            if current_time - timestamp > self.ttl_seconds
        ]
        
        for key in expired_keys:
            del self._cache[key]
        
        if expired_keys:
            logger.debug("Cleaned up expired cache entries",
                        expired_count=len(expired_keys),
                        remaining_count=len(self._cache))
    
    def get_stats(self) -> Dict[str, int]:
        """Get cache statistics."""
        current_time = time.time()
        valid_entries = sum(
            1 for timestamp, _ in self._cache.values()
            if current_time - timestamp <= self.ttl_seconds
        )
        
        return {
            "total_entries": len(self._cache),
            "valid_entries": valid_entries,
            "ttl_seconds": self.ttl_seconds
        }
    
    def clear(self) -> None:
        """Clear all cache entries."""
        cleared_count = len(self._cache)
        self._cache.clear()
        logger.info("Deduplication cache cleared", cleared_count=cleared_count)


# Global cache instance
_global_cache = DeduplicationCache()


def is_duplicate_content(content_hash: str, description: str = "") -> bool:
    """Check if content hash is a duplicate using global cache."""
    return _global_cache.is_duplicate(content_hash, description)


def get_cache_stats() -> Dict[str, int]:
    """Get global cache statistics."""
    return _global_cache.get_stats()


def clear_cache() -> None:
    """Clear global cache."""
    _global_cache.clear()
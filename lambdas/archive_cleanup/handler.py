"""
SIGINT Archive Cleanup Lambda Handler
Deletes archives older than retention period and updates index.
"""

import json
import logging
import os
import time
from typing import Any

from shared.s3_store import S3Store

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Default retention period
DEFAULT_RETENTION_DAYS = 30


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Lambda handler for archive cleanup.
    
    Event parameters:
        retention_days: Optional override for retention period (default 30)
        dry_run: If true, only report what would be deleted (default false)
    
    Returns:
        Summary of cleanup operation.
    """
    start_time = time.time()
    
    # Get configuration from event or environment
    retention_days = event.get("retention_days", DEFAULT_RETENTION_DAYS)
    dry_run = event.get("dry_run", False)
    
    # Validate retention days
    retention_days = max(7, min(retention_days, 365))  # Between 7 and 365 days
    
    bucket_name = os.environ.get("DATA_BUCKET", "sigint-data")
    s3_store = S3Store(bucket_name)
    
    logger.info(f"Starting archive cleanup (retention: {retention_days} days, dry_run: {dry_run})")
    
    try:
        if dry_run:
            # Just report what would be deleted
            from datetime import UTC, datetime, timedelta
            cutoff_date = (datetime.now(UTC) - timedelta(days=retention_days)).strftime("%Y-%m-%d")
            available_dates = s3_store.list_archive_dates()
            would_delete = [d for d in available_dates if d < cutoff_date]
            
            result = {
                "dry_run": True,
                "would_delete_dates": would_delete,
                "would_delete_count": len(would_delete),
                "cutoff_date": cutoff_date,
            }
        else:
            # Perform actual cleanup
            result = s3_store.cleanup_old_archives(retention_days)
            
            # Update the archive index after cleanup
            index_data = s3_store.update_archive_index()
            result["index_updated"] = True
            result["remaining_dates"] = len(index_data.get("available_dates", []))
        
        duration_ms = int((time.time() - start_time) * 1000)
        result["duration_ms"] = duration_ms
        
        logger.info(f"Archive cleanup completed in {duration_ms}ms")
        
        return {
            "statusCode": 200,
            "body": json.dumps(result, default=str),
        }
        
    except Exception as e:
        logger.error(f"Archive cleanup error: {e}")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)}),
        }

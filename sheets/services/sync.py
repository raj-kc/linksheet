"""
sheets/services/sync.py
=======================
Utility functions for the sync pipeline.

generate_fingerprint() creates a deterministic hash from (sheet_id, row_number,
action, payload). This allows SheetSyncEvent to be stored with a unique
fingerprint so the same logical event is never written twice (idempotency).
"""
import json
import hashlib


def generate_fingerprint(sheet_id, row_number, action, payload):
    """Return a SHA-256 hex digest uniquely identifying this sync event."""
    raw = f"{sheet_id}:{row_number}:{action}:{json.dumps(payload, sort_keys=True)}"
    return hashlib.sha256(raw.encode()).hexdigest()

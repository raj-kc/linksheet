"""
sheets/tasks.py
===============
Celery tasks for syncing LinkSheet DB rows to Google Sheets.

Sync pipeline order (important — must match Google Sheets row numbering):
  1. CREATE  — append new rows, record assigned row numbers
  2. UPDATE  — overwrite existing rows by row number
  3. DELETE  — delete rows (highest first to avoid index drift)
"""
from datetime import datetime
import logging

from celery import shared_task
from django.db import transaction
from django.utils import timezone
from django.db.models import F
from googleapiclient.errors import HttpError

from sheets.models import Sheet, SheetRow, SheetSyncEvent
from sheets.google_sheets import get_sheets_service

logger = logging.getLogger(__name__)

# HTTP status codes that indicate a transient (retriable) error from Google.
# 429 = rate-limited, 500/503 = server-side errors. Do NOT retry on 403/404
# (permanent auth/not-found errors) — retrying wastes quota and fills the error log.
_RETRIABLE_STATUS_CODES = {429, 500, 503}


def _is_retriable(exc):
    """Return True if the exception represents a transient Google API error."""
    if isinstance(exc, HttpError):
        return exc.resp.status in _RETRIABLE_STATUS_CODES
    return False


@shared_task(
    bind=True,
    autoretry_for=(HttpError,),          # only retry on Google API errors, not all exceptions
    retry_kwargs={"max_retries": 5, "countdown": 10},
    retry_backoff=True,                  # exponential back-off between retries
)
def process_sheet_events(self, sheet_id):
    """
    Process all pending SheetSyncEvents for a given sheet.

    Guards:
    - Skips if the sheet is already syncing (prevents concurrent runs).
    - Sets is_syncing=True for the duration; always resets in finally.
    - Processes CREATE before UPDATE before DELETE to maintain correct ordering.
    """
    # Retry only on transient HTTP errors (rate-limit / server error).
    # Permanent errors (bad creds, sheet deleted) bubble up and are NOT retried.
    exc = getattr(self.request, "exc", None)
    if isinstance(exc, HttpError) and not _is_retriable(exc):
        raise  # stop retrying

    # ATOMIC LOCK PROTECTION:
    # Use select_for_update inside a transaction to ensure only one worker
    # processes this sheet at a time. This prevents race conditions.
    try:
        with transaction.atomic():
            sheet = Sheet.objects.select_for_update(nowait=True).get(id=sheet_id)
            
            # If we got here, we have the lock. Check if it's already syncing
            # and not stale.
            is_stale = sheet.is_syncing and (timezone.now() - sheet.updated_at).total_seconds() > 300
            
            if sheet.is_syncing and not is_stale:
                logger.debug("Sheet %s is already syncing — skipping.", sheet_id)
                return

            sheet.is_syncing = True
            sheet.save(update_fields=["is_syncing", "updated_at"])
    except (Sheet.DoesNotExist, transaction.DatabaseError):
        # DatabaseError happens if select_for_update(nowait=True) fails to get the lock
        logger.debug("Could not acquire lock for sheet %s — skipping.", sheet_id)
        return

    synced_successfully = False

    try:
        service = get_sheets_service(sheet.owner)

        # OUTER LOOP: Continuously process batches of events until none remain.
        # This handles cases where new events arrive while we are busy syncing a previous batch.
        while True:
            events = (
                SheetSyncEvent.objects
                .select_related("row")
                .filter(sheet=sheet, processed=False)
                .order_by("created_at")
            )

            # Check if there are any events to process in this iteration.
            if not events.exists():
                break

            # PHASE 1 — CREATE (Batch Optimized)
            # We group rows by their target tabs to perform fewer append calls.
            create_events = events.filter(action="create")
            if create_events.exists():
                tab_batches = {} # tab_name -> [(event, values)]
                
                for event in create_events:
                    row = event.row
                    if not row: continue
                    
                    target_tabs = _get_target_tabs(sheet, event.payload, first_tab_title=first_tab_title)
                    if not target_tabs: target_tabs = [first_tab_title]
                    
                    row_values = [event.payload.get(col, "") for col in sheet.columns]
                    
                    for tab_name in target_tabs:
                        if tab_name not in tab_batches:
                            tab_batches[tab_name] = []
                        tab_batches[tab_name].append((event, row_values))

                for tab_name, entries in tab_batches.items():
                    try:
                        _ensure_sheet_tab(service, sheet, tab_name)
                        values = [e[1] for e in entries]
                        
                        response = service.spreadsheets().values().append(
                            spreadsheetId=sheet.google_sheet_id,
                            range=f"'{tab_name}'!A1",
                            valueInputOption="RAW",
                            insertDataOption="INSERT_ROWS",
                            body={"values": values}
                        ).execute()

                        updated_range = response["updates"]["updatedRange"]
                        match = re.search(r"!A(\d+):", updated_range + ":") # add colon to handle single row range
                        if match:
                            start_row = int(match.group(1))
                            for idx, (event, _) in enumerate(entries):
                                row = event.row
                                rmap = row.tab_row_numbers or {}
                                rmap[tab_name] = start_row + idx
                                row.tab_row_numbers = rmap
                                if not row.sheet_row_number:
                                    row.sheet_row_number = rmap[tab_name]
                                row.save(update_fields=["tab_row_numbers", "sheet_row_number"])
                    except Exception as exc:
                        logger.error("Batch create failed for tab %s: %s", tab_name, exc)
                        for event, _ in entries:
                            event.error = str(exc)
                            event.save(update_fields=["error"])
                
                # Mark all as processed
                create_events.update(processed=True)

            # PHASE 2 — UPDATE (Batch Optimized)
            # We use spreadsheets.values.batchUpdate to update multiple ranges in one call.
            update_events = events.filter(action="update")
            if update_events.exists():
                batch_data = [] # list of {range, values}
                processed_events = []
                
                num_cols = max(1, len(sheet.columns))
                end_col = _index_to_col(num_cols - 1)

                for event in update_events:
                    if event.row:
                        event.row.refresh_from_db()
                    row = event.row
                    if not row or not row.tab_row_numbers: continue
                    
                    row_values = [event.payload.get(col, "") for col in sheet.columns]
                    
                    # Logic: for simplicity in batching, we only update tabs that didn't change.
                    # Complex movements (moving between tabs) are still handled individually 
                    # if needed, but here we try to batch the majority.
                    current_tabs = _get_target_tabs(sheet, event.payload, first_tab_title=first_tab_title)
                    if not current_tabs: current_tabs = [first_tab_title]
                    
                    old_row_map = row.tab_row_numbers
                    
                    # If tabs changed, fallback to individual handle for this specific row
                    # to manage deletions/appends correctly.
                    tabs_changed = set(old_row_map.keys()) != set(current_tabs)
                    if tabs_changed:
                        try:
                            _handle_update(service, sheet, event)
                        except Exception as exc:
                            event.error = str(exc)
                            event.save(update_fields=["error"])
                        processed_events.append(event)
                        continue

                    for tab_name, num in old_row_map.items():
                        batch_data.append({
                            "range": f"'{tab_name}'!A{num}:{end_col}{num}",
                            "values": [row_values]
                        })
                    processed_events.append(event)

                if batch_data:
                    try:
                        service.spreadsheets().values().batchUpdate(
                            spreadsheetId=sheet.google_sheet_id,
                            body={
                                "valueInputOption": "RAW",
                                "data": batch_data
                            }
                        ).execute()
                    except Exception as exc:
                        logger.error("Batch update failed: %s", exc)
                        for event in processed_events:
                            event.error = str(exc)
                            event.save(update_fields=["error"])
                
                for event in processed_events:
                    event.processed = True
                    event.save(update_fields=["processed"])

            # PHASE 3 — DELETE (highest row numbers first to avoid index drift)
            delete_events = list(
                events.filter(action="delete", processed=False).order_by("-row_number")
            )
            for event in delete_events:
                try:
                    _handle_delete(service, sheet, event)
                except Exception as exc:
                    logger.error("Delete sync failed for event %s: %s", event.id, exc)
                    event.error = str(exc)
                    event.save(update_fields=["error"])
                # We always mark as processed so we don't infinitely loop
                event.processed = True
                event.save(update_fields=["processed"])

        # Mark that sync completed successfully so we can update last_synced.
        synced_successfully = True
        sheet.last_synced = timezone.now()

    finally:
        # Always reset the syncing flag. Only update last_synced when we had
        # a fully successful run (prevents recording a stale/misleading timestamp
        # after a partial failure).
        if synced_successfully:
            sheet.save(update_fields=["is_syncing", "last_synced"])
        else:
            sheet.is_syncing = False
            sheet.save(update_fields=["is_syncing"])


def _get_sheet_meta(service, spreadsheet_id):
    """Fetch the full properties of all sheet tabs in the spreadsheet."""
    meta = service.spreadsheets().get(
        spreadsheetId=spreadsheet_id,
        fields="sheets.properties(sheetId,title,index)"
    ).execute()
    return sorted(meta["sheets"], key=lambda s: s["properties"]["index"])


def _ensure_sheet_tab(service, sheet, tab_title):
    """
    Ensure a sheet tab with the given title exists. If not, create it
    and add the headers from sheet.columns. Returns (sheet_id, was_created).
    """
    sheets = _get_sheet_meta(service, sheet.google_sheet_id)
    for s in sheets:
        if s["properties"]["title"] == tab_title:
            return s["properties"]["sheetId"], False

    # Not found, create it
    req = {
        "requests": [
            {
                "addSheet": {
                    "properties": {
                        "title": tab_title,
                    }
                }
            }
        ]
    }
    res = service.spreadsheets().batchUpdate(
        spreadsheetId=sheet.google_sheet_id,
        body=req
    ).execute()
    
    new_sheet_id = res["replies"][0]["addSheet"]["properties"]["sheetId"]
    
    # Add headers to the new tab
    if sheet.columns:
        service.spreadsheets().values().update(
            spreadsheetId=sheet.google_sheet_id,
            range=f"'{tab_title}'!A1",
            valueInputOption="RAW",
            body={"values": [sheet.columns]}
        ).execute()
        
    return new_sheet_id, True


def _get_target_tabs(sheet, row_data, first_tab_title="All Details"):
    """
    Determine which tabs this row should live in based on sync_config.
    Returns list of strings (tab names).
    """
    config = sheet.sync_config or {}
    group_col = config.get("grouping_column")
    
    # If no grouping is configured, return empty list to trigger legacy first-tab behavior
    if not group_col:
        return []

    tabs = []
    
    # 1. Master Tab
    keep_all = config.get("keep_all", True)
    if keep_all:
        tabs.append(first_tab_title)
    
    # Determination of categorization value
    category_tab = None
    target_val = None
    is_date = False

    if group_col == "__created_at__":
        target_val = datetime.now()
        is_date = True
    elif group_col in row_data:
        target_val = row_data[group_col]
        for c in sheet.get_column_configs():
            if c.get("column_name") == group_col or c.get("name") == group_col:
                if c.get("column_type") == "date" or c.get("type") == "date":
                    is_date = True
                break

    if target_val:
        interval = config.get("grouping_interval")
        if is_date and interval:
            try:
                d = None
                if isinstance(target_val, datetime):
                    d = target_val
                else:
                    str_val = str(target_val).strip()
                    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y"):
                        try:
                            d = datetime.strptime(str_val, fmt)
                            break
                        except ValueError:
                            continue
                
                if d:
                    if interval == "yearly": category_tab = d.strftime("%Y")
                    elif interval == "monthly": category_tab = d.strftime("%B %Y")
                    elif interval == "daily": category_tab = d.strftime("%Y-%m-%d")
                    elif interval == "weekly":
                        week = d.isocalendar()[1]
                        category_tab = f"Week {week}, {d.year}"
                else:
                    category_tab = str(target_val)
            except:
                category_tab = str(target_val)
        else:
            category_tab = str(target_val)

    if category_tab and category_tab not in tabs:
        tabs.append(category_tab)
        
    return tabs


def _handle_create(service, sheet, event):
    """
    Append a new row to Google Sheets (one or more tabs) and record row numbers.
    """
    row = event.row
    if not row:
        logger.warning("Create event %s has no associated row — skipping.", event.id)
        event.processed = True
        event.save(update_fields=["processed"])
        return

    # IDEMPOTENCY CHECK: If the row already has numbers assigned for ALL target tabs,
    # it means a previous attempt succeeded but failed to mark the event as processed.
    sheets_meta = _get_sheet_meta(service, sheet.google_sheet_id)
    first_tab_title = sheets_meta[0]["properties"]["title"]
    target_tabs = _get_target_tabs(sheet, event.payload, first_tab_title=first_tab_title)
    
    if not target_tabs:
        target_tabs = [first_tab_title]

    row_map = row.tab_row_numbers or {}
    
    # If we already have mappings for all target tabs, skip appending.
    all_mapped = all(tab in row_map for tab in target_tabs)
    if all_mapped and row_map:
        logger.info("Row %s already has mappings in Google Sheets — skipping append.", row.id)
        return

    # PHASE 1: Fetch the first sheet's literal title for the range.
    sheets = _get_sheet_meta(service, sheet.google_sheet_id)
    first_tab_title = sheets[0]["properties"]["title"]

    target_tabs = _get_target_tabs(sheet, event.payload, first_tab_title=first_tab_title)
    
    if not target_tabs:
        target_tabs = [first_tab_title]

    row_map = row.tab_row_numbers or {}
    values = [[event.payload.get(col, "") for col in sheet.columns]]

    for tab_name in target_tabs:
        _ensure_sheet_tab(service, sheet, tab_name)
        
        response = service.spreadsheets().values().append(
            spreadsheetId=sheet.google_sheet_id,
            range=f"'{tab_name}'!A1",
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": values}
        ).execute()

        updated_range = response["updates"]["updatedRange"]
        match = re.search(r"!A(\d+)", updated_range)
        if match:
            # We store the row number in the map
            row_map[tab_name] = int(match.group(1))

    # Backward compatibility: use the first entry in row_map for sheet_row_number
    if row_map:
        first_num = list(row_map.values())[0]
        row.sheet_row_number = first_num
        row.tab_row_numbers = row_map
        row.save(update_fields=["sheet_row_number", "tab_row_numbers"])


def _index_to_col(index: int) -> str:
    result = []
    while index >= 0:
        result.append(chr(65 + (index % 26)))
        index = (index // 26) - 1
    return "".join(reversed(result))


def _handle_update(service, sheet, event):
    """Overwrite an existing row in all relevant tabs."""
    # REFRESH ROW: Another event in the same batch may have shifted row numbers.
    if event.row:
        event.row.refresh_from_db()
    
    row = event.row
    if not row or not row.tab_row_numbers:
        # Fallback for old rows that only have sheet_row_number
        if row and row.sheet_row_number:
            sheets = _get_sheet_meta(service, sheet.google_sheet_id)
            tab_name = sheets[0]["properties"]["title"]
            row.tab_row_numbers = {tab_name: row.sheet_row_number}
        else:
            raise ValueError("Row has no Google Sheet row mapping — cannot update.")

    values = [[event.payload.get(col, "") for col in sheet.columns]]
    num_cols = max(1, len(sheet.columns))
    end_col = _index_to_col(num_cols - 1)

    sheets = _get_sheet_meta(service, sheet.google_sheet_id)
    first_tab_title = sheets[0]["properties"]["title"]

    # Determine current desired tabs
    current_tabs = _get_target_tabs(sheet, event.payload, first_tab_title=first_tab_title)
    if not current_tabs:
        current_tabs = [first_tab_title]

    old_row_map = row.tab_row_numbers
    new_row_map = {}

    # Logic:
    # 1. Update in tabs that were already there
    # 2. Append in tabs that are now new (if the categorized value changed)
    # 3. Delete in tabs that are no longer applicable (if the categorized value changed)
    
    # Simple strategy: Sync everywhere we can
    for tab_name, num in old_row_map.items():
        if tab_name in current_tabs:
            # Still in this tab - Update
            range_str = f"'{tab_name}'!A{num}:{end_col}{num}"
            service.spreadsheets().values().update(
                spreadsheetId=sheet.google_sheet_id,
                range=range_str,
                valueInputOption="RAW",
                body={"values": values}
            ).execute()
            new_row_map[tab_name] = num
        else:
            # Category changed! Delete from this tab in Google Sheets
            # (Requires re-indexing later rows in THIS specific tab)
            _delete_and_shift(service, sheet, tab_name, num)

    # Any new tabs?
    for tab_name in current_tabs:
        if tab_name not in old_row_map:
            # Row moved to this tab! Append it.
            _ensure_sheet_tab(service, sheet, tab_name)
            response = service.spreadsheets().values().append(
                spreadsheetId=sheet.google_sheet_id,
                range=f"'{tab_name}'!A1",
                valueInputOption="RAW",
                insertDataOption="INSERT_ROWS",
                body={"values": values}
            ).execute()
            match = re.search(r"!A(\d+)", response["updates"]["updatedRange"])
            if match:
                new_row_map[tab_name] = int(match.group(1))

    row.tab_row_numbers = new_row_map
    row.sheet_row_number = list(new_row_map.values())[0] if new_row_map else None
    row.save(update_fields=["tab_row_numbers", "sheet_row_number"])


def _handle_delete(service, sheet, event):
    """Delete a row from all mapped tabs and shift row numbers."""
    # Use JSON from payload if row is already gone
    row_map = (event.payload or {}).get("tab_row_numbers", {})
    if not row_map and event.row:
        row_map = event.row.tab_row_numbers or {}
    
    if not row_map and event.row_number:
        # Fallback for old system
        sheets = _get_sheet_meta(service, sheet.google_sheet_id)
        row_map = {sheets[0]["properties"]["title"]: event.row_number}
    
    if not row_map:
        raise ValueError("Missing row mapping for delete event.")

    for tab_name, num in row_map.items():
        _delete_and_shift(service, sheet, tab_name, num)


def _delete_and_shift(service, sheet, tab_name, row_num):
    """Internal helper to delete from Google and shift DB indexes for a specific tab."""
    sheets = _get_sheet_meta(service, sheet.google_sheet_id)
    tab_id = None
    for s in sheets:
        if s["properties"]["title"] == tab_name:
            tab_id = s["properties"]["sheetId"]
            break
            
    if tab_id is None: return # Tab gone?

    service.spreadsheets().batchUpdate(
        spreadsheetId=sheet.google_sheet_id,
        body={
            "requests": [{
                "deleteDimension": {
                    "range": {
                        "sheetId": tab_id,
                        "dimension": "ROWS",
                        "startIndex": row_num - 1,
                        "endIndex": row_num,
                    }
                }
            }]
        }
    ).execute()

    # COMPLEX: Update row numbers in the DB for THIS tab
    # Find all rows that were in this tab AFTER the deleted row index.
    # OPTIMIZED: Only fetch rows that actually need shifting.
    # We narrow down the queryset to rows that contain the specific tab_name.
    rows_to_shift = SheetRow.objects.filter(
        sheet=sheet, 
        tab_row_numbers__has_key=tab_name
    )
    
    to_update = []
    for r in rows_to_shift:
        rmap = r.tab_row_numbers or {}
        val = rmap.get(tab_name)
        
        if val is not None and val > row_num:
            rmap[tab_name] = val - 1
            
            # Maintenance: sync the legacy sheet_row_number if it matched the old tab_row
            if r.sheet_row_number == val:
                r.sheet_row_number -= 1
                
            r.tab_row_numbers = rmap
            to_update.append(r)
    
    if to_update:
        # Use a reasonable batch size for bulk_update to stay under memory limits
        SheetRow.objects.bulk_update(to_update, ["tab_row_numbers", "sheet_row_number"], batch_size=500)


@shared_task(bind=True)
def sync_sheet_task(self, sheet_id):
    """
    Lightweight trigger task — enqueues processing of pending sync events.

    Calls process_sheet_events directly (not .delay()) to avoid double-dispatch:
    this task IS the processing task, not a dispatcher.
    """
    return process_sheet_events(sheet_id)
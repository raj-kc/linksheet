"""
sheets/tasks.py
===============
Celery tasks for syncing LinkSheet DB rows to Google Sheets.

Sync pipeline order (important — must match Google Sheets row numbering):
  1. CREATE  — append new rows, record assigned row numbers
  2. UPDATE  — overwrite existing rows by row number
  3. DELETE  — delete rows (highest first to avoid index drift)
"""
import re
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

    try:
        sheet = Sheet.objects.get(id=sheet_id)
    except Sheet.DoesNotExist:
        logger.error("Sheet %s not found — skipping sync.", sheet_id)
        return

    if sheet.is_syncing:
        logger.debug("Sheet %s is already syncing — skipping.", sheet_id)
        return

    sheet.is_syncing = True
    sheet.save(update_fields=["is_syncing"])

    synced_successfully = False

    try:
        # get_sheets_service is inside the try block so a credential error
        # is caught and is_syncing is correctly reset in finally.
        service = get_sheets_service(sheet.owner)

        events = (
            SheetSyncEvent.objects
            .select_related("row")
            .filter(sheet=sheet, processed=False)
            .order_by("created_at")
        )

        # PHASE 1 — CREATE (must run first to establish row numbers)
        for event in events.filter(action="create"):
            _handle_create(service, sheet, event)
            event.processed = True
            event.save(update_fields=["processed"])

        # PHASE 2 — UPDATE
        for event in events.filter(action="update"):
            try:
                _handle_update(service, sheet, event)
            except Exception as exc:
                logger.error("Update sync failed for event %s: %s", event.id, exc)
                event.error = str(exc)
                event.save(update_fields=["error"])
                continue
            event.processed = True
            event.save(update_fields=["processed"])

        # PHASE 3 — DELETE (highest row numbers first to avoid index drift)
        delete_events = list(
            events.filter(action="delete").order_by("-row_number")
        )
        for event in delete_events:
            try:
                _handle_delete(service, sheet, event)
            except Exception as exc:
                logger.error("Delete sync failed for event %s: %s", event.id, exc)
                event.error = str(exc)
                event.save(update_fields=["error"])
                continue
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


def _handle_create(service, sheet, event):
    """
    Append a new row to Google Sheets and record the assigned row number.

    After appending, parse the returned updatedRange to find the actual row
    number Google assigned. This is stored on the SheetRow so future updates
    and deletes target the correct row.
    """
    # Guard: the row FK is SET_NULL — if the row was somehow deleted before
    # sync ran, skip gracefully rather than crashing.
    if not event.row:
        logger.warning("Create event %s has no associated row — skipping.", event.id)
        event.processed = True
        event.save(update_fields=["processed"])
        return

    values = [[event.payload.get(col, "") for col in sheet.columns]]

    response = service.spreadsheets().values().append(
        spreadsheetId=sheet.google_sheet_id,
        range="A1",
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body={"values": values}
    ).execute()

    updated_range = response["updates"]["updatedRange"]

    # updatedRange looks like "Sheet1!A7:C7". Use regex to reliably extract
    # the row number — simple split fails when sheet names contain "!A".
    match = re.search(r"!A(\d+)", updated_range)
    if not match:
        raise ValueError(f"Cannot parse row number from updatedRange: {updated_range!r}")
    row_number = int(match.group(1))

    event.row.sheet_row_number = row_number
    event.row.save(update_fields=["sheet_row_number"])


def _index_to_col(index: int) -> str:
    result = []
    while index >= 0:
        result.append(chr(65 + (index % 26)))
        index = (index // 26) - 1
    return "".join(reversed(result))


def _handle_update(service, sheet, event):
    """Overwrite an existing row in Google Sheets by its row number."""
    row = event.row

    if not row or not row.sheet_row_number:
        raise ValueError("Row has no Google Sheet row number — cannot update.")

    values = [[event.payload.get(col, "") for col in sheet.columns]]
    num_cols = max(1, len(sheet.columns))
    end_col = _index_to_col(num_cols - 1)

    meta = service.spreadsheets().get(
        spreadsheetId=sheet.google_sheet_id,
        fields="sheets.properties(title,index)"
    ).execute()
    sheets_sorted = sorted(meta["sheets"], key=lambda s: s["properties"]["index"])
    sheet_title = sheets_sorted[0]["properties"]["title"]

    range_str = f"'{sheet_title}'!A{row.sheet_row_number}:{end_col}{row.sheet_row_number}"

    service.spreadsheets().values().update(
        spreadsheetId=sheet.google_sheet_id,
        range=range_str,
        valueInputOption="RAW",
        body={"values": values}
    ).execute()


def _get_first_sheet_id(service, spreadsheet_id):
    """
    Fetch the numeric sheetId of the first worksheet tab.

    The sheetId in batchUpdate deleteDimension requests is the *tab* ID
    (an integer like 0, 12345…), NOT the spreadsheet ID string. Hardcoding 0
    breaks when the first tab has been renamed or reordered.
    """
    meta = service.spreadsheets().get(
        spreadsheetId=spreadsheet_id,
        fields="sheets.properties(sheetId,index)"
    ).execute()
    sheets = sorted(meta["sheets"], key=lambda s: s["properties"]["index"])
    return sheets[0]["properties"]["sheetId"]


def _handle_delete(service, sheet, event):
    """
    Delete a row from Google Sheets by row number and renumber all subsequent
    rows in the DB to keep them in sync.
    """
    if not event.row_number:
        raise ValueError("Missing row_number for delete event.")

    # Fetch the actual tab sheetId (not the spreadsheet ID) for the API call.
    sheet_tab_id = _get_first_sheet_id(service, sheet.google_sheet_id)

    service.spreadsheets().batchUpdate(
        spreadsheetId=sheet.google_sheet_id,
        body={
            "requests": [{
                "deleteDimension": {
                    "range": {
                        "sheetId": sheet_tab_id,
                        "dimension": "ROWS",
                        "startIndex": event.row_number - 1,  # 0-indexed
                        "endIndex": event.row_number,
                    }
                }
            }]
        }
    ).execute()

    # Shift all DB row numbers above the deleted row down by 1 to maintain
    # consistency with Google Sheets. Use select_for_update to prevent races.
    with transaction.atomic():
        SheetRow.objects.select_for_update().filter(
            sheet=sheet,
            sheet_row_number__gt=event.row_number
        ).update(sheet_row_number=F("sheet_row_number") - 1)


@shared_task(bind=True)
def sync_sheet_task(self, sheet_id):
    """
    Lightweight trigger task — enqueues processing of pending sync events.

    Calls process_sheet_events directly (not .delay()) to avoid double-dispatch:
    this task IS the processing task, not a dispatcher.
    """
    return process_sheet_events(sheet_id)
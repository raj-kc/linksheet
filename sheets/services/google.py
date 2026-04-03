"""
sheets/services/google.py
=========================
Google API service factories and low-level helper functions.

NOTE: get_sheets_service() is intentionally NOT defined here.
The canonical implementation lives in sheets/google_sheets.py (which adds
cache_discovery=False and token auto-refresh). Import it from there:

    from sheets.google_sheets import get_sheets_service

This file provides:
  - get_drive_service()  — authenticated Drive v3 client
  - append_row()         — append a single row to a spreadsheet
  - update_row()         — overwrite a full row in a spreadsheet
"""
from googleapiclient.discovery import build
from sheets.google_sheets import get_sheets_service  # noqa: F401 — re-exported for convenience
from sheets.models import GoogleCredentials


def get_drive_service(user):
    """Return an authenticated Google Drive v3 service for the given user."""
    gc = GoogleCredentials.objects.get(user=user)
    creds = gc.get_credentials()
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def append_row(service, spreadsheet_id, values):
    """Append a single row of values to the given spreadsheet."""
    return service.spreadsheets().values().append(
        spreadsheetId=spreadsheet_id,
        range="A1",
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body={"values": [values]},
    ).execute()


def update_row(service, spreadsheet_id, row_number, values):
    """
    Overwrite all columns of a specific row number.

    Uses a full-row range (A{n}:{end_col}{n}) so every column is updated
    correctly — writing only to A{n} would leave the remaining columns unchanged.
    """
    num_cols = len(values)
    end_col = chr(64 + num_cols) if num_cols > 0 else "A"
    return service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"A{row_number}:{end_col}{row_number}",
        valueInputOption="USER_ENTERED",
        body={"values": [values]},
    ).execute()
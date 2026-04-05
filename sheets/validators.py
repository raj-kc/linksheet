"""
sheets/validators.py
====================
Validation and default-value logic for typed SheetColumn fields.

All functions are pure helpers — they raise no exceptions and return error
dicts / mutated data so callers can decide how to respond.

SECURITY NOTE:
  - Unique checks query SheetRow.objects.filter(sheet=sheet) ONLY.
    This means they never leak data from other sheets or other users.
  - The validate_row_data function only returns error message strings —
    it never includes other users' row values in the error output.
"""
import re
import json
import logging
from datetime import datetime

from django.utils import timezone

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Default Value Application
# ─────────────────────────────────────────────────────────────────────────────

def apply_defaults(sheet, data: dict) -> dict:
    """
    Fill in missing or empty values from column default_value configs.

    Rules:
      - Only fills a value if data[col] is missing or blank string.
      - Never overrides a value the user has explicitly provided.
      - Handles the special sentinel '__auto_timestamp__' → ISO timestamp.

    Returns the mutated data dict (same object).
    """
    from sheets.models import SheetColumn

    AUTO_TS = SheetColumn.DEFAULT_AUTO_TIMESTAMP
    now_str = timezone.now().strftime("%Y-%m-%d %H:%M:%S")

    configs = sheet.get_column_configs()
    for col in configs:
        name    = col["column_name"]
        default = col.get("default_value", "")

        if not default:
            continue  # nothing to fill

        # Only apply if user left the field blank/missing
        current = data.get(name, "")
        if current is not None and str(current).strip():
            continue

        if default == AUTO_TS:
            data[name] = now_str
        else:
            data[name] = default

    return data


# ─────────────────────────────────────────────────────────────────────────────
# Per-Cell Validation
# ─────────────────────────────────────────────────────────────────────────────

def validate_cell_value(col_config: dict, value, sheet, exclude_row_id=None):
    """
    Validate a single cell value against its column configuration.

    Args:
        col_config      : dict from Sheet.get_column_configs()
        value           : the submitted value (string / None)
        sheet           : Sheet instance (for unique scope)
        exclude_row_id  : SheetRow.id to exclude from unique checks (edit mode)

    Returns:
        (True, None)          → valid
        (False, error_string) → invalid, with a human-readable message
    """
    from sheets.models import SheetRow

    col_type   = col_config.get("column_type", "text")
    col_name   = col_config.get("column_name", "")
    rules      = col_config.get("validation") or {}
    options    = col_config.get("options") or []

    # Normalise value to string for text checks
    str_value = str(value).strip() if value is not None else ""
    is_blank  = (str_value == "")

    # ── Required ──────────────────────────────────────────────────────────────
    if rules.get("required") and is_blank:
        return False, f"'{col_name}' is required."

    # If blank and not required, skip remaining checks
    if is_blank:
        return True, None

    # ── Type-specific format checks ───────────────────────────────────────────
    if col_type == "email":
        pattern = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
        if not re.match(pattern, str_value):
            return False, f"'{col_name}' must be a valid email address."

    elif col_type == "number":
        try:
            float(str_value)
        except (ValueError, TypeError):
            return False, f"'{col_name}' must be a number."

    elif col_type == "date":
        parsed = False
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y"):
            try:
                datetime.strptime(str_value, fmt)
                parsed = True
                break
            except ValueError:
                pass
        if not parsed:
            return False, f"'{col_name}' must be a valid date (YYYY-MM-DD)."

    elif col_type == "phone":
        # Allow digits, spaces, +, -, (), min 7 chars
        pattern = r"^[\d\s\+\-\(\)]{7,}$"
        if not re.match(pattern, str_value):
            return False, f"'{col_name}' must be a valid phone number."

    elif col_type in ("dropdown", "radio") and options:
        if str_value not in [str(o) for o in options]:
            return False, (
                f"'{col_name}' must be one of: {', '.join(str(o) for o in options)}."
            )

    elif col_type == "checkbox":
        allowed = {"true", "false", "1", "0", "yes", "no", "on", "off"}
        if str_value.lower() not in allowed:
            return False, f"'{col_name}' must be a checkbox value (true/false)."

    # file type: value should be a URL (set by Cloudinary upload endpoint)
    # basic URL check only
    elif col_type == "file":
        if not (str_value.startswith("http://") or str_value.startswith("https://")):
            return False, f"'{col_name}' must be a valid uploaded file URL."

    # ── min_length ────────────────────────────────────────────────────────────
    min_len = rules.get("min_length")
    if min_len is not None:
        try:
            min_len = int(min_len)
            if len(str_value) < min_len:
                return False, f"'{col_name}' must be at least {min_len} characters."
        except (ValueError, TypeError):
            pass

    # ── max_length ────────────────────────────────────────────────────────────
    max_len = rules.get("max_length")
    if max_len is not None:
        try:
            max_len = int(max_len)
            if len(str_value) > max_len:
                return False, f"'{col_name}' must be at most {max_len} characters."
        except (ValueError, TypeError):
            pass

    # ── Regex ─────────────────────────────────────────────────────────────────
    regex = rules.get("regex")
    if regex:
        try:
            if not re.match(regex, str_value):
                return False, f"'{col_name}' does not match the required pattern."
        except re.error:
            pass  # Bad regex in config — skip silently

    # ── Unique (sheet-scoped — NEVER cross-sheet) ─────────────────────────────
    if rules.get("unique"):
        qs = SheetRow.objects.filter(sheet=sheet)
        if exclude_row_id is not None:
            qs = qs.exclude(id=exclude_row_id)
        # JSON containment check: look for col_name key with this exact value
        duplicate = qs.filter(**{f"data__{col_name}": str_value}).exists()
        if duplicate:
            return False, f"'{col_name}' must be unique — this value already exists."

    return True, None


# ─────────────────────────────────────────────────────────────────────────────
# Full Row Validation
# ─────────────────────────────────────────────────────────────────────────────

def validate_row_data(sheet, data: dict, exclude_row_id=None) -> dict:
    """
    Validate all columns in a row submission.

    Returns:
        {} if all valid.
        {"ColumnName": "error message", ...} for every failing column.

    The error messages never include other users' data — they are generic
    constraint messages (e.g. "must be unique", "must be a valid email").
    """
    errors = {}
    configs = sheet.get_column_configs()

    for col in configs:
        col_name = col["column_name"]
        value    = data.get(col_name)

        valid, msg = validate_cell_value(col, value, sheet, exclude_row_id)
        if not valid:
            errors[col_name] = msg

    return errors

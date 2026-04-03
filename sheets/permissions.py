"""
sheets/permissions.py
=====================
Centralized role-based access control helpers for LinkSheet.

ROLE CONTRACT (never violate):
  OWNER        — sheet.owner == user. Full access to all rows + management.
  COLLABORATOR — SheetMember.role == "collaborator". Same as owner for data.
  JOINEE       — SheetMember.role == "joinee". OWN rows ONLY — no visibility
                 into other users' data whatsoever.

PERFORMANCE NOTE:
  Use get_role(sheet, user) when you need to check multiple permissions for
  the same (sheet, user) pair — it issues a single DB query and returns the
  role string. The individual helpers (is_owner, is_collaborator, etc.) are
  convenient for single checks but each may issue its own query.
"""

from sheets.models import SheetMember


# ─────────────────────────────────────────────────────────────────────────────
# Core role resolver — single DB query
# ─────────────────────────────────────────────────────────────────────────────

def get_role(sheet, user):
    """
    Return the user's role on this sheet as a string, or None if no access.

    Returns: "owner" | "collaborator" | "joinee" | None

    Issues a SINGLE DB query (or zero if the user is the owner, which is an
    in-memory comparison). Use this in views that need multiple permission
    checks instead of calling is_owner(), is_collaborator(), is_joinee()
    separately.
    """
    # Owner check is a pure in-memory comparison — no DB hit.
    if sheet.owner_id == user.pk:
        return "owner"

    member = SheetMember.objects.filter(
        sheet=sheet, user=user, is_active=True
    ).values_list("role", flat=True).first()

    if member == SheetMember.ROLE_COLLABORATOR:
        return "collaborator"
    if member == SheetMember.ROLE_JOINEE:
        return "joinee"
    return None  # no access


# ─────────────────────────────────────────────────────────────────────────────
# Low-level membership queries (use for simple single checks)
# ─────────────────────────────────────────────────────────────────────────────

def get_membership(sheet, user):
    """Return the active SheetMember for this user+sheet, or None."""
    return SheetMember.objects.filter(
        sheet=sheet, user=user, is_active=True
    ).first()


def is_owner(sheet, user):
    """In-memory check — no DB query."""
    return sheet.owner_id == user.pk


def is_collaborator(sheet, user):
    """User was explicitly invited — full data access."""
    return SheetMember.objects.filter(
        sheet=sheet,
        user=user,
        role=SheetMember.ROLE_COLLABORATOR,
        is_active=True,
    ).exists()


def is_joinee(sheet, user):
    """User joined via a link — own-rows-only access."""
    return SheetMember.objects.filter(
        sheet=sheet,
        user=user,
        role=SheetMember.ROLE_JOINEE,
        is_active=True,
    ).exists()


def is_any_member(sheet, user):
    """Is the user attached to the sheet at all (any role)?"""
    return is_owner(sheet, user) or SheetMember.objects.filter(
        sheet=sheet, user=user, is_active=True
    ).exists()


# ─────────────────────────────────────────────────────────────────────────────
# Composite permission checks — use these in views
# ─────────────────────────────────────────────────────────────────────────────

def can_access_sheet(sheet, user):
    """
    Can the user open the sheet at all?
    Yes for OWNER, COLLABORATOR, and JOINEE.
    """
    return is_any_member(sheet, user)


def can_see_all_rows(sheet, user):
    """
    OWNER and COLLABORATOR see every row.
    JOINEE sees only their own rows.
    """
    return is_owner(sheet, user) or is_collaborator(sheet, user)


def can_manage_sheet(sheet, user):
    """
    Full management: add/remove collaborators, delete sheet, view Google link.
    OWNER only.
    """
    return is_owner(sheet, user)


def can_trigger_sync(sheet, user):
    """Only OWNER and COLLABORATOR may trigger syncs."""
    return is_owner(sheet, user) or is_collaborator(sheet, user)


def can_download_sheet(sheet, user):
    """Only OWNER and COLLABORATOR may download the full sheet."""
    return is_owner(sheet, user) or is_collaborator(sheet, user)


def can_modify_row(sheet, user, row):
    """
    OWNER / COLLABORATOR → may modify any row.
    JOINEE               → may only modify rows they created.
    """
    if is_owner(sheet, user) or is_collaborator(sheet, user):
        return True
    if is_joinee(sheet, user):
        return row.user_id == user.pk
    return False


def can_delete_row(sheet, user, row):
    """Same logic as can_modify_row — separated for clarity."""
    return can_modify_row(sheet, user, row)


def get_visible_rows(sheet, user):
    """
    Return the QuerySet of rows visible to this user:
    OWNER / COLLABORATOR → all rows for the sheet.
    JOINEE               → only rows owned by user.
    """
    from sheets.models import SheetRow
    qs = SheetRow.objects.filter(sheet=sheet)
    if can_see_all_rows(sheet, user):
        return qs.order_by("sheet_row_number")
    return qs.filter(user=user).order_by("sheet_row_number")

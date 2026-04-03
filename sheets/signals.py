"""
sheets/signals.py
=================
Auto-write ActivityLog entries on every meaningful Django ORM event.

IMPORTANT: Only import models inside receivers (avoid circular imports).
"""
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver


# ─────────────────────────────────────────────────────────────────────────────
# Sheet created
# ─────────────────────────────────────────────────────────────────────────────
@receiver(post_save, sender="sheets.Sheet")
def log_sheet_created(sender, instance, created, **kwargs):
    if not created:
        return
    try:
        from sheets.models import ActivityLog
        ActivityLog.objects.create(
            user=instance.owner,
            sheet=instance,
            action=ActivityLog.ACTION_SHEET_CREATED,
        )
    except Exception:
        pass  # never crash the request


# ─────────────────────────────────────────────────────────────────────────────
# Row created / updated
# ─────────────────────────────────────────────────────────────────────────────
@receiver(post_save, sender="sheets.SheetRow")
def log_row_saved(sender, instance, created, **kwargs):
    try:
        from sheets.models import ActivityLog
        action = ActivityLog.ACTION_ROW_ADDED if created else ActivityLog.ACTION_ROW_UPDATED
        ActivityLog.objects.create(
            user=instance.user,
            sheet=instance.sheet,
            action=action,
        )
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# Row deleted
# ─────────────────────────────────────────────────────────────────────────────
@receiver(post_delete, sender="sheets.SheetRow")
def log_row_deleted(sender, instance, **kwargs):
    try:
        from sheets.models import ActivityLog
        # sheet may have already been cascade-deleted — guard with try/except
        ActivityLog.objects.create(
            user=instance.user,
            sheet=instance.sheet,
            action=ActivityLog.ACTION_ROW_DELETED,
        )
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# Member joined / collaborator added
# ─────────────────────────────────────────────────────────────────────────────
@receiver(post_save, sender="sheets.SheetMember")
def log_member_joined(sender, instance, created, **kwargs):
    if not created:
        return
    try:
        from sheets.models import ActivityLog, SheetMember
        action = (
            ActivityLog.ACTION_COLLAB_ADDED
            if instance.role == SheetMember.ROLE_COLLABORATOR
            else ActivityLog.ACTION_MEMBER_JOINED
        )
        ActivityLog.objects.create(
            user=instance.user,
            sheet=instance.sheet,
            action=action,
        )
    except Exception:
        pass

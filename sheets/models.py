from django.utils import timezone
from datetime import timedelta
import uuid
import json
import hashlib
import logging

from django.conf import settings
from django.db import models
from django.contrib.auth.models import User
from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)


def _get_fernet():
    """Return a Fernet instance using the key from settings."""
    key = getattr(settings, "FIELD_ENCRYPTION_KEY", None)
    if not key:
        raise ValueError("FIELD_ENCRYPTION_KEY is not configured in settings.")
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_value(value):
    """Encrypt a string value. Returns the encrypted string, or empty string for falsy input."""
    if not value:
        return ""
    return _get_fernet().encrypt(value.encode()).decode()


def decrypt_value(value):
    """Decrypt a string value. Returns the decrypted string, or empty string for falsy input."""
    if not value:
        return ""
    try:
        return _get_fernet().decrypt(value.encode()).decode()
    except Exception:
        # Decryption can fail for two legitimate reasons:
        #   1. Pre-migration data stored in plain text (before encryption was introduced).
        #   2. Key rotation — if FIELD_ENCRYPTION_KEY was changed without re-encrypting rows.
        # In both cases, return the raw value so the app doesn't hard-crash. The caller
        # (Google's Credentials library) will fail gracefully if the token is truly corrupt.
        logger.warning(
            "Token decryption failed — returning raw value. "
            "This is expected for pre-migration data; if it persists, "
            "check that FIELD_ENCRYPTION_KEY has not been rotated without re-encryption.",
            exc_info=True,   # includes exception type/message in the log for diagnostics
        )
        return value


# =====================================================
# Google OAuth Credentials
# =====================================================
class GoogleCredentials(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="google_credentials"
    )

    # Encrypted fields — stored as Fernet-encrypted ciphertext
    token = models.TextField()
    refresh_token = models.TextField(null=True, blank=True)

    token_uri = models.TextField()
    client_id = models.TextField()
    client_secret = models.TextField()
    scopes = models.TextField()  # JSON list
    expiry = models.DateTimeField(null=True, blank=True)

    profile_picture = models.URLField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def get_credentials(self):
        from google.oauth2.credentials import Credentials

        # Google's auth library expects naive UTC datetimes for expiry
        expiry = self.expiry
        if expiry and timezone.is_aware(expiry):
            expiry = expiry.replace(tzinfo=None)

        return Credentials(
            token=decrypt_value(self.token),
            refresh_token=decrypt_value(self.refresh_token) if self.refresh_token else None,
            token_uri=self.token_uri,
            client_id=self.client_id,
            client_secret=self.client_secret,
            scopes=json.loads(self.scopes),
            expiry=expiry,
        )

    def save_credentials(self, creds):
        self.token = encrypt_value(creds.token)
        self.refresh_token = encrypt_value(creds.refresh_token) if creds.refresh_token else None
        self.token_uri = creds.token_uri
        self.client_id = creds.client_id
        self.client_secret = creds.client_secret
        self.scopes = json.dumps(creds.scopes)

        if creds.expiry:
            if timezone.is_naive(creds.expiry):
                self.expiry = timezone.make_aware(creds.expiry)
            else:
                self.expiry = creds.expiry

        self.save(update_fields=[
            "token", "refresh_token", "token_uri",
            "client_id", "client_secret", "scopes", "expiry", "updated_at"
        ])

    def __str__(self):
        return f"GoogleCredentials({self.user.username})"


# =====================================================
# Sheet (Core Entity)
# =====================================================
class Sheet(models.Model):
    owner = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="owned_sheets"
    )

    name = models.CharField(max_length=255)

    google_sheet_id = models.CharField(
        max_length=255,
        unique=True,
        db_index=True
    )

    google_url = models.URLField()

    share_token = models.CharField(
        max_length=64,
        unique=True,
        editable=False,
        db_index=True
    )

    columns = models.JSONField(default=list)

    response_count = models.PositiveIntegerField(default=0)

    is_active = models.BooleanField(default=True)
    is_syncing = models.BooleanField(default=False)
    last_synced = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if not self.share_token:
            self.share_token = uuid.uuid4().hex
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.owner.username})"


# =====================================================
# Sheet Membership (Access Control)
# =====================================================
class SheetMember(models.Model):
    # ROLE DEFINITIONS (strict — never mix):
    #   collaborator: Invited explicitly by owner. Full access = same as owner.
    #   joinee:       Joined via private link. Sees & edits ONLY their own rows.
    ROLE_COLLABORATOR = "collaborator"
    ROLE_JOINEE = "joinee"

    ROLE_CHOICES = (
        ("collaborator", "Collaborator"),  # invite-only, full access
        ("joinee", "Joinee"),              # link-only, row-restricted
    )

    sheet = models.ForeignKey(
        Sheet,
        on_delete=models.CASCADE,
        related_name="members"
    )

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="sheet_memberships"
    )

    role = models.CharField(
        max_length=15,
        choices=ROLE_CHOICES,
        default="joinee"
    )

    joined_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = (("sheet", "user"),)
        indexes = [
            models.Index(fields=["sheet", "user"]),
        ]

    @property
    def is_collaborator(self):
        return self.role == self.ROLE_COLLABORATOR

    @property
    def is_joinee(self):
        return self.role == self.ROLE_JOINEE

    def __str__(self):
        return f"{self.user.username} [{self.role}] → {self.sheet.name}"


# =====================================================
# Sheet Rows (DB ↔ Google Sync Unit)
# =====================================================
class SheetRow(models.Model):
    sheet = models.ForeignKey(
        Sheet,
        on_delete=models.CASCADE,
        related_name="rows"
    )

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="sheet_rows"
    )

    sheet_row_number = models.PositiveIntegerField(null=True, blank=True)

    data = models.JSONField()  # column -> value

    version = models.PositiveIntegerField(default=1)  # optimistic locking

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        # NOTE: (sheet, sheet_row_number) is NOT enforced as unique_together here
        # because sheet_row_number is NULL until sync assigns it from Google Sheets.
        # Multiple rows with NULL are intentional (pending sync). Uniqueness is
        # guaranteed at the app level: once assigned, row numbers come from Google
        # Sheets' append response and are unique per sheet.
        ordering = ["sheet_row_number"]
        indexes = [
            models.Index(fields=["sheet", "sheet_row_number"]),
        ]

    def checksum(self):
        return hashlib.sha256(
            json.dumps(self.data, sort_keys=True).encode()
        ).hexdigest()

    def __str__(self):
        return f"Row {self.sheet_row_number} ({self.sheet.name})"


# =====================================================
# Sync Events (Idempotent + Ordered)
# =====================================================
class SheetSyncEvent(models.Model):
    ACTION_CHOICES = (
        ("create", "Create"),
        ("update", "Update"),
        ("delete", "Delete"),
    )

    ORIGIN_CHOICES = (
        ("db", "DB"),
        ("sheet", "Sheet"),
    )

    sheet = models.ForeignKey(
        Sheet,
        on_delete=models.CASCADE,
        related_name="sync_events"
    )

    row = models.ForeignKey(
        SheetRow,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    row_number = models.PositiveIntegerField(null=True, blank=True)

    action = models.CharField(max_length=10, choices=ACTION_CHOICES)

    payload = models.JSONField(null=True, blank=True)

    origin = models.CharField(
        max_length=10,
        choices=ORIGIN_CHOICES,
        default="db"
    )

    fingerprint = models.CharField(
        max_length=64,
        unique=True,
        db_index=True,
        default=uuid.uuid4
    )

    processed = models.BooleanField(default=False)
    error = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["sheet", "processed"]),
            models.Index(fields=["fingerprint"]),
        ]


# =====================================================
# Sheet Snapshot (Consistency Check)
# =====================================================
class SheetSnapshot(models.Model):
    sheet = models.OneToOneField(
        Sheet,
        on_delete=models.CASCADE,
        related_name="snapshot"
    )

    checksum = models.CharField(max_length=64)
    last_checked = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Snapshot({self.sheet.name})"


# =====================================================
# Sync Conflict (Audit + Recovery)
# =====================================================
class SyncConflict(models.Model):
    sheet = models.ForeignKey(
        Sheet,
        on_delete=models.CASCADE,
        related_name="conflicts"
    )

    row_number = models.PositiveIntegerField()

    db_payload = models.JSONField()
    google_payload = models.JSONField()

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Conflict | {self.sheet.name} | Row {self.row_number}"


# =====================================================
# Activity Log (Real-time feed for dashboard + page)
# =====================================================
class ActivityLog(models.Model):
    ACTION_SHEET_CREATED    = "sheet_created"
    ACTION_ROW_ADDED        = "row_added"
    ACTION_ROW_UPDATED      = "row_updated"
    ACTION_ROW_DELETED      = "row_deleted"
    ACTION_MEMBER_JOINED    = "member_joined"
    ACTION_COLLAB_ADDED     = "collaborator_added"

    ACTION_CHOICES = [
        (ACTION_SHEET_CREATED, "Created sheet"),
        (ACTION_ROW_ADDED,     "Added a row to"),
        (ACTION_ROW_UPDATED,   "Updated a row in"),
        (ACTION_ROW_DELETED,   "Deleted a row from"),
        (ACTION_MEMBER_JOINED, "Joined"),
        (ACTION_COLLAB_ADDED,  "Added as collaborator to"),
    ]

    # --- who did it ---
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="activity_logs"
    )

    # --- on which sheet ---
    sheet = models.ForeignKey(
        Sheet,
        on_delete=models.CASCADE,
        related_name="activity_logs",
        null=True,
        blank=True
    )

    action = models.CharField(max_length=30, choices=ACTION_CHOICES)

    # extra info (e.g. row data snapshot)
    metadata = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["sheet", "-created_at"]),
        ]

    @property
    def verb(self):
        return dict(self.ACTION_CHOICES).get(self.action, self.action)

    @property
    def icon(self):
        return {
            self.ACTION_SHEET_CREATED: "ph-file-plus",
            self.ACTION_ROW_ADDED:     "ph-plus-circle",
            self.ACTION_ROW_UPDATED:   "ph-pencil-simple",
            self.ACTION_ROW_DELETED:   "ph-trash",
            self.ACTION_MEMBER_JOINED: "ph-sign-in",
            self.ACTION_COLLAB_ADDED:  "ph-users",
        }.get(self.action, "ph-activity")

    @property
    def color(self):
        return {
            self.ACTION_SHEET_CREATED: "text-blue-600 bg-blue-50",
            self.ACTION_ROW_ADDED:     "text-emerald-600 bg-emerald-50",
            self.ACTION_ROW_UPDATED:   "text-amber-600 bg-amber-50",
            self.ACTION_ROW_DELETED:   "text-red-600 bg-red-50",
            self.ACTION_MEMBER_JOINED: "text-purple-600 bg-purple-50",
            self.ACTION_COLLAB_ADDED:  "text-indigo-600 bg-indigo-50",
        }.get(self.action, "text-gray-600 bg-gray-50")

    def __str__(self):
        return f"{self.user.username} {self.action} @ {self.sheet}"

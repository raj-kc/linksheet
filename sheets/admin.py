"""
sheets/admin.py
===============
Django admin registration for all LinkSheet models.

Provides searchable, filterable admin views for every model so that
debugging, support, and data inspection are possible without direct DB access.
"""
from django.contrib import admin
from django.utils.html import format_html

from sheets.models import (
    ActivityLog,
    GoogleCredentials,
    Sheet,
    SheetMember,
    SheetRow,
    SheetSnapshot,
    SheetSyncEvent,
    SyncConflict,
)


@admin.register(Sheet)
class SheetAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "response_count", "is_active", "is_syncing", "last_synced", "created_at")
    list_filter = ("is_active", "is_syncing")
    search_fields = ("name", "owner__username", "owner__email", "google_sheet_id")
    readonly_fields = ("share_token", "google_sheet_id", "google_url", "created_at", "updated_at")
    ordering = ("-created_at",)


@admin.register(SheetMember)
class SheetMemberAdmin(admin.ModelAdmin):
    list_display = ("user", "sheet", "role", "is_active", "joined_at")
    list_filter = ("role", "is_active")
    search_fields = ("user__username", "user__email", "sheet__name")
    ordering = ("-joined_at",)


@admin.register(SheetRow)
class SheetRowAdmin(admin.ModelAdmin):
    list_display = ("sheet", "user", "sheet_row_number", "version", "created_at")
    list_filter = ("sheet",)
    search_fields = ("sheet__name", "user__username")
    ordering = ("sheet", "sheet_row_number")
    readonly_fields = ("created_at", "updated_at")


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = ("user", "action", "sheet", "created_at")
    list_filter = ("action",)
    search_fields = ("user__username", "sheet__name")
    ordering = ("-created_at",)
    readonly_fields = ("created_at",)


@admin.register(GoogleCredentials)
class GoogleCredentialsAdmin(admin.ModelAdmin):
    list_display = ("user", "expiry", "has_refresh_token", "created_at", "updated_at")
    search_fields = ("user__username", "user__email")
    readonly_fields = ("token", "refresh_token", "client_id", "client_secret", "created_at", "updated_at")

    @admin.display(boolean=True, description="Has Refresh Token")
    def has_refresh_token(self, obj):
        return bool(obj.refresh_token)


@admin.register(SheetSyncEvent)
class SheetSyncEventAdmin(admin.ModelAdmin):
    list_display = ("sheet", "action", "origin", "processed", "row_number", "created_at")
    list_filter = ("action", "processed", "origin")
    search_fields = ("sheet__name", "fingerprint")
    ordering = ("-created_at",)
    readonly_fields = ("fingerprint", "created_at")


@admin.register(SheetSnapshot)
class SheetSnapshotAdmin(admin.ModelAdmin):
    list_display = ("sheet", "checksum", "last_checked")
    search_fields = ("sheet__name",)
    readonly_fields = ("last_checked",)


@admin.register(SyncConflict)
class SyncConflictAdmin(admin.ModelAdmin):
    list_display = ("sheet", "row_number", "created_at")
    list_filter = ("sheet",)
    search_fields = ("sheet__name",)
    ordering = ("-created_at",)
    readonly_fields = ("created_at",)

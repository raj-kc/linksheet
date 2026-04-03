"""
sheets/urls.py
==============
URL routing for the sheets application.

All routes use a single import style (`from sheets import views`) for
consistency — avoids mixing explicit names and module-level lookups.
"""
from django.urls import path
from sheets import views

urlpatterns = [
    # ── Public ────────────────────────────────────────────────────────────────
    path("", views.home, name="home"),
    path("google/login/", views.google_login, name="google_login"),
    path("google/callback/", views.google_callback, name="google_callback"),
    path("logout/", views.logout_view, name="logout"),

    # ── Dashboard ─────────────────────────────────────────────────────────────
    path("dashboard/", views.dashboard, name="dashboard"),

    # ── Sheet management ──────────────────────────────────────────────────────
    path("create-sheet/", views.create_google_sheet, name="create_sheet"),
    path("sheets/<int:sheet_id>/delete/", views.delete_sheet, name="delete_sheet"),
    path("sheets/<int:sheet_id>/download/", views.download_sheet, name="download_sheet"),

    # ── Membership ────────────────────────────────────────────────────────────
    path("join/<str:token>/", views.join_sheet, name="join_sheet"),

    # ── Row CRUD (REST-ish API) ────────────────────────────────────────────────
    path("api/sheets/<int:sheet_id>/grid/", views.sheet_grid_data, name="sheet_grid"),
    path("api/sheets/<int:sheet_id>/rows/", views.add_row, name="add_row"),
    path("api/sheets/<int:sheet_id>/rows/<int:row_id>/", views.update_row, name="update_row"),
    path("api/rows/<int:row_id>/", views.delete_row, name="delete_row"),

    # ── Collaborator management ───────────────────────────────────────────────
    path("api/sheets/<int:sheet_id>/collaborators/", views.add_collaborator, name="add_collaborator"),
    path("api/sheets/<int:sheet_id>/collaborators/remove/", views.remove_collaborator, name="remove_collaborator"),

    # ── Sync ──────────────────────────────────────────────────────────────────
    path("api/sheets/<int:sheet_id>/sync/", views.trigger_sync, name="trigger_sync"),

    # ── AJAX helpers ──────────────────────────────────────────────────────────
    path("sheets/created/", views.get_created_sheets, name="get_created_sheets"),

    # ── Activity ──────────────────────────────────────────────────────────────
    path("activity/", views.activity_page, name="activity"),
]

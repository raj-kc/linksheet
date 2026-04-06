from django.core.management.base import BaseCommand
from sheets.models import Sheet, ActivityLog, SheetSyncEvent, SheetRow, SheetMember, SheetColumn

class Command(BaseCommand):
    help = "Clears all data records (Sheets, Rows, Members, ActivityLogs) for a fresh start."

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING("Starting database cleanup for presentation..."))

        # 1. Activity Logs
        activity_count = ActivityLog.objects.count()
        ActivityLog.objects.all().delete()
        self.stdout.write(f"- Deleted {activity_count} Activity Logs.")

        # 2. Sync Events
        sync_count = SheetSyncEvent.objects.count()
        SheetSyncEvent.objects.all().delete()
        self.stdout.write(f"- Deleted {sync_count} Sync Events.")

        # 3. Explicitly delete child records to reduce cascade load/locks
        row_count = SheetRow.objects.count()
        SheetRow.objects.all().delete()
        self.stdout.write(f"- Deleted {row_count} Sheet Rows.")

        member_count = SheetMember.objects.count()
        SheetMember.objects.all().delete()
        self.stdout.write(f"- Deleted {member_count} Sheet Members.")

        column_count = SheetColumn.objects.count()
        SheetColumn.objects.all().delete()
        self.stdout.write(f"- Deleted {column_count} Sheet Column Configs.")

        # 4. Sheets
        sheet_count = Sheet.objects.count()
        Sheet.objects.all().delete()
        self.stdout.write(f"- Deleted {sheet_count} LinkSheets.")

        self.stdout.write(self.style.SUCCESS("\n✅ Successfully purged all data records. READY FOR PRESENTATION."))

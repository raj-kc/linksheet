# Hand-written migration — Step 1 of fix roadmap.
# Removes the unique_together constraint on (sheet, sheet_row_number) from SheetRow.
# Reason: sheet_row_number is NULL until Celery sync assigns it from Google Sheets.
# SQLite treats NULL == NULL in unique checks, causing IntegrityError on the second
# row creation for any sheet. The index on (sheet, sheet_row_number) is preserved
# for query performance.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('sheets', '0003_alter_sheetmember_role'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='sheetrow',
            unique_together=set(),  # Remove all unique_together constraints
        ),
    ]

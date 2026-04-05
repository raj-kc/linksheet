# Generated migration: adds SheetColumn model for typed column definitions
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("sheets", "0006_add_activity_log"),
    ]

    operations = [
        migrations.CreateModel(
            name="SheetColumn",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("column_name", models.CharField(max_length=255)),
                ("column_type", models.CharField(
                    choices=[
                        ("text",     "Text"),
                        ("number",   "Number"),
                        ("email",    "Email"),
                        ("phone",    "Phone"),
                        ("date",     "Date"),
                        ("radio",    "Radio"),
                        ("dropdown", "Dropdown"),
                        ("checkbox", "Checkbox"),
                        ("file",     "File Upload"),
                    ],
                    default="text",
                    max_length=20,
                )),
                ("position", models.PositiveIntegerField(default=0)),
                ("options", models.JSONField(blank=True, default=list)),
                ("validation", models.JSONField(blank=True, default=dict)),
                ("default_value", models.CharField(blank=True, default="", max_length=512)),
                ("sheet", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="column_configs",
                    to="sheets.sheet",
                )),
            ],
            options={
                "ordering": ["position"],
            },
        ),
        migrations.AddIndex(
            model_name="sheetcolumn",
            index=models.Index(fields=["sheet", "position"], name="sheets_shee_sheet_i_pos_idx"),
        ),
        migrations.AlterUniqueTogether(
            name="sheetcolumn",
            unique_together={("sheet", "column_name")},
        ),
    ]

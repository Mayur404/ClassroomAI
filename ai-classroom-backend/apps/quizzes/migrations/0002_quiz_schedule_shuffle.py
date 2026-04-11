from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("quizzes", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="quiz",
            name="scheduled_for",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="quiz",
            name="shuffle_options",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="quiz",
            name="shuffle_questions",
            field=models.BooleanField(default=True),
        ),
    ]

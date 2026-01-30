from django.db import migrations, models
import django.db.models.deletion
from django.db.models.signals import pre_delete
from django.dispatch import receiver
from django.conf import settings
import os


def migrate_collection_to_tags(apps, schema_editor):
    """Migrate collection.name to tags[0] before removing collection field"""
    from django.db import transaction

    Video = apps.get_model("video", "Video")
    Collection = apps.get_model("video", "Collection")

    processed_count = 0
    skipped_count = 0
    error_count = 0

    with transaction.atomic():
        videos = Video.objects.select_related("collection").all()
        for video in videos:
            try:
                if video.collection_id:
                    try:
                        collection = Collection.objects.get(id=video.collection_id)
                        if collection.name and collection.name.strip():
                            # Replace tags with collection.name
                            video.tags = [collection.name]
                            video.save(update_fields=["tags"])
                            processed_count += 1
                        else:
                            # Collection exists but name is empty, skip
                            skipped_count += 1
                    except Collection.DoesNotExist:
                        # Collection reference exists but collection deleted
                        skipped_count += 1
                else:
                    # No collection, skip
                    skipped_count += 1
            except Exception as e:
                print(f"Error processing video {video.id}: {e}")
                error_count += 1

    print(f"Migration statistics:")
    print(f"  - Processed: {processed_count}")
    print(f"  - Skipped: {skipped_count}")
    print(f"  - Errors: {error_count}")


class Migration(migrations.Migration):
    dependencies = [
        ("video", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(migrate_collection_to_tags),
        migrations.RemoveField(
            model_name="video",
            name="collection",
        ),
        migrations.RemoveField(
            model_name="video",
            name="mindmap_content",
        ),
    ]

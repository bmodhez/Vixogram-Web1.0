from __future__ import annotations

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import Max
from django.db.models.functions import Coalesce
from django.utils import timezone

from a_rtchat.models import ChatGroup


class Command(BaseCommand):
    help = "Delete old private rooms (code rooms) to control DB size (batched)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=4,
            help="Delete private code rooms older than this many days (default: 4)",
        )
        parser.add_argument(
            "--batch",
            type=int,
            default=50,
            help="Max number of rooms to delete per run (default: 50)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Only report how many would be deleted.",
        )

    def handle(self, *args, **options):
        days = max(0, int(options.get("days") or 0))
        batch = max(1, int(options.get("batch") or 1))
        dry_run = bool(options.get("dry_run"))

        cutoff = timezone.now() - timedelta(days=days)

        # Delete only rooms that have been inactive for N days.
        # Inactivity is computed as:
        # - last message created time, if any
        # - else room.created
        ids = list(
            ChatGroup.objects.filter(
                is_private=True,
                is_code_room=True,
            )
            .annotate(
                last_message_at=Max('chat_messages__created'),
                last_activity_at=Coalesce('last_message_at', 'created'),
            )
            .filter(last_activity_at__lt=cutoff)
            .order_by('last_activity_at', 'id')
            .values_list('id', flat=True)[:batch]
        )

        if not ids:
            self.stdout.write("purge_old_rooms: 0 deleted")
            return

        if dry_run:
            self.stdout.write(f"purge_old_rooms: {len(ids)} would delete")
            return

        deleted_count, _ = ChatGroup.objects.filter(id__in=ids).delete()
        self.stdout.write(f"purge_old_rooms: {deleted_count} deleted")

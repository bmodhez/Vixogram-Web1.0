from __future__ import annotations

import time

from django.conf import settings
from django.core.management.base import BaseCommand

from a_rtchat.ipl_live import run_ipl_live_cycle


class Command(BaseCommand):
    help = 'Run IPL live score poller until match is no longer live.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--interval',
            type=int,
            default=int(getattr(settings, 'IPL_POLL_INTERVAL_SECONDS', 180) or 180),
            help='Polling interval in seconds while match is live (default from settings).',
        )

    def handle(self, *args, **options):
        interval = max(60, int(options.get('interval') or 180))
        self.stdout.write(self.style.NOTICE(f'IPL poller started (interval: {interval}s)'))

        while True:
            result = run_ipl_live_cycle()
            if not result.live:
                self.stdout.write(self.style.WARNING('No live IPL match found. Poller stopped.'))
                break

            if result.changed:
                self.stdout.write(self.style.SUCCESS('Score changed: broadcasted update.'))
            else:
                self.stdout.write('No score change.')

            time.sleep(interval)

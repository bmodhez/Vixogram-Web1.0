from __future__ import annotations

import time

from celery import shared_task
from django.conf import settings

from .natasha_bot import natasha_maybe_reply
from .ipl_live import run_ipl_live_cycle


@shared_task(bind=True, ignore_result=True)
def natasha_maybe_reply_task(self, chat_group_id: int, trigger_message_id: int):
    natasha_maybe_reply(chat_group_id=chat_group_id, trigger_message_id=trigger_message_id)


@shared_task(bind=True, ignore_result=True)
def run_ipl_live_score_cycle_task(self):
    result = run_ipl_live_cycle()
    return {
        'live': bool(result.live),
        'changed': bool(result.changed),
        'broadcasted': bool(result.broadcasted),
        'reason': result.reason,
    }


@shared_task(bind=True, ignore_result=True)
def run_ipl_live_score_poller_task(self):
    interval = int(getattr(settings, 'IPL_POLL_INTERVAL_SECONDS', 180) or 180)
    interval = max(60, interval)

    while True:
        result = run_ipl_live_cycle()
        if not result.live:
            break
        time.sleep(interval)


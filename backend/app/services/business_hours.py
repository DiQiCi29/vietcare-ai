"""Reception SLA: four Vietnam office hours, Monday–Friday, no holiday calendar."""
from datetime import datetime, time, timedelta, timezone

from backend.app.models.warranty import RequestStatus
from backend.app.services.eligibility import VIETNAM_TZ


def utc_now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def as_utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def local_time(value):
    return as_utc(value).astimezone(VIETNAM_TZ)


def reception_deadline(created_at):
    cursor = local_time(created_at)
    remaining = timedelta(hours=4)
    while True:
        if cursor.weekday() < 5:
            for start_hour, end_hour in ((8, 12), (13, 17)):
                start = datetime.combine(cursor.date(), time(start_hour), VIETNAM_TZ)
                end = datetime.combine(cursor.date(), time(end_hour), VIETNAM_TZ)
                cursor = max(cursor, start)
                available = end - cursor
                if available <= timedelta(0):
                    continue
                if remaining <= available:
                    return (cursor + remaining).astimezone(timezone.utc).replace(tzinfo=None)
                remaining -= available
                cursor = end
        cursor = datetime.combine(cursor.date() + timedelta(days=1), time(8), VIETNAM_TZ)


def is_overdue(request, now=None):
    return request.status == RequestStatus.RECEIVED and as_utc(now or utc_now()) >= as_utc(reception_deadline(request.created_at))


def sla_data(request, now=None):
    due = reception_deadline(request.created_at)
    first_response = min((h.created_at for h in request.status_history if h.status != RequestStatus.RECEIVED), default=None)
    return {
        'is_overdue': is_overdue(request, now),
        'response_due_at': local_time(due).isoformat(),
        'handled_late': first_response is not None and as_utc(first_response) > as_utc(due),
    }

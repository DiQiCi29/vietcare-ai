"""Allocate monthly numbers in the same transaction as the new request."""
import logging
import re

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

from backend.app.models.chat import ChatMessage
from backend.app.models.notification import NotificationLog
from backend.app.models.warranty import RequestCodeSequence, RequestStatusHistory, WarrantyRequest
from backend.app.services.business_hours import local_time, utc_now

logger = logging.getLogger(__name__)
CODE_FORMAT = re.compile(r'BH-(\d{2})(\d{2})-(\d{4,})')


def allocate_request_code(db, now=None):
    period = local_time(now or utc_now()).strftime('%m%y')
    if db.get(RequestCodeSequence, period) is None:
        prefix = f'BH-{period}-'
        existing = db.query(WarrantyRequest.request_code).filter(WarrantyRequest.request_code.startswith(prefix)).all()
        last = max((int(code[len(prefix):]) for (code,) in existing if code[len(prefix):].isdigit()), default=0)
        try:
            with db.begin_nested():
                db.add(RequestCodeSequence(period=period, last_number=last))
                db.flush()
        except IntegrityError:
            # Another transaction initialized this month first.
            pass
    number = db.execute(update(RequestCodeSequence).where(RequestCodeSequence.period == period)
                        .values(last_number=RequestCodeSequence.last_number + 1)
                        .returning(RequestCodeSequence.last_number)).scalar_one()
    return f'BH-{period}-{number:04d}'


def _is_current_format(code):
    match = CODE_FORMAT.fullmatch(code or '')
    return bool(match) and 1 <= int(match.group(1)) <= 12


def migrate_legacy_request_codes(db):
    """Rename old codes (e.g. BH-2026-0007) to BH-MMYY-NNNN by the month each request was created.

    Codes already in the new format are never changed; legacy requests are numbered after them,
    oldest first. References to the old code in emails, chat history and status notes are updated
    too. Safe to run repeatedly: once nothing is legacy it does nothing.
    """
    legacy = [r for r in db.query(WarrantyRequest).order_by(WarrantyRequest.created_at, WarrantyRequest.id)
              if not _is_current_format(r.request_code)]
    if not legacy:
        return {}
    taken = {r.request_code for r in db.query(WarrantyRequest.request_code)}
    renamed = {}
    for req in legacy:
        period = local_time(req.created_at or utc_now()).strftime('%m%y')
        seq = db.get(RequestCodeSequence, period)
        if seq is None:
            prefix = f'BH-{period}-'
            last = max((int(c[len(prefix):]) for c in taken if c.startswith(prefix) and c[len(prefix):].isdigit()),
                       default=0)
            seq = RequestCodeSequence(period=period, last_number=last)
            db.add(seq)
        new_code = None
        while new_code is None or new_code in taken:
            seq.last_number += 1
            new_code = f'BH-{period}-{seq.last_number:04d}'
        renamed[req.request_code] = new_code
        taken.add(new_code)
        # Core update keeps updated_at as-is: a rename is not a status change.
        db.execute(update(WarrantyRequest).where(WarrantyRequest.id == req.id)
                   .values(request_code=new_code, updated_at=WarrantyRequest.updated_at)
                   .execution_options(synchronize_session=False))
    db.flush()
    db.expire_all()

    # Longest codes first so one code never rewrites part of another.
    pattern = re.compile('|'.join(re.escape(c) for c in sorted(renamed, key=len, reverse=True)))

    def swap(text):
        return pattern.sub(lambda m: renamed[m.group(0)], text) if text else text

    for model, fields in ((NotificationLog, ('subject', 'content')), (ChatMessage, ('message',)),
                          (RequestStatusHistory, ('notes',))):
        for row in db.query(model):
            for field in fields:
                value = getattr(row, field)
                new_value = swap(value)
                if new_value != value:
                    setattr(row, field, new_value)
    db.commit()
    for old, new in renamed.items():
        logger.info('Đổi mã phiếu %s -> %s', old, new)
    return renamed

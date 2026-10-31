"""Allocate monthly numbers in the same transaction as the new request."""
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

from backend.app.models.warranty import RequestCodeSequence, WarrantyRequest
from backend.app.services.business_hours import local_time, utc_now


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

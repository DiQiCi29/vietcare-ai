"""Office-hour boundaries, monthly numbers and private uploads; isolated from real data."""
import base64
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import test_security as fixtures
from backend.app.core.config import settings
from backend.app.models.warranty import Attachment, RequestCodeSequence, WarrantyRequest, RequestStatus as S, RequestStatusHistory
from backend.app.services.business_hours import reception_deadline, is_overdue
from backend.app.services.eligibility import VIETNAM_TZ
from backend.app.services.request_codes import allocate_request_code


def vietnam(value):
    return datetime.fromisoformat(value).replace(tzinfo=VIETNAM_TZ).astimezone(timezone.utc).replace(tzinfo=None)


PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRusAAAAASUVORK5CYII=')


class BusinessHourTests(unittest.TestCase):
    def test_lunch_evenings_weekends_and_no_holiday_exclusions(self):
        cases = [
            ('2026-10-19T08:00', '2026-10-19T12:00'),
            ('2026-10-19T10:00', '2026-10-19T15:00'),
            ('2026-10-19T12:30', '2026-10-19T17:00'),
            ('2026-10-19T16:00', '2026-10-20T11:00'),
            ('2026-10-23T16:00', '2026-10-26T11:00'),
            ('2026-10-24T10:00', '2026-10-26T12:00'),
            ('2026-10-19T18:00', '2026-10-20T12:00'),
            ('2026-10-19T07:00', '2026-10-19T12:00'),
            ('2026-09-02T08:00', '2026-09-02T12:00'),
        ]
        for start, due in cases:
            with self.subTest(start=start):
                self.assertEqual(reception_deadline(vietnam(start)), vietnam(due))

    def test_only_received_tickets_are_overdue_at_deadline(self):
        req = WarrantyRequest(status=S.RECEIVED, created_at=vietnam('2026-10-23T16:00'))
        due = vietnam('2026-10-26T11:00')
        self.assertFalse(is_overdue(req, due - timedelta(microseconds=1)))
        self.assertTrue(is_overdue(req, due))
        req.status = S.VERIFYING
        self.assertFalse(is_overdue(req, due + timedelta(days=10)))


class WarrantyExtensionTests(unittest.TestCase):
    headers = fixtures.SecurityTests.headers
    call = fixtures.SecurityTests.call
    state = fixtures.SecurityTests.state

    @classmethod
    def setUpClass(cls):
        fixtures.SecurityTests.setUpClass()
        cls.password = fixtures.SecurityTests.password

    def setUp(self):
        fixtures.SecurityTests.setUp(self)
        self.directory = tempfile.TemporaryDirectory(prefix='vietcare-media-tests-')
        self.addCleanup(self.directory.cleanup)
        self.upload_setting = patch.object(settings, 'UPLOAD_DIR', self.directory.name)
        self.upload_setting.start()
        self.addCleanup(self.upload_setting.stop)

    def payload(self, **extra):
        return {'sold_item_id': 1, 'error_group': 'Không nguồn', 'error_description': 'Thiết bị không lên điện',
                'support_address': 'Đà Nẵng', **extra}

    def upload(self, files=None, payload=None):
        import json
        return self.call('POST', '/customer/requests-with-media', 'CUSTOMER', 1,
                         data={'payload': json.dumps(payload or self.payload())},
                         files=files or [('files', ('incident.png', PNG, 'image/png'))])

    def test_monthly_sequence_resets_uses_vietnam_time_and_keeps_old_codes(self):
        with self.Session() as db:
            old_code = db.get(WarrantyRequest, 1).request_code
            self.assertEqual(allocate_request_code(db, vietnam('2026-10-31T23:59')), 'BH-1026-0001')
            self.assertEqual(allocate_request_code(db, vietnam('2026-10-31T23:59')), 'BH-1026-0002')
            self.assertEqual(allocate_request_code(db, vietnam('2026-11-01T00:00')), 'BH-1126-0001')
            db.commit()
            self.assertEqual(db.get(WarrantyRequest, 1).request_code, old_code)
            self.assertEqual(db.get(RequestCodeSequence, '1026').last_number, 2)
            self.assertEqual(allocate_request_code(db, vietnam('2026-10-31T23:59')), 'BH-1026-0003')
            db.rollback()
            self.assertEqual(allocate_request_code(db, vietnam('2026-10-31T23:59')), 'BH-1026-0003')

    def test_creation_uses_new_monthly_code_and_preserves_history(self):
        self.state(S.COMPLETED)
        with patch('backend.app.api.v1.endpoints.utc_now', return_value=vietnam('2026-10-26T10:00')):
            response = self.call('POST', '/customer/requests', 'CUSTOMER', 1, json=self.payload())
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['request_code'], 'BH-1026-0001')
        with self.Session() as db:
            req = db.get(WarrantyRequest, response.json()['request_id'])
            self.assertEqual(len(req.status_history), 1)
            self.assertEqual(req.status_history[0].status, S.RECEIVED)

    def test_upload_and_private_download_for_owner_and_assigned_technician(self):
        self.state(S.COMPLETED)
        response = self.upload()
        self.assertEqual(response.status_code, 200, response.text)
        request_id = response.json()['request_id']
        detail = self.call('GET', f'/requests/{request_id}', 'CUSTOMER', 1).json()
        self.assertEqual(detail['attachments'][0]['file_name'], 'incident.png')
        path = detail['attachments'][0]['url'].removeprefix('/api/v1')
        self.assertEqual(self.client.get('/api/v1' + path).status_code, 401)
        self.assertEqual(self.call('GET', path, 'CUSTOMER', 2).status_code, 403)
        self.assertEqual(self.call('GET', path, 'TECHNICIAN', 3).status_code, 403)
        self.assertEqual(self.call('GET', path, 'CUSTOMER', 1).content, PNG)
        self.assertEqual(self.call('GET', path).content, PNG)
        with self.Session() as db:
            req = db.get(WarrantyRequest, request_id)
            req.status, req.technician_id = S.ASSIGNED, 3
            db.add(RequestStatusHistory(request_id=request_id, status=S.ASSIGNED, notes='INTERNAL', is_internal_note=True))
            db.commit()
            self.assertEqual(db.query(Attachment).count(), 1)
        self.assertEqual(self.call('GET', path, 'TECHNICIAN', 3).content, PNG)
        self.assertEqual(self.call('GET', path, 'TECHNICIAN', 4).status_code, 403)
        self.assertEqual(self.call('GET', f'/requests/{request_id}', 'CUSTOMER', 2).status_code, 403)
        owner = self.call('GET', f'/requests/{request_id}', 'CUSTOMER', 1).json()
        self.assertNotIn('INTERNAL', str(owner))
        self.assertNotIn(self.directory.name, str(owner))

    def test_rejected_uploads_and_duplicate_tickets_leave_no_files_or_rows(self):
        cases = [
            [('files', ('bad.svg', b'<svg></svg>', 'image/svg+xml'))],
            [('files', ('fake.png', b'<html>invalid</html>', 'image/png'))],
            [('files', ('fake.jpg', PNG, 'image/jpeg'))],
            [('files', ('ok.png', PNG, 'image/png'))] * 6,
            [('files', ('ok.png', PNG, 'image/png')), ('files', ('bad.png', b'bad', 'image/png'))],
        ]
        for files in cases:
            response = self.upload(files)
            self.assertEqual(response.status_code, 422, response.text)
            self.assertEqual(list(Path(self.directory.name).iterdir()), [])
        with patch.object(settings, 'MAX_UPLOAD_SIZE_MB', 0):
            self.assertEqual(self.upload().status_code, 413)
        self.assertEqual(self.upload().status_code, 400)  # Existing active request.
        self.assertEqual(self.upload(payload=self.payload(sold_item_id=2)).status_code, 403)
        with self.Session() as db:
            self.assertEqual(db.query(Attachment).count(), 0)
            self.assertEqual(db.query(WarrantyRequest).count(), 2)
        self.assertEqual(list(Path(self.directory.name).iterdir()), [])

    def test_overdue_list_kpi_and_historical_late_response(self):
        with self.Session() as db:
            db.get(WarrantyRequest, 1).created_at = vietnam('2026-10-23T16:00')
            db.get(WarrantyRequest, 2).created_at = vietnam('2026-10-26T10:00')
            db.commit()
        with patch('backend.app.api.v1.endpoints.utc_now', return_value=vietnam('2026-10-26T11:00')):
            rows = self.call('GET', '/staff/requests?overdue_only=true').json()
            self.assertEqual([r['id'] for r in rows], [1])
            self.assertTrue(rows[0]['is_overdue'])
            self.assertEqual(self.call('GET', '/staff/kpi').json()['overdue_count'], 1)
        with self.Session() as db:
            db.get(WarrantyRequest, 1).status = S.VERIFYING
            db.add(RequestStatusHistory(request_id=1, status=S.VERIFYING, created_at=vietnam('2026-10-26T11:01')))
            db.commit()
        detail = self.call('GET', '/requests/1').json()
        self.assertFalse(detail['is_overdue'])
        self.assertTrue(detail['handled_late'])

    def test_manager_overview_is_admin_only_and_uses_real_counts(self):
        for role, user in [('CUSTOMER', 1), ('CSKH', 2), ('TECHNICIAN', 3)]:
            self.assertEqual(self.call('GET', '/admin/overview', role, user).status_code, 403)
        self.state(S.IN_PROGRESS, 3)
        response = self.call('GET', '/admin/overview', 'ADMIN', 1)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['kpi']['total_requests'], 2)
        self.assertEqual(response.json()['technicians'][0]['in_progress'], 1)


if __name__ == '__main__':
    unittest.main()

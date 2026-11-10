"""Run with: python -m unittest discover -s backend/tests -v

All requests use a separate in-memory database; no production data or AI calls.
"""
import os
os.environ['DATABASE_URL'] = 'sqlite://'
os.environ['DEBUG'] = 'false'
for _name in ('TWILIO_ACCOUNT_SID', 'TWILIO_AUTH_TOKEN', 'TWILIO_VERIFY_SERVICE_SID'):
    os.environ[_name] = ''  # Never reach Twilio from tests, even when .env holds real keys.

from datetime import date, timedelta
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.core.database import Base, get_db
from backend.app.core.security import create_access_token, get_password_hash
from backend.app.api.v1.endpoints import router
from backend.app.models.user import Customer, User, UserRole
from backend.app.models.product import Product, SoldItem
from backend.app.models.chat import ChatSession
from backend.app.models.warranty import (
    WarrantyRequest, RequestStatus as S, RequestStatusHistory, Inspection,
)


class SecurityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.password = get_password_hash('test-password')

    def setUp(self):
        self.engine = create_engine('sqlite://', poolclass=StaticPool,
                                    connect_args={'check_same_thread': False})
        @event.listens_for(self.engine, 'connect')
        def foreign_keys(connection, _):
            connection.execute('PRAGMA foreign_keys=ON')
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        with self.Session() as db:
            db.add_all([
                Customer(id=i, full_name=f'Customer {i}', phone=f'090000000{i}',
                         email=f'customer{i}@example.test', hashed_password=self.password)
                for i in (1, 2)
            ])
            db.add_all([
                User(id=i, name=f'Staff {i}', username=f'staff{i}', email=f'staff{i}@example.test',
                     role=role, hashed_password=self.password)
                for i, role in ((1, UserRole.ADMIN), (2, UserRole.CSKH),
                                (3, UserRole.TECHNICIAN), (4, UserRole.TECHNICIAN))
            ])
            db.add(Product(id=1, name='Test product', model='TEST', category='Tivi'))
            db.commit()
            db.add_all([
                SoldItem(id=i, product_id=1, customer_id=i, serial_number=f'SERIAL{i}',
                         purchase_date=date.today(), warranty_expire_date=date.today())
                for i in (1, 2)
            ])
            db.commit()
            db.add_all([
                WarrantyRequest(id=i, request_code=f'TEST-{i}', customer_id=i, sold_item_id=i,
                                error_group='Test', error_description='Test', support_address='Test',
                                status=S.RECEIVED)
                for i in (1, 2)
            ])
            db.add(ChatSession(session_id='private-session', customer_id=2))
            db.commit()
        app = FastAPI()
        app.include_router(router, prefix='/api/v1')
        def override_db():
            with self.Session() as db:
                yield db
        app.dependency_overrides[get_db] = override_db
        self.client = TestClient(app)
        self.ai = patch('backend.app.api.v1.endpoints.generate_chat_response', return_value={'reply': 'Test reply'})
        self.ai.start()
        self.addCleanup(self.ai.stop)
        self.addCleanup(self.client.close)
        self.addCleanup(self.engine.dispose)

    def headers(self, role='CSKH', user_id=2):
        return {'Authorization': 'Bearer ' + create_access_token(user_id, role)}

    def call(self, method, path, role='CSKH', user_id=2, **kwargs):
        return self.client.request(method, '/api/v1' + path, headers=self.headers(role, user_id), **kwargs)

    def state(self, state, technician=None):
        with self.Session() as db:
            req = db.get(WarrantyRequest, 1)
            req.status, req.technician_id = state, technician
            db.commit()

    def test_every_private_route_requires_token(self):
        paths = [('GET', '/customer/products/0900000001'), ('GET', '/customer/requests/0900000001'),
                 ('POST', '/customer/requests'), ('POST', '/customer/contact'), ('POST', '/customer/chat'),
                 ('GET', '/staff/requests'), ('GET', '/staff/technicians'), ('GET', '/staff/kpi'),
                 ('PUT', '/staff/requests/1/status'), ('POST', '/staff/requests/1/verify'),
                 ('POST', '/staff/requests/1/assign'), ('POST', '/staff/requests/1/complete'),
                 ('POST', '/staff/requests/1/repeat-call')]
        for method, path in paths:
            with self.subTest(path=path):
                response = self.client.request(method, '/api/v1' + path, json={})
                self.assertEqual(response.status_code, 401, response.text)
        self.assertEqual(self.client.get('/api/v1/products').status_code, 200)

    def test_invalid_expired_and_missing_claim_tokens(self):
        from jose import jwt
        from backend.app.core.config import settings
        tokens = ['invalid', create_access_token(1, 'ADMIN', timedelta(seconds=-1)),
                  jwt.encode({'sub': '1', 'role': 'ADMIN'}, settings.SECRET_KEY, algorithm=settings.ALGORITHM),
                  create_access_token(1, 'UNKNOWN')]
        for token in tokens:
            response = self.client.get('/api/v1/staff/requests', headers={'Authorization': f'Bearer {token}'})
            self.assertEqual(response.status_code, 401)

    def test_login_and_disabled_or_changed_role(self):
        login = self.client.post('/api/v1/auth/login', json={'username_or_phone': 'staff2', 'password': 'test-password'})
        self.assertEqual(login.status_code, 200)
        self.assertEqual(self.client.get('/api/v1/staff/requests', headers={
            'Authorization': 'Bearer ' + login.json()['access_token']}).status_code, 200)
        with self.Session() as db:
            db.get(User, 2).is_active = False
            db.get(Customer, 1).is_active = False
            db.commit()
        self.assertEqual(self.call('GET', '/staff/requests').status_code, 401)
        self.assertEqual(self.call('GET', '/customer/products/0900000001', 'CUSTOMER', 1).status_code, 401)
        self.assertEqual(self.client.post('/api/v1/auth/login', json={
            'username_or_phone': 'staff2', 'password': 'test-password'}).status_code, 403)
        self.assertEqual(self.call('GET', '/staff/requests', 'ADMIN', 3).status_code, 401)

    def test_customer_and_technician_data_isolation(self):
        self.assertEqual(self.call('GET', '/customer/products/0900000001', 'CUSTOMER', 1).status_code, 200)
        for resource in ('products', 'requests'):
            self.assertEqual(self.call('GET', f'/customer/{resource}/0900000002', 'CUSTOMER', 1).status_code, 403)
        self.assertEqual(self.call('GET', '/staff/requests', 'CUSTOMER', 1).status_code, 403)
        self.state(S.ASSIGNED, 3)
        result = self.call('GET', '/staff/requests?technician_id=4', 'TECHNICIAN', 3)
        self.assertEqual([r['id'] for r in result.json()], [1])
        for path in ('/staff/technicians', '/staff/kpi', '/customer/products/0900000001'):
            self.assertEqual(self.call('GET', path, 'TECHNICIAN', 3).status_code, 403)

    def test_chat_ownership_and_general_chat(self):
        for payload in ({'query': 'test', 'sold_item_id': 2}, {'query': 'test', 'session_id': 'private-session'}):
            self.assertEqual(self.call('POST', '/customer/chat', 'CUSTOMER', 1, json=payload).status_code, 403)
        result = self.call('POST', '/customer/chat', 'CUSTOMER', 1, json={'query': 'test', 'session_id': 'new-session'})
        self.assertEqual(result.status_code, 200, result.text)
        with self.Session() as db:
            self.assertEqual(db.query(ChatSession).filter_by(session_id='new-session').one().customer_id, 1)

    def test_customer_cannot_impersonate_or_choose_foreign_product(self):
        payload = {'sold_item_id': 2, 'error_group': 'Test', 'error_description': 'Test', 'support_address': 'Test'}
        self.assertEqual(self.call('POST', '/customer/requests', 'CUSTOMER', 1, json=payload).status_code, 403)
        payload.update(sold_item_id=1, customer_phone='0900000002')
        self.assertEqual(self.call('POST', '/customer/requests', 'CUSTOMER', 1, json=payload).status_code, 403)
        payload.update(customer_phone='0900000001', channel='Điện thoại')
        self.assertEqual(self.call('POST', '/customer/requests', 'CUSTOMER', 1, json=payload).status_code, 403)
        self.assertEqual(self.call('POST', '/customer/contact', 'CUSTOMER', 1,
                                   json={'phone': '0900000002', 'message': 'Test', 'sold_item_id': 1}).status_code, 403)

    def test_valid_workflow_and_audit_actor(self):
        self.assertEqual(self.call('POST', '/staff/requests/1/verify', json={'action': 'VALID'}).status_code, 200)
        self.assertEqual(self.call('POST', '/staff/requests/1/assign', json={
            'technician_id': 3, 'appointment_date': '2026-10-20'}).status_code, 200)
        self.assertEqual(self.call('PUT', '/staff/requests/1/status', 'TECHNICIAN', 3,
                                   json={'new_status': S.IN_PROGRESS}).status_code, 200)
        result = self.call('POST', '/staff/requests/1/complete', 'TECHNICIAN', 3,
                           json={'conclusion': 'Được bảo hành', 'repair_content': 'Replaced component'})
        self.assertEqual(result.status_code, 200, result.text)
        with self.Session() as db:
            req = db.get(WarrantyRequest, 1)
            self.assertEqual(req.status, S.COMPLETED)
            self.assertIsNotNone(req.completed_at)
            self.assertEqual(db.query(Inspection).one().technician_id, 3)
            self.assertEqual([h.performed_by_id for h in req.status_history], [2, 2, 3, 3])

    def test_skip_and_terminal_transitions_rejected_without_writes(self):
        for state in (S.RECEIVED, S.COMPLETED, S.REJECTED):
            self.state(state, 3)
            for path, payload, method in (
                ('/complete', {'conclusion': 'Được bảo hành', 'repair_content': 'Test'}, 'POST'),
                ('/assign', {'technician_id': 3, 'appointment_date': '2026-10-20'}, 'POST'),
                ('/status', {'new_status': S.COMPLETED, 'conclusion': 'Được bảo hành', 'repair_content': 'Test'}, 'PUT'),
            ):
                role, user = ('TECHNICIAN', 3) if path != '/assign' else ('CSKH', 2)
                response = self.call(method, '/staff/requests/1' + path, role, user, json=payload)
                self.assertEqual(response.status_code, 409, response.text)
        with self.Session() as db:
            self.assertEqual(db.query(Inspection).count(), 0)
            self.assertEqual(db.query(RequestStatusHistory).count(), 0)

    def test_wrong_technician_and_manager_cannot_repair(self):
        self.state(S.ASSIGNED, 3)
        for role, user in (('TECHNICIAN', 4), ('CSKH', 2), ('ADMIN', 1)):
            response = self.call('PUT', '/staff/requests/1/status', role, user, json={'new_status': S.IN_PROGRESS})
            self.assertEqual(response.status_code, 403, response.text)
        self.assertEqual(self.call('POST', '/staff/requests/1/verify', 'TECHNICIAN', 3,
                                   json={'action': 'REJECT', 'notes': 'Test'}).status_code, 403)

    def test_assignment_validation_and_decline(self):
        self.state(S.VERIFYING)
        for payload in ({'technician_id': 1, 'appointment_date': '2026-10-20'},
                        {'technician_id': 999, 'appointment_date': '2026-10-20'},
                        {'technician_id': 3, 'appointment_date': 'invalid'}, {'technician_id': 3}):
            self.assertEqual(self.call('POST', '/staff/requests/1/assign', json=payload).status_code, 422)
        self.state(S.ASSIGNED, 3)
        response = self.call('PUT', '/staff/requests/1/status', 'TECHNICIAN', 3,
                             json={'new_status': S.ASSIGNED, 'notes': 'Cannot attend'})
        self.assertEqual(response.status_code, 200, response.text)
        with self.Session() as db:
            self.assertIsNone(db.get(WarrantyRequest, 1).technician_id)
        self.assertEqual(self.call('POST', '/staff/requests/1/assign', json={
            'technician_id': 4, 'appointment_date': '2026-10-21'}).status_code, 200)

    def test_rejection_requires_reason_and_records_verification(self):
        self.assertEqual(self.call('POST', '/staff/requests/1/verify', json={'action': 'REJECT'}).status_code, 422)
        result = self.call('POST', '/staff/requests/1/verify', json={'action': 'REJECT', 'notes': 'Not covered'})
        self.assertEqual(result.status_code, 200, result.text)
        with self.Session() as db:
            self.assertEqual([h.status for h in db.get(WarrantyRequest, 1).status_history], [S.VERIFYING, S.REJECTED])

    def test_invalid_status_and_incomplete_report(self):
        self.state(S.IN_PROGRESS, 3)
        for payload in ({'new_status': 'arbitrary'}, {'new_status': S.COMPLETED},
                        {'new_status': S.COMPLETED, 'conclusion': 'Được bảo hành', 'repair_content': '  '}):
            self.assertEqual(self.call('PUT', '/staff/requests/1/status', 'TECHNICIAN', 3, json=payload).status_code, 422)

    def test_customer_and_phone_reception_still_create_requests(self):
        self.state(S.COMPLETED)
        payload = {'sold_item_id': 1, 'error_group': 'Test', 'error_description': 'Test', 'support_address': 'Test'}
        result = self.call('POST', '/customer/requests', 'CUSTOMER', 1, json=payload)
        self.assertEqual(result.status_code, 200, result.text)
        with self.Session() as db:
            db.get(WarrantyRequest, 2).status = S.COMPLETED
            db.commit()
        result = self.call('POST', '/customer/requests', json={
            'customer_phone': '0900000002', 'sold_item_id': 2,
            'channel': 'Điện thoại', 'error_group': 'Test', 'error_description': 'Test', 'support_address': 'Test'})
        self.assertEqual(result.status_code, 200, result.text)
        with self.Session() as db:
            self.assertEqual(db.get(WarrantyRequest, result.json()['request_id']).created_by_user_id, 2)

    def test_internal_notes_are_hidden_from_customer(self):
        with self.Session() as db:
            db.add(RequestStatusHistory(request_id=1, status=S.RECEIVED,
                                        notes='Private staff note', is_internal_note=True))
            db.commit()
        result = self.call('GET', '/customer/requests/0900000001', 'CUSTOMER', 1)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()[0]['timeline'], [])

    def test_generic_status_endpoint_cannot_bypass_validation(self):
        self.state(S.VERIFYING)
        for payload in ({'new_status': S.ASSIGNED, 'technician_id': 1, 'appointment_date': '2026-10-20'},
                        {'new_status': S.ASSIGNED, 'technician_id': 3},
                        {'new_status': S.REJECTED, 'notes': '  '}):
            self.assertEqual(self.call('PUT', '/staff/requests/1/status', json=payload).status_code, 422)
        self.assertEqual(self.call('PUT', '/staff/requests/1/status', json={
            'new_status': S.PENDING_ADDITIONAL_INFO, 'notes': 'Need photos'}).status_code, 200)
        self.assertEqual(self.call('POST', '/staff/requests/1/verify', json={'action': 'VALID'}).status_code, 200)
        self.assertEqual(self.call('PUT', '/staff/requests/1/status', json={
            'new_status': S.ASSIGNED, 'technician_id': 3, 'appointment_date': '2026-10-20'}).status_code, 200)
        self.assertEqual(self.call('PUT', '/staff/requests/1/status', 'TECHNICIAN', 3, json={
            'new_status': S.IN_PROGRESS, 'technician_id': 4}).status_code, 403)

    def test_stale_transition_does_not_overwrite_current_status(self):
        from fastapi import HTTPException
        from backend.app.services.warranty_workflow import transition
        from backend.app.schemas.api_schemas import StatusUpdateInput
        with self.Session() as stale_db:
            stale = stale_db.get(WarrantyRequest, 1)
            actor = stale_db.get(User, 2)
            self.state(S.COMPLETED)
            with self.assertRaises(HTTPException) as raised:
                transition(stale_db, stale, actor, StatusUpdateInput(new_status=S.VERIFYING))
            self.assertEqual(raised.exception.status_code, 409)
        with self.Session() as db:
            self.assertEqual(db.get(WarrantyRequest, 1).status, S.COMPLETED)

    def test_appointment_and_workload_filters_keep_role_boundaries(self):
        from datetime import datetime
        with self.Session() as db:
            first, second = db.get(WarrantyRequest, 1), db.get(WarrantyRequest, 2)
            first.status, first.technician_id = S.ASSIGNED, 3
            first.appointment_date = datetime(2026, 10, 24, 18, 30)
            first.repeat_call_count = 2
            second.status, second.technician_id = S.COMPLETED, 4
            second.appointment_date = datetime(2026, 10, 25, 9)
            db.commit()
        for query in ('appointment_from=2026-10-24&appointment_to=2026-10-24',
                      'pending_only=true', 'repeat_calls_only=true'):
            response = self.call('GET', '/staff/requests?' + query)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual([r['id'] for r in response.json()], [1])
        self.assertEqual(self.call('GET', '/staff/requests?appointment_from=2026-10-25',
                                   'TECHNICIAN', 3).json(), [])
        self.assertEqual(self.call('GET', '/staff/requests?appointment_from=2026-10-25&appointment_to=2026-10-24').status_code, 422)
        stats = self.call('GET', '/staff/kpi').json()
        self.assertEqual(stats['waiting_count'], 1)
        self.assertEqual(stats['completed_count'], 1)
        self.assertEqual(stats['repeat_calls'], 2)


if __name__ == '__main__':
    unittest.main()

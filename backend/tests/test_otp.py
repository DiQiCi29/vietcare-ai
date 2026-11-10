"""Customer OTP login: demo provider, Twilio Verify transport, and staff password login."""
import unittest
from unittest.mock import patch

import httpx
import test_security as fixtures
from backend.app.core.config import settings
from backend.app.models.user import Customer
from backend.app.services import otp

SID = 'VA' + '0' * 32


class OtpFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.SecurityTests.setUpClass()
        cls.password = fixtures.SecurityTests.password

    def setUp(self):
        fixtures.SecurityTests.setUp(self)
        otp.reset_demo_state()
        self.addCleanup(otp.reset_demo_state)

    def post(self, path, **body):
        return self.client.post('/api/v1/auth' + path, json=body)


class OtpLoginTests(OtpFixture):
    def request_code(self, phone='0900000001'):
        response = self.post('/otp/request', phone=phone)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_customer_password_login_is_rejected_but_staff_still_works(self):
        response = self.post('/login', username_or_phone='0900000001', password='test-password')
        self.assertEqual(response.status_code, 400)
        self.assertIn('OTP', response.json()['detail'])
        self.assertEqual(self.post('/login', username_or_phone='staff2', password='test-password').status_code, 200)

    def test_demo_code_logs_in_once(self):
        sent = self.request_code()
        self.assertEqual(sent['mode'], 'demo')
        login = self.post('/otp/verify', phone='0900000001', code=sent['demo_code'])
        self.assertEqual(login.status_code, 200, login.text)
        token = login.json()
        self.assertEqual((token['user_type'], token['role'], token['user_id']), ('customer', 'CUSTOMER', 1))
        products = self.client.get('/api/v1/customer/products/0900000001',
                                   headers={'Authorization': 'Bearer ' + token['access_token']})
        self.assertEqual(products.status_code, 200)
        self.assertEqual(self.post('/otp/verify', phone='0900000001', code=sent['demo_code']).status_code, 400)

    def test_international_format_and_unknown_or_locked_accounts(self):
        sent = self.request_code('+84900000001')
        self.assertEqual(self.post('/otp/verify', phone='84900000001', code=sent['demo_code']).status_code, 200)
        self.assertEqual(self.post('/otp/request', phone='0999999999').status_code, 404)
        self.assertEqual(self.post('/otp/request', phone='not-a-phone').status_code, 422)
        with self.Session() as db:
            db.get(Customer, 2).is_active = False
            db.commit()
        self.assertEqual(self.post('/otp/request', phone='0900000002').status_code, 403)

    def test_wrong_codes_expire_the_code_and_resend_is_throttled(self):
        sent = self.request_code()
        self.assertEqual(self.post('/otp/request', phone='0900000001').status_code, 429)
        wrong = '000000' if sent['demo_code'] != '000000' else '111111'
        for _ in range(settings.OTP_MAX_ATTEMPTS):
            self.assertEqual(self.post('/otp/verify', phone='0900000001', code=wrong).status_code, 400)
        # The correct code no longer works after too many failures.
        self.assertEqual(self.post('/otp/verify', phone='0900000001', code=sent['demo_code']).status_code, 400)

    def test_dev_bypass_phone_logs_in_without_code_and_never_sends(self):
        with patch.object(settings, 'OTP_BYPASS_PHONES', '0900000002, 0900000009'), \
                patch('backend.app.services.otp.send_code') as send:
            response = self.post('/otp/request', phone='0900000002')
            self.assertEqual(response.status_code, 200, response.text)
            body = response.json()
            self.assertEqual(body['mode'], 'bypass')
            self.assertEqual((body['token']['user_id'], body['token']['role']), (2, 'CUSTOMER'))
            send.assert_not_called()
            products = self.client.get('/api/v1/customer/products/0900000002',
                                       headers={'Authorization': 'Bearer ' + body['token']['access_token']})
            self.assertEqual(products.status_code, 200)
        # Other customers still need a code, and an emptied setting disables the bypass.
        self.assertEqual(self.request_code('0900000001')['mode'], 'demo')
        with patch.object(settings, 'OTP_BYPASS_PHONES', ''):
            self.assertEqual(self.request_code('0900000002')['mode'], 'demo')

    def test_expired_code_is_rejected(self):
        with patch.object(settings, 'OTP_TTL_SECONDS', -1):
            sent = self.request_code()
        response = self.post('/otp/verify', phone='0900000001', code=sent['demo_code'])
        self.assertEqual(response.status_code, 400)
        self.assertIn('hết hạn', response.json()['detail'])


class TwilioVerifyTests(OtpFixture):
    def twilio(self):
        return patch.multiple(settings, TWILIO_ACCOUNT_SID='AC-test', TWILIO_AUTH_TOKEN='secret-token',
                              TWILIO_VERIFY_SERVICE_SID=SID)

    def test_send_and_check_use_verify_api_without_exposing_codes(self):
        with self.twilio(), patch('backend.app.services.otp.httpx.post',
                                  return_value=httpx.Response(201, json={'status': 'pending'})) as post:
            sent = self.post('/otp/request', phone='0900000001')
            self.assertEqual(sent.status_code, 200, sent.text)
            self.assertEqual(sent.json()['mode'], 'twilio')
            self.assertNotIn('demo_code', sent.json())
            self.assertTrue(post.call_args.args[0].endswith(f'/Services/{SID}/Verifications'))
            self.assertEqual(post.call_args.kwargs['data']['To'], '+84900000001')
            self.assertEqual(post.call_args.kwargs['auth'], ('AC-test', 'secret-token'))

            post.return_value = httpx.Response(200, json={'status': 'pending'})
            self.assertEqual(self.post('/otp/verify', phone='0900000001', code='123456').status_code, 400)
            post.return_value = httpx.Response(200, json={'status': 'approved'})
            login = self.post('/otp/verify', phone='0900000001', code='123456')
            self.assertEqual(login.status_code, 200, login.text)
            self.assertTrue(post.call_args.args[0].endswith('/VerificationCheck'))

    def test_trial_and_network_errors_are_translated_and_do_not_block_retry(self):
        with self.twilio(), patch('backend.app.services.otp.httpx.post',
                                  return_value=httpx.Response(400, json={'code': 21608})):
            response = self.post('/otp/request', phone='0900000001')
            self.assertEqual(response.status_code, 400)
            self.assertIn('đã xác minh', response.json()['detail'])
        with self.twilio(), patch('backend.app.services.otp.httpx.post', side_effect=httpx.ConnectError('offline')):
            self.assertEqual(self.post('/otp/request', phone='0900000001').status_code, 503)
        with self.twilio(), patch('backend.app.services.otp.httpx.post',
                                  return_value=httpx.Response(404, json={'code': 20404})):
            self.assertIn('hết hạn', self.post('/otp/verify', phone='0900000001', code='123456').json()['detail'])


if __name__ == '__main__':
    unittest.main()

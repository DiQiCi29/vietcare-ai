import os
os.environ['DATABASE_URL'] = 'sqlite://'
os.environ['DEBUG'] = 'false'

from datetime import timedelta
import unittest
from unittest.mock import patch

import httpx
import test_security as fixtures
from backend.app.core.security import get_password_hash
from backend.app.models.policy import WarrantyPolicy
from backend.app.models.product import SoldItem
from backend.app.models.warranty import WarrantyRequest, RequestStatus as S, RequestStatusHistory
from backend.app.rag.advice import generate_chat_response
from backend.app.rag.retriever import sync_policies_to_vector_store, retrieve_relevant_policies
from backend.app.rag.vector_store import SimpleVectorStore
from backend.app.services.eligibility import today_vietnam


class ChatTests(unittest.TestCase):
    headers = fixtures.SecurityTests.headers
    call = fixtures.SecurityTests.call
    state = fixtures.SecurityTests.state

    @classmethod
    def setUpClass(cls):
        cls.password = get_password_hash('test-password')

    def setUp(self):
        fixtures.SecurityTests.setUp(self)
        self.ai.stop()  # Test the actual generation/retrieval pipeline, without network calls.
        self.provider = patch('backend.app.rag.advice._call_gemini', return_value=None)
        self.provider.start()
        self.addCleanup(self.provider.stop)
        with self.Session() as db:
            item = db.get(SoldItem, 1)
            item.product.name = 'Điều hòa Daikin'
            item.product.category = 'Điều hòa'
            item.product.brand = 'Daikin'
            item.product.model = 'FTF50XV1V'
            db.get(WarrantyRequest, 1).request_code = 'BH-2026-0001'
            db.get(WarrantyRequest, 2).request_code = 'BH-2026-0002'
            db.add_all([
                WarrantyPolicy(product_category='Chung', brand='Viettronimex', error_group='Từ chối bảo hành',
                    title='Loại trừ bảo hành', is_covered=False,
                    content='Từ chối bảo hành miễn phí với hư hỏng do rơi vỡ, va đập, ngấm nước, tự ý tháo sửa.',
                    conditions='Nhân viên kiểm tra nguyên nhân thực tế.'),
                WarrantyPolicy(product_category='Chung', brand='Viettronimex', error_group='Điều kiện chung',
                    title='Điều kiện bảo hành', is_covered=True,
                    content='Được bảo hành khi còn hạn và hư hỏng do lỗi kỹ thuật nhà sản xuất trong điều kiện sử dụng bình thường.'),
                WarrantyPolicy(product_category='Điều hòa', brand='Daikin', error_group='Bo mạch / Máy nén',
                    title='Bảo hành Daikin', is_covered=True,
                    content='Daikin bảo hành thân máy 1 năm, máy nén 5 năm. Lỗi bo mạch do nhà sản xuất được bảo hành 24 tháng.'),
                WarrantyPolicy(product_category='Tivi', brand='Samsung', error_group='Nhiệt độ',
                    title='WRONG BRAND POLICY', is_covered=True,
                    content='Điều hòa không điều chỉnh được nhiệt độ bị rơi được bảo hành miễn phí.'),
            ])
            db.commit()
            sync_policies_to_vector_store(db)

    def chat(self, query, **extra):
        return self.call('POST', '/customer/chat', 'CUSTOMER', 1,
                         json={'query': query, 'session_id': 'test-chat', **extra})

    def test_exact_dropped_air_conditioner_regression(self):
        first = self.chat('tôi lỡ để điều hòa rớt và giờ nó không hoạt động dượ bảo hành không', sold_item_id=1)
        self.assertEqual(first.status_code, 200, first.text)
        reply = first.json()
        self.assertIn('không thuộc phạm vi bảo hành miễn phí', reply['reply'])
        self.assertIn('rơi/rớt', reply['reply'])
        self.assertEqual(reply['cited_policies'], ['Loại trừ bảo hành'])
        self.assertIsNone(reply['suggested_action'])
        second = self.chat('điều hòa không điều chỉnh được nhiệt độ được bảo hành không', sold_item_id=1)
        self.assertEqual(second.status_code, 200)
        self.assertIn('nhiệt độ', second.json()['reply'])
        self.assertIn('Bạn đã nói máy', second.json()['reply'])
        self.assertIn('trước hay sau', second.json()['reply'])
        self.assertNotEqual(reply['reply'], second.json()['reply'])
        self.assertNotIn('5 năm', second.json()['reply'])

    def test_temperature_alone_requests_clarification(self):
        reply = self.chat('không điều chỉnh được nhiệt độ có được bảo hành không', sold_item_id=1).json()
        self.assertIn('chưa đủ', reply['reply'])
        self.assertIn('điều khiển', reply['reply'])
        self.assertNotIn('Bạn đã nói máy', reply['reply'])
        self.assertIsNone(reply['suggested_action'])

    def test_correction_clears_accident_context(self):
        self.chat('máy bị rơi có được bảo hành không', sold_item_id=1)
        reply = self.chat('tôi nói nhầm máy không bị rơi, chỉ không chỉnh được nhiệt độ', sold_item_id=1).json()
        self.assertNotIn('Bạn đã nói máy', reply['reply'])
        self.assertNotIn('không thuộc phạm vi', reply['reply'])

    def test_expired_product_blocked_in_all_creation_channels(self):
        with self.Session() as db:
            db.get(SoldItem, 1).warranty_expire_date = today_vietnam() - timedelta(days=1)
            db.get(SoldItem, 1).product.image_url = 'https://example.test/product.jpg'
            db.commit()
        response = self.chat('Máy có được bảo hành không?', sold_item_id=1)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.chat('Điều hòa FTF50XV1V bị lỗi').status_code, 403)
        payload = {'sold_item_id': 1, 'customer_phone': '0900000001', 'error_group': 'Test',
                   'error_description': 'Test', 'support_address': 'Test'}
        for role, actor in (('CUSTOMER', 1), ('CSKH', 2), ('ADMIN', 1)):
            self.assertEqual(self.call('POST', '/customer/requests', role, actor, json=payload).status_code, 403)
        self.assertEqual(self.call('POST', '/customer/contact', 'CUSTOMER', 1, json={
            'phone': '0900000001', 'message': 'Test', 'sold_item_id': 1}).status_code, 403)
        with self.Session() as db:
            self.assertEqual(db.query(WarrantyRequest).count(), 2)

    def test_expired_product_details_and_old_tickets_are_hidden(self):
        with self.Session() as db:
            db.get(SoldItem, 1).warranty_expire_date = today_vietnam() - timedelta(days=1)
            db.get(SoldItem, 1).product.image_url = 'https://example.test/product.jpg'
            db.commit()
        response = self.call('GET', '/customer/requests/0900000001', 'CUSTOMER', 1)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])
        self.assertEqual(self.chat('Xem phiếu của tôi', request_id=1).status_code, 403)
        self.assertEqual(self.chat('Xem phiếu BH-2026-0001').json()['requests'], [])
        self.assertEqual(self.chat('Xem tất cả phiếu của tôi').json()['requests'], [])
        product = self.call('GET', '/customer/products/0900000001', 'CUSTOMER', 1).json()[0]
        self.assertEqual(set(product), {'id', 'product_name', 'is_expired', 'image_url'})
        self.assertEqual(product['image_url'], 'https://example.test/product.jpg')
        # Internal staff retain records needed for administration, independently of customer access.
        self.assertEqual(len(self.call('GET', '/staff/requests').json()), 2)

    def test_create_intent_after_tracking_never_lists_old_tickets(self):
        self.chat('phiếu bảo hành tôi nhưu nào r', sold_item_id=1)
        self.chat('điều hòa tôi lỡ rơi hư có được bảo hành không nhỉ', sold_item_id=1)
        for query in ('vậy cho tôi làm phiếu bảo hành đi', 'điều hòa tôi hư tôi cần làm phiếu bảo hành', 'làm phiếu bảo hành đi'):
            with self.subTest(query=query):
                reply = self.chat(query, sold_item_id=1).json()
                self.assertNotEqual(reply['response_mode'], 'request_status')
                self.assertEqual(reply['suggested_action'], 'VIEW_WARRANTY_REQUESTS')
                self.assertIn('chưa thể tạo thêm phiếu', reply['reply'])
                self.assertEqual(len(reply['requests']), 1)

    def test_create_without_active_ticket_shows_form_even_after_accident(self):
        self.state(S.COMPLETED)
        self.chat('điều hòa tôi lỡ rơi hư có được bảo hành không nhỉ', sold_item_id=1)
        reply = self.chat('làm phiếu bảo hành đi', sold_item_id=1).json()
        self.assertEqual(reply['suggested_action'], 'CREATE_WARRANTY_REQUEST')
        self.assertEqual(reply['sold_item_id'], 1)
        self.assertIn('chỉ được tạo khi', reply['reply'])
        self.assertIn('không đồng nghĩa', reply['reply'])
        with self.Session() as db:
            self.assertEqual(db.query(WarrantyRequest).count(), 2)

    def test_selected_ticket_does_not_force_unrelated_messages_into_tracking(self):
        self.chat('Xem tiến độ phiếu này', request_id=1)
        advice = self.chat('điều hòa bị rơi có được bảo hành không', request_id=1).json()
        self.assertNotEqual(advice['response_mode'], 'request_status')
        creation = self.chat('làm phiếu bảo hành đi', request_id=1).json()
        self.assertNotEqual(creation['response_mode'], 'request_status')
        self.assertEqual(creation['suggested_action'], 'VIEW_WARRANTY_REQUESTS')

    def test_status_reads_fresh_database_and_followup_context(self):
        response = self.chat('Phiếu BH-2026-0001 đến đâu rồi?')
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['requests'][0]['status'], S.RECEIVED)
        self.state(S.ASSIGNED, 3)
        with self.Session() as db:
            db.add(RequestStatusHistory(request_id=1, status=S.ASSIGNED, notes='PUBLIC UPDATE'))
            db.add(RequestStatusHistory(request_id=1, status=S.ASSIGNED, notes='PRIVATE SECRET', is_internal_note=True))
            db.commit()
        reply = self.chat('Khi nào kỹ thuật viên đến?').json()
        self.assertIn('Staff 3', reply['reply'])
        self.assertIn('Chưa có lịch hẹn', reply['reply'])
        self.assertIn('PUBLIC UPDATE', reply['reply'])
        self.assertNotIn('PRIVATE SECRET', reply['reply'])
        self.assertEqual(reply['requests'][0]['status'], S.ASSIGNED)

    def test_ticket_codes_and_ids_cannot_read_another_customer(self):
        reply = self.chat('Xem phiếu BH-2026-0002').json()
        self.assertEqual(reply['requests'], [])
        self.assertNotIn('Customer 2', reply['reply'])
        self.assertEqual(self.chat('xem phiếu', request_id=2).status_code, 404)

    def test_no_duplicate_ticket_suggestion_for_active_request(self):
        with patch('backend.app.rag.advice._call_gemini', return_value='Cần kiểm tra nguyên nhân.'):
            reply = self.chat('máy bị lỗi bo mạch', sold_item_id=1).json()
        self.assertEqual(reply['suggested_action'], 'VIEW_WARRANTY_REQUESTS')
        self.assertIn('BH-2026-0001', reply['reply'])

    def test_no_product_or_unknown_query_does_not_dump_policy(self):
        reply = self.chat('cho tôi hỏi một chút').json()
        self.assertIn('chọn', reply['reply'])
        reply = self.chat('quantum aardvark xyzzy', sold_item_id=1).json()
        self.assertIn('chưa tìm thấy chính sách', reply['reply'])
        self.assertEqual(reply['cited_policies'], [])

    def test_retrieval_hard_filters_and_drops_zero_similarity(self):
        with self.Session() as db:
            item = db.get(SoldItem, 1)
            docs = retrieve_relevant_policies('máy lạnh rớt có được bảo hành không', item, top_k=10)
            titles = [d['document']['metadata']['title'] for d in docs]
            self.assertIn('Loại trừ bảo hành', titles)
            self.assertNotIn('WRONG BRAND POLICY', titles)
            self.assertEqual(retrieve_relevant_policies('xyzzy aardvark', item), [])

    def test_generic_advice_handles_upstream_failure_without_false_promises(self):
        reply = self.chat('máy báo lỗi bo mạch có được bảo hành không', sold_item_id=1).json()
        self.assertEqual(reply['response_mode'], 'fallback')
        self.assertIn('nguyên nhân', reply['reply'])
        self.assertNotIn('tiếp nối', reply['reply'])

    def test_date_boundary_and_defense_inside_generator(self):
        with self.Session() as db:
            item = db.get(SoldItem, 1)
            item.warranty_expire_date = today_vietnam()
            result = generate_chat_response('không chỉnh được nhiệt độ', [], item)
            self.assertFalse(result['is_expired'])
            item.warranty_expire_date -= timedelta(days=1)
            result = generate_chat_response('có được bảo hành không', [], item)
            self.assertTrue(result['is_expired'])
            self.assertIsNone(result['suggested_action'])
            self.assertNotIn('miễn phí 100%', result['reply'])

    def test_empty_index_cannot_return_stale_policies(self):
        store = SimpleVectorStore()
        store.add_documents([{'text': 'bảo hành', 'metadata': {}}])
        self.assertTrue(store.search('bảo hành'))
        store.add_documents([])
        self.assertEqual(store.search('bảo hành'), [])


class GeminiTransportTests(unittest.TestCase):
    def test_transport_uses_header_and_handles_errors(self):
        from backend.app.rag.advice import _call_gemini
        from backend.app.core.config import settings
        with patch.object(settings, 'GEMINI_API_KEY', 'test-secret'), patch.object(settings, 'GEMINI_MODEL', 'gemini-3.1-flash-lite'):
            with patch('backend.app.rag.advice.httpx.post', return_value=httpx.Response(200, json={
                'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text': 'Trả lời đúng câu hỏi.'}]}}]})) as post:
                self.assertEqual(_call_gemini('test', [], None, []), 'Trả lời đúng câu hỏi.')
                self.assertNotIn('test-secret', post.call_args.args[0])
                self.assertEqual(post.call_args.kwargs['headers']['x-goog-api-key'], 'test-secret')
            with patch('backend.app.rag.advice.httpx.post', return_value=httpx.Response(429, json={})):
                self.assertIsNone(_call_gemini('test', [], None, []))
            with patch('backend.app.rag.advice.httpx.post', side_effect=httpx.ConnectError('offline')):
                self.assertIsNone(_call_gemini('test', [], None, []))


if __name__ == '__main__':
    unittest.main()

"""Exercise the actual templates in an installed headless Chromium browser.

Run: python backend/tests/check_frontend.py
Serves fixtures only on localhost; never starts the production app or opens its DB.
"""
import functools
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import threading

API_CLIENT = None
STAFF_TOKEN = ''
CUSTOMER_TOKEN = ''
ADMIN_TOKEN = ''

ROOT = Path(__file__).resolve().parents[2]
ATTACK = '<img data-attack src=x onerror="window.__xss=1">\'"&<svg onload="window.__xss=1">'
product = dict(id=1, product_name=ATTACK, name=ATTACK, model=ATTACK, brand=ATTACK,
               category=ATTACK, serial_number=ATTACK, warranty_expire_date=ATTACK,
               is_expired=False, image_url='javascript:window.__xss=1', warranty_months=24)
request = dict(id=1, request_code=ATTACK, customer_name=ATTACK, customer_phone=ATTACK,
               product_name=ATTACK, model=ATTACK, error_group=ATTACK, error_description=ATTACK,
               support_address=ATTACK, status='Tiếp nhận', channel='Web', appointment_date=ATTACK,
               technician_name=ATTACK, created_at=ATTACK,
               timeline=[dict(status='Tiếp nhận', note=ATTACK, time=ATTACK)])
fixtures = json.dumps(dict(product=product, request=request, attack=ATTACK), ensure_ascii=True).replace('<', '\\u003c')
BOOT = '''<script>
window.__xss = 0; window.__errors = []; window.__calls = [];
window.addEventListener('error', e => { if(e.message) window.__errors.push(e.message); });
window.FIXTURES = FIXTURE_JSON;
localStorage.setItem('vietcare_user', JSON.stringify({access_token: 'fixture-token',
  user_type: location.pathname.startsWith('/staff') || location.pathname.startsWith('/manager') ? 'staff' : 'customer',
  role: 'CSKH', user_id: 2, phone_or_email: '0900000001', name: FIXTURES.attack}));
window.alert = () => {};
window.fetch = async (input, options = {}) => {
  __calls.push({url: String(input), token: new Headers(options.headers).get('Authorization'), body: options.body ? JSON.parse(options.body instanceof FormData ? options.body.get('payload') : options.body) : null});
  let data = [];
  if (String(input).includes('/chat')) data = window.__chatResponse || {reply: '**Hello** ' + FIXTURES.attack};
  else if (options.method === 'POST' && (String(input).endsWith('/requests') || String(input).endsWith('/requests-with-media') || String(input).endsWith('/contact'))) data = {success: true, request_code: 'BH-2026-0009', request_id: 9};
  else if (String(input).includes('/admin/overview')) data = {kpi: {total_requests: 1, waiting_count: 1, overdue_count: 1, completed_count: 0}, statuses: [{status: 'Tiếp nhận', count: 1}], technicians: [{id: 3, name: FIXTURES.attack, assigned: 1, in_progress: 0, completed: 0}]};
  else if (/\/api\/v1\/requests\/\d+$/.test(String(input))) data = {...FIXTURES.request, attachments: [], inspections: []};
  else if (String(input).includes('/products')) data = [FIXTURES.product];
  else if (String(input).includes('/requests')) data = [FIXTURES.request];
  else if (String(input).includes('/technicians')) data = [{id: 3, name: FIXTURES.attack, phone: FIXTURES.attack}];
  else if (String(input).includes('/kpi')) data = {};
  return new Response(JSON.stringify(data), {status: 200, headers: {'Content-Type': 'application/json'}});
};
</script>'''.replace('FIXTURE_JSON', fixtures)

HARNESS = '''<!doctype html><meta charset="utf-8"><body><pre id="result">PENDING</pre>
<script src="/static/js/security.js"></script><script>
const failures = []; let assertions = 0;
function check(value, label) { assertions++; if (!value) failures.push(label); }
async function waitFor(test) {
  for (let i=0; i<100; i++) { if (test()) return; await new Promise(r=>setTimeout(r, 20)); }
  throw Error('Page scripts did not initialize');
}
async function page(path, ready, run) {
  const frame = document.createElement('iframe'); frame.style.width='1100px'; frame.src=path; document.body.append(frame);
  await waitFor(() => frame.contentWindow[ready]);
  const w = frame.contentWindow;
  await run(w);
  await new Promise(r=>setTimeout(r, 50));
  check(w.__xss === 0, path + ': payload executed');
  check(!w.document.querySelector('[data-attack], svg[onload]'), path + ': injected HTML survived');
  check(w.__errors.length === 0, path + ': ' + w.__errors.join(', '));
  check(w.__calls.length > 0 && w.__calls.every(c=>c.token === 'Bearer ' + (w.__expectedToken || 'fixture-token')), path + ': token missing');
  frame.remove();
}
(async () => {
  try {
    await page('/customer', 'loadProducts', async w => {
      await w.loadProducts(); await w.loadRequests(); w.openChatForProduct(1);
      w.document.getElementById('chatInputBox').value = w.FIXTURES.attack;
      await w.sendCustomerChat();
      check(w.document.getElementById('chatMessages').querySelector('strong')?.textContent.includes('img'), 'product greeting escape');
      check(w.document.getElementById('chatMessages').textContent.includes('<img'), 'payload should remain visible as text');
      check(w.formatMarkdown('**safe**').includes('<strong>safe</strong>'), 'Markdown still works');
      check(!w.formatMarkdown(w.FIXTURES.attack).includes('<img'), 'Markdown must escape HTML');
      w.showRequestSuccess({request_code: w.FIXTURES.attack});
      const success = w.document.getElementById('requestSuccess');
      check(!success.hidden && success.textContent.includes('<img'), 'success panel shows escaped request code');
      check(!success.textContent.includes('Email'), 'success does not promise an email delivery');
      success.querySelector('.btn').click();
      check(success.hidden && w.document.getElementById('sectionRequests').style.display === 'block', 'success action opens tracking');
      await w.loadRequests();
      check(w.document.querySelector('.request-detail-columns > .request-progress'), 'request details have a separate history column');
      const columns = w.document.querySelector('.request-detail-columns');
      check(w.getComputedStyle(columns).gridTemplateColumns.split(' ').length === 2, 'desktop request uses two columns');
      w.frameElement.style.width = '375px';
      await new Promise(r => setTimeout(r, 50));
      check(w.getComputedStyle(columns).gridTemplateColumns.split(' ').length === 1, 'mobile request uses one column');
      w.frameElement.style.width = '1100px';
      w.openWarrantyModal(1);
      w.document.getElementById('formErrorDesc').value = 'Thiết bị không hoạt động';
      const form = w.document.querySelector('#warrantyModalBackdrop form');
      await w.handleCustomerRequestSubmit({preventDefault() {}, target: form});
      check(!success.hidden && success.textContent.includes('BH-2026-0009'), 'submitting request shows real response in success panel');
      check(!form.querySelector('[type="submit"]').disabled, 'submit unlocks after recording request');
      check(!w.document.getElementById('warrantyModalBackdrop').classList.contains('open'), 'request form closes after success');
      success.querySelector('.success-close').click();
      await w.showRequestDetail(1);
      check(w.document.getElementById('requestDetailBody').textContent.includes('<img'), 'request detail escapes customer and issue fields');
      w.frameElement.style.width = '375px';
      await new Promise(r => setTimeout(r, 50));
      check(w.document.querySelector('.request-detail-modal').getBoundingClientRect().right <= w.innerWidth, 'incident detail fits the mobile viewport');
      w.frameElement.style.width = '1100px';
      w.closeRequestDetail();
      check(w.productDisplayName('Điều hòa Daikin FTF50XV1V New 2026 (FTF50XV1V)', 'FTF50XV1V') === 'Điều hòa Daikin', 'product name removes duplicate model and marketing suffix');
      check(w.statusDisplayName('Tiếp nhận') === 'Đã tiếp nhận', 'received status uses friendly label');
      const originalSession = w.__calls.find(c=>c.url.includes('/chat')).body.session_id;
      w.openChatForRequest(1);
      await waitFor(() => w.__calls.filter(c=>c.url.includes('/chat')).length === 2);
      const trackingCall = w.__calls.filter(c=>c.url.includes('/chat'))[1];
      check(trackingCall.body.request_id === 1 && trackingCall.body.sold_item_id === null, 'tracking passes ticket id independently of product expiry');
      check(trackingCall.body.session_id !== originalSession, 'new context starts a separate session');
      await new Promise(r=>setTimeout(r, 50));
      w.clearChatContext();
      w.__chatResponse = {reply: 'Bạn có thể tạo phiếu.', suggested_action: 'CREATE_WARRANTY_REQUEST', sold_item_id: 1};
      w.document.getElementById('chatInputBox').value = 'làm phiếu bảo hành đi';
      await w.sendCustomerChat();
      const createButton = w.document.querySelector('#chatMessages [onclick^="openWarrantyModal"]');
      check(Boolean(createButton), 'chat can offer a form using product id returned by server');
      const suggestion = createButton.closest('.suggest-box');
      check(w.getComputedStyle(suggestion).flexDirection === 'column', 'chat action uses a vertical layout');
      check(createButton.getBoundingClientRect().width >= 150, 'chat action button has enough room for its label');
      createButton?.click();
      check(w.document.getElementById('warrantyModalBackdrop').classList.contains('open'), 'chat create button opens the request form');
      w.closeWarrantyModal();
      w.FIXTURES.product.is_expired = true;
      w.clearChatContext();
      await w.loadProducts();
      const grid = w.document.getElementById('productGrid');
      check(!grid.querySelector('[onclick^="openChatForProduct"], [onclick^="openWarrantyModal"]'), 'expired products have no chat/create buttons');
      check(!grid.querySelector('button, a, .product-code'), 'expired product shows no restricted details or actions');
      check(Boolean(grid.querySelector('.product-img-box img')), 'expired product retains its image');
      check(grid.textContent.includes('Đã hết bảo hành'), 'expired status remains visible');
      check(w.document.getElementById('contactSoldItem').options.length === 1, 'expired product excluded from callbacks');
      w.openChatForProduct(1); w.openWarrantyModal(1);
      check(!w.document.getElementById('warrantyModalBackdrop').classList.contains('open'), 'expired product cannot open request form');
      check(w.document.getElementById('chatProductBar').style.display === 'none', 'expired product cannot open advice context');
    });
    await page('/staff', 'loadStaffData', async w => {
      await w.loadStaffData(); await w.loadTechs();
      check(w.document.getElementById('staffTableBody').textContent.includes('<img'), 'staff escaped text');
      const btn = w.document.querySelector('#staffTableBody [onclick^="openVerifyModal"]');
      btn.click();
      check(w.document.getElementById('verifyReqCode').innerText === w.FIXTURES.attack, 'modal treats request code as plain data');
      w.document.getElementById('pPhone').value = '0900000001';
      await w.loadPhoneProducts();
      check(w.document.getElementById('pProduct').options.length === 2, 'staff selects an eligible purchased item');
      w.FIXTURES.product.is_expired = true;
      await w.loadPhoneProducts();
      check(w.document.getElementById('pProduct').options.length === 1, 'staff cannot select expired item');
      w.filterByKpi('waiting');
      await waitFor(() => w.__calls.some(c => c.url.includes('pending_only=true')));
      check(w.document.querySelector('.kpi-tile[data-view="waiting"]').getAttribute('aria-pressed') === 'true', 'KPI selection is accessible');
      w.resetStaffFilters();
      w.document.getElementById('appointmentFrom').value = '2026-10-24';
      w.document.getElementById('appointmentTo').value = '2026-10-25';
      await w.loadStaffData();
      check(w.__calls.some(c => c.url.includes('appointment_from=2026-10-24') && c.url.includes('appointment_to=2026-10-25')), 'appointment filters reach API');
      w.filterByKpi('overdue');
      await waitFor(() => w.__calls.some(c => c.url.includes('overdue_only=true')));
      check(w.__calls.some(c => c.url.includes('overdue_only=true')), 'overdue KPI filters through API');
    });
    await page('/staff-tech', 'loadStaffData', async w => {
      await w.loadStaffData();
      check(!w.document.getElementById('newAssignments').hidden, 'new technician assignment appears above table');
      check(w.document.querySelector('#newAssignmentCards .status-pill').textContent === 'Chờ xác nhận', 'new assignment has confirmation label');
      check(!w.document.querySelector('#staffTableBody [onclick^="quickStatus"]'), 'new assignments are separate from accepted work');
      check(w.document.getElementById('btnPhoneReception').hidden, 'technician cannot create requests for callers');
      check(!w.document.querySelector('#newAssignmentCards').textContent.includes('KTV '), 'assignment does not repeat technician name');
      w.FIXTURES.request.status = 'Sửa chữa';
      await w.loadStaffData();
      check(w.document.getElementById('newAssignments').hidden, 'accepted work leaves the new assignment list');
      check(w.document.querySelector('#staffTableBody [onclick^="openCompleteModal"]').textContent === 'Báo hoàn thành', 'accepted work offers completion action');
    });
    await page('/catalog-demo', 'loadCatalogProducts', async w => {
      await w.loadCatalogProducts(); w.checkUserSession();
      check(!w.document.querySelector('img[src^="javascript:"]'), 'unsafe image URL');
    });
    await page('/legacy', 'loadCustomerData', async w => {
      await w.loadCustomerData(); await w.loadStaffRequests();
    });
    await page('/staff-real', 'loadStaffData', async w => {
      await w.loadStaffData(); await w.loadTechs();
      w.document.querySelector('#staffTableBody [onclick^="openVerifyModal(1,"]').click();
      w.document.getElementById('btnVerifyValid').click();
      await waitFor(() => w.document.querySelector('#staffTableBody [onclick^="openAssignModal(1,"]'));
      const assign = w.document.querySelector('#staffTableBody [onclick^="openAssignModal(1,"]');
      assign.click();
      check(w.document.getElementById('assignModalBackdrop').classList.contains('open'), 'CSKH assignment modal opens');
      w.document.getElementById('techSelect').value = '3';
      w.document.getElementById('appDate').value = '2026-10-20';
      w.document.getElementById('assignNotes').value = 'Customer requested afternoon appointment';
      w.document.querySelector('#assignModalBackdrop form').requestSubmit();
      await waitFor(() => !w.document.getElementById('assignModalBackdrop').classList.contains('open'));
      const records = await (await w.apiFetch('/api/v1/staff/requests')).json();
      const assigned = records.find(r=>r.id === 1);
      check(assigned.status === 'Phân công' && assigned.technician_id === 3, 'CSKH submits assignment to the real API');
      check(assigned.appointment_date === '20/10/2026', 'assignment appointment persisted');
      await w.loadStaffData();
      const reassignment = w.document.querySelector('#staffTableBody [onclick^="openAssignModal(1,"]');
      check(reassignment.textContent === 'Đổi KTV / lịch hẹn', 'assigned ticket uses a distinct reassignment label after refresh');
      check(reassignment.closest('tr').textContent.includes('Chờ KTV nhận việc'), 'CSKH sees the next workflow step');
      check(reassignment.closest('tr').textContent.includes('Staff 3'), 'CSKH sees the assigned technician');
      check(w.document.getElementById('staffActionNotice').textContent.includes('Đang chờ kỹ thuật viên nhận việc'), 'assignment success is visible without blocking the UI');
      reassignment.click();
      check(w.document.getElementById('assignModalTitle').textContent === 'Đổi kỹ thuật viên / lịch hẹn', 'reassignment modal has a distinct title');
      check(w.document.getElementById('btnAssignSubmit').textContent === 'Lưu thay đổi', 'reassignment does not ask to assign again');
      check(w.document.getElementById('techSelect').value === '3' && w.document.getElementById('appDate').value === '2026-10-20', 'reassignment preserves technician and date');
    });
    await page('/customer-real', 'loadProducts', async w => {
      await w.loadProducts();
      w.openWarrantyModal(3);
      const transfer = new w.DataTransfer();
      const png = Uint8Array.from(atob('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRusAAAAASUVORK5CYII='), c => c.charCodeAt(0));
      transfer.items.add(new w.File([png], 'incident.png', {type:'image/png'}));
      const input = w.document.getElementById('incidentFiles');
      input.files = transfer.files;
      w.previewIncidentFiles(input, 'incidentPreview');
      check(Boolean(w.document.querySelector('#incidentPreview img')), 'selected incident image has a preview');
      w.document.getElementById('formErrorDesc').value = 'Không lên nguồn, có ảnh kèm theo';
      const form = w.document.querySelector('#warrantyModalBackdrop form');
      await w.handleCustomerRequestSubmit({preventDefault() {}, target: form});
      const success = w.document.getElementById('requestSuccess');
      check(!success.hidden && /BH-\d{4}-\d{4}/.test(success.textContent), 'multipart upload records a monthly request code');
      const tickets = await (await w.apiFetch('/api/v1/customer/requests/0900000001')).json();
      const ticket = tickets.find(r => r.product_name && r.attachments?.length);
      check(Boolean(ticket), 'uploaded media is linked to the new ticket');
      await w.showRequestDetail(ticket.id);
      check(w.document.querySelector('#detailMedia img')?.src.startsWith('blob:'), 'private incident photo loads through authenticated API');
      await waitFor(() => w.document.querySelector('#detailMedia img')?.complete);
      check(w.document.querySelector('#detailMedia img').naturalWidth > 0, 'uploaded image decodes in the browser');
      check(w.document.getElementById('requestDetailBody').textContent.includes('incident.png'), 'detail shows incident filename');
      w.closeRequestDetail();
    });
    await page('/manager-real', 'loadStaffData', async w => {
      await w.loadKPIs(); await w.loadTechs();
      check(!w.document.getElementById('managerOverview').hidden, 'admin sees the manager overview');
      check(w.document.querySelector('#managerWorkload .text-button'), 'manager sees real technician workload');
      w.document.querySelector('#managerWorkload .text-button').click();
      await waitFor(() => w.__calls.some(c => c.url.includes('technician_id=3')));
      check(w.document.getElementById('managerTechnicianFilter').value === '3', 'manager workload links filter assigned tickets');
      w.filterByKpi('overdue');
      await waitFor(() => w.__calls.some(c => c.url.includes('overdue_only=true')));
      check(w.__calls.some(c => c.url.includes('overdue_only=true')), 'manager can list overdue reception tickets');
    });
    const login = document.createElement('iframe'); login.src='/'; document.body.append(login);
    await waitFor(() => login.contentWindow.executeLogin);
    check(login.contentDocument.getElementById('loginIdentity').value === '', 'login identity starts empty');
    check(login.contentDocument.getElementById('loginPassword').value === '', 'login password starts empty');
    check(!login.contentDocument.querySelector('.quick-fill-btn'), 'demo account buttons removed');
    check(!login.contentDocument.documentElement.innerHTML.includes('123456'), 'login source contains no demo password');
    login.remove();
    localStorage.setItem('vietcare_user', JSON.stringify({access_token:'expired'}));
    window.fetch = async () => new Response(JSON.stringify({detail:'Forbidden'}), {status:403});
    let rejected = false;
    try { await apiFetch('/api/v1/staff/requests'); } catch(e) { rejected = e.message === 'Forbidden'; }
    check(rejected, 'API errors surface to callers');
  } catch(e) { failures.push(e.stack); }
  document.getElementById('result').textContent = JSON.stringify({assertions, failures});
})();
</script>'''


class Handler(SimpleHTTPRequestHandler):
    def forward_api(self):
        length = int(self.headers.get('Content-Length', 0))
        payload = self.rfile.read(length) if length else None
        response = API_CLIENT.request(self.command, self.path, content=payload,
                                      headers={k: v for k, v in self.headers.items() if k.lower() in ('authorization', 'content-type')})
        self.send_response(response.status_code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(response.content)))
        self.end_headers()
        self.wfile.write(response.content)

    def do_POST(self):
        return self.forward_api()

    def do_PUT(self):
        return self.forward_api()

    def do_GET(self):
        route = self.path.split('?')[0]
        if route.startswith('/api/v1/'):
            return self.forward_api()
        templates = {'/': 'login', '/catalog-demo': 'dashboard', '/customer': 'customer', '/customer-real': 'customer', '/staff': 'staff', '/staff-tech': 'staff', '/manager-real': 'staff', '/legacy': 'index', '/staff-real': 'staff', '/login': 'login'}
        if route == '/test':
            body = HARNESS
        elif route in templates:
            body = (ROOT / 'frontend/templates' / (templates[route] + '.html')).read_text(encoding='utf-8')
            boot = BOOT
            if route == '/staff-tech':
                boot = boot.replace("role: 'CSKH'", "role: 'TECHNICIAN'")
                boot = boot.replace("window.fetch = async", "FIXTURES.request.status = 'Phân công'; FIXTURES.request.technician_id = 2; window.fetch = async")
            if route in ('/staff-real', '/customer-real', '/manager-real'):
                token = {'/staff-real': STAFF_TOKEN, '/customer-real': CUSTOMER_TOKEN, '/manager-real': ADMIN_TOKEN}[route]
                boot = BOOT.split('window.fetch = async')[0].replace('fixture-token', token)
                if route == '/manager-real':
                    boot = boot.replace("role: 'CSKH'", "role: 'ADMIN'")
                boot += '''window.__expectedToken = TOKEN_JSON;
const originalFetch = window.fetch.bind(window);
window.fetch = (input, options={}) => {
  __calls.push({url: String(input), token: new Headers(options.headers).get('Authorization')});
  return originalFetch(input, options);
};</script>'''.replace('TOKEN_JSON', json.dumps(token))
            body = body.replace('<head>', '<head>' + boot)
            # Avoid unrelated network resources during the isolated UI test.
            body = re.sub(r'<link[^>]+href="https?://[^>]+>', '', body)
        else:
            if route.startswith('/static/'):
                self.path = '/frontend' + self.path
            return super().do_GET()
        raw = body.encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, *_):
        pass


if __name__ == '__main__':
    sys.path.insert(0, str(ROOT))
    import test_security
    fixture = test_security.SecurityTests('test_valid_workflow_and_audit_actor')
    test_security.SecurityTests.setUpClass()
    fixture.setUp()
    from backend.app.models.product import SoldItem
    from backend.app.core.config import settings
    from datetime import date, timedelta
    upload_directory = tempfile.TemporaryDirectory(prefix='vietcare-ui-media-')
    settings.UPLOAD_DIR = upload_directory.name
    with fixture.Session() as db:
        db.add(SoldItem(id=3, product_id=1, customer_id=1, serial_number='MEDIA-TEST', purchase_date=date.today(), warranty_expire_date=date.today()+timedelta(days=365)))
        db.commit()
    API_CLIENT = fixture.client
    STAFF_TOKEN = fixture.headers()['Authorization'].removeprefix('Bearer ')
    CUSTOMER_TOKEN = fixture.headers('CUSTOMER', 1)['Authorization'].removeprefix('Bearer ')
    ADMIN_TOKEN = fixture.headers('ADMIN', 1)['Authorization'].removeprefix('Bearer ')
    browser = next((p for p in [
        Path('C:/Program Files/Google/Chrome/Application/chrome.exe'),
        Path('C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'),
    ] if p.exists()), None)
    if browser is None:
        raise SystemExit('Install Chrome or Edge to run the UI security checks')
    server = ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Handler, directory=str(ROOT)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with tempfile.TemporaryDirectory(prefix='vietcare-ui-') as profile:
            result = subprocess.run([str(browser), '--headless', '--disable-gpu', '--no-first-run',
                '--no-default-browser-check', '--disable-background-networking', f'--user-data-dir={profile}',
                '--dump-dom', '--virtual-time-budget=15000', f'http://127.0.0.1:{server.server_port}/test'],
                capture_output=True, text=True, encoding='utf-8', timeout=45)
            found = re.search(r'<pre id="result">(.*?)</pre>', result.stdout, re.S)
            if not found or found.group(1) == 'PENDING':
                raise SystemExit('Browser checks did not complete: ' + result.stderr[-1500:])
            from html import unescape
            report = json.loads(unescape(found.group(1)))
            print(json.dumps(report, ensure_ascii=True, indent=2))
            if report['failures']:
                raise SystemExit(1)
    finally:
        server.shutdown()
        server.server_close()
        fixture.doCleanups()
        upload_directory.cleanup()

// Global Application State
const AppState = {
  currentRole: 'CUSTOMER', // 'CUSTOMER', 'CSKH', 'TECHNICIAN', 'ADMIN'
  customerPhone: '0905123456',
  customerName: 'Nguyễn Văn An',
  currentTab: 'products', // 'products', 'requests'
  activeChatProduct: null,
  chatSessionId: 'sess_' + Math.random().toString(36).substr(2, 9),
  products: [],
  requests: [],
  technicians: []
};

// Initializer
document.addEventListener('DOMContentLoaded', () => {
  initEventListeners();
  loadCustomerData();
  loadTechnicians();
});

function initEventListeners() {
  // Main View Switcher (Customer vs Staff)
  document.getElementById('switchCustomerView').addEventListener('click', () => switchPortal('CUSTOMER'));
  document.getElementById('switchStaffView').addEventListener('click', () => switchPortal('CSKH'));

  // User/Role Selectors
  document.getElementById('userSelect').addEventListener('change', (e) => {
    const val = e.target.value;
    if (val === '0905123456') {
      AppState.customerPhone = '0905123456';
      AppState.customerName = 'Nguyễn Văn An';
      loadCustomerData();
    } else if (val === '0914987654') {
      AppState.customerPhone = '0914987654';
      AppState.customerName = 'Trần Thị Bích';
      loadCustomerData();
    }
  });

  document.getElementById('staffRoleSelect').addEventListener('change', (e) => {
    AppState.currentRole = e.target.value;
    loadStaffRequests();
  });

  // Customer sub-tabs
  document.getElementById('tabMyProducts').addEventListener('click', () => switchCustomerTab('products'));
  document.getElementById('tabMyRequests').addEventListener('click', () => switchCustomerTab('requests'));

  // Chatbot floating triggers
  document.getElementById('chatBubbleTrigger').addEventListener('click', toggleChatModal);
  document.getElementById('closeChatBtn').addEventListener('click', toggleChatModal);
  document.getElementById('sendChatBtn').addEventListener('click', sendChatMessage);
  document.getElementById('chatInput').addEventListener('keypress', (e) => {
    if (e.key === 'Enter') sendChatMessage();
  });

  // Staff Filters
  document.getElementById('statusFilter').addEventListener('change', loadStaffRequests);
  document.getElementById('channelFilter').addEventListener('change', loadStaffRequests);
  document.getElementById('searchInput').addEventListener('input', loadStaffRequests);
}

// -------------------------------------------------------------
// PORTAL & TAB SWITCHING
// -------------------------------------------------------------
function switchPortal(role) {
  AppState.currentRole = role;
  const custView = document.getElementById('customerPortalSection');
  const staffView = document.getElementById('staffPortalSection');
  const custTab = document.getElementById('switchCustomerView');
  const staffTab = document.getElementById('switchStaffView');

  if (role === 'CUSTOMER') {
    custView.style.display = 'block';
    staffView.style.display = 'none';
    custTab.classList.add('active');
    staffTab.classList.remove('active');
    document.getElementById('customerControls').style.display = 'flex';
    document.getElementById('staffControls').style.display = 'none';
    loadCustomerData();
  } else {
    custView.style.display = 'none';
    staffView.style.display = 'block';
    custTab.classList.remove('active');
    staffTab.classList.add('active');
    document.getElementById('customerControls').style.display = 'none';
    document.getElementById('staffControls').style.display = 'flex';
    loadStaffRequests();
    loadKPIStats();
  }
}

function switchCustomerTab(tab) {
  AppState.currentTab = tab;
  const prodTab = document.getElementById('tabMyProducts');
  const reqTab = document.getElementById('tabMyRequests');
  const prodSec = document.getElementById('productsSection');
  const reqSec = document.getElementById('requestsSection');

  if (tab === 'products') {
    prodTab.classList.add('active');
    reqTab.classList.remove('active');
    prodSec.style.display = 'block';
    reqSec.style.display = 'none';
  } else {
    prodTab.classList.remove('active');
    reqTab.classList.add('active');
    prodSec.style.display = 'none';
    reqSec.style.display = 'block';
    loadCustomerRequests();
  }
}

// -------------------------------------------------------------
// CUSTOMER DATA RENDERING
// -------------------------------------------------------------
async function loadCustomerData() {
  document.getElementById('bannerCustomerName').innerText = AppState.customerName;
  document.getElementById('bannerCustomerPhone').innerText = AppState.customerPhone;
  try {
    const res = await apiFetch(`/api/v1/customer/products/${AppState.customerPhone}`);
    AppState.products = await res.json();
    renderProducts(AppState.products);
  } catch (err) {
    console.error('Lỗi khi tải sản phẩm:', err);
  }
}

function renderProducts(products) {
  const container = document.getElementById('productGrid');
  container.innerHTML = '';

  if (!products || products.length === 0) {
    container.innerHTML = `<p style="grid-column: 1/-1; text-align: center; color: var(--gray-500); padding: 40px;">Bạn chưa có sản phẩm nào được ghi nhận. Vui lòng liên hệ CSKH.</p>`;
    return;
  }

  products.forEach(p => {
    const card = document.createElement('div');
    card.className = 'product-card';
    if (p.is_expired) {
      card.innerHTML = `<div class="product-img-box"><img src="${safeImageUrl(p.image_url || 'https://vietro.com.vn/uploads/files/Untitled-2-01%20copy.png')}" alt="${escapeHtml(p.product_name)}"></div><div class="product-title">${escapeHtml(p.product_name)}</div><div class="warranty-status-pill expired">Đã hết bảo hành</div>`;
      container.appendChild(card);
      return;
    }
    
    const statusPill = p.is_expired
      ? `<span class="warranty-status-pill expired">⚠️ Hết hạn (${escapeHtml(p.warranty_expire_date)})</span>`
      : `<span class="warranty-status-pill valid">🛡️ Còn hạn đến ${escapeHtml(p.warranty_expire_date)}</span>`;

    let actionBtn = '';
    if (p.active_request_id) {
      actionBtn = `<button class="btn btn-warning" onclick="switchCustomerTab('requests')">Xem yêu cầu đang xử lý</button>`;
    } else {
      actionBtn = `<button class="btn btn-primary" onclick="openWarrantyModal(${Number(p.id)})">Yêu cầu bảo hành</button>`;
    }

    card.innerHTML = `
      <div class="product-img-wrap">
        <img src="${safeImageUrl(p.image_url || 'https://vietro.com.vn/uploads/files/Untitled-2-01%20copy.png')}" alt="${escapeHtml(p.product_name)}">
      </div>
      <div class="product-title" title="${escapeHtml(p.product_name)}">${escapeHtml(p.product_name)}</div>
      <div class="product-meta">Model: <strong>${escapeHtml(p.model)}</strong> | Serial: ${escapeHtml(p.serial_number)}</div>
      ${statusPill}
      <div class="card-actions">
        ${p.is_expired ? '' : `<button class="btn btn-secondary" onclick="openChatWithProduct(${Number(p.id)})">💬 Hỏi Chatbot</button>`}
        ${actionBtn}
      </div>
    `;
    container.appendChild(card);
  });
}

async function loadCustomerRequests() {
  const container = document.getElementById('customerRequestsList');
  container.innerHTML = `<p style="text-align: center; color: var(--gray-500); padding: 30px;">Đang tải danh sách yêu cầu...</p>`;

  try {
    const res = await apiFetch(`/api/v1/customer/requests/${AppState.customerPhone}`);
    AppState.requests = await res.json();

    if (AppState.requests.length === 0) {
      container.innerHTML = `<p style="text-align: center; color: var(--gray-500); padding: 40px;">Bạn chưa gửi yêu cầu bảo hành nào.</p>`;
      return;
    }

    container.innerHTML = '';
    AppState.requests.forEach(r => {
      const card = document.createElement('div');
      card.className = 'request-card';

      const statusClass = getStatusClass(r.status);
      let timelineHtml = '';
      r.timeline.forEach(t => {
        timelineHtml += `
          <div class="timeline-item">
            <div class="timeline-bullet"></div>
            <div class="timeline-title">${escapeHtml(t.status)} <span class="timeline-time">${escapeHtml(t.time)}</span></div>
            <div class="timeline-note">${escapeHtml(t.note || 'Cập nhật hệ thống')}</div>
          </div>
        `;
      });

      card.innerHTML = `
        <div class="request-header">
          <div>
            <span class="req-code">${escapeHtml(r.request_code)}</span>
            <div style="font-weight: 600; font-size: 1rem; margin-top: 4px;">${escapeHtml(r.product_name)} (Model: ${escapeHtml(r.model)})</div>
            <div style="font-size: 0.85rem; color: var(--gray-500);">Kênh gửi: <strong>${escapeHtml(r.channel)}</strong> | Ngày tạo: ${escapeHtml(r.created_at)}</div>
          </div>
          <span class="status-badge ${statusClass}">${escapeHtml(r.status)}</span>
        </div>
        <div style="margin: 10px 0; font-size: 0.9rem;">
          <div><strong>Sự cố:</strong> ${escapeHtml(r.error_group)} - <em>${escapeHtml(r.error_description)}</em></div>
          <div style="margin-top: 4px; color: var(--gray-700);"><strong>Kỹ thuật viên:</strong> ${escapeHtml(r.technician_name)} ${r.appointment_date ? `(Lịch hẹn: ${escapeHtml(r.appointment_date)})` : ''}</div>
        </div>
        <div style="font-weight: 600; font-size: 0.88rem; color: var(--primary); margin-top: 14px;">Lịch sử tiến độ:</div>
        <div class="timeline-list">
          ${timelineHtml}
        </div>
      `;
      container.appendChild(card);
    });
  } catch (err) {
    container.innerHTML = `<p style="color: var(--danger); text-align: center;">Lỗi khi tải yêu cầu: ${escapeHtml(err.message)}</p>`;
  }
}

// -------------------------------------------------------------
// WARRANTY REQUEST MODAL (KH-03)
// -------------------------------------------------------------
function openWarrantyModal(soldItemId) {
  const product = AppState.products.find(p => p.id === soldItemId);
  if (!product) return;
  if (product.is_expired) {
    alert('Sản phẩm đã hết hạn bảo hành, không thể tạo phiếu mới.');
    return;
  }

  document.getElementById('modalSoldItemId').value = product.id;
  document.getElementById('modalProductName').value = `${product.product_name} (${product.model})`;
  document.getElementById('modalSerial').value = product.serial_number;
  document.getElementById('modalWarrantyStatus').innerText = product.is_expired ? 'Đã hết hạn bảo hành' : 'Còn hạn bảo hành';
  document.getElementById('modalWarrantyStatus').className = product.is_expired ? 'warranty-status-pill expired' : 'warranty-status-pill valid';
  document.getElementById('modalSupportAddress').value = '120 Nguyễn Văn Linh, Q. Hải Châu, TP. Đà Nẵng';
  document.getElementById('warrantyModalOverlay').classList.add('open');
}

function closeWarrantyModal() {
  document.getElementById('warrantyModalOverlay').classList.remove('open');
}

async function submitWarrantyForm(e) {
  e.preventDefault();
  const soldItemId = parseInt(document.getElementById('modalSoldItemId').value);
  const errorGroup = document.getElementById('modalErrorGroup').value;
  const description = document.getElementById('modalErrorDesc').value;
  const address = document.getElementById('modalSupportAddress').value;

  if (!description.trim()) {
    alert('Vui lòng mô tả chi tiết hư hỏng.');
    return;
  }

  const payload = {
    sold_item_id: soldItemId,
    customer_phone: AppState.customerPhone,
    error_group: errorGroup,
    error_description: description,
    support_address: address,
    channel: 'Web'
  };

  try {
    const res = await apiFetch('/api/v1/customer/requests', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (!res.ok) {
      alert(data.detail || 'Có lỗi xảy ra khi gửi yêu cầu.');
      return;
    }

    closeWarrantyModal();
    alert(`🎉 ${data.message}\nMã yêu cầu: ${data.request_code}\nEmail thông báo đã được gửi cho quý khách.`);
    loadCustomerData();
    switchCustomerTab('requests');
  } catch (err) {
    alert('Lỗi kết nối máy chủ: ' + err.message);
  }
}

// -------------------------------------------------------------
// AI CHATBOT (RAG GROUNDED) (AI-01 -> AI-05)
// -------------------------------------------------------------
function toggleChatModal() {
  const modal = document.getElementById('chatModal');
  modal.classList.toggle('open');
  if (modal.classList.contains('open')) {
    document.getElementById('chatInput').focus();
  }
}

function openChatWithProduct(soldItemId) {
  const product = AppState.products.find(p => p.id === soldItemId);
  if (!product) return;
  if (product.is_expired) {
    alert('Sản phẩm đã hết hạn bảo hành, không hỗ trợ chat tư vấn.');
    return;
  }

  AppState.activeChatProduct = product;
  AppState.chatSessionId = crypto.randomUUID();
  document.getElementById('chatContextBar').style.display = 'flex';
  document.getElementById('chatProductName').innerText = `${product.product_name} (${product.model})`;
  
  const modal = document.getElementById('chatModal');
  if (!modal.classList.contains('open')) {
    modal.classList.add('open');
  }

  // Add welcome greeting
  const chatBody = document.getElementById('chatBody');
  chatBody.innerHTML = `
    <div class="chat-bubble bot">
      Dạ chào bạn, tôi là trợ lý AI VietCare. Tôi đang hỗ trợ thông tin bảo hành cho sản phẩm <strong>${escapeHtml(product.product_name)}</strong> (Model: <code>${escapeHtml(product.model)}</code>).
      <br><br>Thiết bị của bạn đang gặp vấn đề gì?
    </div>
  `;
}

function resetChatContext() {
  AppState.activeChatProduct = null;
  document.getElementById('chatContextBar').style.display = 'none';
  document.getElementById('chatBody').innerHTML = `
    <div class="chat-bubble bot">
      Dạ chào bạn, tôi là trợ lý AI VietCare của Viettronimex. Bạn đang cần hỏi về chính sách bảo hành sản phẩm nào ạ?
    </div>
  `;
}

async function sendChatMessage() {
  const input = document.getElementById('chatInput');
  const text = input.value.trim();
  if (!text) return;

  input.value = '';
  const chatBody = document.getElementById('chatBody');

  // Append user bubble
  chatBody.innerHTML += `<div class="chat-bubble user">${escapeHtml(text)}</div>`;
  chatBody.scrollTop = chatBody.scrollHeight;

  // Append typing indicator
  const typingId = 'typing_' + Date.now();
  chatBody.innerHTML += `<div id="${typingId}" class="chat-bubble bot" style="font-style: italic; color: var(--gray-500);">VietCare AI đang đối chiếu chính sách...</div>`;
  chatBody.scrollTop = chatBody.scrollHeight;

  try {
    const payload = {
      query: text,
      sold_item_id: AppState.activeChatProduct ? AppState.activeChatProduct.id : null,
      session_id: AppState.chatSessionId
    };

    const res = await apiFetch('/api/v1/customer/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const data = await res.json();

    document.getElementById(typingId)?.remove();

    let botBubble = `<div class="chat-bubble bot">${escapeHtml(data.reply)}`;

    // If RAG suggests creating a warranty request
    if (data.suggested_action === 'CREATE_WARRANTY_REQUEST' && AppState.activeChatProduct) {
      botBubble += `
        <div class="chat-suggested-action">
          <span class="suggest-box-title">🛠️ Yêu cầu kiểm tra thiết bị</span>
          <button class="btn btn-primary" onclick="openWarrantyModal(${Number(AppState.activeChatProduct.id)})">Tạo phiếu bảo hành</button>
        </div>
      `;
    }
    botBubble += `</div>`;

    chatBody.innerHTML += botBubble;
    chatBody.scrollTop = chatBody.scrollHeight;
  } catch (err) {
    document.getElementById(typingId)?.remove();
    chatBody.innerHTML += `<div class="chat-bubble bot" style="color: var(--danger);">Không thể kết nối dịch vụ AI. Vui lòng thử lại sau.</div>`;
  }
}

// -------------------------------------------------------------
// STAFF & ADMIN LOGIC (CSKH & TECHNICIAN)
// -------------------------------------------------------------
async function loadStaffRequests() {
  const statusFilter = document.getElementById('statusFilter').value;
  const channelFilter = document.getElementById('channelFilter').value;
  const search = document.getElementById('searchInput').value;

  const tbody = document.getElementById('staffTableBody');
  tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; color: var(--gray-500); padding: 24px;">Đang tải danh sách yêu cầu...</td></tr>`;

  try {
    const url = `/api/v1/staff/requests?status_filter=${statusFilter}&channel_filter=${channelFilter}&search=${encodeURIComponent(search)}`;
    const res = await apiFetch(url);
    const requests = await res.json();

    if (requests.length === 0) {
      tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; color: var(--gray-500); padding: 30px;">Không có yêu cầu nào phù hợp.</td></tr>`;
      return;
    }

    tbody.innerHTML = '';
    requests.forEach(r => {
      const tr = document.createElement('tr');
      const statusClass = getStatusClass(r.status);

      // Render action buttons depending on staff role & status
      let actionBtns = '';
      if (AppState.currentRole === 'CSKH' || AppState.currentRole === 'ADMIN') {
        if (r.status === 'Tiếp nhận' || r.status === 'Chờ bổ sung') {
          actionBtns += `<button class="btn btn-secondary" style="padding: 4px 8px; font-size: 0.78rem;" data-request-code="${escapeHtml(r.request_code)}" onclick="openVerifyModal(${Number(r.id)}, this.dataset.requestCode)">Xác minh</button> `;
        }
        if (r.status === 'Xác minh' || r.status === 'Phân công') {
          const assignLabel = r.status === 'Xác minh' ? 'Phân công KTV' : (r.technician_id ? 'Đổi KTV / lịch hẹn' : 'Phân công lại KTV');
          actionBtns += `<button class="btn btn-primary" style="padding: 4px 8px; font-size: 0.78rem;" data-request-code="${escapeHtml(r.request_code)}" onclick="openAssignModal(${Number(r.id)}, this.dataset.requestCode)">${assignLabel}</button> `;
        }
        // Button CS-08: Mark repeated call
        actionBtns += `<button class="btn btn-warning" style="padding: 4px 8px; font-size: 0.78rem;" title="Khách gọi hỏi tiến độ (+1 KPI)" onclick="markRepeatCall(${Number(r.id)})">📞 Hỏi tiến độ (${Number(r.repeat_call_count)})</button>`;
      } else if (AppState.currentRole === 'TECHNICIAN') {
        if (r.status === 'Phân công') {
          actionBtns += `<button class="btn btn-primary" style="padding: 4px 8px; font-size: 0.78rem;" onclick="updateStatus(${Number(r.id)}, 'Sửa chữa', 'KTV nhận việc và bắt đầu kiểm tra')">Nhận việc</button>`;
        } else if (r.status === 'Sửa chữa') {
          actionBtns += `<button class="btn btn-primary" style="padding: 4px 8px; font-size: 0.78rem; background: #16a34a;" data-request-code="${escapeHtml(r.request_code)}" onclick="openCompleteRepairModal(${Number(r.id)}, this.dataset.requestCode)">Hoàn tất sửa</button>`;
        }
      }

      const assignedStatus = r.status === 'Phân công' ? (r.technician_id ? 'Chờ KTV nhận việc' : 'Chờ phân công lại') : r.status;
      const technicianHtml = r.technician_id ? `<div>KTV: ${escapeHtml(r.technician_name)}</div>` : '';
      tr.innerHTML = `
        <td><strong style="color: var(--primary);">${escapeHtml(r.request_code)}</strong></td>
        <td><strong>${escapeHtml(r.customer_name)}</strong><br><span style="font-size: 0.8rem; color: var(--gray-500);">${escapeHtml(r.customer_phone)}</span></td>
        <td>${escapeHtml(r.product_name)}</td>
        <td><span style="font-size: 0.85rem;">${escapeHtml(r.error_group)}</span></td>
        <td><span class="status-badge ${statusClass}">${escapeHtml(assignedStatus)}</span>${technicianHtml}</td>
        <td><span style="font-size: 0.82rem;">${escapeHtml(r.channel)}</span></td>
        <td><div style="display: flex; gap: 4px; flex-wrap: wrap;">${actionBtns}</div></td>
      `;
      tbody.appendChild(tr);
    });
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="7" style="color: var(--danger); text-align: center;">Lỗi tải dữ liệu: ${escapeHtml(err.message)}</td></tr>`;
  }
}

async function markRepeatCall(requestId) {
  try {
    const res = await apiFetch(`/api/v1/staff/requests/${requestId}/repeat-call`, { method: 'POST' });
    const data = await res.json();
    alert(`Đã ghi nhận cuộc gọi hỏi tiến độ! Tổng số cuộc gọi lặp lại: ${data.repeat_call_count}`);
    loadStaffRequests();
    loadKPIStats();
  } catch (err) {
    alert('Lỗi: ' + err.message);
  }
}

async function updateStatus(requestId, newStatus, notes = '') {
  try {
    const res = await apiFetch(`/api/v1/staff/requests/${requestId}/status`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ new_status: newStatus, notes: notes })
    });
    if (res.ok) {
      alert(`Đã cập nhật trạng thái: ${newStatus}`);
      loadStaffRequests();
      loadKPIStats();
    }
  } catch (err) {
    alert('Lỗi cập nhật: ' + err.message);
  }
}

async function loadTechnicians() {
  try {
    const res = await apiFetch('/api/v1/staff/technicians');
    AppState.technicians = await res.json();
    const select = document.getElementById('assignTechSelect');
    if (select) {
      select.innerHTML = AppState.technicians.map(t => `<option value="${Number(t.id)}">${escapeHtml(t.name)} (${escapeHtml(t.phone)})</option>`).join('');
    }
  } catch (err) {
    console.error('Lỗi khi tải KTV:', err);
  }
}

async function loadKPIStats() {
  try {
    const res = await apiFetch('/api/v1/staff/kpi');
    const data = await res.json();
    document.getElementById('kpiTotal').innerText = data.total_requests;
    document.getElementById('kpiWebRatio').innerText = data.web_ratio + '%';
    document.getElementById('kpiRepeatCalls').innerText = data.repeat_calls;
    document.getElementById('kpiCompleted').innerText = data.completed_count;
  } catch (err) {
    console.error('Lỗi khi tải KPI:', err);
  }
}

// -------------------------------------------------------------
// PHONE RECEPTION (CS-02: CSKH NHẬP NHANH THAY KHÁCH)
// -------------------------------------------------------------
function openPhoneReceptionModal() {
  document.getElementById('phoneReceptionModal').classList.add('open');
}

function closePhoneReceptionModal() {
  document.getElementById('phoneReceptionModal').classList.remove('open');
}

async function submitPhoneReception(e) {
  e.preventDefault();
  const phone = document.getElementById('phoneRecPhone').value.trim();
  const name = document.getElementById('phoneRecName').value.trim();
  const productInfo = document.getElementById('phoneRecProduct').value.trim();
  const errorGroup = document.getElementById('phoneRecError').value;
  const desc = document.getElementById('phoneRecDesc').value.trim();
  const address = document.getElementById('phoneRecAddress').value.trim();

  if (!phone || !desc) {
    alert('Vui lòng điền đầy đủ SĐT và mô tả lỗi.');
    return;
  }

  const payload = {
    customer_phone: phone,
    customer_name: name || `Khách hàng ${phone}`,
    error_group: errorGroup,
    sold_item_id: Number(productInfo),
    error_description: desc,
    support_address: address || 'Tại cửa hàng hoặc nhà riêng',
    channel: 'Điện thoại'
  };

  try {
    const res = await apiFetch('/api/v1/customer/requests', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (res.ok) {
      closePhoneReceptionModal();
      alert(`Đã tạo thành công phiếu ${data.request_code} cho khách ${phone} qua kênh Điện thoại!`);
      loadStaffRequests();
      loadKPIStats();
    }
  } catch (err) {
    alert('Lỗi: ' + err.message);
  }
}

async function loadReceptionProducts() {
  const phone = document.getElementById('phoneRecPhone').value.trim();
  const select = document.getElementById('phoneRecProduct');
  select.replaceChildren(new Option('Chọn sản phẩm còn hạn bảo hành', ''));
  if (!phone) return;
  try {
    const response = await apiFetch(`/api/v1/customer/products/${encodeURIComponent(phone)}`);
    const products = await response.json();
    if (phone !== document.getElementById('phoneRecPhone').value.trim()) return;
    products.filter(p => !p.is_expired).forEach(p => select.add(new Option(`${p.product_name} (${p.model})`, p.id)));
    if (select.options.length === 1) select.options[0].text = 'Khách chưa có sản phẩm còn hạn bảo hành';
  } catch (error) {
    if (phone === document.getElementById('phoneRecPhone').value.trim()) select.options[0].text = error.message;
  }
}

// -------------------------------------------------------------
// ASSIGN TECHNICIAN MODAL (CS-06)
// -------------------------------------------------------------
let currentAssignRequestId = null;
function openAssignModal(requestId, requestCode) {
  currentAssignRequestId = requestId;
  document.getElementById('assignRequestCode').innerText = requestCode || '#' + requestId;
  document.getElementById('assignModal').classList.add('open');
}

function closeAssignModal() {
  document.getElementById('assignModal').classList.remove('open');
}

async function submitAssignForm(e) {
  e.preventDefault();
  const techId = parseInt(document.getElementById('assignTechSelect').value);
  const appointmentDate = document.getElementById('assignAppDate').value;
  const note = document.getElementById('assignNote').value;

  try {
    const res = await apiFetch(`/api/v1/staff/requests/${currentAssignRequestId}/status`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        new_status: 'Phân công',
        technician_id: techId,
        appointment_date: appointmentDate || null,
        notes: note || 'Đã phân công kỹ thuật viên phụ trách'
      })
    });
    if (res.ok) {
      closeAssignModal();
      alert('Phân công kỹ thuật viên thành công! Email thông báo đã gửi cho khách.');
      loadStaffRequests();
    }
  } catch (err) {
    alert('Lỗi: ' + err.message);
  }
}

// -------------------------------------------------------------
// VERIFY MODAL (CS-05)
// -------------------------------------------------------------
let currentVerifyRequestId = null;
function openVerifyModal(requestId, requestCode) {
  currentVerifyRequestId = requestId;
  document.getElementById('verifyRequestCode').innerText = requestCode || '#' + requestId;
  document.getElementById('verifyModal').classList.add('open');
}

function closeVerifyModal() {
  document.getElementById('verifyModal').classList.remove('open');
}

async function submitVerify(decision) {
  let newStatus = 'Xác minh';
  let note = document.getElementById('verifyNote').value.trim();

  if (decision === 'VALID') {
    newStatus = 'Xác minh';
    note = note || 'Hồ sơ bảo hành hợp lệ, chuẩn bị phân công kỹ thuật viên.';
  } else if (decision === 'NEED_INFO') {
    newStatus = 'Chờ bổ sung';
    note = note || 'Cần bổ sung thêm hình ảnh hiện trường sự cố.';
  } else if (decision === 'REJECT') {
    newStatus = 'Từ chối bảo hành';
    if (!note) {
      alert('Bắt buộc phải ghi lý do từ chối bảo hành theo quy định!');
      return;
    }
  }

  try {
    const res = await apiFetch(`/api/v1/staff/requests/${currentVerifyRequestId}/verify`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: decision, notes: note })
    });
    if (res.ok) {
      closeVerifyModal();
      alert(`Đã cập nhật kết quả xác minh: ${newStatus}`);
      loadStaffRequests();
    }
  } catch (err) {
    alert('Lỗi: ' + err.message);
  }
}

// -------------------------------------------------------------
// COMPLETE REPAIR MODAL (KT-05)
// -------------------------------------------------------------
let currentCompleteRequestId = null;
function openCompleteRepairModal(requestId, requestCode) {
  currentCompleteRequestId = requestId;
  document.getElementById('completeRequestCode').innerText = requestCode || '#' + requestId;
  document.getElementById('completeRepairModal').classList.add('open');
}

function closeCompleteRepairModal() {
  document.getElementById('completeRepairModal').classList.remove('open');
}

async function submitCompleteRepair(e) {
  e.preventDefault();
  const repairContent = document.getElementById('completeRepairContent').value;
  const parts = document.getElementById('completeParts').value;
  const conclusion = document.getElementById('completeConclusion').value;

  try {
    const res = await apiFetch(`/api/v1/staff/requests/${currentCompleteRequestId}/status`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        new_status: 'Hoàn tất',
        conclusion: conclusion,
        repair_content: repairContent,
        parts_replaced: parts,
        notes: `KTV hoàn tất sửa chữa: ${repairContent}`
      })
    });
    if (res.ok) {
      closeCompleteRepairModal();
      alert('Đã cập nhật hoàn tất ca bảo hành! Email thông báo kết quả đã gửi cho khách.');
      loadStaffRequests();
      loadKPIStats();
    }
  } catch (err) {
    alert('Lỗi: ' + err.message);
  }
}

// -------------------------------------------------------------
// UTILITIES
// -------------------------------------------------------------
function getStatusClass(status) {
  switch (status) {
    case 'Tiếp nhận': return 'status-tiepnhan';
    case 'Xác minh': return 'status-xacminh';
    case 'Chờ bổ sung': return 'status-xacminh';
    case 'Phân công': return 'status-phancong';
    case 'Sửa chữa': return 'status-suachua';
    case 'Hoàn tất': return 'status-hoantat';
    case 'Từ chối bảo hành': return 'status-tuchoi';
    default: return 'status-tiepnhan';
  }
}

// Escape data at the HTML boundary; keep plain values in application state.
function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  })[char]);
}

function safeImageUrl(value) {
  try {
    const url = new URL(value, window.location.origin);
    if (['https:', 'http:'].includes(url.protocol)) return escapeHtml(url.href);
  } catch (_) {}
  return '/static/invalid-image';
}

async function apiFetch(input, options = {}) {
  let session;
  try { session = JSON.parse(localStorage.getItem('vietcare_user') || 'null'); } catch (_) {}
  const headers = new Headers(options.headers);
  if (session?.access_token) headers.set('Authorization', `Bearer ${session.access_token}`);
  const response = await fetch(input, { ...options, headers });
  if (response.status === 401) {
    localStorage.removeItem('vietcare_user');
    window.location.href = '/login';
  }
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(typeof data.detail === 'string' ? data.detail : 'Dữ liệu hoặc thao tác không hợp lệ');
  }
  return response;
}

// Keep the complete product name in storage; shorten only its presentation.
function productDisplayName(name, model = '') {
  let text = String(name ?? '');
  if (model) {
    const escaped = String(model).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    text = text.replace(new RegExp('\\(?\\s*' + escaped + '\\s*\\)?', 'gi'), ' ');
  }
  return text.replace(/\bnew\s*20\d{2}\b/gi, '').replace(/\s+/g, ' ').replace(/[\s-]+$/, '').trim() || String(name ?? '');
}

function statusDisplayName(status, technician = false) {
  if (status === 'Tiếp nhận') return 'Đã tiếp nhận';
  if (technician && status === 'Phân công') return 'Chờ xác nhận';
  return status;
}

function formatLocalTime(value) {
  if (!value) return 'Chưa có';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '' : date.toLocaleString('vi-VN', {timeZone: 'Asia/Ho_Chi_Minh', hour: '2-digit', minute: '2-digit', day: '2-digit', month: '2-digit', year: 'numeric'});
}

function previewIncidentFiles(input, containerId) {
  (input._previewUrls || []).forEach(url => URL.revokeObjectURL(url));
  input._previewUrls = [];
  const container = document.getElementById(containerId);
  container.replaceChildren();
  const files = [...input.files];
  const total = files.reduce((sum, file) => sum + file.size, 0);
  const allowed = /\.(jpe?g|png|gif|webp|mp4|webm|mov)$/i;
  if (files.length > 5 || total > 50 * 1024 * 1024 || files.some(file => file.size > 25 * 1024 * 1024 || !allowed.test(file.name))) {
    input.value = '';
    container.innerHTML = '<p class="error-text">Chọn tối đa 5 ảnh/video đúng định dạng, mỗi tệp tối đa 25 MB và tổng tối đa 50 MB.</p>';
    return;
  }
  files.forEach(file => {
    const figure = document.createElement('figure');
    const media = document.createElement(/\.(mp4|webm|mov)$/i.test(file.name) ? 'video' : 'img');
    const url = URL.createObjectURL(file);
    input._previewUrls.push(url);
    media.src = url;
    if (media.tagName === 'VIDEO') { media.controls = true; media.preload = 'metadata'; }
    else media.alt = file.name;
    const caption = document.createElement('figcaption');
    caption.textContent = file.name;
    figure.append(media, caption);
    container.append(figure);
  });
}

let detailGeneration = 0;
let detailUrls = [];
function closeRequestDetail() {
  ++detailGeneration;
  detailUrls.forEach(url => URL.revokeObjectURL(url));
  detailUrls = [];
  document.getElementById('requestDetailModal')?.remove();
}

async function showRequestDetail(id) {
  closeRequestDetail();
  const generation = detailGeneration;
  const modal = document.createElement('div');
  modal.id = 'requestDetailModal';
  modal.className = 'modal-backdrop open';
  modal.innerHTML = `<section class="modal-box request-detail-modal" role="dialog" aria-modal="true" aria-labelledby="requestDetailTitle">
    <div class="detail-heading"><h2 id="requestDetailTitle">Chi tiết yêu cầu</h2><button type="button" class="detail-close" aria-label="Đóng" onclick="closeRequestDetail()">&times;</button></div>
    <div id="requestDetailBody" aria-live="polite">Đang tải...</div></section>`;
  modal.addEventListener('click', event => { if (event.target === modal) closeRequestDetail(); });
  document.body.append(modal);
  modal.querySelector('.detail-close').focus();
  const body = modal.querySelector('#requestDetailBody');
  try {
    const data = await (await apiFetch(`/api/v1/requests/${Number(id)}`)).json();
    if (generation !== detailGeneration) return;
    body.innerHTML = `<p class="req-code">${escapeHtml(data.request_code)}</p>
      <h3>${escapeHtml(productDisplayName(data.product_name, data.model))}</h3>
      <dl class="detail-facts">
        <div><dt>Khách hàng</dt><dd>${escapeHtml(data.customer_name)} — ${escapeHtml(data.customer_phone)}</dd></div>
        <div><dt>Model</dt><dd>${escapeHtml(data.model)}</dd></div>
        <div><dt>Trạng thái</dt><dd>${escapeHtml(statusDisplayName(data.status))}${data.is_overdue ? ' <span class="overdue-badge">Quá hạn xử lý</span>' : ''}</dd></div>
        <div><dt>Ngày gửi</dt><dd>${escapeHtml(formatLocalTime(data.created_at))}</dd></div>
        <div><dt>Hạn xử lý tiếp nhận</dt><dd>${escapeHtml(formatLocalTime(data.response_due_at))}${data.handled_late ? ' · Đã xử lý trễ hạn' : ''}</dd></div>
        <div><dt>Sự cố</dt><dd>${escapeHtml(data.error_group)} — ${escapeHtml(data.error_description)}</dd></div>
        <div><dt>Địa chỉ</dt><dd>${escapeHtml(data.support_address)}</dd></div>
        <div><dt>Kỹ thuật viên</dt><dd>${escapeHtml(data.technician_name)}</dd></div>
        <div><dt>Lịch hẹn</dt><dd>${escapeHtml(data.appointment_date || 'Chưa hẹn')}</dd></div>
      </dl>
      <h3>Ảnh/video sự cố</h3><div id="detailMedia" class="media-preview"></div>
      <h3>Lịch sử xử lý</h3><div class="detail-history">${(data.timeline || []).map(t => `<p><strong>${escapeHtml(statusDisplayName(t.status))}</strong> · ${escapeHtml(t.time)}<br>${escapeHtml(t.note || '')}</p>`).join('') || '<p>Chưa có cập nhật.</p>'}</div>
      ${(data.inspections || []).map(i => `<h3>Kết quả sửa chữa</h3><p>${escapeHtml(i.conclusion)}<br>${escapeHtml(i.repair_content || '')}<br>${escapeHtml(i.parts_replaced || '')}</p>`).join('')}`;
    const gallery = body.querySelector('#detailMedia');
    if (!data.attachments?.length) gallery.textContent = 'Chưa có tệp đính kèm.';
    for (const file of data.attachments || []) {
      if (generation !== detailGeneration) return;
      const figure = document.createElement('figure');
      const caption = document.createElement('figcaption');
      caption.textContent = `${file.file_name} (${Math.ceil(file.file_size / 1024)} KB)`;
      figure.append(caption);
      gallery.append(figure);
      try {
        const response = await apiFetch(`/api/v1/attachments/${Number(file.id)}`);
        const blob = await response.blob();
        if (generation !== detailGeneration) return;
        const url = URL.createObjectURL(blob);
        detailUrls.push(url);
        const media = document.createElement(file.file_type === 'video' ? 'video' : 'img');
        media.src = url;
        if (file.file_type === 'video') { media.controls = true; media.preload = 'metadata'; }
        else media.alt = file.file_name;
        const link = document.createElement('a');
        link.href = url; link.target = '_blank'; link.rel = 'noopener'; link.textContent = 'Mở tệp';
        figure.prepend(media);
        figure.append(link);
      } catch (error) {
        const message = document.createElement('p'); message.className = 'error-text'; message.textContent = error.message; figure.append(message);
      }
    }
  } catch (error) {
    if (generation === detailGeneration) body.textContent = error.message;
  }
}

document.addEventListener('keydown', event => { if (event.key === 'Escape') closeRequestDetail(); });

// Centered notification dialogs shared by every page (replaces the browser's alert/prompt).
(function () {
  const ICONS = { success: '✓', error: '!', warning: '!', info: 'i' };
  const TITLES = { success: 'Thành công', error: 'Không thực hiện được', warning: 'Lưu ý', info: 'Thông báo' };
  let queue = Promise.resolve();

  function build({ type, title, message, actions, input }) {
    return new Promise(resolve => {
      const backdrop = document.createElement('div');
      backdrop.className = 'vc-notice-backdrop';
      const box = document.createElement('div');
      box.className = `vc-notice vc-notice-${type}`;
      box.setAttribute('role', type === 'error' || type === 'warning' ? 'alertdialog' : 'dialog');
      box.setAttribute('aria-modal', 'true');

      const icon = document.createElement('div');
      icon.className = 'vc-notice-icon';
      icon.setAttribute('aria-hidden', 'true');
      icon.textContent = ICONS[type] || ICONS.info;
      const heading = document.createElement('h3');
      heading.className = 'vc-notice-title';
      heading.id = `vc-notice-${Date.now()}`;
      heading.textContent = title || TITLES[type] || TITLES.info;
      box.setAttribute('aria-labelledby', heading.id);
      box.append(icon, heading);

      if (message) {
        const body = document.createElement('div');
        body.className = 'vc-notice-message';
        // Text only (never HTML) so server messages cannot inject markup; **x** renders bold.
        String(message).split(/(\*\*[^*]+\*\*)/).forEach(part => {
          if (/^\*\*[^*]+\*\*$/.test(part)) {
            const strong = document.createElement('strong');
            strong.textContent = part.slice(2, -2);
            body.append(strong);
          } else {
            body.append(document.createTextNode(part));
          }
        });
        box.append(body);
      }

      let field = null;
      if (input) {
        field = document.createElement('textarea');
        field.className = 'form-control vc-notice-input';
        field.rows = 3;
        field.placeholder = input.placeholder || '';
        field.setAttribute('aria-label', input.label || title || '');
        box.append(field);
      }

      const row = document.createElement('div');
      row.className = 'vc-notice-actions';
      const close = value => {
        document.removeEventListener('keydown', onKey, true);
        backdrop.remove();
        if (previousFocus && previousFocus.focus) previousFocus.focus();
        resolve(value);
      };
      const buttons = actions.map(action => {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = `btn ${action.primary ? 'btn-red' : 'btn-outline-navy'}`;
        btn.textContent = action.label;
        btn.addEventListener('click', () => {
          if (field && action.value === true) {
            const text = field.value.trim();
            if (input.required && !text) {
              field.classList.add('vc-notice-invalid');
              field.focus();
              return;
            }
            close(text);
          } else {
            close(field ? null : action.value);
          }
        });
        row.append(btn);
        return btn;
      });
      box.append(row);
      backdrop.append(box);

      const onKey = event => {
        if (event.key === 'Escape') {
          event.stopPropagation();
          close(field ? null : actions.find(a => !a.primary)?.value ?? actions[0].value);
        } else if (event.key === 'Enter' && !field && document.activeElement?.tagName !== 'BUTTON') {
          event.preventDefault();
          buttons[buttons.length - 1].click();
        } else if (event.key === 'Tab') {
          const focusables = [field, ...buttons].filter(Boolean);
          const index = focusables.indexOf(document.activeElement);
          const next = event.shiftKey ? (index <= 0 ? focusables.length - 1 : index - 1) : (index + 1) % focusables.length;
          event.preventDefault();
          focusables[next].focus();
        }
      };
      const previousFocus = document.activeElement;
      document.addEventListener('keydown', onKey, true);
      document.body.append(backdrop);
      (field || buttons[buttons.length - 1]).focus();
    });
  }

  // Dialogs are shown one at a time, in order.
  function enqueue(options) {
    const result = queue.then(() => build(options));
    queue = result.catch(() => {});
    return result;
  }

  /** showNotice('Nội dung', { type: 'success'|'error'|'warning'|'info', title, buttonText }) */
  window.showNotice = function (message, options = {}) {
    const type = options.type || 'info';
    return enqueue({ type, title: options.title, message,
                     actions: [{ label: options.buttonText || 'Đã hiểu', value: true, primary: true }] });
  };

  /** confirmNotice('Nội dung', { title, confirmText, cancelText }) -> Promise<boolean> */
  window.confirmNotice = function (message, options = {}) {
    return enqueue({ type: options.type || 'warning', title: options.title, message,
                     actions: [{ label: options.cancelText || 'Hủy', value: false },
                               { label: options.confirmText || 'Đồng ý', value: true, primary: true }] });
  };

  /** askText('Tiêu đề', { message, placeholder, confirmText, required }) -> Promise<string|null> */
  window.askText = function (title, options = {}) {
    return enqueue({ type: 'info', title, message: options.message,
                     input: { placeholder: options.placeholder, label: title, required: options.required !== false },
                     actions: [{ label: options.cancelText || 'Hủy', value: false },
                               { label: options.confirmText || 'Xác nhận', value: true, primary: true }] });
  };

  // Safety net: any leftover alert() still uses the styled dialog.
  window.alert = message => { window.showNotice(String(message ?? '')); };
})();

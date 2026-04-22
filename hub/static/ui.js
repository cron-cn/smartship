/* 全局 UI 脚本：统一设备行事件与搜索过滤逻辑 */
(function () {
  function onEditTriggerClick(e) {
    const btn = e.target.closest && e.target.closest('.edit-trigger');
    if (!btn) return;
    const data = btn.dataset.device;
    if (!data) return;
    try {
      const device = JSON.parse(data);
      if (window.openEditModal && typeof window.openEditModal === 'function') {
        window.openEditModal(device);
      } else {
        // 触发自定义事件，供页面其他脚本监听
        document.dispatchEvent(new CustomEvent('open-edit', { detail: device }));
      }
    } catch (err) {
      console.error('解析 device 数据失败', err);
    }
  }

  function setupDelegation() {
    document.addEventListener('click', onEditTriggerClick);
  }

  // 编辑模态相关状态与方法
  let currentEditIndex = -1;
  let allDevicesForEdit = [];

  function updateEditList() {
    allDevicesForEdit = [];
    document.querySelectorAll('.edit-trigger').forEach(btn => {
      const row = btn.closest('tr');
      if (row && row.style.display !== 'none') {
        try {
          allDevicesForEdit.push(JSON.parse(btn.dataset.device));
        } catch (e) {}
      }
    });
  }

  function openEditModal(device) {
    updateEditList();
    currentEditIndex = allDevicesForEdit.findIndex(d => d.id === device.id);

    const prevBtn = document.getElementById('edit-prev');
    const nextBtn = document.getElementById('edit-next');
    if(prevBtn) prevBtn.disabled = currentEditIndex <= 0;
    if(nextBtn) nextBtn.disabled = currentEditIndex >= allDevicesForEdit.length - 1;

    const editForm = document.getElementById('edit-form');
    if (editForm) {
      editForm.action = `/edit/${device.id}`;
      Object.entries(device).forEach(([key, value]) => {
        const field = editForm.elements[key];
        if (field && field.type !== 'file' && field.type !== 'hidden') {
          try { field.value = value || ''; } catch (e) {}
        }
      });
      // 处理分类多选框：选中设备已有分类
      try {
        const catSelect = editForm.querySelector('select[name="category_ids"]');
        if (catSelect) {
          const selected = (device.categories || []).map(c => String(c.id));
          Array.from(catSelect.options).forEach(opt => {
            opt.selected = selected.includes(opt.value);
          });
        }
      } catch (e) { /* ignore */ }
    }

    const currentBrokenList = document.getElementById('edit-existing-broken-list');
    if (currentBrokenList) {
      currentBrokenList.innerHTML = '';
      (device.broken_items || []).forEach((item) => {
        const entry = document.createElement('div');
        entry.className = 'broken-hint-card';
        entry.innerHTML = `<strong>${item.index}.</strong> ${item.reason || '无原因'}`;
        if (item.image_file_id) {
          entry.innerHTML += ` <a href="/device-file/${item.image_file_id}" target="_blank" style="margin-left:8px;">查看图片</a>`;
        }
        currentBrokenList.appendChild(entry);
      });
      if (!device.broken_items || device.broken_items.length === 0) {
        currentBrokenList.innerHTML = '<span class="empty-hint" style="font-size:13px;color:var(--text-muted);">暂无记录</span>';
      }
    }

    const editBrokenList = document.getElementById('edit-broken-list');
    if (editBrokenList && window.resetBrokenList) window.resetBrokenList(editBrokenList);

    // 打开抽屉（如果页面定义了 openDrawer）
    if (window.openDrawer) {
      window.openDrawer('edit-drawer');
    } else {
      // 触发事件供页面处理
      document.dispatchEvent(new CustomEvent('open-edit-drawer', { detail: device }));
    }
  }

  function setupEditNav() {
    const prev = document.getElementById('edit-prev');
    const next = document.getElementById('edit-next');
    if (prev) prev.addEventListener('click', (e) => {
      e.preventDefault();
      if (currentEditIndex > 0) openEditModal(allDevicesForEdit[currentEditIndex - 1]);
    });
    if (next) next.addEventListener('click', (e) => {
      e.preventDefault();
      if (currentEditIndex < allDevicesForEdit.length - 1) openEditModal(allDevicesForEdit[currentEditIndex + 1]);
    });
  }

  // 抽屉（drawer）控制
  function openDrawer(id) {
    const backdrop = document.getElementById('drawer-backdrop');
    const drawer = document.getElementById(id);
    if (!drawer) return;
    if (backdrop) backdrop.setAttribute('aria-hidden', 'false');
    drawer.setAttribute('aria-hidden', 'false');
    document.body.style.overflow = 'hidden';
  }

  function closeDrawers() {
    const backdrop = document.getElementById('drawer-backdrop');
    if (backdrop) backdrop.setAttribute('aria-hidden', 'true');
    document.querySelectorAll('.drawer').forEach(d => d.setAttribute('aria-hidden', 'true'));
    document.body.style.overflow = '';
    const editForm = document.getElementById('edit-form');
    if (editForm) {
      try { editForm.reset(); editForm.action = ''; } catch (e) {}
    }
  }

  function setupDrawerControls() {
    // 使用事件委托处理打开/关闭抽屉，避免在 DOM 被替换后事件监听失效
    const backdrop = document.getElementById('drawer-backdrop');
    if (backdrop) backdrop.addEventListener('click', closeDrawers);
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeDrawers(); });

    document.addEventListener('click', (e) => {
      const openBtn = e.target.closest && e.target.closest('#open-add-drawer');
      if (openBtn) {
        e.preventDefault();
        openDrawer('add-drawer');
        return;
      }
      const closeBtn = e.target.closest && e.target.closest('.drawer-close');
      if (closeBtn) {
        e.preventDefault();
        closeDrawers();
        return;
      }
    });
  }

  // 图片预览弹窗（轻量级）
  function createImageModal() {
    let modal = document.getElementById('image-modal');
    if (modal) return modal;
    modal = document.createElement('div');
    modal.id = 'image-modal';
    modal.setAttribute('aria-hidden', 'true');
    modal.style.cssText = 'position:fixed;inset:0;display:none;align-items:center;justify-content:center;z-index:1200;';

    const backdrop = document.createElement('div');
    backdrop.className = 'image-modal-backdrop';
    backdrop.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.55);';
    backdrop.style.zIndex = '1200';
    backdrop.addEventListener('click', closeImageModal);

    const box = document.createElement('div');
    box.className = 'image-modal-box';
    box.style.cssText = 'max-width:90%;max-height:90%;background:#fff;border-radius:6px;overflow:hidden;pointer-events:auto;box-shadow:0 10px 30px rgba(0,0,0,0.4);padding:8px;';
    box.style.zIndex = '1201';

    const img = document.createElement('img');
    img.id = 'image-modal-img';
    img.style.cssText = 'display:block;max-width:100%;max-height:80vh;margin:0 auto;filter:none;';

    const caption = document.createElement('div');
    caption.id = 'image-modal-caption';
    caption.style.cssText = 'padding:8px 12px;font-size:13px;color:#333;background:#fafafa;border-top:1px solid #eee;';

    const controls = document.createElement('div');
    controls.className = 'image-modal-controls';
    controls.style.cssText = 'display:flex;gap:8px;align-items:center;padding:8px 12px;background:#fff;border-top:1px solid #eee;';

    const openLink = document.createElement('a');
    openLink.id = 'image-modal-open';
    openLink.className = 'btn btn-ghost';
    openLink.target = '_blank';
    openLink.rel = 'noopener noreferrer';
    openLink.textContent = '打开原图';

    const downloadLink = document.createElement('a');
    downloadLink.id = 'image-modal-download';
    downloadLink.className = 'btn btn-ghost';
    downloadLink.textContent = '下载原图';

    controls.appendChild(openLink);
    controls.appendChild(downloadLink);

    const closeBtn = document.createElement('button');
    closeBtn.className = 'icon-btn image-modal-close';
    closeBtn.innerHTML = '\u00d7';
    closeBtn.style.cssText = 'position:absolute;right:12px;top:12px;font-size:22px;background:transparent;border:0;color:#fff;cursor:pointer;z-index:1202;';
    closeBtn.addEventListener('click', closeImageModal);

    box.appendChild(img);
    box.appendChild(caption);
    box.appendChild(controls);

    modal.appendChild(backdrop);
    modal.appendChild(box);
    modal.appendChild(closeBtn);
    document.body.appendChild(modal);
    return modal;
  }

  function openImageModal(url, title) {
    const modal = createImageModal();
    const img = modal.querySelector('#image-modal-img');
    const caption = modal.querySelector('#image-modal-caption');
    const openLink = modal.querySelector('#image-modal-open');
    const downloadLink = modal.querySelector('#image-modal-download');
    img.src = url;
    caption.textContent = title || '';
    if (openLink) openLink.href = url;
    if (downloadLink) {
      downloadLink.href = url;
      // 尝试从 title 或 url 推断文件名
      try {
        const urlObj = new URL(url, window.location.origin);
        const path = urlObj.pathname;
        const name = (title && title.trim()) || path.split('/').pop() || 'image';
        downloadLink.setAttribute('download', name);
      } catch (e) {
        // 如果 URL 无法解析，仍设置 href
        downloadLink.removeAttribute('download');
      }
    }
    modal.setAttribute('aria-hidden', 'false');
    modal.style.display = 'flex';
    document.body.style.overflow = 'hidden';
  }

  function closeImageModal() {
    const modal = document.getElementById('image-modal');
    if (!modal) return;
    modal.setAttribute('aria-hidden', 'true');
    modal.style.display = 'none';
    const img = modal.querySelector('#image-modal-img');
    if (img) img.src = '';
    // 恢复页面滚动（简单处理）
    document.body.style.overflow = '';
  }

  function setupImagePreview() {
    document.addEventListener('click', (e) => {
      const link = e.target.closest && e.target.closest('.preview-img-link');
      if (!link) return;
      e.preventDefault();
      const url = link.dataset && (link.dataset.fileUrl || link.href);
      const title = link.getAttribute('title') || link.textContent || '';
      if (url) openImageModal(url, title.trim());
    });
    // 也响应 Esc 关闭
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeImageModal(); });
  }

  function setupTableSearch(inputSelector, rowSelector, updateCallbackName) {
    const input = document.querySelector(inputSelector);
    if (!input) return;
    input.addEventListener('input', () => {
      const q = input.value.trim().toLowerCase();
      const rows = Array.from(document.querySelectorAll(rowSelector));
      rows.forEach(row => {
        const searchable = (row.dataset.search || '').toLowerCase();
        row.style.display = !q || searchable.includes(q) ? '' : 'none';
      });
      if (updateCallbackName && window[updateCallbackName]) {
        try { window[updateCallbackName](); } catch (e) {}
      }
    });
  }

  function setupSidebarSearch(inputSelector, itemSelector) {
    const input = document.querySelector(inputSelector);
    if (!input) return;
    input.addEventListener('input', () => {
      const q = input.value.trim().toLowerCase();
      const items = Array.from(document.querySelectorAll(itemSelector));
      items.forEach(item => {
        const searchable = (item.dataset.search || '').toLowerCase();
        item.style.display = !q || searchable.includes(q) ? '' : 'none';
      });
    });
  }

  // 验证侧边栏 ID 是否按升序排列，如果检测到不按顺序则在列表上方显示提示
  function verifySidebarOrder(itemSelector) {
    const items = Array.from(document.querySelectorAll(itemSelector));
    if (!items.length) return;
    const ids = items.map(it => {
      const v = it.getAttribute('data-id');
      return v == null ? NaN : parseInt(v, 10);
    }).filter(n => !Number.isNaN(n));
    let ordered = true;
    for (let i = 1; i < ids.length; i++) {
      if (ids[i] < ids[i - 1]) { ordered = false; break; }
    }
    // 如果不按升序，展示一个短提示（只显示一次）
    if (!ordered) {
      const first = items[0].closest('.sidebar-device-list') || items[0].parentElement;
      if (!first) return;
      if (first.querySelector('.sidebar-order-warning')) return;
      const warn = document.createElement('div');
      warn.className = 'sidebar-order-warning';
      warn.style.cssText = 'padding:8px 12px; background:var(--warn-bg, #fff4e5); color:var(--warn-fore, #663c00); border-radius:4px; margin-bottom:8px; font-size:13px;';
      warn.textContent = '警告：侧栏设备编号未按升序排列，页面显示顺序可能与数据库顺序不一致。';
      first.insertBefore(warn, first.firstChild);
    }
  }

  // 验证表格中行的 data-id 是否按升序排列（用于设备列表/编辑页）
  function verifyTableOrder(rowSelector) {
    const rows = Array.from(document.querySelectorAll(rowSelector));
    if (!rows.length) return;
    const ids = rows.map(r => {
      const v = r.getAttribute('data-id');
      return v == null ? NaN : parseInt(v, 10);
    }).filter(n => !Number.isNaN(n));
    let ordered = true;
    for (let i = 1; i < ids.length; i++) {
      if (ids[i] < ids[i - 1]) { ordered = false; break; }
    }
    if (!ordered) {
      const table = rows[0].closest('.table-container') || rows[0].closest('table') || rows[0].parentElement;
      if (!table) return;
      if (table.querySelector('.table-order-warning')) return;
      const warn = document.createElement('div');
      warn.className = 'table-order-warning';
      warn.style.cssText = 'padding:8px 12px; background:var(--warn-bg, #fff4e5); color:var(--warn-fore, #663c00); border-radius:4px; margin-bottom:8px; font-size:13px;';
      warn.textContent = '注意：设备列表编号未按升序排列，检查后端排序或分页参数。';
      table.parentElement.insertBefore(warn, table);
    }
  }

  // 初始化入口
  function initUI() {
    setupDelegation();
    setupTableSearch('#device-search', 'tbody tr[data-search]', 'updateEditList');
    setupSidebarSearch('#sidebar-device-search', '.sidebar-device-item');
    // 验证侧边栏编号顺序与表格编号顺序
    verifySidebarOrder('.sidebar-device-item');
    verifyTableOrder('tbody tr[data-id]');
    setupEditNav();
    setupDrawerControls();
    setupImagePreview();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initUI);
  } else {
    initUI();
  }

  // 导出以便测试/手动触发
  window.__lab_ui = { initUI, updateEditList, openEditModal, openDrawer, closeDrawers };
  // 同时向全局暴露函数，兼容模板中可能的直接调用
  window.updateEditList = updateEditList;
  window.openEditModal = openEditModal;
  window.openDrawer = openDrawer;
  window.closeDrawers = closeDrawers;
})();

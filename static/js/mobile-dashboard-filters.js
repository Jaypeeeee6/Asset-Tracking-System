/**
 * Mobile filter bottom sheet for the asset dashboard (QC-Monitor / maa-inventory pattern).
 */
(function () {
  var MQ = window.matchMedia('(max-width: 640px)');
  var sheet = null;
  var activeCtx = null;

  function isMobile() {
    return MQ.matches;
  }

  function ensureSheet() {
    if (sheet) return sheet;
    sheet = document.getElementById('mobile-filter-sheet');
    if (!sheet) return null;

    sheet.querySelectorAll('[data-mobile-filter-close]').forEach(function (el) {
      el.addEventListener('click', closeSheet);
    });
    var clearBtn = sheet.querySelector('[data-mobile-filter-clear]');
    var applyBtn = sheet.querySelector('[data-mobile-filter-apply]');
    if (clearBtn) clearBtn.addEventListener('click', onClear);
    if (applyBtn) applyBtn.addEventListener('click', onApply);
    return sheet;
  }

  function getForm() {
    return document.getElementById('searchForm');
  }

  function buildCategories(form) {
    var cats = [];
    if (!form) return cats;

    form.querySelectorAll('.filter-panel__controls .filter-group select').forEach(function (select, idx) {
      var label = (select.getAttribute('aria-label') || '').trim();
      cats.push({
        id: select.name || ('select-' + idx),
        label: label || 'Option',
        type: 'select',
        select: select
      });
    });
    return cats;
  }

  function readDraft(cats) {
    return cats.map(function (cat) {
      return cat.select.value || '';
    });
  }

  function categoryHasValue(cat, draftVal) {
    return !!(draftVal && String(draftVal).trim());
  }

  function filtersAreActive(cats, draft) {
    return cats.some(function (cat, idx) {
      return categoryHasValue(cat, draft ? draft[idx] : readDraft(cats)[idx]);
    });
  }

  function updateBadge(cats) {
    var active = filtersAreActive(cats);
    document.querySelectorAll('[data-mobile-filter-trigger]').forEach(function (el) {
      el.classList.toggle('is-active', active);
    });
  }

  function renderCategoryList(cats, activeIndex, draft) {
    var catsEl = sheet.querySelector('[data-mobile-filter-cats]');
    if (!catsEl) return;
    catsEl.innerHTML = '';
    cats.forEach(function (cat, idx) {
      var btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'mobile-filter-cat' + (idx === activeIndex ? ' is-selected' : '');
      btn.textContent = cat.label;
      if (categoryHasValue(cat, draft[idx])) btn.classList.add('has-value');
      btn.addEventListener('click', function () {
        activeCtx.activeIndex = idx;
        renderCategoryList(cats, idx, draft);
        renderOptions(cats[idx], draft[idx]);
      });
      catsEl.appendChild(btn);
    });
  }

  function renderOptions(cat, draftVal) {
    var optionsEl = sheet.querySelector('[data-mobile-filter-options]');
    if (!optionsEl || !cat || cat.type !== 'select') return;
    optionsEl.innerHTML = '';

    Array.prototype.forEach.call(cat.select.options, function (opt) {
      var row = document.createElement('label');
      row.className = 'mobile-filter-option';
      var input = document.createElement('input');
      input.type = 'radio';
      input.name = 'mobile-filter-option';
      input.value = opt.value;
      if (String(draftVal) === String(opt.value)) input.checked = true;
      input.addEventListener('change', function () {
        if (!activeCtx) return;
        activeCtx.draft[activeCtx.activeIndex] = opt.value;
        renderCategoryList(activeCtx.cats, activeCtx.activeIndex, activeCtx.draft);
      });
      var mark = document.createElement('span');
      mark.className = 'mobile-filter-option-check';
      var text = document.createElement('span');
      text.className = 'mobile-filter-option-label';
      text.textContent = (opt.textContent || '').trim() || opt.value || 'All';
      row.appendChild(input);
      row.appendChild(mark);
      row.appendChild(text);
      optionsEl.appendChild(row);
    });
  }

  function openSheet() {
    if (!isMobile()) return false;
    var form = getForm();
    if (!form || !ensureSheet()) return false;

    var cats = buildCategories(form);
    if (!cats.length) return false;

    var draft = readDraft(cats);
    activeCtx = {
      form: form,
      cats: cats,
      activeIndex: 0,
      draft: draft
    };

    sheet.hidden = false;
    sheet.setAttribute('aria-hidden', 'false');
    sheet.classList.add('is-open');
    document.documentElement.classList.add('mobile-filter-open');
    renderCategoryList(cats, 0, draft);
    renderOptions(cats[0], draft[0]);
    return true;
  }

  function closeSheet() {
    if (!sheet) return;
    sheet.classList.remove('is-open');
    sheet.hidden = true;
    sheet.setAttribute('aria-hidden', 'true');
    document.documentElement.classList.remove('mobile-filter-open');
    activeCtx = null;
  }

  function applyDraftToForm() {
    if (!activeCtx) return;
    activeCtx.cats.forEach(function (cat, idx) {
      cat.select.value = activeCtx.draft[idx] || '';
    });
  }

  function triggerLiveSearch() {
    if (typeof window.liveSearchRefresh === 'function') {
      window.liveSearchRefresh(true);
      return;
    }
    var form = getForm();
    if (!form) return;
    if (typeof form.requestSubmit === 'function') form.requestSubmit();
    else form.submit();
  }

  function commitFilters(triggerRefresh) {
    if (!activeCtx) return;
    var cats = activeCtx.cats;
    applyDraftToForm();
    updateBadge(cats);
    closeSheet();
    if (triggerRefresh) triggerLiveSearch();
  }

  function onApply(e) {
    e.preventDefault();
    commitFilters(true);
  }

  function onClear(e) {
    e.preventDefault();
    if (!activeCtx) return;
    activeCtx.draft = activeCtx.cats.map(function () {
      return '';
    });
    commitFilters(true);
  }

  function setupDock() {
    document.body.classList.add('dashboard-page-open', 'has-dashboard-mobile-dock');

    var dock = document.querySelector('.dashboard-mobile-dock');
    if (dock && dock.parentElement !== document.body) {
      document.body.appendChild(dock);
    }
    if (sheet && sheet.parentElement !== document.body) {
      document.body.appendChild(sheet);
    }

    document.querySelectorAll('[data-dashboard-dock-filter]').forEach(function (btn) {
      btn.addEventListener('click', function (e) {
        e.preventDefault();
        openSheet();
      });
    });

    document.querySelectorAll('[data-dashboard-dock-qr]').forEach(function (btn) {
      btn.addEventListener('click', function (e) {
        e.preventDefault();
        var qrBtn = document.getElementById('departmentQRBtn');
        if (qrBtn) qrBtn.click();
      });
    });
  }

  window.ATSMobileFilters = {
    open: openSheet,
    close: closeSheet,
    refreshBadge: function () {
      var form = getForm();
      if (!form) return;
      updateBadge(buildCategories(form));
    }
  };

  function init() {
    if (!getForm()) return;
    ensureSheet();
    setupDock();
    var form = getForm();
    if (form) {
      updateBadge(buildCategories(form));
      form.querySelectorAll('.filter-panel__controls select').forEach(function (select) {
        select.addEventListener('change', function () {
          updateBadge(buildCategories(form));
        });
      });
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && sheet && sheet.classList.contains('is-open')) {
      closeSheet();
    }
  });
})();

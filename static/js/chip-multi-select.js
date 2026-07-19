(function () {
  'use strict';

  function escapeHtml(text) {
    var div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  function getOptionsFromSource(root) {
    var options = [];
    var native = root.querySelector('.chip-multi-select-native');
    if (native) {
      native.querySelectorAll('input[type="checkbox"]').forEach(function (cb) {
        var label = native.querySelector('label[for="' + cb.id + '"]');
        options.push({
          value: cb.value,
          text: label ? label.textContent.trim() : cb.value,
        });
      });
      if (options.length) return options;
    }

    var select = root.querySelector('.chip-multi-select-source');
    if (select) {
      Array.prototype.forEach.call(select.options, function (opt) {
        if (opt.value) {
          options.push({ value: opt.value, text: opt.textContent.trim() });
        }
      });
    }
    return options;
  }

  function getInitialValues(root) {
    var values = [];
    var native = root.querySelector('.chip-multi-select-native');
    if (native) {
      native.querySelectorAll('input[type="checkbox"]:checked').forEach(function (cb) {
        values.push(cb.value);
      });
      if (values.length) return values;
    }

    var select = root.querySelector('.chip-multi-select-source');
    if (select) {
      Array.prototype.forEach.call(select.selectedOptions, function (opt) {
        if (opt.value) values.push(opt.value);
      });
    }
    return values;
  }

  function syncNative(root, selected) {
    var native = root.querySelector('.chip-multi-select-native');
    if (native) {
      native.querySelectorAll('input[type="checkbox"]').forEach(function (cb) {
        cb.checked = selected.indexOf(cb.value) !== -1;
      });
    }

    var select = root.querySelector('.chip-multi-select-source');
    if (select) {
      Array.prototype.forEach.call(select.options, function (opt) {
        opt.selected = selected.indexOf(opt.value) !== -1;
      });
    }
  }

  function destroyChipMultiSelect(root) {
    if (!root) return;
    var api = root._chipMultiSelectApi;
    if (api && typeof api.destroy === 'function') {
      api.destroy();
    }
    delete root._chipMultiSelectApi;
    delete root.dataset.chipMultiSelectInit;
    root.classList.remove('is-open');
    var chipsEl = root.querySelector('.chip-multi-select-chips');
    var dropdownEl = root.querySelector('.chip-multi-select-dropdown');
    if (chipsEl) chipsEl.innerHTML = '';
    if (dropdownEl) dropdownEl.innerHTML = '';
  }

  function initChipMultiSelect(root) {
    if (!root) return null;
    if (root.dataset.chipMultiSelectInit === '1' && root._chipMultiSelectApi) {
      return root._chipMultiSelectApi;
    }
    destroyChipMultiSelect(root);
    root.dataset.chipMultiSelectInit = '1';

    var readOnly = root.classList.contains('is-readonly') || root.dataset.readOnly === 'true';
    var allOptions = getOptionsFromSource(root);
    var selected = getInitialValues(root);
    var clickingOption = false;
    var docClickHandler = null;

    var chipsEl = root.querySelector('.chip-multi-select-chips');
    var searchEl = root.querySelector('.chip-multi-select-search');
    var dropdownEl = root.querySelector('.chip-multi-select-dropdown');
    if (!chipsEl || !dropdownEl || (!readOnly && !searchEl)) return null;

    var placeholder = root.dataset.placeholder || 'Search...';

    function emitChange() {
      syncNative(root, selected);
      root.dispatchEvent(new CustomEvent('chipmultiselect:change', {
        bubbles: true,
        detail: { values: selected.slice() },
      }));
    }

    function setOpen(open) {
      if (readOnly) return;
      root.classList.toggle('is-open', open);
      if (open) {
        renderDropdown(searchEl.value.trim());
      }
    }

    function renderChips() {
      chipsEl.innerHTML = '';
      selected.forEach(function (value) {
        var opt = allOptions.find(function (o) { return o.value === value; });
        if (!opt) return;
        var chip = document.createElement('div');
        chip.className = 'chip-multi-select-chip';
        chip.innerHTML = '<span>' + escapeHtml(opt.text) + '</span>';
        if (!readOnly) {
          var btn = document.createElement('button');
          btn.type = 'button';
          btn.className = 'remove-chip';
          btn.title = 'Remove';
          btn.setAttribute('aria-label', 'Remove ' + opt.text);
          btn.textContent = '×';
          btn.addEventListener('click', function (e) {
            e.stopPropagation();
            selected = selected.filter(function (v) { return v !== value; });
            renderChips();
            renderDropdown(searchEl ? searchEl.value.trim() : '');
            emitChange();
          });
          chip.appendChild(btn);
        }
        chipsEl.appendChild(chip);
      });
    }

    function renderDropdown(filterTerm) {
      dropdownEl.innerHTML = '';
      var term = (filterTerm || '').toLowerCase();
      var visible = 0;

      allOptions.forEach(function (opt) {
        var matches = !term || opt.text.toLowerCase().indexOf(term) !== -1;
        if (!matches) return;
        visible += 1;

        var row = document.createElement('div');
        row.className = 'chip-multi-select-option';
        if (selected.indexOf(opt.value) !== -1) {
          row.classList.add('is-selected');
        }
        row.textContent = opt.text;
        row.setAttribute('data-value', opt.value);

        function toggleOption(e) {
          if (readOnly) return;
          e.preventDefault();
          e.stopPropagation();
          clickingOption = true;
          var idx = selected.indexOf(opt.value);
          if (idx === -1) {
            selected.push(opt.value);
          } else {
            selected.splice(idx, 1);
          }
          renderChips();
          renderDropdown(searchEl.value.trim());
          emitChange();
          setOpen(true);
          if (searchEl) {
            setTimeout(function () { searchEl.focus(); }, 0);
          }
          setTimeout(function () { clickingOption = false; }, 200);
        }

        row.addEventListener('mousedown', toggleOption);
        row.addEventListener('click', function (e) {
          e.preventDefault();
          e.stopPropagation();
        });
        dropdownEl.appendChild(row);
      });

      if (visible === 0) {
        var empty = document.createElement('div');
        empty.className = 'chip-multi-select-empty';
        empty.textContent = term ? 'No matches found' : 'No options available';
        dropdownEl.appendChild(empty);
      }
    }

    if (searchEl) {
      searchEl.placeholder = placeholder;
      searchEl.addEventListener('focus', function () {
        setOpen(true);
      });
      searchEl.addEventListener('input', function () {
        setOpen(true);
        renderDropdown(searchEl.value.trim());
      });
      searchEl.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') {
          setOpen(false);
          searchEl.blur();
        }
      });
    }

    docClickHandler = function (e) {
      if (clickingOption) return;
      if (!root.contains(e.target)) {
        setOpen(false);
      }
    };
    document.addEventListener('click', docClickHandler);

    renderChips();
    renderDropdown('');
    syncNative(root, selected);

    var api = {
      getValues: function () { return selected.slice(); },
      setValues: function (values) {
        var allowed = {};
        allOptions.forEach(function (o) { allowed[o.value] = true; });
        selected = (values || []).filter(function (v) { return allowed[v]; });
        renderChips();
        renderDropdown(searchEl ? searchEl.value.trim() : '');
        emitChange();
      },
      refresh: function (keepSelected) {
        var prev = keepSelected === false ? [] : selected.slice();
        allOptions = getOptionsFromSource(root);
        var allowed = {};
        allOptions.forEach(function (o) { allowed[o.value] = true; });
        selected = prev.filter(function (v) { return allowed[v]; });
        renderChips();
        renderDropdown(searchEl ? searchEl.value.trim() : '');
        syncNative(root, selected);
      },
      destroy: function () {
        if (docClickHandler) {
          document.removeEventListener('click', docClickHandler);
          docClickHandler = null;
        }
        setOpen(false);
      }
    };
    root._chipMultiSelectApi = api;
    return api;
  }

  function refreshChipMultiSelect(root, keepSelected) {
    if (!root) return null;
    if (root._chipMultiSelectApi && typeof root._chipMultiSelectApi.refresh === 'function') {
      root._chipMultiSelectApi.refresh(keepSelected !== false);
      return root._chipMultiSelectApi;
    }
    return initChipMultiSelect(root);
  }

  function initAll(scope) {
    (scope || document).querySelectorAll('[data-chip-multi-select]').forEach(initChipMultiSelect);
  }

  window.initChipMultiSelect = initChipMultiSelect;
  window.refreshChipMultiSelect = refreshChipMultiSelect;
  window.destroyChipMultiSelect = destroyChipMultiSelect;
  window.initAllChipMultiSelects = initAll;

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () { initAll(); });
  } else {
    initAll();
  }
})();

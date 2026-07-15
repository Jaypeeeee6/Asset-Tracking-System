/**
 * Add asset type / asset name modals.
 */
(function (global) {
    'use strict';

    var assetNameTypeCombo = null;

    function $(id) {
        return document.getElementById(id);
    }

    function isChecked(id) {
        var el = $(id);
        return el && el.checked;
    }

    function appendLocationFlags(fd, prefix) {
        if (isChecked(prefix + 'AllRestaurants')) {
            fd.append('all_restaurants', '1');
        }
        if (isChecked(prefix + 'AllOfficeDepts')) {
            fd.append('all_office_departments', '1');
        }
    }

    function validateLocation(prefix) {
        if (!isChecked(prefix + 'AllRestaurants') && !isChecked(prefix + 'AllOfficeDepts')) {
            return 'Select at least one location (all restaurants and/or all office departments).';
        }
        return null;
    }

    function assetTypeLocationLabel(t) {
        if (!t) return '';
        var fv = t.for_venue || 'restaurant';
        if (fv === 'both') return 'All restaurants & All office departments';
        if (fv === 'office') return 'All office departments';
        return 'All restaurants';
    }

    function getAssetTypesList() {
        if (typeof global.assetTypesData !== 'undefined' && global.assetTypesData) {
            return global.assetTypesData;
        }
        if (global.AssetAppState && global.AssetAppState.assetTypes) {
            return global.AssetAppState.assetTypes;
        }
        return [];
    }

    function buildAssetTypeComboOptions() {
        return getAssetTypesList().slice().sort(function (a, b) {
            var byName = (a.name || '').localeCompare(b.name || '');
            if (byName !== 0) return byName;
            return assetTypeLocationLabel(a).localeCompare(assetTypeLocationLabel(b));
        }).map(function (t) {
            var loc = assetTypeLocationLabel(t);
            var name = t.name || '';
            return {
                value: String(t.id),
                label: name + ' — ' + loc,
                searchText: (name + ' ' + loc).toLowerCase()
            };
        });
    }

    function ensureAssetNameTypeCombo() {
        if (assetNameTypeCombo || !global.AppSearchableCombobox) {
            return assetNameTypeCombo;
        }
        assetNameTypeCombo = global.AppSearchableCombobox.create({
            wrapId: 'addMgmtAssetNameTypeCombo',
            inputId: 'addMgmtAssetNameTypeSearch',
            hiddenId: 'addMgmtAssetNameTypeId',
            panelId: 'addMgmtAssetNameTypeOptions',
            emptyText: 'No asset types found. Add a type first.',
            getOptions: buildAssetTypeComboOptions
        });
        return assetNameTypeCombo;
    }

    function refreshAssetNameTypeCombo() {
        var combo = ensureAssetNameTypeCombo();
        if (combo) combo.refresh();
    }

    function showError(msg) {
        if (global.AppDialogs) return global.AppDialogs.error(msg);
        if (typeof mgmtShowError === 'function') return mgmtShowError(msg);
        return Promise.resolve();
    }

    function showSuccess(msg) {
        if (global.AppDialogs) return global.AppDialogs.success(msg);
        return Promise.resolve();
    }

    function resetAddAssetTypeModal() {
        var name = $('addMgmtAssetTypeName');
        var rest = $('addMgmtAssetTypeAllRestaurants');
        var office = $('addMgmtAssetTypeAllOfficeDepts');
        if (name) name.value = '';
        if (rest) rest.checked = false;
        if (office) office.checked = false;
    }

    function resetAddAssetNameModal() {
        var name = $('addMgmtAssetNameValue');
        if (name) name.value = '';
        var combo = ensureAssetNameTypeCombo();
        if (combo) combo.reset();
        clearSpecList('addMgmtAssetNameSpecList');
    }

    function clearSpecList(listId) {
        var list = $(listId);
        if (list) list.innerHTML = '';
    }

    function addSpecRow(listId, value, specId) {
        var list = $(listId);
        if (!list) return;
        var row = document.createElement('div');
        row.className = 'd-flex gap-2 align-items-center mb-2 asset-spec-row';
        if (specId) row.dataset.specId = String(specId);
        row.innerHTML =
            '<input type="text" class="form-control form-control-sm asset-spec-label-input" maxlength="100" placeholder="e.g. Serial No." value="' +
            (value || '').replace(/"/g, '&quot;') +
            '">' +
            '<button type="button" class="btn btn-sm btn-app-tab asset-spec-remove-btn" title="Remove specification" aria-label="Remove specification">' +
            '<i class="bi bi-x-lg" aria-hidden="true"></i></button>';
        list.appendChild(row);
        var removeBtn = row.querySelector('.asset-spec-remove-btn');
        if (removeBtn) {
            removeBtn.addEventListener('click', function () {
                row.remove();
            });
        }
    }

    function collectSpecLabels(listId) {
        var list = $(listId);
        if (!list) return [];
        return Array.prototype.slice.call(list.querySelectorAll('.asset-spec-label-input'))
            .map(function (input) { return input.value.trim(); })
            .filter(function (label) { return !!label; });
    }

    function collectSpecUpdates(listId) {
        var list = $(listId);
        if (!list) return [];
        return Array.prototype.slice.call(list.querySelectorAll('.asset-spec-row'))
            .map(function (row) {
                var input = row.querySelector('.asset-spec-label-input');
                var label = input ? input.value.trim() : '';
                if (!label) return null;
                var item = { label: label };
                if (row.dataset.specId) item.id = parseInt(row.dataset.specId, 10);
                return item;
            })
            .filter(function (item) { return !!item; });
    }

    function populateSpecList(listId, specFields) {
        clearSpecList(listId);
        (specFields || []).forEach(function (field) {
            addSpecRow(listId, field.label, field.id);
        });
    }

    function saveAddAssetType() {
        var nameEl = $('addMgmtAssetTypeName');
        var name = nameEl ? nameEl.value.trim() : '';
        if (!name) return showError('Please enter an asset type name.');

        var locErr = validateLocation('addMgmtAssetType');
        if (locErr) return showError(locErr);

        var fd = new FormData();
        fd.append('name', name);
        appendLocationFlags(fd, 'addMgmtAssetType');

        return fetch('/admin/asset-types', { method: 'POST', body: fd })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (data.success) {
                    var modalEl = $('addMgmtAssetTypeModal');
                    if (modalEl && global.bootstrap) {
                        global.bootstrap.Modal.getInstance(modalEl).hide();
                    }
                    resetAddAssetTypeModal();
                    var msg = 'Added ' + (data.created_count || 1) + ' asset type(s).';
                    if (data.skipped_count) msg += ' ' + data.skipped_count + ' already existed.';
                    showSuccess(msg);
                    reloadAfterAssetTypeChange();
                } else {
                    return showError(data.error || 'Failed to add asset type.');
                }
            })
            .catch(function () { return showError('Failed to add asset type.'); });
    }

    function reloadAfterAssetTypeChange() {
        if (global.MgmtEditCallbacks && global.MgmtEditCallbacks.onAssetTypeSaved) {
            global.MgmtEditCallbacks.onAssetTypeSaved();
            return;
        }
        if (typeof global.loadAssetTypes === 'function') global.loadAssetTypes();
        if (typeof global.loadAssetNames === 'function') global.loadAssetNames();
        if (typeof global.updateAssetNameDropdowns === 'function') global.updateAssetNameDropdowns();
        refreshAssetNameTypeCombo();
    }

    function saveAddAssetName() {
        var nameEl = $('addMgmtAssetNameValue');
        var combo = ensureAssetNameTypeCombo();
        var name = nameEl ? nameEl.value.trim() : '';
        var typeId = combo ? combo.getValue() : ($('addMgmtAssetNameTypeId') && $('addMgmtAssetNameTypeId').value);

        if (!name) return showError('Please enter an asset name.');
        if (!typeId) return showError('Please select an asset type from the list.');

        var fd = new FormData();
        fd.append('name', name);
        fd.append('asset_type_id', typeId);
        var specLabels = collectSpecLabels('addMgmtAssetNameSpecList');
        fd.append('specifications_json', JSON.stringify(specLabels));

        return fetch('/admin/asset-names', { method: 'POST', body: fd })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (data.success) {
                    var modalEl = $('addMgmtAssetNameModal');
                    if (modalEl && global.bootstrap) {
                        global.bootstrap.Modal.getInstance(modalEl).hide();
                    }
                    resetAddAssetNameModal();
                    var msg = 'Added ' + (data.created_count || 1) + ' asset name(s).';
                    if (data.skipped_count) msg += ' ' + data.skipped_count + ' already existed.';
                    showSuccess(msg);
                    if (global.MgmtEditCallbacks && global.MgmtEditCallbacks.onAssetNameSaved) {
                        global.MgmtEditCallbacks.onAssetNameSaved();
                    } else {
                        if (typeof global.loadAssetNames === 'function') global.loadAssetNames();
                        if (typeof global.updateAssetNameDropdowns === 'function') global.updateAssetNameDropdowns();
                    }
                    refreshAssetNameTypeCombo();
                } else {
                    return showError(data.error || 'Failed to add asset name.');
                }
            })
            .catch(function () { return showError('Failed to add asset name.'); });
    }

    function bindOnce() {
        if (document.body.dataset.mgmtAddAssetModalsBound === '1') return;
        document.body.dataset.mgmtAddAssetModalsBound = '1';

        var saveType = $('addMgmtAssetTypeSaveBtn');
        if (saveType) saveType.addEventListener('click', saveAddAssetType);
        var saveName = $('addMgmtAssetNameSaveBtn');
        if (saveName) saveName.addEventListener('click', saveAddAssetName);

        var addSpecBtn = $('addMgmtAssetNameSpecBtn');
        if (addSpecBtn) {
            addSpecBtn.addEventListener('click', function () {
                addSpecRow('addMgmtAssetNameSpecList', '', null);
            });
        }

        var typeModal = $('addMgmtAssetTypeModal');
        if (typeModal) {
            typeModal.addEventListener('show.bs.modal', resetAddAssetTypeModal);
        }

        var nameModal = $('addMgmtAssetNameModal');
        if (nameModal) {
            nameModal.addEventListener('show.bs.modal', function () {
                ensureAssetNameTypeCombo();
                refreshAssetNameTypeCombo();
            });
            nameModal.addEventListener('hidden.bs.modal', function () {
                var combo = assetNameTypeCombo;
                if (combo && combo.close) combo.close();
            });
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', bindOnce);
    } else {
        bindOnce();
    }

    global.MgmtAddAssetModals = {
        resetAddAssetTypeModal: resetAddAssetTypeModal,
        resetAddAssetNameModal: resetAddAssetNameModal,
        refreshAssetNameTypeCombo: refreshAssetNameTypeCombo,
        addSpecRow: addSpecRow,
        clearSpecList: clearSpecList,
        populateSpecList: populateSpecList,
        collectSpecLabels: collectSpecLabels,
        collectSpecUpdates: collectSpecUpdates
    };
})(window);

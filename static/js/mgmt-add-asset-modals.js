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
        if (!t.branch_id && !t.department_id) {
            var fv = (t.for_venue || 'restaurant');
            if (fv === 'both') return 'All restaurants & All office departments';
            if (fv === 'office') return 'All office departments';
            return 'All restaurants';
        }
        var venue = (t.for_venue === 'office') ? 'Office' : 'Restaurant';
        if (t.branch_name) {
            return t.brand_name
                ? venue + ' — ' + t.brand_name + ' — ' + t.branch_name
                : venue + ' — ' + t.branch_name;
        }
        if (t.department_name) {
            return venue + ' — ' + t.department_name;
        }
        return venue;
    }

    function getAssetTypesList() {
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
        global.alert(msg);
        return Promise.resolve();
    }

    function showSuccess(msg) {
        if (global.AppDialogs) return global.AppDialogs.success(msg);
        global.alert(msg);
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
                    if (global.MgmtEditCallbacks && global.MgmtEditCallbacks.onAssetTypeSaved) {
                        global.MgmtEditCallbacks.onAssetTypeSaved();
                    }
                } else {
                    return showError(data.error || 'Failed to add asset type.');
                }
            })
            .catch(function () { return showError('Failed to add asset type.'); });
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
                    if (typeof loadAssetNames === 'function') loadAssetNames();
                    if (typeof updateAssetNameDropdowns === 'function') updateAssetNameDropdowns();
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
        refreshAssetNameTypeCombo: refreshAssetNameTypeCombo
    };
})(window);

/**
 * Management edit modals (branch, department, employee, asset type).
 * Uses Bootstrap app-modal styling and AppDialogs for confirm/error.
 */
(function (global) {
    'use strict';

    var OFFICE_BRANCH_LABEL = 'Office';
    var RESTAURANT_DEFAULT_DEPT = 'Restaurant';

    function $(id) {
        return document.getElementById(id);
    }

    function dlg() {
        return global.AppDialogs || null;
    }

    function showError(msg) {
        if (dlg()) return dlg().error(msg);
        global.alert(msg);
        return Promise.resolve();
    }

    function getBsModal(el) {
        if (!el || !global.bootstrap) return null;
        return global.bootstrap.Modal.getOrCreateInstance(el);
    }

    function brandsList() {
        if (global.AssetAppState && global.AssetAppState.brands) {
            return global.AssetAppState.brands;
        }
        return [];
    }

    function branchesList() {
        if (global.AssetAppState && global.AssetAppState.branches) {
            return global.AssetAppState.branches;
        }
        return [];
    }

    function fillBrandSelect(sel, selectedId) {
        if (!sel) return;
        sel.innerHTML = '<option value="">Select brand</option>';
        brandsList().slice().sort(function (a, b) {
            return a.name.localeCompare(b.name);
        }).forEach(function (brand) {
            var o = document.createElement('option');
            o.value = String(brand.id);
            o.textContent = brand.name;
            sel.appendChild(o);
        });
        if (selectedId) sel.value = String(selectedId);
    }

    function fillBranchSelectByBrand(sel, brandId, selectedBranchId) {
        if (!sel) return;
        sel.innerHTML = '<option value="">Select branch</option>';
        if (!brandId) return;
        branchesList().filter(function (b) {
            return String(b.brand_id) === String(brandId);
        }).sort(function (a, b) {
            return a.name.localeCompare(b.name);
        }).forEach(function (b) {
            var o = document.createElement('option');
            o.value = String(b.id);
            o.textContent = b.name;
            sel.appendChild(o);
        });
        if (selectedBranchId) sel.value = String(selectedBranchId);
    }

    function fillDepartmentBranchSelect(sel, selectedBranchId, isOffice) {
        if (!sel) return;
        var prev = isOffice ? '__office__' : (selectedBranchId ? String(selectedBranchId) : '');
        sel.innerHTML = '<option value="">Select branch</option><option value="__office__">Office</option>';
        branchesList().slice().sort(function (a, b) {
            return a.name.localeCompare(b.name);
        }).forEach(function (b) {
            var o = document.createElement('option');
            o.value = String(b.id);
            o.textContent = b.name;
            sel.appendChild(o);
        });
        if (prev) sel.value = prev;
    }

    function syncEditMgmtAssetTypeVenue() {
        var v = $('editMgmtAssetTypeVenue');
        var bw = $('editMgmtAssetTypeBrandWrap');
        var rw = $('editMgmtAssetTypeBranchWrap');
        var ow = $('editMgmtAssetTypeOfficeDeptWrap');
        var b = $('editMgmtAssetTypeBrand');
        var br = $('editMgmtAssetTypeBranch');
        var od = $('editMgmtAssetTypeOfficeDepartment');
        if (!v || !bw || !rw || !ow) return;
        var val = v.value;
        if (val === 'restaurant') {
            bw.classList.remove('d-none');
            rw.classList.remove('d-none');
            ow.classList.add('d-none');
            fillBrandSelect(b, b && b.value ? b.value : '');
            if (br) br.innerHTML = '<option value="">Select branch</option>';
        } else if (val === 'office') {
            bw.classList.add('d-none');
            rw.classList.add('d-none');
            ow.classList.remove('d-none');
            if (od) {
                od.innerHTML = '<option value="">Loading...</option>';
                fetch('/admin/departments?office_only=1')
                    .then(function (r) { return r.json(); })
                    .then(function (depts) {
                        od.innerHTML = '<option value="">Select department</option>';
                        depts.forEach(function (d) {
                            var o = document.createElement('option');
                            o.value = String(d.id);
                            o.textContent = d.name;
                            od.appendChild(o);
                        });
                    })
                    .catch(function () {
                        od.innerHTML = '<option value="">Error loading departments</option>';
                    });
            }
        } else {
            bw.classList.add('d-none');
            rw.classList.add('d-none');
            ow.classList.add('d-none');
        }
    }

    function syncEditMgmtEmployeeVenue() {
        var val = $('editMgmtEmployeeVenue') ? $('editMgmtEmployeeVenue').value : '';
        var bwrap = $('editMgmtEmployeeBrandWrap');
        var wrap = $('editMgmtEmployeeBranchWrap');
        var dwrap = $('editMgmtEmployeeDepartment');
        var brand = $('editMgmtEmployeeBrand');
        var branch = $('editMgmtEmployeeBranch');
        var dept = $('editMgmtEmployeeDepartment');
        if (!dept) return;

        if (val === 'office') {
            if (bwrap) bwrap.classList.add('d-none');
            if (wrap) wrap.classList.add('d-none');
            dept.innerHTML = '<option value="">Loading...</option>';
            fetch('/admin/departments?office_only=1')
                .then(function (r) { return r.json(); })
                .then(function (depts) {
                    dept.innerHTML = '<option value="">Select department</option>';
                    depts.forEach(function (d) {
                        var o = document.createElement('option');
                        o.value = String(d.id);
                        o.textContent = d.name;
                        dept.appendChild(o);
                    });
                    if (global.__editMgmtEmployeeDeptId) {
                        dept.value = String(global.__editMgmtEmployeeDeptId);
                        global.__editMgmtEmployeeDeptId = null;
                    }
                });
        } else if (val === 'restaurant') {
            if (bwrap) bwrap.classList.remove('d-none');
            if (wrap) wrap.classList.remove('d-none');
            fillBrandSelect(brand, brand ? brand.value : '');
            if (branch) branch.innerHTML = '<option value="">Select branch</option>';
            dept.innerHTML = '<option value="">Select branch first</option>';
        } else {
            if (bwrap) bwrap.classList.add('d-none');
            if (wrap) wrap.classList.add('d-none');
            dept.innerHTML = '<option value="">Choose location first</option>';
        }
    }

    function loadEditMgmtEmployeeDepartments(branchId, departmentId, venue) {
        var dept = $('editMgmtEmployeeDepartment');
        if (!dept || !branchId) return Promise.resolve();

        return fetch('/admin/departments?branch_id=' + encodeURIComponent(branchId))
            .then(function (r) { return r.json(); })
            .then(function (departments) {
                if (venue === 'restaurant') {
                    var pick = departments.filter(function (d) {
                        return d.name === RESTAURANT_DEFAULT_DEPT;
                    });
                    dept.innerHTML = '';
                    pick.forEach(function (d) {
                        var o = document.createElement('option');
                        o.value = String(d.id);
                        o.textContent = d.name;
                        dept.appendChild(o);
                    });
                    if (pick.length) dept.value = String(pick[0].id);
                    return;
                }
                dept.innerHTML = '<option value="">Select department</option>';
                departments.forEach(function (d) {
                    var o = document.createElement('option');
                    o.value = String(d.id);
                    o.textContent = d.name;
                    dept.appendChild(o);
                });
                if (departmentId) dept.value = String(departmentId);
            });
    }

    function openEditBranch(data) {
        var modalEl = $('editMgmtBranchModal');
        if (!modalEl) return;
        $('editMgmtBranchId').value = data.id;
        $('editMgmtBranchName').value = data.name || '';
        var codeEl = $('editMgmtBranchCode');
        if (codeEl) codeEl.value = (data.branchCode || data.branch_code || '').toUpperCase();
        fillBrandSelect($('editMgmtBranchBrand'), data.brandId || data.brand_id || '');
        getBsModal(modalEl).show();
    }

    function saveEditBranch() {
        var id = $('editMgmtBranchId').value;
        var name = ($('editMgmtBranchName').value || '').trim();
        var branchCode = ($('editMgmtBranchCode') && $('editMgmtBranchCode').value || '').trim().toUpperCase();
        var brandId = $('editMgmtBranchBrand').value;
        if (!name) return showError('Please enter a branch name.');
        if (!brandId) return showError('Please select a brand for this branch.');

        var formData = new FormData();
        formData.append('name', name);
        formData.append('branch_code', branchCode);
        formData.append('brand_id', brandId);

        return fetch('/admin/branches/' + encodeURIComponent(id), { method: 'PUT', body: formData })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (data.success) {
                    getBsModal($('editMgmtBranchModal')).hide();
                    if (global.MgmtEditCallbacks && global.MgmtEditCallbacks.onBranchSaved) {
                        global.MgmtEditCallbacks.onBranchSaved();
                    }
                } else {
                    return showError(data.error || 'Failed to update branch.');
                }
            })
            .catch(function () { return showError('Failed to update branch.'); });
    }

    function openEditDepartment(data) {
        var modalEl = $('editMgmtDepartmentModal');
        if (!modalEl) return;
        $('editMgmtDepartmentId').value = data.id;
        $('editMgmtDepartmentName').value = data.name || '';
        fillDepartmentBranchSelect(
            $('editMgmtDepartmentBranch'),
            data.branchId,
            data.isOffice
        );
        getBsModal(modalEl).show();
    }

    function saveEditDepartment() {
        var id = $('editMgmtDepartmentId').value;
        var name = ($('editMgmtDepartmentName').value || '').trim();
        var branchVal = $('editMgmtDepartmentBranch').value;
        if (!name) return showError('Please enter a department name.');
        if (!branchVal) return showError('Please select a branch or Office.');

        var formData = new FormData();
        formData.append('name', name);
        formData.append('branch_id', branchVal);

        return fetch('/admin/departments/' + encodeURIComponent(id), { method: 'PUT', body: formData })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (data.success) {
                    getBsModal($('editMgmtDepartmentModal')).hide();
                    if (global.MgmtEditCallbacks && global.MgmtEditCallbacks.onDepartmentSaved) {
                        global.MgmtEditCallbacks.onDepartmentSaved();
                    }
                } else {
                    return showError(data.error || 'Failed to update department.');
                }
            })
            .catch(function () { return showError('Failed to update department.'); });
    }

    function openEditEmployee(data) {
        var modalEl = $('editMgmtEmployeeModal');
        if (!modalEl) return;
        $('editMgmtEmployeeId').value = data.id;
        $('editMgmtEmployeeName').value = data.name || '';
        global.__editMgmtEmployeeDeptId = data.departmentId || null;

        var venue = data.venue || (data.branchName === OFFICE_BRANCH_LABEL ? 'office' : 'restaurant');
        $('editMgmtEmployeeVenue').value = venue;
        syncEditMgmtEmployeeVenue();

        if (venue === 'office') {
            global.__editMgmtEmployeeDeptId = data.departmentId;
            syncEditMgmtEmployeeVenue();
        } else {
            fillBrandSelect($('editMgmtEmployeeBrand'), data.brandId || '');
            fillBranchSelectByBrand($('editMgmtEmployeeBranch'), data.brandId, data.branchId);
            loadEditMgmtEmployeeDepartments(data.branchId, data.departmentId, venue);
        }

        getBsModal(modalEl).show();
    }

    function saveEditEmployee() {
        var id = $('editMgmtEmployeeId').value;
        var name = ($('editMgmtEmployeeName').value || '').trim();
        var departmentId = $('editMgmtEmployeeDepartment').value;
        if (!name) return showError('Please enter an employee name.');
        if (!departmentId) return showError('Please select a department.');

        return fetch('/admin/users/' + encodeURIComponent(id), {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: name, department_id: departmentId })
        })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (data.success) {
                    getBsModal($('editMgmtEmployeeModal')).hide();
                    if (global.MgmtEditCallbacks && global.MgmtEditCallbacks.onEmployeeSaved) {
                        global.MgmtEditCallbacks.onEmployeeSaved();
                    }
                } else {
                    return showError(data.error || 'Failed to update employee.');
                }
            })
            .catch(function () { return showError('Failed to update employee.'); });
    }

    function locationLabelForEditAssetType(data) {
        var venue = data.forVenue || 'restaurant';
        if (venue === 'both') return 'All restaurants & All office departments';
        if (venue === 'office') return 'All office departments';
        return 'All restaurants';
    }

    function openEditAssetType(data) {
        var modalEl = $('editMgmtAssetTypeModal');
        if (!modalEl) return;
        $('editMgmtAssetTypeId').value = data.id;
        $('editMgmtAssetTypeName').value = data.name || '';
        $('editMgmtAssetTypeVenue').value = data.forVenue || 'restaurant';
        var loc = $('editMgmtAssetTypeLocationDisplay');
        if (loc) loc.textContent = locationLabelForEditAssetType(data);

        getBsModal(modalEl).show();
    }

    function saveEditAssetType() {
        var id = $('editMgmtAssetTypeId').value;
        var name = ($('editMgmtAssetTypeName').value || '').trim();
        if (!name) return showError('Please enter an asset type name.');

        var formData = new FormData();
        formData.append('name', name);

        return fetch('/admin/asset-types/' + encodeURIComponent(id), { method: 'PUT', body: formData })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (data.success) {
                    getBsModal($('editMgmtAssetTypeModal')).hide();
                    if (global.MgmtEditCallbacks && global.MgmtEditCallbacks.onAssetTypeSaved) {
                        global.MgmtEditCallbacks.onAssetTypeSaved();
                    }
                } else {
                    return showError(data.error || 'Failed to update asset type.');
                }
            })
            .catch(function () { return showError('Failed to update asset type.'); });
    }

    function bindOnce() {
        if (document.body.dataset.mgmtEditModalsBound === '1') return;
        document.body.dataset.mgmtEditModalsBound = '1';

        var saveBranch = $('editMgmtBranchSaveBtn');
        if (saveBranch) saveBranch.addEventListener('click', saveEditBranch);

        var saveDept = $('editMgmtDepartmentSaveBtn');
        if (saveDept) saveDept.addEventListener('click', saveEditDepartment);

        var saveEmp = $('editMgmtEmployeeSaveBtn');
        if (saveEmp) saveEmp.addEventListener('click', saveEditEmployee);

        var saveType = $('editMgmtAssetTypeSaveBtn');
        if (saveType) saveType.addEventListener('click', saveEditAssetType);

        var ev = $('editMgmtEmployeeVenue');
        if (ev) ev.addEventListener('change', syncEditMgmtEmployeeVenue);

        var eb = $('editMgmtEmployeeBrand');
        if (eb) {
            eb.addEventListener('change', function () {
                fillBranchSelectByBrand($('editMgmtEmployeeBranch'), this.value, '');
                var dep = $('editMgmtEmployeeDepartment');
                if (dep) dep.innerHTML = '<option value="">Select branch first</option>';
            });
        }

        var ebr = $('editMgmtEmployeeBranch');
        if (ebr) {
            ebr.addEventListener('change', function () {
                var venue = $('editMgmtEmployeeVenue') ? $('editMgmtEmployeeVenue').value : '';
                loadEditMgmtEmployeeDepartments(this.value, null, venue);
            });
        }

        var atv = $('editMgmtAssetTypeVenue');
        if (atv) atv.addEventListener('change', syncEditMgmtAssetTypeVenue);

        var atb = $('editMgmtAssetTypeBrand');
        if (atb) {
            atb.addEventListener('change', function () {
                fillBranchSelectByBrand($('editMgmtAssetTypeBranch'), this.value, '');
            });
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', bindOnce);
    } else {
        bindOnce();
    }

    global.MgmtEditModals = {
        openBranch: openEditBranch,
        openDepartment: openEditDepartment,
        openEmployee: openEditEmployee,
        openAssetType: openEditAssetType
    };
})(window);

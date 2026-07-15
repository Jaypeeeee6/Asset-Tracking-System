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
        return Promise.resolve();
    }

    function getBsModal(el) {
        if (!el || !global.bootstrap) return null;
        return global.bootstrap.Modal.getOrCreateInstance(el);
    }

    function brandsList() {
        if (global.brandsData && global.brandsData.length) return global.brandsData;
        if (global.AssetAppState && global.AssetAppState.brands) {
            return global.AssetAppState.brands;
        }
        return [];
    }

    function branchesList() {
        if (global.branchesData && global.branchesData.length) return global.branchesData;
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

    function renderEditBranchChecklist(checkedIds) {
        if (global.EmployeeBranchChecklist && global.EmployeeBranchChecklist.render) {
            global.EmployeeBranchChecklist.render('editMgmtEmployeeBranchList', checkedIds || []);
        }
    }

    function syncEditMgmtEmployeeVenue() {
        var val = $('editMgmtEmployeeVenue') ? $('editMgmtEmployeeVenue').value : '';
        var brwrap = $('editMgmtEmployeeBranchesWrap');
        var dwrap = $('editMgmtEmployeeDepartmentWrap');
        var dept = $('editMgmtEmployeeDepartment');
        var search = $('editMgmtEmployeeBranchSearch');
        if (!dept) return;

        if (val === 'office') {
            if (brwrap) brwrap.classList.add('d-none');
            if (dwrap) dwrap.classList.remove('d-none');
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
            if (brwrap) brwrap.classList.remove('d-none');
            if (dwrap) dwrap.classList.add('d-none');
            if (search) search.value = '';
            renderEditBranchChecklist([]);
        } else {
            if (brwrap) brwrap.classList.add('d-none');
            if (dwrap) dwrap.classList.add('d-none');
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
                    if (departmentId) {
                        dept.value = String(departmentId);
                    } else if (pick.length) {
                        dept.value = String(pick[0].id);
                    }
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
        getBsModal(modalEl).show();
    }

    function saveEditDepartment() {
        var id = $('editMgmtDepartmentId').value;
        var name = ($('editMgmtDepartmentName').value || '').trim();
        if (!name) return showError('Please enter a department name.');

        var formData = new FormData();
        formData.append('name', name);

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
        var employeeIdEl = $('editMgmtEmployeeEmployeeId');
        if (employeeIdEl) employeeIdEl.value = data.employeeId || data.employee_id || '';
        $('editMgmtEmployeeName').value = data.name || '';
        var mobileEl = $('editMgmtEmployeeMobile');
        if (mobileEl) mobileEl.value = data.mobile || '';
        var emailEl = $('editMgmtEmployeeEmail');
        if (emailEl) emailEl.value = data.email || '';

        var departmentId = data.departmentId || data.department_id || null;
        var venue = data.venue || (data.branchName === OFFICE_BRANCH_LABEL ? 'office' : 'restaurant');
        $('editMgmtEmployeeVenue').value = venue;

        var brwrap = $('editMgmtEmployeeBranchesWrap');
        var dwrap = $('editMgmtEmployeeDepartmentWrap');
        var dept = $('editMgmtEmployeeDepartment');
        var search = $('editMgmtEmployeeBranchSearch');
        if (search) search.value = '';

        if (venue === 'office') {
            if (brwrap) brwrap.classList.add('d-none');
            if (dwrap) dwrap.classList.remove('d-none');
            if (dept) {
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
                        if (departmentId) dept.value = String(departmentId);
                    })
                    .catch(function () {
                        dept.innerHTML = '<option value="">Error loading departments</option>';
                    });
            }
        } else {
            if (brwrap) brwrap.classList.remove('d-none');
            if (dwrap) dwrap.classList.add('d-none');
            var branchIds = data.branchIds || data.branch_ids || [];
            renderEditBranchChecklist(branchIds);
        }

        getBsModal(modalEl).show();
    }

    function saveEditEmployee() {
        var id = $('editMgmtEmployeeId').value;
        var employeeId = ($('editMgmtEmployeeEmployeeId') && $('editMgmtEmployeeEmployeeId').value || '').trim();
        var name = ($('editMgmtEmployeeName').value || '').trim();
        var mobile = ($('editMgmtEmployeeMobile') && $('editMgmtEmployeeMobile').value || '').trim();
        var email = ($('editMgmtEmployeeEmail') && $('editMgmtEmployeeEmail').value || '').trim();
        var venue = $('editMgmtEmployeeVenue') ? $('editMgmtEmployeeVenue').value : '';
        var departmentId = $('editMgmtEmployeeDepartment') ? $('editMgmtEmployeeDepartment').value : '';
        if (!employeeId) return showError('Please enter an employee ID.');
        if (!name) return showError('Please enter an employee name.');

        var payload = { name: name, employee_id: employeeId, mobile: mobile, email: email };
        if (venue === 'restaurant') {
            var branchIds = (global.EmployeeBranchChecklist && global.EmployeeBranchChecklist.getChecked)
                ? global.EmployeeBranchChecklist.getChecked('editMgmtEmployeeBranchList') : [];
            if (!branchIds.length) return showError('Please select at least one branch.');
            payload.branch_ids = branchIds;
        } else {
            if (!departmentId) return showError('Please select a department.');
            payload.department_id = departmentId;
        }

        return fetch('/admin/users/' + encodeURIComponent(id), {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (data.success) {
                    getBsModal($('editMgmtEmployeeModal')).hide();
                    if (data.warning) { showError(data.warning); }
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

    function openEditAssetName(data) {
        var modalEl = $('editMgmtAssetNameModal');
        if (!modalEl) return;

        function showModal(specFields, inclusions) {
            $('editMgmtAssetNameId').value = data.id;
            $('editMgmtAssetNameValue').value = data.name || '';
            var typeDisplay = $('editMgmtAssetNameTypeDisplay');
            if (typeDisplay) typeDisplay.textContent = data.assetTypeName || '';
            if (global.MgmtAddAssetModals && global.MgmtAddAssetModals.populateSpecList) {
                global.MgmtAddAssetModals.populateSpecList('editMgmtAssetNameSpecList', specFields || []);
                global.MgmtAddAssetModals.populateSpecList('editMgmtAssetNameInclusionList', inclusions || []);
            }
            getBsModal(modalEl).show();
        }

        var hasSpecs = data.specFields && data.specFields.length;
        var hasInclusions = data.inclusions && data.inclusions.length;
        if (hasSpecs || hasInclusions) {
            showModal(data.specFields || [], data.inclusions || []);
            return;
        }

        fetch('/admin/asset-names')
            .then(function (r) { return r.json(); })
            .then(function (names) {
                var found = names.find(function (n) { return String(n.id) === String(data.id); });
                showModal(
                    found ? (found.spec_fields || []) : [],
                    found ? (found.inclusions || []) : []
                );
            })
            .catch(function () { showModal([], []); });
    }

    function saveEditAssetName() {
        var id = $('editMgmtAssetNameId').value;
        var name = ($('editMgmtAssetNameValue').value || '').trim();
        if (!name) return showError('Please enter an asset name.');

        var updates = (global.MgmtAddAssetModals && global.MgmtAddAssetModals.collectSpecUpdates)
            ? global.MgmtAddAssetModals.collectSpecUpdates('editMgmtAssetNameSpecList')
            : [];
        var inclusionUpdates = (global.MgmtAddAssetModals && global.MgmtAddAssetModals.collectSpecUpdates)
            ? global.MgmtAddAssetModals.collectSpecUpdates('editMgmtAssetNameInclusionList')
            : [];

        var formData = new FormData();
        formData.append('name', name);
        formData.append('specifications_json', JSON.stringify(updates));
        formData.append('inclusions_json', JSON.stringify(inclusionUpdates));

        return fetch('/admin/asset-names/' + encodeURIComponent(id), { method: 'PUT', body: formData })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (data.success) {
                    getBsModal($('editMgmtAssetNameModal')).hide();
                    if (global.MgmtEditCallbacks && global.MgmtEditCallbacks.onAssetNameSaved) {
                        global.MgmtEditCallbacks.onAssetNameSaved();
                    } else if (typeof global.loadAssetNames === 'function') {
                        global.loadAssetNames();
                        if (typeof global.updateAssetNameDropdowns === 'function') global.updateAssetNameDropdowns();
                    }
                } else {
                    return showError(data.error || 'Failed to update asset name.');
                }
            })
            .catch(function () { return showError('Failed to update asset name.'); });
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

        var saveAssetName = $('editMgmtAssetNameSaveBtn');
        if (saveAssetName) saveAssetName.addEventListener('click', saveEditAssetName);

        var editSpecBtn = $('editMgmtAssetNameSpecBtn');
        if (editSpecBtn) {
            editSpecBtn.addEventListener('click', function () {
                if (global.MgmtAddAssetModals && global.MgmtAddAssetModals.addSpecRow) {
                    global.MgmtAddAssetModals.addSpecRow('editMgmtAssetNameSpecList', '', null);
                }
            });
        }

        var editInclusionBtn = $('editMgmtAssetNameInclusionBtn');
        if (editInclusionBtn) {
            editInclusionBtn.addEventListener('click', function () {
                if (global.MgmtAddAssetModals && global.MgmtAddAssetModals.addSpecRow) {
                    global.MgmtAddAssetModals.addSpecRow('editMgmtAssetNameInclusionList', '', null, 'e.g. Charger');
                }
            });
        }

        var ev = $('editMgmtEmployeeVenue');
        if (ev) ev.addEventListener('change', syncEditMgmtEmployeeVenue);

        var esearch = $('editMgmtEmployeeBranchSearch');
        if (esearch) {
            esearch.addEventListener('input', function () {
                if (global.EmployeeBranchChecklist && global.EmployeeBranchChecklist.filter) {
                    global.EmployeeBranchChecklist.filter('editMgmtEmployeeBranchList', esearch.value);
                }
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
        openAssetType: openEditAssetType,
        openAssetName: openEditAssetName
    };
})(window);

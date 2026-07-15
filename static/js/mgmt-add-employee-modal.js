/**
 * Register employee modal (Settings → Employees).
 */
(function (global) {
    'use strict';

    var OFFICE_BRANCH_LABEL = 'Office';
    var RESTAURANT_DEFAULT_DEPT = 'Restaurant';

    function $(id) {
        return document.getElementById(id);
    }

    function brandsList() {
        if (global.brandsData && global.brandsData.length) return global.brandsData;
        if (global.AssetAppState && global.AssetAppState.brands) return global.AssetAppState.brands;
        return [];
    }

    function branchesList() {
        if (global.branchesData && global.branchesData.length) return global.branchesData;
        if (global.AssetAppState && global.AssetAppState.branches) return global.AssetAppState.branches;
        return [];
    }

    function fillBrandSelect(sel, selectedId) {
        if (!sel) return;
        sel.innerHTML = '<option value="">Select brand</option>';
        brandsList().slice().sort(function (a, b) {
            return (a.name || '').localeCompare(b.name || '');
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
            return (a.name || '').localeCompare(b.name || '');
        }).forEach(function (b) {
            var o = document.createElement('option');
            o.value = String(b.id);
            o.textContent = b.name;
            sel.appendChild(o);
        });
        if (selectedBranchId) sel.value = String(selectedBranchId);
    }

    function showError(msg) {
        if (global.AppDialogs) return global.AppDialogs.error(msg);
        if (typeof global.alert === 'function') global.alert(msg);
        return Promise.resolve();
    }

    function showSuccess(msg) {
        if (global.AppDialogs) return global.AppDialogs.success(msg);
        if (typeof global.alert === 'function') global.alert(msg);
        return Promise.resolve();
    }

    function renderBranchChecklist(checkedIds) {
        if (global.EmployeeBranchChecklist && global.EmployeeBranchChecklist.render) {
            global.EmployeeBranchChecklist.render('addMgmtEmployeeBranchList', checkedIds || []);
        }
    }

    function syncAddEmployeeVenue() {
        var venueEl = $('addMgmtEmployeeVenue');
        var brwrap = $('addMgmtEmployeeBranchesWrap');
        var dwrap = $('addMgmtEmployeeDepartmentWrap');
        var dept = $('addMgmtEmployeeDepartment');
        var search = $('addMgmtEmployeeBranchSearch');
        if (!venueEl || !dept) return;

        var val = venueEl.value;
        if (val === 'office') {
            if (brwrap) brwrap.classList.add('d-none');
            if (dwrap) dwrap.classList.remove('d-none');
            dept.innerHTML = '<option value="">Loading...</option>';
            fetch('/admin/departments?office_only=1')
                .then(function (r) { return r.json(); })
                .then(function (depts) {
                    dept.innerHTML = '<option value="">Select department</option>';
                    depts.forEach(function (d) {
                        var option = document.createElement('option');
                        option.value = d.id;
                        option.textContent = d.name;
                        dept.appendChild(option);
                    });
                })
                .catch(function () {
                    dept.innerHTML = '<option value="">Error loading departments</option>';
                });
        } else if (val === 'restaurant') {
            if (brwrap) brwrap.classList.remove('d-none');
            if (dwrap) dwrap.classList.add('d-none');
            if (search) search.value = '';
            renderBranchChecklist([]);
        } else {
            if (brwrap) brwrap.classList.add('d-none');
            if (dwrap) dwrap.classList.add('d-none');
        }
    }

    function loadAddEmployeeDepartments(branchId) {
        var departmentSelect = $('addMgmtEmployeeDepartment');
        if (!departmentSelect || !branchId) return;

        departmentSelect.innerHTML = '<option value="">Loading...</option>';
        fetch('/admin/departments?branch_id=' + encodeURIComponent(branchId))
            .then(function (response) { return response.json(); })
            .then(function (departments) {
                var venueEl = $('addMgmtEmployeeVenue');
                var venue = venueEl ? venueEl.value : '';
                if (venue === 'restaurant') {
                    var pick = departments.filter(function (d) {
                        return d.name === RESTAURANT_DEFAULT_DEPT;
                    });
                    departmentSelect.innerHTML = '';
                    if (pick.length === 0) {
                        departmentSelect.innerHTML = '<option value="">Default department missing; contact IT</option>';
                        return;
                    }
                    pick.forEach(function (dept) {
                        var option = document.createElement('option');
                        option.value = dept.id;
                        option.textContent = dept.name;
                        departmentSelect.appendChild(option);
                    });
                    departmentSelect.value = String(pick[0].id);
                    return;
                }
                departmentSelect.innerHTML = '<option value="">Select department</option>';
                departments.forEach(function (dept) {
                    var option = document.createElement('option');
                    option.value = dept.id;
                    option.textContent = dept.name;
                    departmentSelect.appendChild(option);
                });
            })
            .catch(function () {
                departmentSelect.innerHTML = '<option value="">Error loading departments</option>';
            });
    }

    function resetAddEmployeeModal() {
        var venue = $('addMgmtEmployeeVenue');
        var employeeId = $('addMgmtEmployeeIdInput');
        var name = $('addMgmtEmployeeName');
        var mobile = $('addMgmtEmployeeMobile');
        var email = $('addMgmtEmployeeEmail');
        var search = $('addMgmtEmployeeBranchSearch');
        if (venue) venue.value = '';
        if (employeeId) employeeId.value = '';
        if (name) name.value = '';
        if (mobile) mobile.value = '';
        if (email) email.value = '';
        if (search) search.value = '';
        var list = $('addMgmtEmployeeBranchList');
        if (list) list.innerHTML = '';
        syncAddEmployeeVenue();
    }

    function saveAddEmployee() {
        var venue = $('addMgmtEmployeeVenue') ? $('addMgmtEmployeeVenue').value : '';
        var departmentId = $('addMgmtEmployeeDepartment') ? $('addMgmtEmployeeDepartment').value : '';
        var employeeId = $('addMgmtEmployeeIdInput') ? $('addMgmtEmployeeIdInput').value.trim() : '';
        var name = $('addMgmtEmployeeName') ? $('addMgmtEmployeeName').value.trim() : '';
        var mobile = $('addMgmtEmployeeMobile') ? $('addMgmtEmployeeMobile').value.trim() : '';
        var email = $('addMgmtEmployeeEmail') ? $('addMgmtEmployeeEmail').value.trim() : '';

        if (!venue) return showError('Please choose Restaurant or Office.');
        if (!employeeId) return showError('Please enter an employee ID.');
        if (!name) return showError('Please enter an employee name.');

        var payload = { name: name, employee_id: employeeId, mobile: mobile, email: email };
        if (venue === 'restaurant') {
            var branchIds = (global.EmployeeBranchChecklist && global.EmployeeBranchChecklist.getChecked)
                ? global.EmployeeBranchChecklist.getChecked('addMgmtEmployeeBranchList') : [];
            if (!branchIds.length) return showError('Please select at least one branch.');
            payload.branch_ids = branchIds;
        } else {
            if (!departmentId) return showError('Please select a department.');
            payload.department_id = parseInt(departmentId, 10);
        }

        return fetch('/admin/users', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (data.id) {
                    var modalEl = $('addMgmtEmployeeModal');
                    if (modalEl && global.bootstrap) {
                        global.bootstrap.Modal.getInstance(modalEl).hide();
                    }
                    resetAddEmployeeModal();
                    showSuccess('Employee "' + name + '" registered successfully.');
                    if (global.MgmtEditCallbacks && global.MgmtEditCallbacks.onEmployeeSaved) {
                        global.MgmtEditCallbacks.onEmployeeSaved();
                    } else if (typeof global.loadUserModalUsers === 'function') {
                        global.loadUserModalUsers();
                    }
                    if (typeof global.refreshOwnersIfAddAssetForm === 'function') {
                        global.refreshOwnersIfAddAssetForm();
                    }
                } else {
                    return showError(data.error || 'Failed to register employee.');
                }
            })
            .catch(function () { return showError('Failed to register employee.'); });
    }

    function bindOnce() {
        if (document.body.dataset.mgmtAddEmployeeModalBound === '1') return;
        document.body.dataset.mgmtAddEmployeeModalBound = '1';

        var saveBtn = $('addMgmtEmployeeSaveBtn');
        if (saveBtn) saveBtn.addEventListener('click', saveAddEmployee);

        var venueEl = $('addMgmtEmployeeVenue');
        if (venueEl) venueEl.addEventListener('change', syncAddEmployeeVenue);

        var searchEl = $('addMgmtEmployeeBranchSearch');
        if (searchEl) {
            searchEl.addEventListener('input', function () {
                if (global.EmployeeBranchChecklist && global.EmployeeBranchChecklist.filter) {
                    global.EmployeeBranchChecklist.filter('addMgmtEmployeeBranchList', searchEl.value);
                }
            });
        }

        var nameEl = $('addMgmtEmployeeName');
        if (nameEl) {
            nameEl.addEventListener('keypress', function (e) {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    saveAddEmployee();
                }
            });
        }

        var modalEl = $('addMgmtEmployeeModal');
        if (modalEl) {
            modalEl.addEventListener('show.bs.modal', function () {
                resetAddEmployeeModal();
            });
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', bindOnce);
    } else {
        bindOnce();
    }

    global.MgmtAddEmployeeModal = {
        resetAddEmployeeModal: resetAddEmployeeModal,
        populateBrands: function () {
            fillBrandSelect($('addMgmtEmployeeBrand'), $('addMgmtEmployeeBrand') ? $('addMgmtEmployeeBrand').value : '');
        }
    };
})(window);

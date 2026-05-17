/**
 * Reusable confirm / alert dialogs (maa-inventory modal-confirm pattern).
 */
(function (global) {
    'use strict';

    function el(id) {
        return document.getElementById(id);
    }

    function closeModal(modal) {
        if (!modal) return;
        modal.classList.remove('is-open');
        modal.setAttribute('aria-hidden', 'true');
    }

    function openModal(modal) {
        if (!modal) return;
        modal.classList.add('is-open');
        modal.setAttribute('aria-hidden', 'false');
    }

    function confirm(opts) {
        opts = opts || {};
        var modal = el('appConfirmModal');
        var titleEl = el('appConfirmTitle');
        var messageEl = el('appConfirmMessage');
        var cancelBtn = el('appConfirmCancel');
        var confirmBtn = el('appConfirmOk');
        if (!modal || !titleEl || !messageEl || !cancelBtn || !confirmBtn) {
            return Promise.resolve(global.confirm(opts.message || 'Are you sure?'));
        }

        titleEl.textContent = opts.title || 'Confirm';
        messageEl.textContent = opts.message || 'Are you sure?';
        cancelBtn.textContent = opts.cancelText || 'Cancel';
        confirmBtn.textContent = opts.confirmText || 'Confirm';
        confirmBtn.className = 'modal-confirm-btn modal-confirm-btn-confirm ' + (opts.confirmClass || 'modal-confirm-btn-approve');

        return new Promise(function (resolve) {
            function done(value) {
                closeModal(modal);
                cancelBtn.removeEventListener('click', onCancel);
                confirmBtn.removeEventListener('click', onConfirm);
                modal.removeEventListener('click', onBackdrop);
                document.removeEventListener('keydown', onKey);
                resolve(value);
            }

            function onCancel() { done(false); }
            function onConfirm() { done(true); }
            function onBackdrop(e) {
                if (e.target === modal) done(false);
            }
            function onKey(e) {
                if (e.key === 'Escape') done(false);
            }

            cancelBtn.addEventListener('click', onCancel);
            confirmBtn.addEventListener('click', onConfirm);
            modal.addEventListener('click', onBackdrop);
            document.addEventListener('keydown', onKey);
            openModal(modal);
            confirmBtn.focus();
        });
    }

    function alertDialog(opts) {
        opts = opts || {};
        var modal = el('appAlertModal');
        var titleEl = el('appAlertTitle');
        var messageEl = el('appAlertMessage');
        var okBtn = el('appAlertOk');
        if (!modal || !titleEl || !messageEl || !okBtn) {
            global.alert(opts.message || '');
            return Promise.resolve();
        }

        titleEl.textContent = opts.title || (opts.variant === 'error' ? 'Error' : 'Notice');
        messageEl.textContent = opts.message || '';
        okBtn.textContent = opts.okText || 'OK';
        okBtn.className = 'modal-confirm-btn modal-confirm-btn-confirm ' + (
            opts.variant === 'error' ? 'modal-confirm-btn-reject' : 'modal-confirm-btn-approve'
        );

        return new Promise(function (resolve) {
            function done() {
                closeModal(modal);
                okBtn.removeEventListener('click', onOk);
                modal.removeEventListener('click', onBackdrop);
                document.removeEventListener('keydown', onKey);
                resolve();
            }

            function onOk() { done(); }
            function onBackdrop(e) {
                if (e.target === modal) done();
            }
            function onKey(e) {
                if (e.key === 'Escape' || e.key === 'Enter') done();
            }

            okBtn.addEventListener('click', onOk);
            modal.addEventListener('click', onBackdrop);
            document.addEventListener('keydown', onKey);
            openModal(modal);
            okBtn.focus();
        });
    }

    function error(message, title) {
        return alertDialog({ title: title || 'Error', message: message || 'Something went wrong.', variant: 'error' });
    }

    function success(message, title) {
        return alertDialog({ title: title || 'Success', message: message || '', variant: 'success' });
    }

    global.AppDialogs = {
        confirm: confirm,
        alert: alertDialog,
        error: error,
        success: success
    };
})(window);

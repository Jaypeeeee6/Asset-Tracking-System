/**
 * Reusable confirm / alert / prompt dialogs (modal-confirm pattern).
 */
(function (global) {
    'use strict';

    var nativeAlert = global.alert.bind(global);

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

    function renderChips(container, chips) {
        if (!container) return;
        container.innerHTML = '';
        if (!chips || !chips.length) {
            container.hidden = true;
            return;
        }
        container.hidden = false;
        chips.forEach(function (item) {
            var chip = document.createElement('span');
            chip.className = 'modal-confirm-chip';
            var code = '';
            var name = '';
            if (item && typeof item === 'object') {
                code = (item.code != null ? String(item.code) : item.asset_code != null ? String(item.asset_code) : '').trim();
                name = (item.name != null ? String(item.name) : item.label != null ? String(item.label) : '').trim();
            } else {
                name = item != null ? String(item).trim() : '';
            }
            if (!code && !name) return;

            if (code && name) {
                chip.classList.add('modal-confirm-chip--with-code');
                var codeEl = document.createElement('span');
                codeEl.className = 'modal-confirm-chip-code';
                codeEl.textContent = code;
                var nameEl = document.createElement('span');
                nameEl.className = 'modal-confirm-chip-name';
                nameEl.textContent = name;
                chip.appendChild(codeEl);
                chip.appendChild(nameEl);
                chip.title = code + ' — ' + name;
            } else {
                var text = code || name;
                chip.textContent = text;
                chip.title = text;
            }
            container.appendChild(chip);
        });
    }

    function clearPromptExtras() {
        renderChips(el('appPromptChips'), null);
        var sub = el('appPromptSubmessage');
        if (sub) {
            sub.textContent = '';
            sub.hidden = true;
        }
        var card = el('appPromptModal');
        if (card) {
            var cardInner = card.querySelector('.modal-confirm-card');
            if (cardInner) cardInner.classList.remove('modal-confirm-card--wide');
        }
    }

    function bindDialogEvents(modal, handlers) {
        function cleanup() {
            closeModal(modal);
            handlers.onCleanup();
        }

        function onBackdrop(e) {
            if (e.target === modal && handlers.onCancel) handlers.onCancel();
        }

        function onKey(e) {
            if (e.key === 'Escape' && handlers.onCancel) handlers.onCancel();
            if (e.key === 'Enter' && handlers.onEnter) handlers.onEnter(e);
        }

        modal.addEventListener('click', onBackdrop);
        document.addEventListener('keydown', onKey);

        return function unbind() {
            modal.removeEventListener('click', onBackdrop);
            document.removeEventListener('keydown', onKey);
            cleanup();
        };
    }

    function confirm(opts) {
        opts = opts || {};
        var modal = el('appConfirmModal');
        var titleEl = el('appConfirmTitle');
        var messageEl = el('appConfirmMessage');
        var cancelBtn = el('appConfirmCancel');
        var confirmBtn = el('appConfirmOk');
        if (!modal || !titleEl || !messageEl || !cancelBtn || !confirmBtn) {
            return Promise.resolve(false);
        }

        titleEl.textContent = opts.title || 'Confirm';
        messageEl.textContent = opts.message || 'Are you sure?';
        cancelBtn.textContent = opts.cancelText || 'Cancel';
        confirmBtn.textContent = opts.confirmText || 'Confirm';
        confirmBtn.className = 'modal-confirm-btn modal-confirm-btn-confirm ' + (opts.confirmClass || 'modal-confirm-btn-approve');

        return new Promise(function (resolve) {
            var finished = false;

            function done(value) {
                if (finished) return;
                finished = true;
                cancelBtn.removeEventListener('click', onCancel);
                confirmBtn.removeEventListener('click', onConfirm);
                unbind();
                resolve(value);
            }

            function onCancel() { done(false); }
            function onConfirm() { done(true); }

            var unbind = bindDialogEvents(modal, {
                onCancel: onCancel,
                onEnter: function () { onConfirm(); },
                onCleanup: function () {}
            });

            cancelBtn.addEventListener('click', onCancel);
            confirmBtn.addEventListener('click', onConfirm);
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
            return Promise.resolve();
        }

        titleEl.textContent = opts.title || (opts.variant === 'error' ? 'Error' : opts.variant === 'success' ? 'Success' : 'Notice');
        messageEl.textContent = opts.message || '';
        okBtn.textContent = opts.okText || 'OK';
        okBtn.className = 'modal-confirm-btn modal-confirm-btn-confirm ' + (
            opts.variant === 'error' ? 'modal-confirm-btn-reject' : 'modal-confirm-btn-approve'
        );

        return new Promise(function (resolve) {
            var finished = false;

            function done() {
                if (finished) return;
                finished = true;
                okBtn.removeEventListener('click', onOk);
                unbind();
                resolve();
            }

            function onOk() { done(); }

            var unbind = bindDialogEvents(modal, {
                onCancel: done,
                onEnter: function () { done(); },
                onCleanup: function () {}
            });

            okBtn.addEventListener('click', onOk);
            openModal(modal);
            okBtn.focus();
        });
    }

    function promptDialog(opts) {
        opts = opts || {};
        var modal = el('appPromptModal');
        var titleEl = el('appPromptTitle');
        var messageEl = el('appPromptMessage');
        var inputEl = el('appPromptInput');
        var textareaEl = el('appPromptTextarea');
        var cancelBtn = el('appPromptCancel');
        var okBtn = el('appPromptOk');
        if (!modal || !titleEl || !messageEl || !cancelBtn || !okBtn) {
            return Promise.resolve(null);
        }

        var multiline = !!opts.multiline;
        var field = multiline ? textareaEl : inputEl;
        if (!field) return Promise.resolve(null);

        if (inputEl) inputEl.hidden = multiline;
        if (textareaEl) textareaEl.hidden = !multiline;

        clearPromptExtras();

        titleEl.textContent = opts.title || 'Enter value';
        messageEl.textContent = opts.message || '';

        var chipsEl = el('appPromptChips');
        if (opts.chips && opts.chips.length) {
            renderChips(chipsEl, opts.chips);
            var promptCard = modal.querySelector('.modal-confirm-card');
            if (promptCard) promptCard.classList.add('modal-confirm-card--wide');
        }

        var submessageEl = el('appPromptSubmessage');
        if (submessageEl && opts.submessage) {
            submessageEl.textContent = opts.submessage;
            submessageEl.hidden = false;
        }

        field.value = opts.defaultValue != null ? String(opts.defaultValue) : '';
        if (opts.placeholder) field.setAttribute('placeholder', opts.placeholder);
        else field.removeAttribute('placeholder');
        cancelBtn.textContent = opts.cancelText || 'Cancel';
        okBtn.textContent = opts.okText || 'OK';

        return new Promise(function (resolve) {
            var finished = false;

            function done(value) {
                if (finished) return;
                finished = true;
                cancelBtn.removeEventListener('click', onCancel);
                okBtn.removeEventListener('click', onOk);
                unbind();
                clearPromptExtras();
                resolve(value);
            }

            function onCancel() { done(null); }
            function onOk() { done(field.value); }

            var unbind = bindDialogEvents(modal, {
                onCancel: onCancel,
                onEnter: function (e) {
                    if (multiline && e.shiftKey) return;
                    e.preventDefault();
                    onOk();
                },
                onCleanup: function () {
                    clearPromptExtras();
                }
            });

            cancelBtn.addEventListener('click', onCancel);
            okBtn.addEventListener('click', onOk);
            openModal(modal);
            field.focus();
            if (!multiline) field.select();
        });
    }

    function error(message, title) {
        return alertDialog({ title: title || 'Error', message: message || 'Something went wrong.', variant: 'error' });
    }

    function success(message, title) {
        return alertDialog({ title: title || 'Success', message: message || '', variant: 'success' });
    }

    function deleteConfirm(message, title) {
        return confirm({
            title: title || 'Confirm delete',
            message: message,
            confirmText: 'Delete',
            confirmClass: 'modal-confirm-btn-reject'
        });
    }

    global.AppDialogs = {
        confirm: confirm,
        alert: alertDialog,
        prompt: promptDialog,
        error: error,
        success: success,
        deleteConfirm: deleteConfirm
    };

    global.alert = function (message) {
        if (el('appAlertModal')) {
            return alertDialog({ message: String(message) });
        }
        nativeAlert(message);
    };
})(window);

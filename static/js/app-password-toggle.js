/**
 * Show/hide password toggle for all password inputs.
 * Wraps inputs in .app-password-field and toggles type + eye icon.
 */
(function () {
    'use strict';

    function wrapPasswordInput(input) {
        if (!input || input.dataset.passwordToggleBound === '1') {
            return;
        }
        if (input.closest('.app-password-field')) {
            input.dataset.passwordToggleBound = '1';
            return;
        }

        var wrap = document.createElement('div');
        wrap.className = 'app-password-field';
        input.parentNode.insertBefore(wrap, input);
        wrap.appendChild(input);

        var btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'app-password-toggle';
        btn.setAttribute('aria-label', 'Show password');
        btn.setAttribute('tabindex', '0');
        btn.innerHTML = '<i class="bi bi-eye" aria-hidden="true"></i>';
        wrap.appendChild(btn);

        input.classList.add('app-password-input');
        input.dataset.passwordToggleBound = '1';

        btn.addEventListener('click', function () {
            var showing = input.type === 'text';
            input.type = showing ? 'password' : 'text';
            var icon = btn.querySelector('i');
            if (showing) {
                icon.className = 'bi bi-eye';
                btn.setAttribute('aria-label', 'Show password');
            } else {
                icon.className = 'bi bi-eye-slash';
                btn.setAttribute('aria-label', 'Hide password');
            }
        });
    }

    function initPasswordToggles(root) {
        var scope = root && root.querySelectorAll ? root : document;
        scope.querySelectorAll('input[type="password"]').forEach(wrapPasswordInput);
    }

    function onReady(fn) {
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', fn);
        } else {
            fn();
        }
    }

    onReady(function () {
        initPasswordToggles(document);

        document.addEventListener('shown.bs.modal', function (ev) {
            initPasswordToggles(ev.target);
        });

        document.addEventListener('hidden.bs.modal', function (ev) {
            (ev.target || document).querySelectorAll('.app-password-field input.app-password-input').forEach(function (input) {
                if (input.type === 'text') {
                    input.type = 'password';
                    var btn = input.parentNode.querySelector('.app-password-toggle');
                    if (btn) {
                        var icon = btn.querySelector('i');
                        if (icon) {
                            icon.className = 'bi bi-eye';
                        }
                        btn.setAttribute('aria-label', 'Show password');
                    }
                }
            });
        });
    });

    window.initPasswordToggles = initPasswordToggles;
})();

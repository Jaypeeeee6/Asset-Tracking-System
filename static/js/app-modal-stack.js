/**
 * When multiple modals are stacked, Bootstrap removes body.modal-open after the
 * top modal hides even if another modal is still open — background scroll returns.
 * Restore scroll lock if any .modal.show remains.
 */
(function () {
    function scrollbarWidth() {
        return Math.max(0, window.innerWidth - document.documentElement.clientWidth);
    }

    function restoreScrollLockIfNeeded() {
        if (document.querySelectorAll('.modal.show').length === 0) {
            return;
        }
        document.body.classList.add('modal-open');
        document.body.style.overflow = 'hidden';
        var sw = scrollbarWidth();
        document.body.style.paddingRight = sw > 0 ? sw + 'px' : '';
    }

    document.addEventListener('hidden.bs.modal', function () {
        setTimeout(restoreScrollLockIfNeeded, 0);
    });
})();

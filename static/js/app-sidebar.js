document.addEventListener('DOMContentLoaded', function () {
    const toggleBtn = document.getElementById('sidebarToggle');
    const wrapper = document.getElementById('wrapper');

    if (toggleBtn && wrapper) {
        toggleBtn.addEventListener('click', function () {
            wrapper.classList.add('sidebar-transitioning');
            wrapper.classList.toggle('sidebar-hidden');
            wrapper.classList.toggle('sidebar-open');
            window.setTimeout(function () {
                wrapper.classList.remove('sidebar-transitioning');
            }, 280);
        });
    }

    function replayPageEnterAnimation() {
        const el = document.querySelector('.page-enter');
        if (!el || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
        el.classList.remove('page-enter');
        void el.offsetWidth;
        el.classList.add('page-enter');
    }

    window.addEventListener('pageshow', function (event) {
        if (event.persisted) {
            replayPageEnterAnimation();
        }
    });
});

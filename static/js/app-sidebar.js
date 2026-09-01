document.addEventListener('DOMContentLoaded', function () {
    const toggleBtn = document.getElementById('sidebarToggle');
    const drawerCloseBtn = document.getElementById('sidebarDrawerClose');
    const wrapper = document.getElementById('wrapper');
    const sidebar = document.getElementById('sidebar-wrapper');
    const mobileMQ = window.matchMedia('(max-width: 640px)');

    function openSidebar() {
        if (!wrapper) return;
        wrapper.classList.add('sidebar-transitioning');
        wrapper.classList.add('sidebar-hidden');
        wrapper.classList.add('sidebar-open');
        if (toggleBtn) toggleBtn.setAttribute('aria-expanded', 'true');
        window.setTimeout(function () {
            wrapper.classList.remove('sidebar-transitioning');
        }, 280);
    }

    function closeSidebar() {
        if (!wrapper) return;
        wrapper.classList.add('sidebar-transitioning');
        wrapper.classList.remove('sidebar-hidden');
        wrapper.classList.remove('sidebar-open');
        if (toggleBtn) toggleBtn.setAttribute('aria-expanded', 'false');
        window.setTimeout(function () {
            wrapper.classList.remove('sidebar-transitioning');
        }, 280);
    }

    function toggleSidebar() {
        if (!wrapper) return;
        if (wrapper.classList.contains('sidebar-open')) closeSidebar();
        else openSidebar();
    }

    if (toggleBtn && wrapper) {
        toggleBtn.setAttribute('aria-expanded', 'false');
        toggleBtn.addEventListener('click', function () {
            toggleSidebar();
        });
    }

    if (drawerCloseBtn) {
        drawerCloseBtn.addEventListener('click', function (e) {
            e.preventDefault();
            closeSidebar();
        });
    }

    if (sidebar && wrapper) {
        sidebar.querySelectorAll('a.sidebar-item').forEach(function (link) {
            link.addEventListener('click', function () {
                if (mobileMQ.matches) {
                    closeSidebar();
                }
            });
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

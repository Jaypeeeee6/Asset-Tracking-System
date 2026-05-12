(function () {
    function updateDarkModeButton(isDark) {
        var btn = document.getElementById('darkModeToggle');
        if (!btn) return;
        var icon = btn.querySelector('i');
        var text = btn.querySelector('span');
        var isNavToggle = btn.classList.contains('navbar-dark-toggle');

        if (isDark) {
            if (icon) icon.className = 'fas fa-sun';
            if (text) text.textContent = isNavToggle ? 'Light mode' : ' Light Mode';
            if (!isNavToggle) {
                btn.style.borderColor = '#ffd700';
                btn.style.color = '#ffd700';
            }
        } else {
            if (icon) icon.className = 'fas fa-moon';
            if (text) text.textContent = isNavToggle ? 'Dark mode' : ' Dark Mode';
            if (!isNavToggle) {
                btn.style.borderColor = '#6c757d';
                btn.style.color = '#6c757d';
            }
        }
    }

    window.toggleDarkMode = function () {
        var body = document.body;
        var isDark = body.classList.contains('dark-mode');
        if (isDark) {
            body.classList.remove('dark-mode');
            localStorage.setItem('darkMode', 'false');
            updateDarkModeButton(false);
        } else {
            body.classList.add('dark-mode');
            localStorage.setItem('darkMode', 'true');
            updateDarkModeButton(true);
        }
    };

    window.updateDarkModeButton = updateDarkModeButton;

    document.addEventListener('DOMContentLoaded', function () {
        var btn = document.getElementById('darkModeToggle');
        if (!btn) return;
        if (localStorage.getItem('darkMode') === 'true') {
            document.body.classList.add('dark-mode');
            updateDarkModeButton(true);
        }
    });
})();

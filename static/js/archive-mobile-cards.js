/**
 * Archive page: mobile card list (matches dashboard asset register cards).
 */
(function (global) {
    'use strict';

    var MQ = global.matchMedia('(max-width: 640px)');

    function cellAt(row, idx) {
        return row.cells[idx] || null;
    }

    function cellTextAt(row, idx) {
        var cell = cellAt(row, idx);
        if (!cell) return '—';
        var text = cell.textContent.replace(/\s+/g, ' ').trim();
        return text || '—';
    }

    function assetCodeFromRow(row) {
        var qrText = row.querySelector('.qr-code-text');
        if (qrText) {
            var code = qrText.textContent.replace(/\s+/g, ' ').trim();
            if (code) return code;
        }
        var detailsCell = cellAt(row, 1);
        var small = detailsCell && detailsCell.querySelector('small');
        if (small) {
            var smallText = small.textContent.replace(/\s+/g, ' ').trim();
            if (smallText) return smallText;
        }
        return '—';
    }

    function assetNameFromRow(row) {
        var detailsCell = cellAt(row, 1);
        if (!detailsCell) return '—';
        var strong = detailsCell.querySelector('strong');
        if (strong) {
            var name = strong.textContent.replace(/\s+/g, ' ').trim();
            if (name) return name;
        }
        return cellTextAt(row, 1);
    }

    function categoryFromRow(row) {
        var detailsCell = cellAt(row, 1);
        if (!detailsCell) return '—';
        var smalls = detailsCell.querySelectorAll('small');
        if (smalls.length >= 2) {
            return (smalls[1].textContent || '').replace(/\s+/g, ' ').trim() || '—';
        }
        return '—';
    }

    function addCardRow(body, label, valueNode) {
        var rowEl = document.createElement('div');
        rowEl.className = 'asset-register-mobile-card-row';
        var labelEl = document.createElement('span');
        labelEl.className = 'asset-register-mobile-card-label';
        labelEl.textContent = label;
        var valueEl = document.createElement('div');
        valueEl.className = 'asset-register-mobile-card-value';
        if (typeof valueNode === 'string') {
            valueEl.textContent = valueNode;
        } else if (valueNode) {
            valueEl.appendChild(valueNode);
        } else {
            valueEl.textContent = '—';
        }
        rowEl.appendChild(labelEl);
        rowEl.appendChild(valueEl);
        body.appendChild(rowEl);
    }

    function buildMobileCards() {
        var container = document.querySelector('.archive-page .asset-register-mobile-cards');
        var table = document.querySelector('.archive-page .archive-table');
        if (!container || !table) return;

        container.innerHTML = '';
        var rows = table.querySelectorAll('tbody tr.archived-row');

        if (!rows.length) {
            var emptyState = document.querySelector('.archive-page .asset-register-card .empty-state');
            if (emptyState) {
                var emptyEl = document.createElement('div');
                emptyEl.className = 'asset-register-mobile-cards-empty';
                emptyEl.textContent = emptyState.textContent.replace(/\s+/g, ' ').trim() || 'No archived assets found.';
                container.appendChild(emptyEl);
            }
            return;
        }

        rows.forEach(function (row) {
            var card = document.createElement('article');
            card.className = 'asset-register-mobile-card archived-row';

            var checkbox = row.querySelector('.archived-asset-checkbox');
            if (checkbox) {
                var checkWrap = document.createElement('div');
                checkWrap.className = 'asset-register-mobile-card-check';
                checkWrap.appendChild(checkbox.cloneNode(true));
                card.appendChild(checkWrap);
            }

            var header = document.createElement('div');
            header.className = 'asset-register-mobile-card-header';

            var codeEl = document.createElement('span');
            codeEl.className = 'asset-register-mobile-card-code';
            codeEl.textContent = assetCodeFromRow(row);

            var nameEl = document.createElement('span');
            nameEl.className = 'asset-register-mobile-card-name';
            nameEl.textContent = assetNameFromRow(row);

            header.appendChild(codeEl);
            header.appendChild(nameEl);
            card.appendChild(header);

            var body = document.createElement('div');
            body.className = 'asset-register-mobile-card-body';

            addCardRow(body, 'Category', categoryFromRow(row));

            var locationCell = cellAt(row, 3);
            if (locationCell) {
                var locationClone = locationCell.cloneNode(true);
                locationClone.querySelectorAll('.archive-meta').forEach(function (meta) {
                    meta.querySelectorAll('div').forEach(function (div) {
                        div.className = 'archive-meta-line';
                    });
                });
                addCardRow(body, 'Location', locationClone);
            } else {
                addCardRow(body, 'Location', '—');
            }

            var statusCell = cellAt(row, 4);
            if (statusCell) {
                var badge = statusCell.querySelector('.badge');
                var statusRow = document.createElement('div');
                statusRow.className = 'asset-register-mobile-card-row';
                var statusLabel = document.createElement('span');
                statusLabel.className = 'asset-register-mobile-card-label';
                statusLabel.textContent = 'Status';
                var statusValue = document.createElement('div');
                statusValue.className = 'asset-register-mobile-card-value';
                if (badge) {
                    statusValue.appendChild(badge.cloneNode(true));
                } else {
                    statusValue.textContent = cellTextAt(row, 4);
                }
                statusRow.appendChild(statusLabel);
                statusRow.appendChild(statusValue);
                body.appendChild(statusRow);
            }

            var archiveCell = cellAt(row, 5);
            if (archiveCell) {
                var archiveClone = archiveCell.cloneNode(true);
                addCardRow(body, 'Archive info', archiveClone);
            }

            var qrCell = cellAt(row, 2);
            var qrImg = qrCell && qrCell.querySelector('.qr-code-img');
            if (qrImg) {
                var qrRow = document.createElement('div');
                qrRow.className = 'asset-register-mobile-card-row asset-register-mobile-card-row--qr';
                var qrLabel = document.createElement('span');
                qrLabel.className = 'asset-register-mobile-card-label';
                qrLabel.textContent = 'QR Code';
                var qrValue = document.createElement('div');
                qrValue.className = 'asset-register-mobile-card-value';
                var qrClone = qrImg.cloneNode(true);
                qrClone.classList.add('asset-register-qr-img');
                qrValue.appendChild(qrClone);
                qrRow.appendChild(qrLabel);
                qrRow.appendChild(qrValue);
                body.appendChild(qrRow);
            }

            var actionsCell = cellAt(row, 6);
            var actions = actionsCell && actionsCell.querySelector('.archive-actions');
            if (actions) {
                var actionsWrap = document.createElement('div');
                actionsWrap.className = 'asset-register-mobile-card-actions archive-mobile-card-actions';
                actionsWrap.appendChild(actions.cloneNode(true));
                body.appendChild(actionsWrap);
            }

            card.appendChild(body);
            container.appendChild(card);
        });
    }

    function syncArchiveMobileCards() {
        if (!MQ.matches) {
            var container = document.querySelector('.archive-page .asset-register-mobile-cards');
            if (container) container.innerHTML = '';
            return;
        }
        buildMobileCards();
        if (typeof global.applyArchivedCheckboxDomFromSelection === 'function') {
            global.applyArchivedCheckboxDomFromSelection();
        }
    }

    global.syncArchiveMobileCards = syncArchiveMobileCards;

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', syncArchiveMobileCards);
    } else {
        syncArchiveMobileCards();
    }

    if (typeof MQ.addEventListener === 'function') {
        MQ.addEventListener('change', syncArchiveMobileCards);
    } else if (typeof MQ.addListener === 'function') {
        MQ.addListener(syncArchiveMobileCards);
    }
}(window));

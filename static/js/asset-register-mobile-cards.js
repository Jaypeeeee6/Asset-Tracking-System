/**
 * Dashboard asset register: mobile card list (mirrors maa-inventory item master).
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
        var nameCell = cellAt(row, 3);
        var small = nameCell && nameCell.querySelector('small');
        if (small) {
            var smallText = small.textContent.replace(/\s+/g, ' ').trim();
            if (smallText) return smallText;
        }
        return cellTextAt(row, 1);
    }

    function assetNameFromRow(row) {
        var nameCell = cellAt(row, 3);
        if (!nameCell) return '—';
        var strong = nameCell.querySelector('strong');
        if (strong) {
            var name = strong.textContent.replace(/\s+/g, ' ').trim();
            if (name) return name;
        }
        return cellTextAt(row, 3);
    }

    function cloneLocationValue(row) {
        var cell = cellAt(row, 6);
        if (!cell) return null;
        var chips = cell.querySelector('.asset-location-chips');
        if (chips) return chips.cloneNode(true);
        return null;
    }

    function cloneCategoryValue(row) {
        var cell = cellAt(row, 4);
        if (!cell) return null;
        var badge = cell.querySelector('.badge-type');
        if (badge) {
            var span = document.createElement('span');
            span.className = 'badge-type';
            span.textContent = badge.textContent.replace(/\s+/g, ' ').trim();
            return span;
        }
        return null;
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
        var container = document.querySelector('.asset-register-mobile-cards');
        var table = document.querySelector('.asset-register-table');
        if (!container || !table) return;

        container.innerHTML = '';
        var rows = table.querySelectorAll('tbody tr.asset-register-row');

        if (!rows.length) {
            var emptyState = document.querySelector('.asset-register-card .empty-state');
            if (emptyState) {
                var emptyEl = document.createElement('div');
                emptyEl.className = 'asset-register-mobile-cards-empty';
                emptyEl.textContent = emptyState.textContent.replace(/\s+/g, ' ').trim() || 'No assets found.';
                container.appendChild(emptyEl);
            }
            return;
        }

        rows.forEach(function (row) {
            var card = document.createElement('article');
            card.className = 'asset-register-mobile-card asset-register-row';

            var checkbox = row.querySelector('.asset-checkbox');
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

            var categoryNode = cloneCategoryValue(row);
            addCardRow(body, 'Category', categoryNode || cellTextAt(row, 4));

            var ownerCell = cellAt(row, 5);
            if (ownerCell) {
                var ownerClone = ownerCell.cloneNode(true);
                ownerClone.querySelectorAll('br').forEach(function (br) {
                    br.replaceWith(document.createTextNode(' '));
                });
                addCardRow(body, 'Owner', ownerClone);
            } else {
                addCardRow(body, 'Owner', '—');
            }

            var locationNode = cloneLocationValue(row);
            if (locationNode) {
                var locationRow = document.createElement('div');
                locationRow.className = 'asset-register-mobile-card-row';
                var locationLabel = document.createElement('span');
                locationLabel.className = 'asset-register-mobile-card-label';
                locationLabel.textContent = 'Branch/Department';
                var locationValue = document.createElement('div');
                locationValue.className = 'asset-register-mobile-card-value asset-register-mobile-card-value--chips';
                locationValue.appendChild(locationNode);
                locationRow.appendChild(locationLabel);
                locationRow.appendChild(locationValue);
                body.appendChild(locationRow);
            } else {
                addCardRow(body, 'Branch/Department', cellTextAt(row, 6));
            }

            var statusCell = cellAt(row, 7);
            if (statusCell) {
                var statusSelect = statusCell.querySelector('.status-select');
                var statusRow = document.createElement('div');
                statusRow.className = 'asset-register-mobile-card-row';
                var statusLabel = document.createElement('span');
                statusLabel.className = 'asset-register-mobile-card-label';
                statusLabel.textContent = 'Status';
                var statusValue = document.createElement('div');
                statusValue.className = 'asset-register-mobile-card-value asset-register-mobile-card-value--status';
                if (statusSelect) {
                    statusValue.appendChild(statusSelect.cloneNode(true));
                } else {
                    statusValue.textContent = cellTextAt(row, 7);
                }
                statusRow.appendChild(statusLabel);
                statusRow.appendChild(statusValue);
                body.appendChild(statusRow);
            }

            addCardRow(body, 'Date', cellTextAt(row, 8));

            var qrCell = cellAt(row, 2);
            var qrImg = qrCell && qrCell.querySelector('.asset-register-qr-img');
            if (qrImg) {
                var qrRow = document.createElement('div');
                qrRow.className = 'asset-register-mobile-card-row asset-register-mobile-card-row--qr';
                var qrLabel = document.createElement('span');
                qrLabel.className = 'asset-register-mobile-card-label';
                qrLabel.textContent = 'QR Code';
                var qrValue = document.createElement('div');
                qrValue.className = 'asset-register-mobile-card-value';
                qrValue.appendChild(qrImg.cloneNode(true));
                qrRow.appendChild(qrLabel);
                qrRow.appendChild(qrValue);
                body.appendChild(qrRow);
            }

            var actionsCell = cellAt(row, 9);
            var actions = actionsCell && actionsCell.querySelector('.app-table-actions');
            if (actions) {
                var actionsWrap = document.createElement('div');
                actionsWrap.className = 'asset-register-mobile-card-actions';
                actionsWrap.appendChild(actions.cloneNode(true));
                body.appendChild(actionsWrap);
            }

            card.appendChild(body);
            container.appendChild(card);
        });
    }

    function syncAssetRegisterMobileCards() {
        if (!MQ.matches) {
            var container = document.querySelector('.asset-register-mobile-cards');
            if (container) container.innerHTML = '';
            return;
        }
        buildMobileCards();
        if (typeof global.applyAssetCheckboxDomFromSelection === 'function') {
            global.applyAssetCheckboxDomFromSelection();
        }
    }

    global.syncAssetRegisterMobileCards = syncAssetRegisterMobileCards;

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', syncAssetRegisterMobileCards);
    } else {
        syncAssetRegisterMobileCards();
    }

    if (typeof MQ.addEventListener === 'function') {
        MQ.addEventListener('change', syncAssetRegisterMobileCards);
    } else if (typeof MQ.addListener === 'function') {
        MQ.addListener(syncAssetRegisterMobileCards);
    }
}(window));

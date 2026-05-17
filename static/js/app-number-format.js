/**
 * Thousands separators for displayed numbers (en-US).
 */
(function (global) {
    function fmtNum(value) {
        const n = Math.round(Number(value) || 0);
        return n.toLocaleString('en-US');
    }

    function fmtOmr(value, decimals) {
        const d = decimals === undefined ? 3 : decimals;
        const n = Number(value) || 0;
        return n.toLocaleString('en-US', {
            minimumFractionDigits: d,
            maximumFractionDigits: d,
        });
    }

    global.fmtNum = fmtNum;
    global.fmtOmr = fmtOmr;
})(typeof window !== 'undefined' ? window : global);

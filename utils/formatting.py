"""Display formatting for numbers in templates."""


def format_int(value):
    """Format an integer with thousands separators."""
    if value is None:
        return '0'
    try:
        n = int(round(float(value)))
    except (TypeError, ValueError):
        return str(value)
    return f'{n:,}'


def format_omr(value, decimals=3):
    """Format an OMR amount with thousands separators and fixed decimals."""
    if value is None:
        value = 0.0
    try:
        n = float(value)
    except (TypeError, ValueError):
        return str(value)
    return f'{n:,.{decimals}f}'

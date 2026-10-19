from datetime import date, datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

IST = timezone(timedelta(hours=5, minutes=30))
MAX_PAISE = 9_000_000_000_000_000


def today():
    return datetime.now(IST).date().isoformat()


def timestamp():
    return datetime.now(timezone.utc).isoformat(timespec='microseconds')


def valid_date(value):
    try:
        result = date.fromisoformat(value)
    except (ValueError, TypeError):
        raise ValueError('Enter a date as YYYY-MM-DD.') from None
    if result.isoformat() != value:
        raise ValueError('Enter a date as YYYY-MM-DD.')
    return value


def paise(value):
    """Parse rupees exactly; reject fractional paise rather than silently round."""
    try:
        amount = Decimal(str(value).replace(',', '').strip())
        scaled = amount * 100
        if not amount.is_finite() or scaled != scaled.to_integral_value():
            raise ValueError('Amounts must have at most two decimal places.')
        result = int(scaled)
        if abs(result) > MAX_PAISE:
            raise ValueError('Amount is too large.')
        return result
    except (InvalidOperation, TypeError):
        raise ValueError('Enter a valid amount in rupees.') from None


def money(value, symbol='₹'):
    negative = value < 0
    whole, fraction = divmod(abs(int(value)), 100)
    s = str(whole)
    if len(s) > 3:
        tail, head = s[-3:], s[:-3]
        groups = []
        while head:
            groups.insert(0, head[-2:])
            head = head[:-2]
        s = ','.join(groups + [tail])
    return f'{"-" if negative else ""}{symbol}{s}.{fraction:02d}'


def rate(value):
    try:
        result = Decimal(str(value))
        if not result.is_finite() or result < 0 or result > 1000:
            raise ValueError('Annual rate must be between 0 and 1000%.')
        return str(result)
    except InvalidOperation:
        raise ValueError('Enter a valid annual interest rate.') from None


def interest_paise(principal_day_sum, annual_rate):
    return int((Decimal(principal_day_sum) * Decimal(annual_rate) / Decimal(36500)).quantize(Decimal('1'), rounding=ROUND_HALF_UP))

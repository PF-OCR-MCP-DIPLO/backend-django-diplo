import re
from decimal import Decimal, InvalidOperation


def smart_parse_currency(value):
    if not value:
        return None
    cleaned = re.sub(r"[^\d.,-]", "", str(value))
    if not cleaned:
        return None
    dot_pos = cleaned.rfind(".")
    comma_pos = cleaned.rfind(",")
    if dot_pos == -1 and comma_pos == -1:
        try:
            return float(Decimal(cleaned))
        except InvalidOperation:
            return None
    if dot_pos != -1 and comma_pos != -1:
        if dot_pos > comma_pos:
            decimal_sep = "."
            thousand_sep = ","
        else:
            decimal_sep = ","
            thousand_sep = "."
    elif dot_pos != -1:
        if len(cleaned.split(".")[-1]) == 3:
            decimal_sep = ","
            thousand_sep = "."
        else:
            decimal_sep = "."
            thousand_sep = ","
    else:
        if len(cleaned.split(",")[-1]) == 3:
            decimal_sep = "."
            thousand_sep = ","
        else:
            decimal_sep = ","
            thousand_sep = "."
    cleaned = cleaned.replace(thousand_sep, "")
    if decimal_sep != ".":
        cleaned = cleaned.replace(decimal_sep, ".")
    try:
        return float(Decimal(cleaned))
    except InvalidOperation:
        return None

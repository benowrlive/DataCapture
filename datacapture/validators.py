"""Field validation and branching-logic evaluation (server side)."""
import re
from datetime import datetime

FIELD_TYPES = [
    ("text", "Text box"),
    ("notes", "Notes box (paragraph)"),
    ("integer", "Integer"),
    ("number", "Number (decimal)"),
    ("date", "Date (YYYY-MM-DD)"),
    ("time", "Time (HH:MM)"),
    ("email", "Email"),
    ("phone", "Phone"),
    ("dropdown", "Multiple choice — drop-down"),
    ("radio", "Multiple choice — radio buttons"),
    ("checkbox", "Checkboxes (multiple answers)"),
    ("yesno", "Yes / No"),
    ("truefalse", "True / False"),
    ("slider", "Slider (0-100)"),
    ("file", "File / photo upload"),
    ("section_header", "Section header (display only)"),
    ("descriptive", "Descriptive text (display only)"),
]

DISPLAY_ONLY = {"section_header", "descriptive"}
CHOICE_TYPES = {"dropdown", "radio", "checkbox"}
FILE_TYPES = {"file"}

VARNAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,49}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TIME_RE = re.compile(r"^\d{2}:\d{2}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_RE = re.compile(r"^[0-9+()\-\s]{6,20}$")


def parse_choices(choices_str):
    """'1, Male | 2, Female' -> [('1','Male'), ('2','Female')]"""
    out = []
    for part in (choices_str or "").split("|"):
        part = part.strip()
        if not part:
            continue
        if "," in part:
            code, label = part.split(",", 1)
            out.append((code.strip(), label.strip()))
        else:
            out.append((part, part))
    return out


def effective_choices(field):
    t = field["field_type"]
    if t == "yesno":
        return [("1", "Yes"), ("0", "No")]
    if t == "truefalse":
        return [("1", "True"), ("0", "False")]
    if t in CHOICE_TYPES:
        return parse_choices(field["choices"])
    return []


def validate_value(field, value):
    """Return error message or None. `value` is the stored string.
    Checkbox values are comma-separated codes."""
    t = field["field_type"]
    if t in DISPLAY_ONLY:
        return None
    if value == "" or value is None:
        return "This field is required." if field["required"] else None

    if t == "integer" or field["validation"] == "integer":
        if not re.match(r"^-?\d+$", value):
            return "Value must be a whole number."
        return _range_check(field, int(value))
    if t in ("number", "slider") or field["validation"] == "number":
        try:
            v = float(value)
        except ValueError:
            return "Value must be a number."
        if t == "slider" and not (0 <= v <= 100):
            return "Slider value must be 0-100."
        return _range_check(field, v)
    if t == "date" or field["validation"] == "date":
        if not DATE_RE.match(value):
            return "Date must be in YYYY-MM-DD format."
        try:
            datetime.strptime(value, "%Y-%m-%d")
        except ValueError:
            return "Not a valid calendar date."
        return _range_check(field, value)
    if t == "time":
        if not TIME_RE.match(value):
            return "Time must be in HH:MM format."
        h, m = int(value[:2]), int(value[3:])
        if h > 23 or m > 59:
            return "Not a valid time."
        return None
    if t == "email" or field["validation"] == "email":
        return None if EMAIL_RE.match(value) else "Not a valid email address."
    if t == "phone" or field["validation"] == "phone":
        return None if PHONE_RE.match(value) else "Not a valid phone number."

    if t in ("dropdown", "radio", "yesno", "truefalse"):
        codes = {c for c, _ in effective_choices(field)}
        if value not in codes:
            return f"'{value}' is not a valid category for {field['name']}."
        return None
    if t == "checkbox":
        codes = {c for c, _ in effective_choices(field)}
        for v in value.split(","):
            v = v.strip()
            if v and v not in codes:
                return f"'{v}' is not a valid category for {field['name']}."
        return None
    return None


def _range_check(field, v):
    lo, hi = field["min_value"], field["max_value"]
    try:
        if lo != "" and _cmp_cast(v, lo) < 0:
            return f"Value must be ≥ {lo}."
        if hi != "" and _cmp_cast(v, hi) > 0:
            return f"Value must be ≤ {hi}."
    except (ValueError, TypeError):
        pass
    return None


def _cmp_cast(v, bound):
    if isinstance(v, str):  # date compare as string (ISO sorts correctly)
        return (v > bound) - (v < bound)
    b = float(bound)
    return (v > b) - (v < b)


# ------------------------------------------------------------------ branching

_TOKEN_RE = re.compile(
    r"\s*(\[[a-z0-9_]+(?:\(\d+\))?\]|<>|>=|<=|=|>|<|\(|\)|and\b|or\b|"
    r"'[^']*'|\"[^\"]*\"|-?\d+(?:\.\d+)?)",
    re.IGNORECASE,
)


def tokenize_logic(logic):
    pos, tokens = 0, []
    while pos < len(logic):
        m = _TOKEN_RE.match(logic, pos)
        if not m:
            if logic[pos:].strip() == "":
                break
            raise ValueError(f"Bad token near: {logic[pos:pos+20]!r}")
        tokens.append(m.group(1))
        pos = m.end()
    return tokens


def eval_branching(logic, values):
    """Evaluate branching logic against {field_name: value} dict.
    Returns True (show field) on empty/invalid logic (fail open)."""
    logic = (logic or "").strip()
    if not logic:
        return True
    try:
        tokens = tokenize_logic(logic)
        result, rest = _parse_or(tokens, values)
        if rest:
            raise ValueError("Unexpected trailing tokens")
        return result
    except Exception:
        return True


def branching_visibility(fields, values):
    """Return {field_name: visible} while clearing hidden values downstream."""
    working = dict(values)
    visible = {}
    for f in fields:
        name = f["name"]
        is_visible = eval_branching(f["branching_logic"], working)
        visible[name] = is_visible
        if not is_visible:
            working[name] = ""
    return visible


def _parse_or(tokens, values):
    left, tokens = _parse_and(tokens, values)
    while tokens and tokens[0].lower() == "or":
        right, tokens = _parse_and(tokens[1:], values)
        left = left or right
    return left, tokens


def _parse_and(tokens, values):
    left, tokens = _parse_cmp(tokens, values)
    while tokens and tokens[0].lower() == "and":
        right, tokens = _parse_cmp(tokens[1:], values)
        left = left and right
    return left, tokens


def _parse_cmp(tokens, values):
    if not tokens:
        raise ValueError("Unexpected end of logic")
    if tokens[0] == "(":
        inner, tokens = _parse_or(tokens[1:], values)
        if not tokens or tokens[0] != ")":
            raise ValueError("Missing )")
        return inner, tokens[1:]
    left, tokens = _operand(tokens, values)
    if not tokens:
        raise ValueError("Expected operator")
    op, tokens = tokens[0], tokens[1:]
    right, tokens = _operand(tokens, values)
    return _compare(left, op, right), tokens


def _operand(tokens, values):
    if not tokens:
        raise ValueError("Expected operand")
    tok = tokens[0]
    if tok.startswith("["):
        inner = tok[1:-1]
        m = re.match(r"^([a-z0-9_]+)\((\d+)\)$", inner)
        if m:  # checkbox syntax [field(code)] -> '1' if checked
            raw = values.get(m.group(1), "") or ""
            checked = m.group(2) in [v.strip() for v in raw.split(",")]
            return ("1" if checked else "0"), tokens[1:]
        return (values.get(inner, "") or ""), tokens[1:]
    if tok[0] in "'\"":
        return tok[1:-1], tokens[1:]
    return tok, tokens[1:]


def _compare(left, op, right):
    ln, rn = _num(left), _num(right)
    if ln is not None and rn is not None:
        left, right = ln, rn
    if op == "=":
        return left == right
    if op == "<>":
        return left != right
    if ln is None or rn is None:  # ordered compares on strings (dates OK)
        left, right = str(left), str(right)
    if op == ">":
        return left > right
    if op == ">=":
        return left >= right
    if op == "<":
        return left < right
    if op == "<=":
        return left <= right
    raise ValueError(f"Unknown operator {op}")


def _num(s):
    try:
        return float(s)
    except (ValueError, TypeError):
        return None

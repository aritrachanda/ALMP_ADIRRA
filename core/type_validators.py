"""Pure validators used by semantic-type resolution.

Each validator accepts sample values and returns a pass rate in ``[0.0, 1.0]``.
Blank values are ignored so missingness remains a separate profiling concern.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Iterable, Sequence

_VALIDATOR_NAMES = {"mod97", "iso4217", "iso3166", "lei_checksum", "date_range",
                    "hetu_checksum", "y_tunnus_checksum",
                    "bic_structure", "isin_checksum", "email_format", "phone_format",
                    "timestamp_parse", "uuid_format"}

_ISO4217 = {
    "AED", "AFN", "ALL", "AMD", "ANG", "AOA", "ARS", "AUD", "AWG", "AZN",
    "BAM", "BBD", "BDT", "BGN", "BHD", "BIF", "BMD", "BND", "BOB", "BRL",
    "BSD", "BTN", "BWP", "BYN", "BZD", "CAD", "CDF", "CHF", "CLP", "CNY",
    "COP", "CRC", "CUP", "CVE", "CZK", "DJF", "DKK", "DOP", "DZD", "EGP",
    "ERN", "ETB", "EUR", "FJD", "FKP", "GBP", "GEL", "GHS", "GIP", "GMD",
    "GNF", "GTQ", "GYD", "HKD", "HNL", "HTG", "HUF", "IDR", "ILS", "INR",
    "IQD", "IRR", "ISK", "JMD", "JOD", "JPY", "KES", "KGS", "KHR", "KMF",
    "KRW", "KWD", "KYD", "KZT", "LAK", "LBP", "LKR", "LRD", "LSL", "LYD",
    "MAD", "MDL", "MGA", "MKD", "MMK", "MNT", "MOP", "MRU", "MUR", "MVR",
    "MWK", "MXN", "MYR", "MZN", "NAD", "NGN", "NIO", "NOK", "NPR", "NZD",
    "OMR", "PAB", "PEN", "PGK", "PHP", "PKR", "PLN", "PYG", "QAR", "RON",
    "RSD", "RUB", "RWF", "SAR", "SBD", "SCR", "SDG", "SEK", "SGD", "SHP",
    "SLE", "SOS", "SRD", "SSP", "STN", "SYP", "SZL", "THB", "TJS", "TMT",
    "TND", "TOP", "TRY", "TTD", "TWD", "TZS", "UAH", "UGX", "USD", "UYU",
    "UZS", "VES", "VND", "VUV", "WST", "XAF", "XCD", "XOF", "XPF", "YER",
    "ZAR", "ZMW", "ZWL",
}

_ISO3166 = {
    "AD", "AE", "AF", "AG", "AI", "AL", "AM", "AO", "AQ", "AR", "AS", "AT",
    "AU", "AW", "AX", "AZ", "BA", "BB", "BD", "BE", "BF", "BG", "BH", "BI",
    "BJ", "BL", "BM", "BN", "BO", "BQ", "BR", "BS", "BT", "BV", "BW", "BY",
    "BZ", "CA", "CC", "CD", "CF", "CG", "CH", "CI", "CK", "CL", "CM", "CN",
    "CO", "CR", "CU", "CV", "CW", "CX", "CY", "CZ", "DE", "DJ", "DK", "DM",
    "DO", "DZ", "EC", "EE", "EG", "EH", "ER", "ES", "ET", "FI", "FJ", "FK",
    "FM", "FO", "FR", "GA", "GB", "GD", "GE", "GF", "GG", "GH", "GI", "GL",
    "GM", "GN", "GP", "GQ", "GR", "GS", "GT", "GU", "GW", "GY", "HK", "HM",
    "HN", "HR", "HT", "HU", "ID", "IE", "IL", "IM", "IN", "IO", "IQ", "IR",
    "IS", "IT", "JE", "JM", "JO", "JP", "KE", "KG", "KH", "KI", "KM", "KN",
    "KP", "KR", "KW", "KY", "KZ", "LA", "LB", "LC", "LI", "LK", "LR", "LS",
    "LT", "LU", "LV", "LY", "MA", "MC", "MD", "ME", "MF", "MG", "MH", "MK",
    "ML", "MM", "MN", "MO", "MP", "MQ", "MR", "MS", "MT", "MU", "MV", "MW",
    "MX", "MY", "MZ", "NA", "NC", "NE", "NF", "NG", "NI", "NL", "NO", "NP",
    "NR", "NU", "NZ", "OM", "PA", "PE", "PF", "PG", "PH", "PK", "PL", "PM",
    "PN", "PR", "PS", "PT", "PW", "PY", "QA", "RE", "RO", "RS", "RU", "RW",
    "SA", "SB", "SC", "SD", "SE", "SG", "SH", "SI", "SJ", "SK", "SL", "SM",
    "SN", "SO", "SR", "SS", "ST", "SV", "SX", "SY", "SZ", "TC", "TD", "TF",
    "TG", "TH", "TJ", "TK", "TL", "TM", "TN", "TO", "TR", "TT", "TV", "TW",
    "TZ", "UA", "UG", "UM", "US", "UY", "UZ", "VA", "VC", "VE", "VG", "VI",
    "VN", "VU", "WF", "WS", "YE", "YT", "ZA", "ZM", "ZW",
}


def _clean_samples(values: Iterable[object]) -> list[str]:
    cleaned: list[str] = []
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text == "":
            continue
        cleaned.append(text)
    return cleaned


def _rate(values: Iterable[object], predicate) -> float:
    cleaned = _clean_samples(values)
    if not cleaned:
        return 0.0
    return sum(1 for value in cleaned if predicate(value)) / len(cleaned)


def _mod97_valid(identifier: str) -> bool:
    text = "".join(identifier.upper().split())
    if len(text) < 4:
        return False
    rearranged = text[4:] + text[:4]
    digits = []
    for char in rearranged:
        if char.isdigit():
            digits.append(char)
        elif "A" <= char <= "Z":
            digits.append(str(ord(char) - 55))
        else:
            return False
    remainder = 0
    for char in "".join(digits):
        remainder = (remainder * 10 + int(char)) % 97
    return remainder == 1


def mod97(values: Iterable[object]) -> float:
    """Return the share of samples passing the IBAN-style MOD-97 check."""
    return _rate(values, _mod97_valid)


def iso4217(values: Iterable[object]) -> float:
    """Return the share of samples that are ISO 4217 currency codes."""
    return _rate(values, lambda value: value.upper() in _ISO4217)


def iso3166(values: Iterable[object]) -> float:
    """Return the share of samples that are ISO 3166-1 alpha-2 country codes."""
    return _rate(values, lambda value: value.upper() in _ISO3166)


def _iso7064_mod97_10(value: str) -> bool:
    converted = []
    for char in value.upper():
        if char.isdigit():
            converted.append(char)
        elif "A" <= char <= "Z":
            converted.append(str(ord(char) - 55))
        else:
            return False
    remainder = 0
    for char in "".join(converted):
        remainder = (remainder * 10 + int(char)) % 97
    return remainder == 1


def lei_checksum(values: Iterable[object]) -> float:
    """Return the share of samples passing the LEI ISO 17442 checksum."""
    return _rate(values, lambda value: len(value) == 20 and _iso7064_mod97_10(value))


def _parse_date(value: str) -> date | None:
    text = value.strip()
    formats = (
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%d/%m/%Y",
        "%m/%d/%Y",
        "%Y%m%d",
        "%d%m%Y",
        "%m%d%Y",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
    )
    for fmt in formats:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def date_range(
    values: Iterable[object],
    *,
    min_date: date = date(1900, 1, 1),
    max_date: date = date(2100, 12, 31),
) -> float:
    """Return the share of samples parseable as dates in a broad plausible range."""
    def predicate(value: str) -> bool:
        parsed = _parse_date(value)
        return parsed is not None and min_date <= parsed <= max_date

    return _rate(values, predicate)


def _timestamp_valid(value: str, *, min_year: int, max_year: int) -> bool:
    """Check whether *value* parses as a timestamp within [min_year, max_year]."""
    text = value.strip()
    if not text:
        return False

    if text.isdigit() and len(text) >= 8:
        try:
            epoch = int(text)
        except ValueError:
            return False
        for candidate in (epoch, epoch / 1000):
            try:
                dt = datetime.fromtimestamp(candidate)
            except (ValueError, OverflowError, OSError):
                continue
            if min_year <= dt.year <= max_year:
                return True
        return False

    iso_text = text[:-1] + "+00:00" if text.endswith("Z") else text
    parsers = (
        datetime.fromisoformat,
        lambda t: datetime.strptime(t, "%Y-%m-%d %H:%M:%S"),
        lambda t: datetime.strptime(t, "%Y-%m-%dT%H:%M:%S"),
        lambda t: datetime.strptime(t, "%Y-%m-%d %H:%M:%S.%f"),
        lambda t: datetime.strptime(t, "%Y-%m-%dT%H:%M:%S.%f"),
    )
    for parser in parsers:
        try:
            dt = parser(iso_text)
        except ValueError:
            continue
        return min_year <= dt.year <= max_year
    return False


def timestamp_parse(
    values: Iterable[object],
    *,
    min_year: int = 1990,
    max_year: int = 2100,
) -> float:
    """Return the share of samples parseable as a timestamp.

    Accepts ISO 8601 (with or without timezone / trailing ``Z``), the plain
    ``YYYY-MM-DD HH:MM:SS`` form, and epoch seconds/milliseconds expressed as
    digit strings, sanity-bounded to years [*min_year*, *max_year*].
    """
    return _rate(values, lambda v: _timestamp_valid(v, min_year=min_year, max_year=max_year))


# Finnish national identifier validators ────────────────────────────────────

_HETU_CHECKSUM_CHARS = "0123456789ABCDEFHJKLMNPRSTUVWXY"
_HETU_SEPARATORS = {"-", "+", "A", "B", "C", "D", "E", "F", "U", "V", "W", "X", "Y"}


def _hetu_valid(value: str) -> bool:
    """Validate a Finnish personal identity code (Henkilötunnus / HETU).

    Format: DDMMYY[sep]XXXC  where sep ∈ {-, +, A-F, U-Y}.
    """
    v = str(value).strip().upper()
    if len(v) != 11:
        return False
    date_part = v[:6]
    sep = v[6]
    individual = v[7:10]
    check_char = v[10]
    if sep not in _HETU_SEPARATORS:
        return False
    if not (date_part.isdigit() and individual.isdigit()):
        return False
    combined = int(date_part + individual)
    return _HETU_CHECKSUM_CHARS[combined % 31] == check_char


def hetu_checksum(values: Iterable[object]) -> float:
    """Return the share of samples passing the Finnish HETU (Henkilötunnus) checksum."""
    return _rate(values, _hetu_valid)


_Y_TUNNUS_WEIGHTS = (7, 9, 10, 5, 8, 4, 2)


def _y_tunnus_valid(value: str) -> bool:
    """Validate a Finnish business identifier (Y-tunnus).

    Format: XXXXXXX-C  (7 digits, hyphen, 1 check digit).
    """
    v = str(value).strip()
    if len(v) != 9 or v[7] != "-":
        return False
    digits = v[:7]
    check_str = v[8]
    if not (digits.isdigit() and check_str.isdigit()):
        return False
    total = sum(int(d) * w for d, w in zip(digits, _Y_TUNNUS_WEIGHTS))
    remainder = total % 11
    if remainder == 1:
        return False  # invalid by definition
    expected = 0 if remainder == 0 else 11 - remainder
    return expected == int(check_str)


def y_tunnus_checksum(values: Iterable[object]) -> float:
    """Return the share of samples passing the Finnish Y-tunnus checksum."""
    return _rate(values, _y_tunnus_valid)


# ── International financial / contact validators ─────────────────────────────

import re as _re

_BIC_RE = _re.compile(r'^[A-Z]{4}[A-Z]{2}[A-Z0-9][2-9A-Z]([A-Z0-9]{3})?$')


def _bic_valid(value: str) -> bool:
    """True when the value is a valid BIC (ISO 9362) whose country segment is real.

    Two gates, because shape alone is not enough:
      1. The regex enforces the ISO 9362 layout — a 4-letter bank code, a 2-letter
         country code, a 2-character location code whose second character is not
         the reserved test ('0') or passive ('1') marker, and an optional
         3-character branch code.
      2. Characters 5-6 (the country code) must be a real ISO 3166 country. This
         rejects shape-only look-alikes such as 'APPLICATION', whose 'IC'
         segment is not a country — a regex can never catch that on its own.
    """
    v = value.upper()
    return bool(_BIC_RE.match(v)) and v[4:6] in _ISO3166


def bic_structure(values: Iterable[object]) -> float:
    """Return the share of samples that are valid BICs (ISO 9362 layout + ISO 3166 country)."""
    return _rate(values, _bic_valid)


_ISIN_RE = _re.compile(r'^[A-Z]{2}[A-Z0-9]{9}[0-9]$')


def _isin_valid(value: str) -> bool:
    """Validate ISIN (ISO 6166) using the Luhn-mod-10 algorithm."""
    v = value.strip().upper()
    if not _ISIN_RE.match(v):
        return False
    # Convert letters to digits: A=10, B=11 … Z=35
    digits_str = "".join(str(ord(c) - 55) if c.isalpha() else c for c in v)
    total = 0
    for i, ch in enumerate(reversed(digits_str)):
        n = int(ch)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


def isin_checksum(values: Iterable[object]) -> float:
    """Return the share of samples passing the ISIN Luhn checksum."""
    return _rate(values, _isin_valid)


_EMAIL_RE = _re.compile(r'^[^@\s]{1,64}@[^@\s]{1,255}\.[^@\s]{2,}$')


def email_format(values: Iterable[object]) -> float:
    """Return the share of samples matching a basic RFC-style email format."""
    return _rate(values, lambda v: bool(_EMAIL_RE.match(v)))


_PHONE_RE = _re.compile(
    r'^(\+|00)?[1-9]\d{6,14}$'   # E.164-ish: optional +/00 prefix, 7–15 total digits
)
_PHONE_SEPS = _re.compile(r'[\s\-\(\)]+')  # spaces, hyphens, parentheses only
                                              # dots intentionally excluded: 1230028.21 is NOT a phone number


def _phone_normalised(value: str) -> str:
    return _PHONE_SEPS.sub('', value.strip())


def phone_format(values: Iterable[object]) -> float:
    """Return the share of samples plausibly matching an international phone number."""
    return _rate(values, lambda v: bool(_PHONE_RE.match(_phone_normalised(v))))


# UUID / GUID — the distinctive dashed 8-4-4-4-12 structure is near-unforgeable, so
# a value passing this is almost certainly a real UUID (any version v1-v8). Accepts
# the canonical dashed form plus common wrappers: {braces} and the urn:uuid: prefix.
# A bare 32-hex string (no dashes) is intentionally NOT matched here — it is
# shape-indistinguishable from an MD5 hash, so it is handled as a hash-like token.
_UUID_RE = _re.compile(
    r'^(?:urn:uuid:)?\{?'
    r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}'
    r'\}?$'
)


def _uuid_valid(value: str) -> bool:
    return bool(_UUID_RE.match(value.strip()))


def uuid_format(values: Iterable[object]) -> float:
    """Return the share of samples matching the canonical dashed UUID/GUID structure."""
    return _rate(values, _uuid_valid)


def run_validator(name: str | None, values: Sequence[object] | Iterable[object]) -> float | None:
    """Run a named validator if known; return ``None`` for absent/unknown names."""
    if not name:
        return None
    validators = {
        "mod97": mod97,
        "iso4217": iso4217,
        "iso3166": iso3166,
        "lei_checksum": lei_checksum,
        "date_range": date_range,
        "hetu_checksum": hetu_checksum,
        "y_tunnus_checksum": y_tunnus_checksum,
        "bic_structure": bic_structure,
        "isin_checksum": isin_checksum,
        "email_format": email_format,
        "phone_format": phone_format,
        "timestamp_parse": timestamp_parse,
        "uuid_format": uuid_format,
    }
    validator = validators.get(name)
    if validator is None:
        return None
    return validator(values)


def run_validator_detail(
    name: str | None,
    values: Sequence[object] | Iterable[object],
) -> tuple[float | None, list[str], list[str]]:
    """Run a named validator and return (pass_rate, passing_values, failing_values).

    Returns (None, [], []) for absent/unknown validators.
    Caps both lists at 5 entries to keep evidence readable.
    """
    if not name:
        return None, [], []
    validators = {
        "mod97": _mod97_valid,
        "iso4217": lambda v: v.upper() in _ISO4217,
        "iso3166": lambda v: v.upper() in _ISO3166,
        "lei_checksum": lambda v: len(v) == 20 and _iso7064_mod97_10(v),
        "date_range": lambda v: _parse_date(v) is not None and date(1900, 1, 1) <= _parse_date(v) <= date(2100, 12, 31),  # type: ignore[operator]
        "hetu_checksum": _hetu_valid,
        "y_tunnus_checksum": _y_tunnus_valid,
        "bic_structure": _bic_valid,
        "isin_checksum": _isin_valid,
        "email_format": lambda v: bool(_EMAIL_RE.match(v)),
        "phone_format": lambda v: bool(_PHONE_RE.match(_phone_normalised(v))),
        "timestamp_parse": lambda v: _timestamp_valid(v, min_year=1990, max_year=2100),
        "uuid_format": _uuid_valid,
    }
    predicate = validators.get(name)
    if predicate is None:
        return None, [], []
    cleaned = _clean_samples(values)
    if not cleaned:
        return None, [], []
    passing, failing = [], []
    for v in cleaned:
        try:
            result = predicate(v)
        except Exception:
            result = False
        if result:
            passing.append(v)
        else:
            failing.append(v)
    rate = len(passing) / len(cleaned)
    return rate, passing[:5], failing[:5]


def known_validators() -> set[str]:
    return set(_VALIDATOR_NAMES)

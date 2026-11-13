"""Checksum and shape validators. Pure functions over strings of digits/letters."""
import re

_DNI_LETTERS = "TRWAGMYFPDXBNJZSQVHLCKE"


def luhn_valid(digits: str) -> bool:
    if not digits.isdigit() or len(digits) < 2:
        return False
    total = 0
    for i, c in enumerate(reversed(digits)):
        d = int(c)
        if i % 2:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def iban_valid(s: str) -> bool:
    s = re.sub(r"\s+", "", s).upper()
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{11,30}", s):
        return False
    r = s[4:] + s[:4]
    return int("".join(str(int(c, 36)) for c in r)) % 97 == 1


def dni_valid(s: str) -> bool:
    s = s.upper()
    if not re.fullmatch(r"\d{8}[A-Z]", s):
        return False
    return _DNI_LETTERS[int(s[:8]) % 23] == s[8]


def nie_valid(s: str) -> bool:
    s = s.upper()
    if not re.fullmatch(r"[XYZ]\d{7}[A-Z]", s):
        return False
    return dni_valid(str("XYZ".index(s[0])) + s[1:])


def cpf_valid(digits: str) -> bool:
    if not re.fullmatch(r"\d{11}", digits) or len(set(digits)) == 1:
        return False
    n = [int(c) for c in digits]
    d1 = (sum(n[i] * (10 - i) for i in range(9)) * 10) % 11 % 10
    d2 = (sum(n[i] * (11 - i) for i in range(10)) * 10) % 11 % 10
    return d1 == n[9] and d2 == n[10]


def clabe_valid(digits: str) -> bool:
    if not re.fullmatch(r"\d{18}", digits):
        return False
    w = [3, 7, 1] * 6
    s = sum((int(digits[i]) * w[i]) % 10 for i in range(17))
    return (10 - s % 10) % 10 == int(digits[17])


def curp_shape_valid(s: str) -> bool:
    """Shape only. The CURP check digit is not implemented yet (plan §6.3); the catch-all and
    spelled-run rules carry recall for CURPs in the meantime."""
    return bool(re.fullmatch(r"[A-Z]{4}\d{6}[HM][A-Z]{2}[B-DF-HJ-NP-TV-Z]{3}[A-Z\d]\d", s.upper()))


def rfc_shape_valid(s: str) -> bool:
    return bool(re.fullmatch(r"[A-Z&Ñ]{3,4}\d{6}[A-Z\d]{3}", s.upper()))

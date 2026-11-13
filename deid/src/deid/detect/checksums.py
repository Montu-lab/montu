"""Checksum and shape validators. Pure functions over strings of digits/letters."""


def luhn_valid(digits: str) -> bool:
    raise NotImplementedError


def iban_valid(s: str) -> bool:
    raise NotImplementedError


def dni_valid(s: str) -> bool:
    raise NotImplementedError


def nie_valid(s: str) -> bool:
    raise NotImplementedError


def cpf_valid(digits: str) -> bool:
    raise NotImplementedError


def clabe_valid(digits: str) -> bool:
    raise NotImplementedError


def curp_shape_valid(s: str) -> bool:
    """Shape only. The CURP check digit is not implemented yet (plan §6.3); the catch-all and
    spelled-run rules carry recall for CURPs in the meantime."""
    raise NotImplementedError

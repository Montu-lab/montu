"""UNIT. Checksum validators. Expected values computed independently (scratch script, not this code)."""
from deid.detect.checksums import (clabe_valid, cpf_valid, curp_shape_valid, dni_valid, iban_valid,
                                   luhn_valid, nie_valid)


def test_luhn():
    assert luhn_valid("4111111111111111")
    assert luhn_valid("5555555555554444")
    assert not luhn_valid("4111111111111112")


def test_iban():
    assert iban_valid("ES9121000418450200051332")
    assert iban_valid("es91 2100 0418 4502 0005 1332")
    assert not iban_valid("ES9121000418450200051333")


def test_dni_nie():
    assert dni_valid("12345678Z")
    assert not dni_valid("12345678A")
    assert nie_valid("X1234567L")
    assert not nie_valid("X1234567A")


def test_cpf():
    assert cpf_valid("52998224725")
    assert not cpf_valid("52998224726")
    assert not cpf_valid("11111111111")  # repeated digits pass the arithmetic but are invalid CPFs


def test_clabe():
    assert clabe_valid("032180000118359719")
    assert not clabe_valid("032180000118359718")


def test_curp_shape_only():
    assert curp_shape_valid("GODE561231HDFRRN09")
    assert not curp_shape_valid("GODE561231XDFRRN09")  # sex must be H or M

"""Shared types. Every value that reaches a log is one of these enums, an int, a float or a digest."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Channel(str, Enum):
    AGENT = "agent"
    CUSTOMER = "customer"


class Category(str, Enum):
    NAME = "NAME"
    BRAND = "BRAND"
    CARD = "CARD"
    IBAN = "IBAN"
    ACCOUNT = "ACCOUNT"
    NATIONAL_ID = "NATIONAL_ID"
    PHONE = "PHONE"
    EMAIL = "EMAIL"
    DOB = "DOB"
    REFERENCE = "REFERENCE"
    ADDRESS = "ADDRESS"
    NUMBER = "NUMBER"
    SPELLED = "SPELLED"
    UNCLEAR = "UNCLEAR"


class Detector(str, Enum):
    LUHN = "luhn"
    IBAN_MOD97 = "iban_mod97"
    DNI = "dni"
    NIE = "nie"
    CPF = "cpf"
    CLABE = "clabe"
    CURP = "curp"
    RFC = "rfc"
    SSN = "ssn"
    PHONE = "phone"
    EMAIL = "email"
    DOB_CUE = "dob_cue"
    REFERENCE_CUE = "reference_cue"
    ADDRESS_CUE = "address_cue"
    ACCOUNT_CUE = "account_cue"
    CATCH_ALL_DIGITS = "catch_all_digits"
    SPELLED_RUN = "spelled_run"
    LEXICON = "lexicon"
    GREETING_SLOT = "greeting_slot"
    NAME_CUE = "name_cue"
    LOW_CONFIDENCE = "low_confidence"
    NER = "ner"


class DropReason(str, Enum):
    PCI = "pci"
    SPECIAL_CATEGORY = "special_category"
    MINOR = "minor"
    VULNERABLE = "vulnerable"
    LANGUAGE_MISMATCH = "language_mismatch"
    UNREADABLE_AUDIO = "unreadable_audio"
    ALIGNMENT_FAILURE = "alignment_failure"
    VOICE_ANON_UNAVAILABLE = "voice_anon_unavailable"
    LEAK_SCAN = "leak_scan"
    STAGE_ERROR = "stage_error"
    WRITE_ERROR = "write_error"


# Exclusion triggers a policy rule may name. A rule naming anything else is refused by the loader.
TRIGGER_TO_REASON = {
    "pci": DropReason.PCI,
    "special_category": DropReason.SPECIAL_CATEGORY,
    "minor": DropReason.MINOR,
    "vulnerable": DropReason.VULNERABLE,
}


@dataclass(frozen=True)
class Word:
    text: str
    start_ms: int
    end_ms: int
    prob: float
    channel: Channel


@dataclass(frozen=True)
class Entity:
    category: Category
    channel: Channel
    word_start: int  # inclusive index into that channel's word list
    word_end: int  # inclusive
    start_ms: int
    end_ms: int
    detector: Detector
    confidence: float


@dataclass(frozen=True)
class Decision:
    drop: bool
    reasons: tuple[DropReason, ...] = ()
    rule_ids: tuple[str, ...] = ()

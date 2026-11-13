"""Identifier detection over one channel's word stream.

Every detector works on normalised tokens and returns word-index spans; timings come from the words.
Placeholder tokens such as "[NAME]" (from an earlier redaction) are hard boundaries: no entity includes one.
Recall first: where a rule is unsure, it redacts.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from ..lexicon import Lexicon
from ..numbers import NumberRun, find_number_runs
from ..spelling import _letter_at, find_spelled_runs
from ..textnorm import ends_clause, find_phrase, is_placeholder, norm, phrase_tokens
from ..types import Category, Channel, Detector, Entity, Word
from .checksums import (clabe_valid, cpf_valid, curp_shape_valid, dni_valid, iban_valid, luhn_valid,
                        nie_valid, rfc_shape_valid)


@dataclass(frozen=True)
class DetectConfig:
    digit_catch_all: int = 4
    low_conf: float = 0.5
    low_conf_window: int = 2
    unclear_run: int = 3


# ---- language resources (detection cues; what to DROP lives in policies/) ----
CUES = {
    "es": {
        "brand": ["bienvenido a", "bienvenida a", "bienvenidos a", "gracias por llamar a", "ha llamado a",
                  "ha contactado con", "le llamo de", "le llamamos de", "llamo de parte de", "le atendemos desde",
                  "servicio de atencion al cliente de", "atencion al cliente de"],
        "name": ["le atiende", "le habla", "mi nombre es", "me llamo", "a nombre de", "habla con", "soy", "con quien hablo",
                 "el titular es", "la titular es", "mi apellido es", "mi segundo apellido es"],
        "name_weak": ["soy"],
        "stop": {"le", "mi", "en", "y", "e", "que", "como", "buenos", "buenas", "con", "para", "por", "me", "soy",
                 "sobre", "su", "sus", "al", "a", "lo", "la", "el", "es", "hoy", "pues", "bueno", "vale", "si",
                 "no", "gracias", "llamo", "quiero", "queria", "tengo", "porque", "pero", "senor", "senora"},
        "dob": ["fecha de nacimiento", "naci el", "naci en", "nacimiento", "cumpleanos", "nacio el"],
        "address": ["calle", "avenida", "avda", "av", "plaza", "paseo", "colonia", "col", "carrera", "carretera",
                    "camino", "ronda", "travesia", "glorieta", "codigo postal", "cp", "urbanizacion", "barrio",
                    "fraccionamiento", "domicilio", "direccion", "calzada", "boulevard", "bulevar", "privada",
                    "manzana", "lote"],
        "address_keep": {"numero", "piso", "puerta", "bajo", "izquierda", "derecha", "escalera", "portal", "de",
                         "del", "la", "las", "los", "el", "letra", "interior", "exterior", "esquina", "con", "y",
                         "num", "no", "n"},
        "address_stop": {"gracias", "vale", "pero", "porque", "que", "ok", "bueno", "entonces", "y", "en", "es",
                         "para", "por", "si", "me", "mi", "le"},
        "reference": ["pedido", "referencia", "ticket", "incidencia", "expediente", "reserva", "localizador",
                      "contrato", "factura", "numero de cliente", "cliente", "poliza", "orden", "folio",
                      "codigo", "solicitud", "caso", "seguimiento", "matricula", "placa"],
        "account": ["cuenta", "iban", "clabe", "tarjeta", "numero de cuenta"],
        "national": ["dni", "nie", "nif", "curp", "rfc", "cpf", "cedula", "documento", "pasaporte", "ine",
                     "seguridad social", "rut", "cuil", "cuit"],
        "phone": ["telefono", "movil", "celular", "numero de contacto", "llamame", "llameme", "whatsapp"],
        "email_at": {"arroba"},
        "email_dot": {"punto", "dot"},
        "email_conn": {"punto", "guion", "bajo", "barra", "dot"},
        "lead_skip": {"es", "el", "la", "de", "del", "numero", "num", "mi", "su", "pues", "eh", "seria", "son",
                      "sera", "ver", "tengo", "esta", "con", "que"},
        "months": {"enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre",
                   "setiembre", "octubre", "noviembre", "diciembre"},
        "date_glue": {"de", "del", "el", "primero"},
    },
    "en": {
        "brand": ["thank you for calling", "thanks for calling", "welcome to", "you've reached", "youve reached",
                  "you have reached", "calling from", "calling on behalf of", "this is the", "customer service for"],
        "name": ["my name is", "you're speaking with", "youre speaking with", "you are speaking with",
                 "speaking with", "this is", "i'm", "im", "name's", "names", "the account holder is",
                 "account is under", "under the name", "last name is", "first name is", "surname is"],
        "name_weak": ["this is", "i'm", "im", "speaking with"],
        "stop": {"my", "how", "this", "and", "i", "you", "we", "is", "it", "today", "can", "may", "speaking",
                 "the", "a", "an", "to", "for", "with", "from", "calling", "about", "here", "please", "so", "but",
                 "um", "uh", "yes", "no", "thanks", "thank", "what", "who", "that", "on", "in", "at", "of"},
        "dob": ["date of birth", "birthday", "born on", "dob", "birth date", "birthdate", "i was born"],
        "address": ["street", "st", "avenue", "ave", "road", "rd", "boulevard", "blvd", "lane", "ln", "drive",
                    "dr", "court", "ct", "place", "way", "terrace", "highway", "zip code", "zip", "postcode",
                    "postal code", "apartment", "apt", "suite", "unit", "address", "po box"],
        "address_keep": {"north", "south", "east", "west", "n", "s", "e", "w", "apartment", "apt", "suite", "unit",
                         "number", "no", "floor", "and", "of", "the"},
        "address_stop": {"thanks", "thank", "okay", "ok", "but", "because", "so", "is", "and", "in", "for", "please",
                         "yes", "my", "i"},
        "reference": ["order", "reference", "ref", "ticket", "case", "booking", "confirmation", "reservation",
                      "policy", "invoice", "customer number", "member id", "member number", "claim", "tracking",
                      "code", "id", "plate", "license", "licence"],
        "account": ["account", "iban", "routing", "card", "account number", "sort code"],
        "national": ["social security", "ssn", "social", "passport", "driver's license", "drivers license",
                     "tax id", "itin", "ein", "national id"],
        "phone": ["phone", "number", "cell", "mobile", "call me", "reach me", "callback", "call back"],
        "email_at": {"at"},
        "email_dot": {"dot", "period"},
        "email_conn": {"dot", "underscore", "dash", "hyphen", "period"},
        "lead_skip": {"is", "the", "number", "it's", "its", "my", "your", "uh", "um", "it", "that", "of",
                      "would", "be", "should"},
        "months": {"january", "february", "march", "april", "may", "june", "july", "august", "september",
                   "october", "november", "december", "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep",
                   "sept", "oct", "nov", "dec"},
        "date_glue": {"of", "the", "st", "nd", "rd", "th"},
    },
}
TLDS = {"com", "es", "mx", "net", "org", "co", "edu", "gov", "io", "info", "br", "ar", "us", "uk", "fr", "de",
        "it", "pt", "biz", "me", "eu", "cat", "gob"}
PHONE_LENGTHS = {9, 10, 11, 12, 13}
SEVERITY = [Category.CARD, Category.NATIONAL_ID, Category.IBAN, Category.ACCOUNT, Category.PHONE, Category.EMAIL,
            Category.DOB, Category.ADDRESS, Category.NAME, Category.BRAND, Category.REFERENCE, Category.SPELLED,
            Category.NUMBER, Category.UNCLEAR]


def _res(lang: str) -> dict:
    return CUES.get(lang, CUES["en"])


class _Ctx:
    def __init__(self, words: list[Word], lang: str, channel: Channel):
        self.words = words
        self.lang = lang
        self.channel = channel
        self.toks = [norm(w.text) for w in words]
        self.ph = [is_placeholder(w.text) for w in words]
        self.R = _res(lang)
        self.out: list[Entity] = []

    def add(self, cat: Category, s: int, e: int, det: Detector, conf: float = 0.9) -> None:
        if s > e or s < 0 or e >= len(self.words):
            return
        while s <= e and self.ph[s]:
            s += 1
        while e >= s and self.ph[e]:
            e -= 1
        if s > e:
            return
        self.out.append(Entity(cat, self.channel, s, e, self.words[s].start_ms, self.words[e].end_ms, det, conf))

    def cue_hits(self, phrases) -> list[tuple[int, int]]:
        """(start, end) word indices of each cue phrase occurrence."""
        hits = []
        for p in phrases:
            pt = phrase_tokens(p)
            for i in find_phrase(self.toks, pt):
                hits.append((i, i + len(pt) - 1))
        return hits

    def cue_before(self, idx: int, phrases, window: int = 5) -> bool:
        return any(e < idx and idx - e <= window for _, e in self.cue_hits(phrases))


# ---- numbers ----
def _letter_after(ctx: _Ctx, i: int) -> tuple[str, int] | None:
    if i >= len(ctx.toks) or ctx.ph[i]:
        return None
    w = ctx.words[i].text.strip(" ,.;:")
    if len(w) == 1 and w.isalpha():
        return w.upper(), 1
    return _letter_at(ctx.toks, i, ctx.lang)


def _letter_before(ctx: _Ctx, i: int) -> str | None:
    if i < 0 or ctx.ph[i]:
        return None
    got = _letter_at(ctx.toks, i, ctx.lang)
    return got[0] if got and got[1] == 1 else None


def _number_entities(ctx: _Ctx, cfg: DetectConfig) -> None:
    toks = [w.text if not is_placeholder(w.text) else "|" for w in ctx.words]
    for run in find_number_runs(toks, ctx.lang):
        _classify_run(ctx, run, cfg)


def _sub_span(run: NumberRun, a: int, b: int) -> tuple[int, int]:
    cw = run.char_words or tuple([run.start] * len(run.digits))
    return cw[a], cw[b - 1]


def _classify_run(ctx: _Ctx, run: NumberRun, cfg: DetectConfig) -> None:
    d, L, s, e = run.digits, len(run.digits), run.start, run.end
    # cards: whole run, then sub-runs starting/ending on group boundaries
    if 13 <= L <= 19 and luhn_valid(d) and not (L == 18 and clabe_valid(d)):
        ctx.add(Category.CARD, s, e, Detector.LUHN, 0.99)
        return
    if L > 19 or (13 <= L <= 19):
        cw = run.char_words or tuple([s] * L)
        bounds = [0] + [k for k in range(1, L) if cw[k] != cw[k - 1]]
        for a in bounds:
            for ln in range(19, 12, -1):
                if a + ln <= L and luhn_valid(d[a:a + ln]) and (a + ln == L or cw[a + ln] != cw[a + ln - 1]):
                    ws, we = _sub_span(run, a, a + ln)
                    ctx.add(Category.CARD, ws, we, Detector.LUHN, 0.9)
    if L == 18 and clabe_valid(d):
        ctx.add(Category.ACCOUNT, s, e, Detector.CLABE, 0.99)
        return
    if L == 11 and cpf_valid(d):
        ctx.add(Category.NATIONAL_ID, s, e, Detector.CPF, 0.95)
        return
    # DNI: 8 digits + check letter after; NIE: X/Y/Z before + 7 digits + letter
    nxt = _letter_after(ctx, e + 1)
    if L == 8 and nxt and dni_valid(d + nxt[0]):
        ctx.add(Category.NATIONAL_ID, s, e + nxt[1], Detector.DNI, 0.99)
        return
    prev = _letter_before(ctx, s - 1)
    if L == 7 and nxt and prev in ("X", "Y", "Z") and nie_valid(prev + d + nxt[0]):
        ctx.add(Category.NATIONAL_ID, s - 1, e + nxt[1], Detector.NIE, 0.99)
        return
    if L == 9 and ctx.cue_before(s, _res(ctx.lang)["national"], 6):
        ctx.add(Category.NATIONAL_ID, s, e, Detector.SSN, 0.9)
        return
    R = ctx.R
    if ctx.cue_before(s, R["national"], 6) and L >= 4:
        end = e + (nxt[1] if nxt else 0)
        ctx.add(Category.NATIONAL_ID, s, end, Detector.ACCOUNT_CUE, 0.85)
        return
    if ctx.cue_before(s, R["account"], 6) and L >= 4:
        ctx.add(Category.ACCOUNT, s, e, Detector.ACCOUNT_CUE, 0.85)
        return
    if L in PHONE_LENGTHS and (ctx.cue_before(s, R["phone"], 6) or L in (9, 10)):
        ctx.add(Category.PHONE, s, e, Detector.PHONE, 0.9)
        return
    if L >= 3 and ctx.cue_before(s, R["reference"], 6):
        ctx.add(Category.REFERENCE, s, e, Detector.REFERENCE_CUE, 0.85)
        return
    if L >= cfg.digit_catch_all:
        ctx.add(Category.NUMBER, s, e, Detector.CATCH_ALL_DIGITS, 0.8)


# ---- written alphanumeric tokens (ASR often writes IDs as one token) ----
def _token_entities(ctx: _Ctx, cfg: DetectConfig) -> None:
    for i, w in enumerate(ctx.words):
        if ctx.ph[i]:
            continue
        raw = re.sub(r"[\s\-./,]", "", w.text.strip(" ,;:!?¿¡\"'()")).upper()
        if "@" in w.text and "." in w.text.split("@")[-1]:
            ctx.add(Category.EMAIL, i, i, Detector.EMAIL, 0.99)
            continue
        if not raw or raw.isdigit() or not raw.isalnum():
            continue
        digits = sum(c.isdigit() for c in raw)
        if iban_valid(raw):
            ctx.add(Category.IBAN, i, i, Detector.IBAN_MOD97, 0.99)
        elif dni_valid(raw):
            ctx.add(Category.NATIONAL_ID, i, i, Detector.DNI, 0.99)
        elif nie_valid(raw):
            ctx.add(Category.NATIONAL_ID, i, i, Detector.NIE, 0.99)
        elif curp_shape_valid(raw):
            ctx.add(Category.NATIONAL_ID, i, i, Detector.CURP, 0.95)
        elif rfc_shape_valid(raw):
            ctx.add(Category.NATIONAL_ID, i, i, Detector.RFC, 0.9)
        elif digits >= cfg.digit_catch_all or (digits >= 1 and len(raw) >= 5):
            ctx.add(Category.REFERENCE if digits < cfg.digit_catch_all else Category.NUMBER, i, i,
                    Detector.CATCH_ALL_DIGITS, 0.8)


# ---- spoken email ----
def _email(ctx: _Ctx) -> None:
    R, toks, n = ctx.R, ctx.toks, len(ctx.toks)
    for k, t in enumerate(toks):
        if t not in R["email_at"] or ctx.ph[k]:
            continue
        # domain: word (dot word)+ ending in a TLD
        j, end = k + 1, None
        while j + 2 < n + 1 and j < n and not ctx.ph[j]:
            if j + 2 < n and toks[j + 1] in R["email_dot"] and not ctx.ph[j + 2]:
                if toks[j + 2] in TLDS:
                    end = j + 2
                j += 2
                continue
            break
        if end is None:
            continue
        # local part: back over word (conn word)*
        s = k - 1
        if s < 0 or ctx.ph[s]:
            continue
        while s - 2 >= 0 and toks[s - 1] in R["email_conn"] and not ctx.ph[s - 2]:
            s -= 2
            while s - 1 >= 0 and toks[s] in R["email_conn"]:
                s -= 1
        ctx.add(Category.EMAIL, s, end, Detector.EMAIL, 0.95)


# ---- lexicon (BPO-held) ----
def _lexicon(ctx: _Ctx, lex: Lexicon) -> None:
    for items, cat in ((lex.brands, Category.BRAND), (lex.products, Category.BRAND), (lex.names, Category.NAME)):
        for item in items:
            pt = phrase_tokens(item)
            for i in find_phrase(ctx.toks, pt):
                ctx.add(cat, i, i + len(pt) - 1, Detector.LEXICON, 0.99)
            if len(pt) == 1:  # compounds and ASR joins: "movistelafibra"
                for i, t in enumerate(ctx.toks):
                    if pt[0] in t and t != pt[0] and len(pt[0]) >= 4:
                        ctx.add(cat, i, i, Detector.LEXICON, 0.9)


# ---- slots after cues: greeting brand, names ----
def _slot(ctx: _Ctx, after: int, max_words: int) -> tuple[int, int] | None:
    stop = ctx.R["stop"]
    s = after + 1
    if s >= len(ctx.toks) or ctx.ph[s] or ctx.toks[s] in stop or not ctx.toks[s]:
        return None
    e = s
    while True:
        if ends_clause(ctx.words[e].text) or e - s + 1 >= max_words:
            break
        nx = e + 1
        if nx >= len(ctx.toks) or ctx.ph[nx] or ctx.toks[nx] in stop or not ctx.toks[nx]:
            break
        e = nx
    return s, e


def _cue_slots(ctx: _Ctx) -> None:
    R = ctx.R
    if ctx.channel == Channel.AGENT:
        for _, ce in ctx.cue_hits(R["brand"]):
            sl = _slot(ctx, ce, 4)
            if sl:
                ctx.add(Category.BRAND, sl[0], sl[1], Detector.GREETING_SLOT, 0.85)
    weak = {tuple(phrase_tokens(p)) for p in R["name_weak"]}
    for p in R["name"]:
        pt = tuple(phrase_tokens(p))
        for i in find_phrase(ctx.toks, list(pt)):
            sl = _slot(ctx, i + len(pt) - 1, 3)
            if not sl:
                continue
            if pt in weak:
                # weak cues ("soy", "this is") need a capitalised word; ASR casing is the only signal here
                if not ctx.words[sl[0]].text.strip("¿¡\"'")[:1].isupper():
                    continue
            ctx.add(Category.NAME, sl[0], sl[1], Detector.NAME_CUE if pt not in weak else Detector.GREETING_SLOT,
                    0.8)


# ---- dates ----
def _is_date_tok(ctx: _Ctx, i: int, num_idx: set[int]) -> bool:
    t = ctx.toks[i]
    return (i in num_idx or t in ctx.R["months"] or t in ctx.R["date_glue"]
            or bool(re.fullmatch(r"\d{1,2}(st|nd|rd|th)?|\d{1,4}([/-]\d{1,4}){1,2}", t)))


def _dates(ctx: _Ctx) -> None:
    toks = [w.text if not is_placeholder(w.text) else "|" for w in ctx.words]
    num_idx = {k for r in find_number_runs(toks, ctx.lang) for k in range(r.start, r.end + 1)}
    n = len(ctx.toks)
    used = set()
    for _, ce in ctx.cue_hits(ctx.R["dob"]):
        j = ce + 1
        skip = 0
        while j < n and not _is_date_tok(ctx, j, num_idx) and skip < 3 and not ctx.ph[j]:
            j += 1
            skip += 1
        if j >= n or ctx.ph[j] or not _is_date_tok(ctx, j, num_idx):
            continue
        s = e = j
        while e + 1 < n and not ctx.ph[e + 1] and _is_date_tok(ctx, e + 1, num_idx) and e - s < 10:
            e += 1
        while e > s and ctx.toks[e] in ctx.R["date_glue"]:
            e -= 1
        ctx.add(Category.DOB, s, e, Detector.DOB_CUE, 0.9)
        used.update(range(s, e + 1))
    # a full date (number + month + 4-digit year) without a cue
    for i, t in enumerate(ctx.toks):
        if t in ctx.R["months"] and i not in used:
            s = i
            while s - 1 >= 0 and not ctx.ph[s - 1] and _is_date_tok(ctx, s - 1, num_idx) and i - s < 4:
                s -= 1
            e = i
            while e + 1 < n and not ctx.ph[e + 1] and _is_date_tok(ctx, e + 1, num_idx) and e - i < 6:
                e += 1
            span_runs = [r for r in find_number_runs(toks[s:e + 1], ctx.lang)]
            if any(len(r.digits) == 4 and r.digits[:2] in ("19", "20") for r in span_runs) and \
                    any(r.start < i - s for r in span_runs):
                while e > i and ctx.toks[e] in ctx.R["date_glue"]:
                    e -= 1
                while s < i and ctx.toks[s] in ctx.R["date_glue"]:
                    s += 1
                ctx.add(Category.DOB, s, e, Detector.FULL_DATE, 0.8)


# ---- addresses ----
def _addresses(ctx: _Ctx) -> None:
    R, n = ctx.R, len(ctx.toks)
    toks = [w.text if not is_placeholder(w.text) else "|" for w in ctx.words]
    num_idx = {k for r in find_number_runs(toks, ctx.lang) for k in range(r.start, r.end + 1)}
    for cs, ce in ctx.cue_hits(R["address"]):
        s, e = cs, ce
        j = ce + 1
        content = 0
        while j < n and not ctx.ph[j] and j - ce <= 8:
            t = ctx.toks[j]
            if t in R["address_stop"] and t not in R["address_keep"]:
                break
            e = j
            content += 1
            if ends_clause(ctx.words[j].text):
                break
            j += 1
        # trailing glue words are not part of the address
        while e > ce and ctx.toks[e] in R["address_keep"] and e not in num_idx:
            e -= 1
        # "123 Main Street": number just before the street name
        b = cs - 1
        while b >= 0 and not ctx.ph[b] and cs - b <= 4 and (b in num_idx or ctx.toks[b][:1].isupper()
                                                            or ctx.words[b].text[:1].isupper()):
            s = b
            b -= 1
        if content or s < cs:
            ctx.add(Category.ADDRESS, s, e, Detector.ADDRESS_CUE, 0.8)


# ---- references and accounts after a cue: alphanumeric runs mixing letters and digits ----
def _references(ctx: _Ctx) -> None:
    R, n = ctx.R, len(ctx.toks)
    for cues, cat in ((R["reference"], Category.REFERENCE), (R["account"], Category.ACCOUNT),
                      (R["national"], Category.NATIONAL_ID)):
        for _, ce in ctx.cue_hits(cues):
            j, skip = ce + 1, 0
            while j < n and ctx.toks[j] in R["lead_skip"] and skip < 4 and not ctx.ph[j]:
                j += 1
                skip += 1
            s = j
            chars, digits = 0, 0
            e = None
            toks = [w.text if not is_placeholder(w.text) else "|" for w in ctx.words]
            runs = {r.start: r for r in find_number_runs(toks[j:], ctx.lang)}
            while j < n and not ctx.ph[j]:
                if (j - s) in runs:
                    r = runs[j - s]
                    chars += len(r.digits)
                    digits += len(r.digits)
                    e = r.end + s
                    j = e + 1
                    continue
                got = _letter_after(ctx, j)
                raw = re.sub(r"[^A-Za-z0-9]", "", ctx.words[j].text)
                if got:
                    chars += 1
                    e = j + got[1] - 1
                    j += got[1]
                elif raw and any(c.isdigit() for c in raw) and raw.isalnum():
                    chars += len(raw)
                    digits += sum(c.isdigit() for c in raw)
                    e = j
                    j += 1
                else:
                    break
            if e is not None and chars >= 3 and digits >= 1:
                ctx.add(cat, s, e, Detector.REFERENCE_CUE if cat == Category.REFERENCE else Detector.ACCOUNT_CUE,
                        0.85)


# ---- spelled runs ----
def _spelled(ctx: _Ctx) -> None:
    toks = [w.text if not is_placeholder(w.text) else "|" for w in ctx.words]
    for r in find_spelled_runs(toks, ctx.lang):
        ctx.add(Category.SPELLED, r.start, r.end, Detector.SPELLED_RUN, 0.85)


# ---- confidence ----
def _widen(ctx: _Ctx, ents: list[Entity], cfg: DetectConfig) -> list[Entity]:
    out = []
    w = ctx.words
    for e in ents:
        s, t = e.word_start, e.word_end
        k = 0
        while s - 1 >= 0 and w[s - 1].prob < cfg.low_conf and not ctx.ph[s - 1] and k < cfg.low_conf_window:
            s -= 1
            k += 1
        k = 0
        while t + 1 < len(w) and w[t + 1].prob < cfg.low_conf and not ctx.ph[t + 1] and k < cfg.low_conf_window:
            t += 1
            k += 1
        if (s, t) != (e.word_start, e.word_end):
            e = Entity(e.category, e.channel, s, t, w[s].start_ms, w[t].end_ms, e.detector, e.confidence)
        out.append(e)
    return out


def _unclear(ctx: _Ctx, ents: list[Entity], cfg: DetectConfig) -> None:
    if ctx.channel != Channel.CUSTOMER:
        return
    covered = {k for e in ents for k in range(e.word_start, e.word_end + 1)}
    i, n = 0, len(ctx.words)
    while i < n:
        if ctx.words[i].prob < cfg.low_conf and i not in covered and not ctx.ph[i]:
            j = i
            while j + 1 < n and ctx.words[j + 1].prob < cfg.low_conf and j + 1 not in covered and not ctx.ph[j + 1]:
                j += 1
            if j - i + 1 >= cfg.unclear_run:
                ctx.add(Category.UNCLEAR, i, j, Detector.LOW_CONFIDENCE, 0.5)
            i = j + 1
        else:
            i += 1


def detect_channel(words: list[Word], lang: str, channel: Channel, lexicon: Lexicon,
                   cfg: DetectConfig = DetectConfig()) -> list[Entity]:
    if not words:
        return []
    ctx = _Ctx(list(words), lang, channel)
    _number_entities(ctx, cfg)
    _token_entities(ctx, cfg)
    _email(ctx)
    _lexicon(ctx, lexicon)
    _cue_slots(ctx)
    _dates(ctx)
    _addresses(ctx)
    _references(ctx)
    _spelled(ctx)
    ents = _widen(ctx, ctx.out, cfg)
    ctx.out = ents
    _unclear(ctx, ents, cfg)
    # dedupe identical spans, keep the most severe category
    best: dict[tuple[int, int], Entity] = {}
    for e in ctx.out:
        k = (e.word_start, e.word_end)
        if k not in best or SEVERITY.index(e.category) < SEVERITY.index(best[k].category):
            best[k] = e
    return sorted(best.values(), key=lambda e: (e.word_start, e.word_end))

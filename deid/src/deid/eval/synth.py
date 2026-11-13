"""Synthetic gold-set generator (EVAL-SYNTHETIC). Offline: Piper TTS from local voice files.

Every phrase is synthesised separately and concatenated, so each identifier's start and end in milliseconds is
exact by construction, not recovered by alignment. The cost is choppier prosody than real speech: one more
reason synthetic recall is an upper bound on what we have shown, not an estimate of real-world recall.

This module has its own number-to-words code on purpose: the gold set must not be produced by the code under test.
"""
from __future__ import annotations

import json
import random
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

SR = 8000

VOICES = {  # variant -> (agent voice, customer voice), paths under models/tts
    "es_ES": ("es/es_ES/davefx/medium/es_ES-davefx-medium.onnx", "es/es_ES/sharvard/medium/es_ES-sharvard-medium.onnx"),
    "es_MX": ("es/es_MX/claude/high/es_MX-claude-high.onnx", "es/es_MX/ald/medium/es_MX-ald-medium.onnx"),
    "en_US": ("en/en_US/ryan/medium/en_US-ryan-medium.onnx", "en/en_US/lessac/medium/en_US-lessac-medium.onnx"),
}
VOICE_LICENCES = {
    "es_ES-davefx-medium": "CC0", "es_ES-sharvard-medium": "CC BY 3.0", "es_MX-claude-high": "Apache-2.0",
    "es_MX-ald-medium": "Unlicense", "en_US-ryan-medium": "CC BY-NC-SA 4.0 (non-commercial: internal eval only)",
    "en_US-lessac-medium": "Blizzard 2013 Lessac licence (research: internal eval only)",
}

# ---------------- independent number words ----------------
ES_U = "cero uno dos tres cuatro cinco seis siete ocho nueve".split()
ES_T = ["diez", "once", "doce", "trece", "catorce", "quince", "dieciséis", "diecisiete", "dieciocho", "diecinueve"]
ES_V = ["veinte", "veintiuno", "veintidós", "veintitrés", "veinticuatro", "veinticinco", "veintiséis", "veintisiete",
        "veintiocho", "veintinueve"]
ES_D = {3: "treinta", 4: "cuarenta", 5: "cincuenta", 6: "sesenta", 7: "setenta", 8: "ochenta", 9: "noventa"}
EN_U = "zero one two three four five six seven eight nine".split()
EN_T = ["ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen"]
EN_D = {2: "twenty", 3: "thirty", 4: "forty", 5: "fifty", 6: "sixty", 7: "seventy", 8: "eighty", 9: "ninety"}


def two_digit(n: int, lang: str) -> str:
    if lang == "es":
        if n < 10:
            return ES_U[n]
        if n < 20:
            return ES_T[n - 10]
        if n < 30:
            return ES_V[n - 20]
        return ES_D[n // 10] + ("" if n % 10 == 0 else " y " + ES_U[n % 10])
    if n < 10:
        return EN_U[n]
    if n < 20:
        return EN_T[n - 10]
    return EN_D[n // 10] + ("" if n % 10 == 0 else " " + EN_U[n % 10])


def say_digits(d: str, lang: str, style: str, rng: random.Random) -> str:
    """style: single | pairs | mixed | filler | double"""
    U = ES_U if lang == "es" else EN_U
    if style == "pairs":
        parts, i = [], 0
        while i < len(d):
            if d[i] == "0" or i == len(d) - 1:
                parts.append(U[int(d[i])])
                i += 1
            else:
                parts.append(two_digit(int(d[i:i + 2]), lang))
                i += 2
        return ", ".join(parts)
    if style == "double":
        out, i = [], 0
        dbl = "doble" if lang == "es" else "double"
        while i < len(d):
            if i + 1 < len(d) and d[i] == d[i + 1]:
                out.append(f"{dbl} {U[int(d[i])]}")
                i += 2
            else:
                out.append(U[int(d[i])])
                i += 1
        return " ".join(out)
    words = [U[int(c)] for c in d]
    if style == "filler":
        f = "eh" if lang == "es" else "um"
        k = rng.randrange(2, len(words) - 1)
        words.insert(k, f + ",")
    if style == "mixed":  # groups with commas, as people dictate
        return ", ".join(" ".join(words[i:i + 3]) for i in range(0, len(words), 3))
    return " ".join(words)


def say_year(y: int, lang: str) -> str:
    if lang == "es":
        h = {19: "mil novecientos", 20: "dos mil"}[y // 100]
        r = y % 100
        return h + ("" if r == 0 else " " + two_digit(r, lang))
    return two_digit(y // 100, lang) + " " + (two_digit(y % 100, lang) if y % 100 >= 10 else
                                              ("hundred" if y % 100 == 0 else "oh " + EN_U[y % 100]))


# ---------------- identifier generators ----------------
ES_FIRST = ["Lucía", "Martín", "Carmen", "Javier", "Elena", "Pablo", "Rocío", "Andrés", "Marta", "Sergio", "Beatriz",
            "Hugo", "Inés", "Diego", "Nuria", "Álvaro", "Ximena", "Rodrigo", "Guadalupe", "Fernanda"]
ES_LAST = ["García", "Fernández", "Moreno", "Navarro", "Iglesias", "Ortega", "Delgado", "Castro", "Romero", "Herrera",
           "Medina", "Vargas", "Cabrera", "Domínguez", "Salazar", "Quintero"]
EN_FIRST = ["Emily", "Jacob", "Olivia", "Michael", "Hannah", "Tyler", "Megan", "Brandon", "Ashley", "Kevin",
            "Rachel", "Derek", "Natalie", "Marcus", "Brooke"]
EN_LAST = ["Whitaker", "Henderson", "Collins", "Brooks", "Sullivan", "Patterson", "Hughes", "Fletcher", "Morrison",
           "Gallagher", "Reynolds", "Caldwell"]
BRAND_A = ["Zen", "Movi", "Bright", "Nova", "Teli", "Alba", "Kora", "Vela", "Lumi", "Orba"]
BRAND_B = ["trix", "stela", "wave", "link", "cora", "via", "net", "fon", "tel", "mar"]
BRAND_C_ES = ["Energía", "Móvil", "Seguros", "Hogar", "Fibra", ""]
BRAND_C_EN = ["Mobile", "Energy", "Insurance", "Home", "Wireless", ""]
ES_LETTERS = {"A": "a", "B": "be", "C": "ce", "D": "de", "E": "e", "F": "efe", "G": "ge", "H": "hache", "I": "i",
              "J": "jota", "K": "ka", "L": "ele", "M": "eme", "N": "ene", "O": "o", "P": "pe", "Q": "cu", "R": "erre",
              "S": "ese", "T": "te", "U": "u", "V": "uve", "W": "uve doble", "X": "equis", "Y": "i griega",
              "Z": "zeta", "Ñ": "eñe"}
EN_LETTERS = {c: c for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"}
NATO = {"A": "alpha", "B": "bravo", "C": "charlie", "D": "delta", "E": "echo", "F": "foxtrot", "G": "golf",
        "H": "hotel", "I": "india", "J": "juliet", "K": "kilo", "L": "lima", "M": "mike", "N": "november",
        "O": "oscar", "P": "papa", "R": "romeo", "S": "sierra", "T": "tango", "U": "uniform", "V": "victor",
        "W": "whiskey", "Y": "yankee", "Z": "zulu"}
ES_MONTHS = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
             "noviembre", "diciembre"]
EN_MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
             "November", "December"]
ES_STREETS = ["calle Alcalá", "avenida de la Constitución", "calle Mayor", "paseo de Gracia", "avenida Reforma",
              "calle Insurgentes", "colonia Roma Norte, calle Durango"]
EN_STREETS = ["Maple Street", "Oak Avenue", "Lincoln Road", "Sunset Boulevard", "Cedar Lane", "Park Drive"]
DNI_L = "TRWAGMYFPDXBNJZSQVHLCKE"


def _luhn_complete(prefix: str, length: int, rng: random.Random) -> str:
    body = prefix + "".join(str(rng.randrange(10)) for _ in range(length - len(prefix) - 1))
    for c in "0123456789":
        s = body + c
        t = 0
        for i, ch in enumerate(reversed(s)):
            d = int(ch) * (2 if i % 2 else 1)
            t += d - 9 if d > 9 else d
        if t % 10 == 0:
            return s
    raise AssertionError


def _clabe(rng: random.Random) -> str:
    b = "".join(str(rng.randrange(10)) for _ in range(17))
    w = [3, 7, 1] * 6
    s = sum((int(b[i]) * w[i]) % 10 for i in range(17))
    return b + str((10 - s % 10) % 10)


def spell(word: str, lang: str, rng: random.Random) -> str:
    from unicodedata import normalize
    letters = [c for c in normalize("NFC", word.upper()) if c.isalpha()]
    letters = ["".join(ch for ch in normalize("NFKD", c) if ch.isalpha() and ord(ch) < 128) or c for c in letters]
    if lang == "es":
        return ", ".join(ES_LETTERS.get(c, c.lower()) for c in letters)
    if rng.random() < 0.4:
        return ", ".join(f"{c} as in {NATO[c]}" if c in NATO and i == 0 else c for i, c in enumerate(letters))
    return ", ".join(letters)


# ---------------- call model ----------------
@dataclass
class Seg:
    text: str
    category: str | None = None  # gold entity category, or None for carrier text


@dataclass
class Turn:
    channel: str  # agent | customer
    segs: list[Seg]
    overlap_ms: int = 0  # start this many ms before the previous turn ends (crosstalk)


@dataclass
class GoldEntity:
    category: str
    channel: str
    start_ms: int
    end_ms: int
    text: str
    digits: str = ""


@dataclass
class GoldCall:
    call_key: str
    variant: str
    lang: str
    expected_drop: str | None  # None = keep; else pci | special_category | minor | vulnerable
    hard_cases: list[str]
    entities: list[GoldEntity] = field(default_factory=list)
    duration_ms: int = 0


def build_script(variant: str, rng: random.Random, drop: str | None) -> tuple[list[Turn], list[str]]:
    es = variant.startswith("es")
    lang = "es" if es else "en"
    first, last = rng.choice(ES_FIRST if es else EN_FIRST), rng.choice(ES_LAST if es else EN_LAST)
    agent = rng.choice(ES_FIRST if es else EN_FIRST)
    brand = rng.choice(BRAND_A) + rng.choice(BRAND_B)
    tail = rng.choice(BRAND_C_ES if es else BRAND_C_EN)
    brand_full = f"{brand} {tail}".strip()
    hard: list[str] = ["brand_in_greeting"]
    T: list[Turn] = []

    def style():
        return rng.choice(["single", "pairs", "mixed", "filler", "double"])

    if rng.random() < 0.3:
        hard.append("ivr_prompt")
        T.append(Turn("agent", [Seg("Bienvenido a" if es else "Welcome to"), Seg(brand_full, "BRAND"),
                                Seg("Para facturación, pulse uno. Para averías, pulse dos." if es else
                                    "For billing, press one. For technical support, press two.")]))
    if rng.random() < 0.3:
        hard.append("hold_music")
        T.append(Turn("agent", [Seg("<HOLD>")]))
    greet = rng.choice(["Gracias por llamar a", "Bienvenido a"] if es else ["Thank you for calling", "Welcome to"])
    T.append(Turn("agent", [Seg(greet), Seg(brand_full + ",", "BRAND"),
                            Seg("le atiende" if es else "my name is"), Seg(agent + ",", "NAME"),
                            Seg("¿en qué puedo ayudarle?" if es else "how can I help you today?")]))
    T.append(Turn("customer", [Seg("Hola, buenos días. Me llamo" if es else "Hi, good morning. My name is"),
                               Seg(f"{first} {last}.", "NAME")]))
    slots = ["phone", "email", "dob", "order", "address", "spelled", "id"]
    rng.shuffle(slots)
    for slot in slots[:rng.randint(4, 6)]:
        if slot == "phone":
            if variant == "es_ES":
                num = "6" + "".join(str(rng.randrange(10)) for _ in range(8))
            else:
                num = rng.choice(["55", "33", "81"] if variant == "es_MX" else ["212", "415", "312"])
                num += "".join(str(rng.randrange(10)) for _ in range(10 - len(num)))
            st = style()
            hard.append(f"digits_{st}")
            T.append(Turn("agent", [Seg("¿Me da un teléfono de contacto?" if es else "Can I get a contact number?")]))
            T.append(Turn("customer", [Seg("Sí, es el" if es else "Sure, it's"), Seg(say_digits(num, lang, st, rng),
                                                                                      "PHONE")]))
            if rng.random() < 0.4:
                hard.append("agent_readback")
                T.append(Turn("agent", [Seg("Le confirmo:" if es else "Let me read that back:"),
                                        Seg(say_digits(num, lang, "single", rng), "PHONE")]))
        elif slot == "email":
            user = rng.choice([first, first + " " + ("punto" if es else "dot") + " " + last])
            dom = rng.choice(["gmail", "hotmail", "outlook", "yahoo"])
            at, dot = ("arroba", "punto") if es else ("at", "dot")
            T.append(Turn("agent", [Seg("¿Y su correo electrónico?" if es else "And your email address?")]))
            T.append(Turn("customer", [Seg("Es" if es else "It's"),
                                       Seg(f"{user.lower()} {at} {dom} {dot} com", "EMAIL")]))
        elif slot == "dob":
            d, m, y = rng.randint(1, 28), rng.randrange(12), rng.randint(1950, 2004)
            txt = (f"el {two_digit(d, 'es')} de {ES_MONTHS[m]} de {say_year(y, 'es')}" if es else
                   f"{EN_MONTHS[m]} {two_digit(d, 'en')}, {say_year(y, 'en')}")
            T.append(Turn("agent", [Seg("¿Su fecha de nacimiento?" if es else "And your date of birth?")]))
            T.append(Turn("customer", [Seg("Nací" if es else "It's"), Seg(txt, "DOB")]))
        elif slot == "order":
            code = "".join(rng.choice("ABCDEFGHJKLMNPRSTUVXZ") for _ in range(2)) + \
                "".join(str(rng.randrange(10)) for _ in range(rng.randint(4, 6)))
            spoken = ", ".join((ES_LETTERS[c] if es else c) if c.isalpha() else (ES_U if es else EN_U)[int(c)]
                               for c in code)
            T.append(Turn("agent", [Seg("¿Tiene el número de pedido?" if es else "Do you have the order number?")]))
            T.append(Turn("customer", [Seg("Sí, el pedido es" if es else "Yes, the order number is"),
                                       Seg(spoken, "REFERENCE")]))
        elif slot == "address":
            street = rng.choice(ES_STREETS if es else EN_STREETS)
            n = rng.randint(2, 240)
            txt = (f"{street}, número {two_digit(n, 'es') if n < 100 else say_digits(str(n), 'es', 'single', rng)}"
                   if es else f"{say_digits(str(n), 'en', 'single', rng)} {street}")
            T.append(Turn("agent", [Seg("¿Me confirma la dirección?" if es else "Can you confirm your address?")]))
            T.append(Turn("customer", [Seg("Vivo en la" if es and street.startswith("calle") else
                                           ("Vivo en" if es else "I live at")), Seg(txt, "ADDRESS")]))
        elif slot == "spelled":
            hard.append("spelled_name")
            T.append(Turn("agent", [Seg("¿Me deletrea el apellido?" if es else "Could you spell your last name?")]))
            T.append(Turn("customer", [Seg("Claro," if es else "Sure,"), Seg(spell(last, lang, rng), "SPELLED")]))
        elif slot == "id":
            T.append(Turn("agent", [Seg({"es_ES": "¿Me indica su DNI?", "es_MX": "¿Me da su cuenta CLABE para el "
                                         "reembolso?", "en_US": "Can I have the last four of your social?"}[variant])]))
            if variant == "es_ES":
                n = rng.randrange(10_000_000, 99_999_999)
                txt = say_digits(str(n), "es", rng.choice(["single", "mixed"]), rng) + ", " + \
                    ES_LETTERS[DNI_L[n % 23]]
                T.append(Turn("customer", [Seg("Sí, es el" if True else ""), Seg(txt, "NATIONAL_ID")]))
            elif variant == "es_MX":
                T.append(Turn("customer", [Seg("Sí, es la"), Seg(say_digits(_clabe(rng), "es", "single", rng),
                                                                 "ACCOUNT")]))
            else:
                T.append(Turn("customer", [Seg("Yeah, it's"), Seg(say_digits(
                    "".join(str(rng.randrange(10)) for _ in range(4)), "en", "single", rng), "NATIONAL_ID")]))
    if rng.random() < 0.25:
        hard.append("crosstalk")
        T.append(Turn("agent", [Seg("Perfecto, déjeme revisar el sistema un momento." if es else
                                    "Perfect, let me check the system for a moment.")]))
        T.append(Turn("customer", [Seg("Vale, gracias" if es else "Okay, thanks"), Seg(first + ".", "NAME")],
                      overlap_ms=900))
    if es and rng.random() < 0.2:
        hard.append("code_switching")
        T.append(Turn("customer", [Seg("O sea, the bill came twice, sabe? Mi otro correo es"),
                                   Seg(f"{first.lower()} at outlook dot com", "EMAIL")]))
    # the reason for the call (and the exclusion, if any)
    reason = {
        None: ["Quería cambiar mi tarifa a una más barata." if es else "I wanted to switch to a cheaper plan.",
               "Ya me llegó la tarjeta nueva, gracias." if es else "The new card arrived, thanks."],
        "special_category": ["Es que estoy con quimioterapia y no puedo ir a la tienda." if es else
                             "I'm going through chemotherapy and can't get to the store."],
        "minor": ["La línea es de mi hija, tiene doce años." if es else
                  "The line is for my daughter, she is twelve years old."],
        "vulnerable": ["Me he quedado sin trabajo y no puedo pagar la factura." if es else
                       "I lost my job and I can't pay the bill."],
    }
    if drop == "pci":
        card = _luhn_complete(rng.choice(["4", "51", "37"]), 16, rng)
        T.append(Turn("agent", [Seg("¿Con qué tarjeta quiere pagar?" if es else "Which card would you like to use?")]))
        T.append(Turn("customer", [Seg("Con esta:" if es else "This one:"),
                                   Seg(say_digits(card, lang, rng.choice(["single", "mixed"]), rng), "CARD")]))
    else:
        T.append(Turn("customer", [Seg(rng.choice(reason[drop]))]))
    T.append(Turn("agent", [Seg("Muy bien," if es else "Alright,"), Seg(first + ",", "NAME"),
                            Seg("gracias por llamar a" if es else "thank you for calling"), Seg(brand_full + ".",
                                                                                                "BRAND")]))
    return T, hard


class Synth:
    def __init__(self, tts_root: Path):
        from piper import PiperVoice
        self._PV = PiperVoice
        self.root = Path(tts_root)
        self.cache: dict[str, object] = {}

    def voice(self, rel: str):
        if rel not in self.cache:
            self.cache[rel] = self._PV.load(str(self.root / rel))
        return self.cache[rel]

    def say(self, rel: str, text: str, rate: float = 1.0, speaker: int | None = None) -> np.ndarray:
        """Deterministic: Piper's sampling noise is set to zero; variety comes from rate and speaker, which the
        caller draws from the seeded RNG."""
        from piper.config import SynthesisConfig
        v = self.voice(rel)
        n_spk = getattr(v.config, "num_speakers", 1) or 1
        cfg = SynthesisConfig(speaker_id=(speaker % n_spk) if (speaker is not None and n_spk > 1) else None,
                              length_scale=rate, noise_scale=0.0, noise_w_scale=0.0)
        chunks = list(v.synthesize(text, syn_config=cfg))
        x = np.concatenate([c.audio_float_array for c in chunks]) if chunks else np.zeros(1, np.float32)
        return telephony(x, chunks[0].sample_rate if chunks else SR)


def telephony(x: np.ndarray, sr: int) -> np.ndarray:
    """Band-limit to 300-3400 Hz, resample to 8 kHz, G.711 mu-law round trip."""
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / sr)
    X[(f < 300) | (f > 3400)] = 0
    y = np.fft.irfft(X, len(x))
    n = int(len(y) * SR / sr)
    y = np.interp(np.arange(n) * sr / SR, np.arange(len(y)), y)
    y = y / (np.max(np.abs(y)) + 1e-9) * 0.5
    mu = 255.0
    enc = np.sign(y) * np.log1p(mu * np.abs(y)) / np.log1p(mu)
    enc = np.round(enc * 127) / 127
    return (np.sign(enc) * (np.power(1 + mu, np.abs(enc)) - 1) / mu).astype(np.float32)


def speech_bounds(x: np.ndarray, frame_ms: int = 10, rel_db: float = -35.0) -> tuple[int, int]:
    """(start_ms, end_ms) of the part of a synthesised phrase louder than rel_db below its peak frame."""
    f = SR * frame_ms // 1000
    n = len(x) // f
    if n == 0:
        return 0, len(x) * 1000 // SR
    e = np.sqrt(np.mean(x[:n * f].reshape(n, f) ** 2, axis=1)) + 1e-9
    loud = np.where(20 * np.log10(e / e.max()) > rel_db)[0]
    if len(loud) == 0:
        return 0, len(x) * 1000 // SR
    return int(loud[0] * frame_ms), int((loud[-1] + 1) * frame_ms)


def hold_music(ms: int, rng: random.Random) -> np.ndarray:
    t = np.arange(int(SR * ms / 1000)) / SR
    notes = [440, 554, 659, 880]
    seg = np.zeros_like(t)
    step = len(t) // 8 or 1
    for i in range(8):
        f = rng.choice(notes)
        seg[i * step:(i + 1) * step] = 0.15 * np.sin(2 * np.pi * f * t[i * step:(i + 1) * step])
    return seg.astype(np.float32)


def render(synth: Synth, variant: str, turns: list[Turn], rng: random.Random, snr_db: float):
    va, vc = VOICES[variant]
    chans = {"agent": [], "customer": []}
    rate = {"agent": rng.uniform(0.9, 1.1), "customer": rng.uniform(0.9, 1.2)}
    spk = {"agent": rng.randrange(2), "customer": rng.randrange(2)}
    cursor = 300
    ents: list[GoldEntity] = []
    placed: list[tuple[str, int, np.ndarray]] = []
    for turn in turns:
        start = max(200, cursor - turn.overlap_ms)
        t = start
        for seg in turn.segs:
            if seg.text == "<HOLD>":
                x = hold_music(rng.randint(2500, 4500), rng)
            else:
                x = synth.say(va if turn.channel == "agent" else vc, seg.text, rate[turn.channel],
                              spk[turn.channel])
            placed.append((turn.channel, t, x))
            dur = len(x) * 1000 // SR
            if seg.category:
                a, b = speech_bounds(x)  # gold marks speech, not the TTS's leading/trailing silence
                ents.append(GoldEntity(seg.category, turn.channel, t + a, t + b, seg.text))
            t += dur + 60
        cursor = t + rng.randint(250, 600)
    total = cursor + 500
    out = {}
    for ch in chans:
        y = np.zeros(int(total * SR / 1000) + SR, dtype=np.float32)
        for c, t, x in placed:
            if c == ch:
                a = int(t * SR / 1000)
                y[a:a + len(x)] += x
        sig = np.sqrt(np.mean(y[y != 0] ** 2)) if np.any(y) else 0.1
        y += rng_noise(len(y), sig / (10 ** (snr_db / 20)), rng)
        out[ch] = np.clip(y, -1, 1)
    return out["agent"], out["customer"], ents, total


def rng_noise(n: int, sd: float, rng: random.Random) -> np.ndarray:
    return np.random.default_rng(rng.randrange(2 ** 32)).normal(0, sd, n).astype(np.float32)


def generate(tts_root: Path, variants: list[str], per_variant: int, seed: int, drop_share: float = 0.35):
    """Yields (GoldCall, agent, customer). Deterministic from the seed."""
    rng = random.Random(seed)
    synth = Synth(tts_root)
    drops = ["pci", "special_category", "minor", "vulnerable"]
    for variant in variants:
        for i in range(per_variant):
            drop = drops[i % 4] if rng.random() < drop_share else None
            turns, hard = build_script(variant, rng, drop)
            a, c, ents, dur = render(synth, variant, turns, rng, snr_db=rng.choice([30, 20, 15]))
            gc = GoldCall(f"{variant}-{i:04d}", variant, "es" if variant.startswith("es") else "en", drop,
                          sorted(set(hard)), ents, dur)
            yield gc, a, c


def gold_to_json(gc: GoldCall) -> str:
    return json.dumps(asdict(gc), ensure_ascii=False)

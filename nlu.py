"""Understanding a shopping request, word by word: the language side of the agent.

Everything here is plain Python (standard library only) and knows nothing about products:
it turns the words heard so far into a *reading* -- the filters the shopper seems to be asking
for.  The catalogue is only used to build a vocabulary (which brands, categories, colours and
sizes exist); it is never used to look a product up.

    >>> read("black Pacevo joggers size nine under four thousand".split()).filters
    {'category': 'track pants', 'colour': 'black', 'size': '9', 'brand': 'Pacevo', 'max_price': 4000}

Reading rule of thumb: every mention of a slot (category, colour, size, brand, max_price) is
recorded in order, and the *last* mention wins.  That one rule covers corrections ("black, no
wait, white"), changed minds ("Horavo, matlab Tikkra") and late constraints ("oh, and in blue").
"""
import re
from dataclasses import dataclass, field

SLOTS = ("category", "colour", "size", "brand", "max_price")

# --------------------------------------------------------------------------- vocabulary
# Category phrases, keyed by the catalogue's own category name.  Plurals are added automatically.
CATEGORY_PHRASES = {
    "running shoes": ["running shoes", "jogging shoes", "runners", "running sneakers",
                      "running trainers", "sports shoes", "sport shoes", "jogging sneakers"],
    "sneakers": ["sneakers", "casual shoes", "casual sneakers", "trainers", "kicks"],
    "sandals": ["sandals", "slides", "floaters", "chappals", "slippers", "flip flops"],
    "track pants": ["track pants", "trackpants", "joggers", "lowers", "track bottoms", "sweatpants"],
    "jeans": ["jeans", "denims", "denim", "pair of jeans"],
    "hoodies": ["hoodies", "hooded sweatshirt", "sweatshirts", "hooded sweatshirts", "sweatshirt"],
    "t-shirts": ["t-shirts", "tshirts", "t shirts", "tees", "tee shirts", "tee"],
    "shirts": ["shirts"],
    "kurtas": ["kurtas", "kurtis", "kurti"],
    "dresses": ["dresses", "frocks", "gowns"],
    "jackets": ["jackets", "coats", "windcheaters", "blazers"],
    "backpacks": ["backpacks", "bag packs", "bagpacks", "bag pack", "rucksacks", "bags"],
    "caps": ["caps", "hats", "baseball caps"],
    "headphones": ["headphones", "headsets", "earphones", "earbuds", "over-ear"],
    "watches": ["watches", "wrist watches", "wristwatches"],
    "wallets": ["wallets", "purses"],
}

COLOUR_PHRASES = {
    "grey": ["gray", "charcoal", "slate"],
    "navy": ["navy blue", "dark blue"],
    "olive": ["olive green"],
    "gold": ["golden"],
    "beige": ["cream", "khaki", "off white", "off-white"],
    "black": ["kaala", "kala", "kali"],
    "red": ["laal", "lal"],
    "pink": ["gulabi"],
    "brown": ["bhura", "bhoora"],
    "blue": ["neela", "neeli", "nila"],
    "white": ["safed", "safaid"],
    "green": ["hara", "hari"],
    "yellow": ["peela", "peeli"],
    "silver": ["chandi"],
}

SIZE_PHRASES = {
    "XXL": ["xxl", "2xl", "double xl", "double extra large", "extra extra large", "xx large", "xx-large"],
    "XL": ["xl", "extra large", "x large", "x-large"],
    "XS": ["xs", "extra small", "x small", "x-small"],
    "S": ["s", "small"],
    "M": ["m", "medium"],
    "L": ["l", "large"],
}

# --------------------------------------------------------------------------- numbers
_UNITS = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
          "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
          "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
          "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
          "seventy": 70, "eighty": 80, "ninety": 90,
          # Hindi (romanised)
          "ek": 1, "do": 2, "teen": 3, "chaar": 4, "char": 4, "paanch": 5, "panch": 5, "chhe": 6,
          "chhah": 6, "che": 6, "saat": 7, "aath": 8, "nau": 9, "das": 10, "gyarah": 11,
          "barah": 12, "terah": 13, "chaudah": 14, "pandrah": 15, "solah": 16, "satrah": 17,
          "atharah": 18, "unnis": 19, "bees": 20, "tees": 30, "chaalis": 40, "pachaas": 50,
          "dhai": 2.5, "dedh": 1.5}
_HUNDRED = {"hundred", "sau"}
_THOUSAND = {"thousand", "hazaar", "hajar", "hazar"}
_HALF = {"saadhe", "sadhe"}
# Hindi words that are also common English words: only numbers when a hundred/thousand follows.
_AMBIGUOUS = {"ek", "do", "one", "tees"}
_NUMBER_WORDS = set(_UNITS) | _HUNDRED | _THOUSAND | _HALF
_DIGITS = re.compile(r"^\d+(?:,\d{3})*(?:\.\d+)?$")
_KILO = re.compile(r"^(\d+(?:\.\d+)?)k$")


def number_value(tokens):
    """The value of a run of number tokens: 'thirty seven hundred' -> 3700, 'saadhe teen hazaar' -> 3500."""
    total, current, half = 0, 0, False
    for t in tokens:
        if t in _HALF:
            half = True
        elif t in _HUNDRED:
            current = ((current or 1) + (0.5 if half else 0)) * 100
            half = False
        elif t in _THOUSAND:
            total += ((current or 1) + (0.5 if half else 0)) * 1000
            current, half = 0, False
        elif t in _UNITS:
            current += _UNITS[t]
        elif _DIGITS.match(t):
            current += float(t.replace(",", ""))
    value = total + current
    return int(value) if value == int(value) else value


def _number_variants(phrase):
    """Singular/plural spellings of a phrase's last word: 'watches' <-> 'watch', 'dresses' -> 'dress'."""
    if phrase.endswith("es"):
        return [phrase[:-2], phrase[:-1]]
    if phrase.endswith("s"):
        return [phrase[:-1]]
    return [phrase + "s"]


def _is_number_token(t):
    return t in _NUMBER_WORDS or bool(_DIGITS.match(t))


# --------------------------------------------------------------------------- tokens
_TAIL_PUNCT = ".,!?;:\"'()[]{}"


def normalise(word):
    """Lowercase, drop currency signs and edge punctuation: 'Rs.' -> 'rs', '₹1,500,' -> '1,500'."""
    w = word.lower().replace("₹", " ").replace("’", "'").strip().strip(_TAIL_PUNCT).strip()
    return w.replace(" ", "")


# Words that signal "I am changing something I said" (used for bare-number sizes and hedging).
CORRECTION_WORDS = {"no", "wait", "oops", "sorry", "actually", "rather", "meant", "mean", "matlab",
                    "nahi", "nahin", "change", "make", "that", "um", "uh", "hmm", "or", "instead"}
SIZE_CONTEXT = {"size", "uk", "waist", "number", "no.", "wala", "wali"}


@dataclass
class Reading:
    """What the words so far seem to ask for."""
    filters: dict
    mentions: list = field(default_factory=list)   # (token position, slot, value), in order
    tokens: list = field(default_factory=list)

    def last_change(self):
        """Token position of the most recent mention (the last word that changed a slot)."""
        return self.mentions[-1][0] if self.mentions else -1

    def filled(self):
        return sum(v is not None for v in self.filters.values())


class Lexicon:
    """Phrase tables built from the catalogue's vocabulary plus the synonym lists above."""

    def __init__(self, catalogue):
        cats = {r["category"].lower() for r in catalogue}
        colours = {r["colour"].lower() for r in catalogue}
        brands = {r["brand"] for r in catalogue}
        self.sizes = {r["size"] for r in catalogue if r["size"]}
        self.phrases = {}                                    # tuple(tokens) -> (slot, value)
        for cat in cats:
            for phrase in [cat] + CATEGORY_PHRASES.get(cat, []):
                self._add(phrase, "category", cat)
                for variant in _number_variants(phrase):
                    self._add(variant, "category", cat)
        if "t-shirts" in cats:
            self._add("t shirt", "category", "t-shirts")
        for colour in colours:
            self._add(colour, "colour", colour)
            for phrase in COLOUR_PHRASES.get(colour, []):
                self._add(phrase, "colour", colour)
        for brand in brands:
            self._add(brand.lower(), "brand", brand)
        for size, phrases in SIZE_PHRASES.items():
            if size in self.sizes:
                for phrase in phrases:
                    self._add(phrase, "size", size)
        self.longest = max(len(k) for k in self.phrases)

    def _add(self, phrase, slot, value):
        self.phrases[tuple(phrase.lower().split())] = (slot, value)


def read(words, lexicon=None):
    """Read the words so far.  `lexicon` defaults to the one built from the shipped catalogue."""
    lexicon = lexicon or default_lexicon()
    tokens = [normalise(w) for w in words]
    # A comma or full stop after a word ends any number being spoken ("4000, das number").
    breaks = {i for i, w in enumerate(words) if w.rstrip()[-1:] in ".,;:!?"}
    mentions = []
    i = 0
    while i < len(tokens):
        t = tokens[i]
        # 1. multi-word phrases: categories, colours, brands, letter sizes
        hit = None
        for n in range(min(lexicon.longest, len(tokens) - i), 0, -1):
            hit = lexicon.phrases.get(tuple(tokens[i:i + n]))
            if hit:
                mentions.append((i + n - 1, *hit))
                i += n
                break
        if hit:
            continue
        # 2. prices written "2k", "1.5k"
        kilo = _KILO.match(t)
        if kilo:
            mentions.append((i, "max_price", int(round(float(kilo.group(1)) * 1000))))
            i += 1
            continue
        # 3. numbers: a maximal run of number tokens ("thirty seven hundred", "saadhe teen hazaar")
        if _is_number_token(t):
            j = i + 1
            while j < len(tokens) and _is_number_token(tokens[j]) and (j - 1) not in breaks:
                j += 1
            run = tokens[i:j]
            # Hindi/English homographs ("ek", "do", "one") only count before a hundred/thousand.
            while run and run[0] in _AMBIGUOUS and not (len(run) > 1 and run[1] in _HUNDRED | _THOUSAND):
                run, i = run[1:], i + 1
            if run:
                _classify_number(run, i, tokens, lexicon, mentions)
            i = j
            continue
        i += 1
    filters = dict.fromkeys(SLOTS)
    for _, slot, value in mentions:
        filters[slot] = value
    return Reading(filters, mentions, tokens)


def _classify_number(run, start, tokens, lexicon, mentions):
    """A number is a size when a size word sits next to it (or a correction just happened); else a price."""
    end = start + len(run)
    value = number_value(run)
    before = tokens[max(0, start - 3):start]
    nxt = tokens[end] if end < len(tokens) else ""
    if value >= 100:
        mentions.append((end - 1, "max_price", int(value)))
        return
    size = str(value)
    if size not in lexicon.sizes:
        return
    near_size_word = (before[-1:] and before[-1] in SIZE_CONTEXT) or nxt in SIZE_CONTEXT
    after_correction = any(b in CORRECTION_WORDS for b in before)
    if near_size_word or after_correction:
        mentions.append((end - 1, "size", size))


_DEFAULT = None


def default_lexicon():
    """The lexicon for the catalogue shipped next to this file (built once)."""
    global _DEFAULT
    if _DEFAULT is None:
        from search import load_catalogue
        _DEFAULT = Lexicon(load_catalogue())
    return _DEFAULT

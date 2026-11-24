"""Unit tests for the reader.  Run:  python -m unittest tests.test_nlu

The phrasings below are NOT taken from dev.jsonl: they probe wording the hidden test set may use.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nlu import number_value, read  # noqa: E402


def filters(text):
    return {k: v for k, v in read(text.split()).filters.items() if v is not None}


class NumberWords(unittest.TestCase):
    def test_english(self):
        for words, value in [("two thousand", 2000), ("forty five hundred", 4500),
                             ("thirty seven hundred", 3700), ("one thousand five hundred", 1500),
                             ("six thousand five hundred", 6500), ("fifteen hundred", 1500),
                             ("seventy five hundred", 7500), ("twenty three hundred", 2300),
                             ("one thousand one hundred", 1100), ("nine", 9)]:
            self.assertEqual(number_value(words.split()), value, words)

    def test_hindi(self):
        for words, value in [("pandrah sau", 1500), ("dhai hazaar", 2500), ("saadhe teen hazaar", 3500),
                             ("satrah sau", 1700), ("paanch hazaar", 5000), ("ek hazaar", 1000),
                             ("do hazaar", 2000), ("dedh hazaar", 1500), ("das", 10)]:
            self.assertEqual(number_value(words.split()), value, words)


class Reading(unittest.TestCase):
    def check(self, text, **want):
        got = filters(text)
        self.assertEqual(got, want, text)

    def test_plain(self):
        self.check("black Pacevo running shoes size nine under four thousand please",
                   category="running shoes", colour="black", brand="Pacevo", size="9", max_price=4000)

    def test_synonyms(self):
        self.check("charcoal joggers waist 32 under 1.2k", category="track pants", colour="grey",
                   size="32", max_price=1200)
        self.check("golden wrist watch Horavo", category="watches", colour="gold", brand="Horavo")
        self.check("a pair of denims in navy blue, 34 waist", category="jeans", colour="navy", size="34")
        self.check("olive green hooded sweatshirt double XL", category="hoodies", colour="olive", size="XXL")
        self.check("Carrafel bag pack in red", category="backpacks", colour="red", brand="Carrafel")
        self.check("Kesar Loom kurta M", category="kurtas", brand="Kesar Loom", size="M")

    def test_prices(self):
        self.check("cap budget Rs. 450", category="caps", max_price=450)
        self.check("cap within ₹1,250", category="caps", max_price=1250)
        self.check("cap up to 0.6k", category="caps", max_price=600)
        self.check("cap under twenty five hundred", category="caps", max_price=2500)

    def test_corrections_last_mention_wins(self):
        self.check("white dress L, oops, actually M", category="dresses", colour="white", size="M")
        self.check("black no wait white sneakers", category="sneakers", colour="white")
        self.check("Wavlo, sorry, Sonquil headset", category="headphones", brand="Sonquil")
        self.check("size 8 actually six slides", category="sandals", size="6")

    def test_late_constraints(self):
        self.check("grey jacket size L, oh and from Zentrail", category="jackets", colour="grey",
                   size="L", brand="Zentrail")

    def test_hinglish(self):
        self.check("mujhe neela Pacevo sneakers das number chahiye", category="sneakers", colour="blue",
                   brand="Pacevo", size="10")
        self.check("kaala wallet Ledgerly 800 tak", category="wallets", colour="black", brand="Ledgerly",
                   max_price=800)

    def test_ordinary_words_are_not_numbers(self):
        # "do" and "one" are English words too: no sizes or prices out of them
        self.check("do you have one red cap", category="caps", colour="red")

    def test_number_stops_at_punctuation(self):
        self.check("shirt under four thousand five hundred. one more thing, size M", category="shirts",
                   size="M", max_price=4500)


if __name__ == "__main__":
    unittest.main()

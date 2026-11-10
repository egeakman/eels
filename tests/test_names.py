from eels.names import NameCorrector

NAMES = ["Lysandros Nikolaou", "PyIstanbul", "Celery", "Ultralytics", "Şuayip Üzülmez", "Django", "Raspberry Pi Pico"]


def test_fixes_near_exact_names_keeping_suffix_and_punctuation():
    c = NameCorrector(NAMES)
    assert c.correct("we start with Lysandris Nikolaou.")[0] == "we start with Lysandros Nikolaou."
    assert c.correct("Ben Py İstanbul üyelerinden biriyim.")[0] == "Ben PyIstanbul üyelerinden biriyim."
    assert c.correct("Ultralitics'in modeli")[0] == "Ultralytics'in modeli"
    assert c.correct("Nikolau said")[0] == "Nikolaou said"


def test_leaves_ordinary_words_alone():
    c = NameCorrector(NAMES)
    for text in (
        "seler dünyasında hiçbir şey değişmedi",
        "bir seler var",
        "Django is great",
        "we celebrate today",
        "Raspberry jam",
        "Python is fun",
    ):
        assert c.correct(text) == (text, []), text


def test_does_not_turn_real_words_into_nearby_names():
    c = NameCorrector(["PyIstanbul", "Gemini", "Django Girls", "EuroPython"])
    for text in ("Python Pizza, İstanbul.", "İstanbul'un tarihi", "Remini'de.", "we have a Django Girls community"):
        assert c.correct(text) == (text, []), text
    assert c.correct("Europython'da yaptım")[0] == "EuroPython'da yaptım"  # case only: normalised

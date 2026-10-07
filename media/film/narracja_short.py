"""Narracja pionowej wersji ~60 s (Reels, TikTok). Format jak w narracja.py."""

CALL = ("Rozsyłamy wici!", "Rozsyłamy wici!", {  # wezwanie do działania, nie płaskie zakończenie
    "settings": {"stability": 0.25, "style": 0.8, "speed": 0.95},
    "next_text": "– zawołał z mocą, wzywając wszystkich do działania."})

SEGMENTS = [
    ("v1", [
        "Gaśnie prąd w całej okolicy.",
        "Po kilku godzinach telefon pokazuje: brak sieci.",
    ]),
    ("v2", [
        "W szkole czy garażu jest pięćdziesiąt osób. Brakuje wody i leków.",
        "Służby są kilka kilometrów dalej. Jak im o tym powiedzieć?",
    ]),
    ("v3", [
        "Takie zgłoszenie to mniej niż dwieście bajtów.",
        "Nie potrzeba do niego internetu. Wystarczy proste radio na bateriach.",
    ]),
    ("v4", [
        "Celujemy w około kilometr zasięgu.",
        "Dlatego każda stacja podaje wiadomość dalej, od sąsiada do sąsiada, aż dotrze do służb.",
        "Jak dawne wici.",
    ]),
    ("v5", [
        "Stacja to małe pudełko z ekranem, przyciskami i bateriami.",
        "Włączasz stację, wystawiasz na zewnątrz antenę i jesteś w sieci.",
        "Laptop i router to kolejne poziomy.",
    ]),
    ("v6", [
        "Projekt jest otwarty, ale jeszcze niesprawdzony w terenie.",
        "Szukamy krótkofalowców, elektroników, programistów i ludzi ze służb.",
    ]),
    ("v7", [
        ("Szczegóły na GitHubie.", "Szczegóły na git habie."),
        CALL,
    ]),
]

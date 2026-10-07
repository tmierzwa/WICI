"""Narracja filmu o WICI.

Każdy segment to lista zdań. Zdanie jest tekstem napisów; jeśli lektor ma
przeczytać coś inaczej, podajemy parę (napis, tekst_dla_lektora).
"""

SEGMENTS = [
    ("s1a", [
        "Wyobraź sobie, że gaśnie światło.",
        "Nie tylko u ciebie, ale w całej okolicy.",
    ]),
    ("s1b", [
        "Na początku to tylko niewygoda.",
        "Ale mijają godziny i telefon pokazuje: brak sieci.",
    ]),
    ("s1c", [
        "W szkole, która stała się schronieniem, jest pięćdziesiąt osób.",
        "Brakuje wody. Ktoś potrzebuje leków.",
    ]),
    ("s1d", [
        "Kilka kilometrów dalej są służby, które mogłyby pomóc.",
        "Tylko skąd ma o tym wiedzieć?",
    ]),
    ("s2a", [
        "Łatwo myśleć, że telefon łączy się z drugim telefonem.",
        "A tak nie jest.",
    ]),
    ("s2b", [
        "Każda wiadomość idzie najpierw do masztu, a stamtąd dalej, przez całą sieć.",
    ]),
    ("s2c", [
        "Maszt potrzebuje prądu.",
        "Przy długiej awarii jego akumulatory w końcu się wyczerpią.",
    ]),
    ("s2d", [
        "I wtedy łańcuch pęka.",
        "Nie przy naszym telefonie, tylko gdzieś daleko, poza naszym wpływem.",
    ]),
    ("s3a", [
        "Postawmy więc proste pytanie.",
        "Czego potrzeba, żeby przenieść krótką wiadomość na kilka kilometrów, bez prądu z sieci i bez internetu?",
    ]),
    ("s4a", [
        "Zacznijmy od tego, jak mała jest taka wiadomość.",
        "Gdzie jesteśmy, ilu nas jest, czego brakuje i jak bardzo jest to pilne.",
    ]),
    ("s4b", [
        "Zapisana w komputerze zajmuje mniej niż dwieście bajtów.",
    ]),
    ("s4c", [
        "Dla porównania: jedno zdjęcie z telefonu jest ponad dziesięć tysięcy razy większe.",
    ]),
    ("s4d", [
        "Skoro wiadomość jest tak mała, nie potrzebujemy szybkiego łącza.",
        "Wystarczy proste, powolne radio.",
        "Takie zgłoszenie przeleci przez eter w mniej więcej sekundę.",
    ]),
    ("s4e", [
        "To radio nadaje z mocą podobną do pilota do bramy, na częstotliwości, z której korzystają też inne sieci radiowe.",
        "Może pracować na zwykłych bateriach.",
    ]),
    ("s5a", [
        "Ale małe radio ma mały zasięg.",
        "Wśród budynków celujemy w około kilometr, i dopiero próby pokażą, czy to realne.",
    ]),
    ("s5b", [
        "Rozwiązanie jest bardzo stare.",
        "Kiedy trzeba było zwołać ludzi, rozsyłano wici: wieść szła od osady do osady, z rąk do rąk.",
    ]),
    ("s5c", [
        "Tutaj robi to każda stacja.",
        "Odbiera wiadomość od sąsiada i podaje ją dalej, aż dotrze do służb.",
    ]),
    ("s5d", [
        "Ale cudów nie ma.",
        "Jeśli jedyny sąsiad zgaśnie, droga się urywa.",
        "Inna istnieje tylko wtedy, gdy ktoś jeszcze jest w zasięgu.",
    ]),
    ("s6a", [
        "Jak wygląda jedna stacja?",
        "Zestaw ma trzy poziomy. Pierwszy, podstawowy, to małe pudełko z ekranem, kilkoma przyciskami i bateriami.",
    ]),
    ("s6b", [
        "Włączam stację, wystawiam na zewnątrz antenę i jestem w sieci.",
    ]),
    ("s6c", [
        "Opiekun wybiera przyciskami, czego brakuje i ilu osób to dotyczy.",
        "A każda włączona stacja podaje dalej wiadomości sąsiadów.",
    ]),
    ("s6d", [
        "Poziom drugi to stary laptop podłączony do stacji: wygodny panel dla opiekuna.",
        "Poziom trzeci dodaje domowy router. Wtedy mieszkańcy zgłaszają potrzeby zwykłą stroną w telefonie.",
        "Bez aplikacji, bez konta, bez internetu.",
    ]),
    ("s6e", [
        "Laptop i router dostają prąd z akumulatora przez przetwornicę z zestawu.",
        "A telefony ładuje osobna ładowarka z zestawu, z drugiego akumulatora.",
    ]),
    ("s7a", [
        "Jedna rzecz jest dla nas szczególnie ważna: uczciwe komunikaty.",
        "„Wysłane” to nie to samo, co „pomoc jedzie”.",
    ]),
    ("s7b", [
        "Dlatego zgłoszenie przechodzi przez osobne stany.",
        "Zapisane lokalnie.",
        "Zapisane u odbiorcy.",
        "Przeczytane przez dyżurnego.",
        "Pomoc skierowana.",
    ]),
    ("s7c", [
        "Każdy z nich oznacza coś innego.",
        "A decyzję o pomocy zawsze podejmuje człowiek.",
    ]),
    ("s8a", [
        "Gdzie dziś jesteśmy?",
        "Jest koncepcja, specyfikacja i płytka do pomiarów radia. Płytka stacji dopiero powstanie.",
        "Wszystko jest otwarte: schematy, kod i dokumentacja.",
    ]),
    ("s8b", [
        "Ale nic jeszcze nie zostało sprawdzone w terenie.",
        "Nie wiemy, czy kilometr wśród budynków się uda.",
        "Czy stacja wytrzyma dwie doby na bateriach.",
        "Czy oprogramowanie sieci zmieści się w małym układzie.",
    ]),
    ("s8c", [
        "To trzeba zmierzyć, a nie założyć.",
        "I tu potrzebujemy innych ludzi.",
    ]),
    ("s9a", [
        "Szukamy krótkofalowców i elektroników, którzy znają radio i anteny.",
        "Programistów.",
        "Ludzi ze służb, którzy wiedzą, jak naprawdę wygląda kryzys.",
    ]),
    ("s9b", [
        "I każdego, kto ma okno, dach albo piwnicę, i chce pomóc sprawdzić, jak to działa naprawdę.",
    ]),
    ("s9c", [
        ("Cały projekt jest otwarty, na GitHubie, pod nazwą WICI.",
         "Cały projekt jest otwarty, na git habie, pod nazwą wici."),
        "Zajrzyj, zadaj pytanie, zgłoś błąd.",
        "Rozsyłamy wici.",
    ]),
]

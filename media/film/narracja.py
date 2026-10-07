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
        "Kilka kilometrów dalej jest straż pożarna, która mogłaby pomóc.",
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
        "Takie zgłoszenie przeleci przez eter w mniej niż sekundę.",
    ]),
    ("s4e", [
        "To radio nadaje z mocą podobną do pilota do bramy, na częstotliwości, z której korzystają też czujniki i piloty.",
        "Może pracować na zwykłym akumulatorze.",
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
        "Odbiera wiadomość od sąsiada i podaje ją dalej, aż dotrze do straży.",
    ]),
    ("s5d", [
        "Ale cudów nie ma.",
        "Jeśli jedyny sąsiad zgaśnie, droga się urywa.",
        "Inna istnieje tylko wtedy, gdy ktoś jeszcze jest w zasięgu.",
    ]),
    ("s6a", [
        "Jak wygląda jedna stacja?",
        "Celowo składamy ją z rzeczy, które zwykle już gdzieś leżą.",
    ]),
    ("s6b", [
        "Stary laptop.",
        "Zwykły domowy router.",
        ("Akumulator 12 V.", "Akumulator dwanaście wolt."),
    ]),
    ("s6c", [
        "Dokładamy tylko jedno: mały moduł radiowy z anteną wystawioną za okno.",
    ]),
    ("s6d", [
        ("Mieszkańcy łączą się telefonem z lokalnym Wi-Fi i otwierają zwykłą stronę.",
         "Mieszkańcy łączą się telefonem z lokalnym łaj-faj i otwierają zwykłą stronę."),
        "Bez aplikacji, bez konta, bez internetu.",
    ]),
    ("s6e", [
        "Kto nie ma telefonu, dyktuje zgłoszenie opiekunowi.",
        "A osobny akumulator ładuje telefony, żeby nie zabierać prądu radiu.",
    ]),
    ("s7a", [
        "Jedna rzecz jest dla nas szczególnie ważna: uczciwe komunikaty.",
        "„Wysłane” to nie to samo, co „pomoc jedzie”.",
    ]),
    ("s7b", [
        "Dlatego zgłoszenie przechodzi przez osobne stany.",
        "Zapisane tutaj.",
        "Zapisane w straży.",
        "Przeczytane przez dyżurnego.",
        "Pomoc skierowana.",
    ]),
    ("s7c", [
        "Każdy z nich oznacza coś innego.",
        "A decyzję o pomocy zawsze podejmuje człowiek.",
    ]),
    ("s8a", [
        "Gdzie dziś jesteśmy?",
        "Jest koncepcja, specyfikacja i projekt pierwszej płytki elektroniki.",
        "Wszystko jest otwarte: schematy, kod i dokumentacja.",
    ]),
    ("s8b", [
        "Ale nic jeszcze nie zostało sprawdzone w terenie.",
        "Nie wiemy, czy kilometr wśród budynków się uda.",
        "Czy stacja wytrzyma dobę na akumulatorach.",
        "Czy laptop z szuflady zawsze wystartuje.",
    ]),
    ("s8c", [
        "To trzeba zmierzyć, a nie założyć.",
        "I tu potrzebujemy innych ludzi.",
    ]),
    ("s9a", [
        "Szukamy krótkofalowców i elektroników, którzy znają radio i anteny.",
        "Programistów.",
        "Ludzi ze straży i z gmin, którzy wiedzą, jak naprawdę wygląda kryzys.",
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

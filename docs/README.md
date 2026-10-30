# Dokumentacja WICI

Zacznij od [koncepcji systemu](concept/index.html): potrzeby i wymagania, scenariusze pracy, dostępne rozwiązania, analiza opcji, architektura komunikacji, wykonalność, zagrożenia i plan prób. Dokumenty są po polsku, oddzielają wymagania od dowodów i wskazują otwarte decyzje.

Specyfikacja stacji 0.5 składa się z pięciu rozdziałów, protokołu USB, rozdziału o stanowisku odbiorczym, instrukcji gospodarza oraz BOM stacji. Karta obsługi i instrukcja dyżurnego są w [dokumentach obsługi](obsluga/README.md). Parametry, kontrakty, warunki odbioru i kandydatów części zmienia się w tych plikach, a uzasadnienia i analizy w `docs/concept/`.

| Rozdział | Zakres |
|---|---|
| [Projekt](spec/projekt.md) | Poziomy zestawu, połączenia, przygotowanie i użycie odebranego zestawu |
| [Radio](spec/radio.md) | Profil LoRa, radia RNode do pomiarów, współdzielenie kanału, dostęp do kanału, warunki prawne, interfejs radiowy w stosie z ponowieniami, interfejs Reticulum przez USB (węzeł stanowiska), USB do laptopa, antena i budżet łącza |
| [Oprogramowanie](spec/oprogramowanie.md) | Oprogramowanie stacji i laptopa, wiadomości SA1, cykl życia zgłoszenia, trwałość i pamięć FRAM, czas, ekran i przyciski, tryby kryzysowe, pakiety offline i aktualizacja |
| [Protokół USB](spec/protokol-usb.md) | Kontrakt laptop–stacja (`"usb":2`): polecenia i odpowiedzi, synchronizacja, transfery w częściach, PRZENIEŚ STACJĘ |
| [Elektronika](spec/elektronika.md) | Stacja pilotażowa na płytce v2, tor zasilania z ogniw AA i 12 V, zanik zasilania przy zapisie, poziom 3 z kupionej stacji zasilania |
| [Stanowisko odbiorcze](spec/stanowisko-osp.md) | Stanowisko odbiorcze: stacja jako węzeł transportu i obowiązkowy komputer z tożsamością odbiorcy (D19), aplikacja, panel, zestaw, awarie |
| [Odbiór](spec/odbior.md) | Próby z grupami T1–T8, minimum pilotażu, warunki zaliczenia i niezrealizowane części |
| [Karta obsługi](obsluga/karta-stacji.html) | Karta obsługi stacji do druku: PL, UK i EN, każda na jednej kartce A4 (strona 1 najważniejsze, strona 2 gdy trzeba), i formularz papierowy; CC BY 4.0 ([dokumenty obsługi](obsluga/README.md)) |
| [Instrukcja dyżurnego](obsluga/instrukcja-dyzurnego.md) | Czynności dyżurnego: uruchomienie, potwierdzenia, odpowiedzi i komunikaty, kwarantanna, przekazywanie służbom, rejestr, awarie, ćwiczenia, cisza, zamknięcie zdarzenia; tabele dla gminy; CC BY 4.0 |
| [Instrukcja gospodarza](spec/instrukcja.md) | Tematy obsługi spoza karty: adres, stany zgłoszenia, alarmy, cisza, energia, poziomy 2–3, przekazanie zmiany, koniec zdarzenia, bezpieczeństwo |
| [BOM stacji](spec/bom-stacji.csv) | Części stacji pilotażowej (płytka v2, moduły, zasilanie, obudowa i antena) i zestawu, z kandydatami i stanem |

Planowany pilotaż obejmuje stacje na płytce v2 z modułami ESP32-S3 i SX1262 ([elektronika](spec/elektronika.md#stacja-pilotażowa), [profil LoRa](spec/radio.md#profil-lora-pilotażu)). Lista prób wymaganych przed pilotażem jest w sekcji [Minimum pilotażu](spec/odbior.md#minimum-pilotażu) odbioru; pozostałe wiersze dotyczą wydania.

Wstrzymane do decyzji po pilotażu są: płytka R02 z torem RF i blokiem zasilania, profil P1 (wariant zapasowy), poziomy 2–3 (poziom 3 na kupionej stacji zasilania) oraz pakiety START. Uzasadnienia zmian i ich historię opisuje [przegląd techniczny](review.md).

Próby stosu można też wykonać na [stanowisku deweloperskim](../hardware/dev-bench/README.md) z płytek rozwojowych i modułów producentów. Wstrzymany projekt płytki stacji ma [własny folder](../hardware/r02/README.md) z kolejnością prac i [lekcjami z poprzedniego kontrolera R01.3](../hardware/r02/lekcje.md), którego pliki są w historii Git. Wyniki obliczeń są w [modelu](../software/reference/README.md).

[Narzędzia i tworzenie paczek](development.md). Bieżąca kontrola repozytorium: `tools/verify_repository.py` i CI dla aktualnego commita.

[Aktualne ustalenia przeglądu technicznego](review.md): poprawione rozbieżności, konkretne przeszkody i warunki ich zamknięcia.

W specyfikacji skrót OSP oznacza tylko ochotniczą straż pożarną. Stanowisko odbiorcze to rola wyznaczona przez wójta (burmistrza, prezydenta miasta). Zwykle jest to jednostka ochotniczej straży pożarnej z grafikiem dyżurów na czas kryzysu, ale może nim być także gminne centrum zarządzania kryzysowego lub stanowisko gminnego zespołu zarządzania kryzysowego ([koncepcja, rozdział 02](concept/02-scenariusze-i-organizacja.html#miejsce-w-systemie-ochrony-ludnosci)).

Status: projekt prototypu 0.5; sprzęt nie jest dopuszczony do użycia (HOLD). Instrukcje użycia opisują docelowy odebrany zestaw, a nie gotowy produkt.

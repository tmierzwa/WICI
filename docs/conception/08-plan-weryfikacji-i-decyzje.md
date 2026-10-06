# 08. Plan weryfikacji i decyzje

## Kolejność prac

Celem pierwszych prób jest odrzucić błędne założenia przed zamówieniem całego sprzętu. Każdy etap kończy się dowodem albo decyzją o zmianie. Wynik wcześniejszy pozostaje ważny tylko dla niezmienionej konfiguracji i warunków.

1. **Lokalna stacja:** aplikacja, kolejka, strona i pakowanie offline na dostępnym laptopie/routerze. Sprawdzić uruchomienie bez internetu oraz trwałość danych. Zasilanie laboratoryjne służy jako narzędzie; nie dowodzi własnej przetwornicy.
2. **Wiadomości i czas radia:** dwa końce Reticulum/LXMF, emulator ograniczeń P1 i adapter. Zmierzyć wszystkie pakiety dla rzeczywistych treści, długie READY i ponowienia. Odrzucić koncepcję terminowości, jeśli stos nie mieści się w budżecie.
3. **RF:** zmontować i pomierzyć dwa wykonania. Przed zamówieniem wykonać kontrolę 1:1 z rzeczywistymi złączami oraz przegląd layoutu. Sprawdzić zgodność w obu kierunkach i warunki emisji.
4. **Sieć terenowa:** A–B–OSP w rzeczywistych miejscach, z wykluczonym bezpośrednim A–OSP. Sprawdzić pojedyncze zgłoszenia, obciążenie, zanik węzła i powrót trasy. Użyć dopuszczonego zasilania; kwalifikacja własnego toru pozostaje odrębnym etapem.
5. **Własne zasilanie:** pełny projekt, pomiary i kwalifikacja obu wariantów części. Dopiero po spełnieniu ochrony i warunków AC dołączyć rzeczywiste zasilacze laptopa/routera oraz ładowanie telefonów.
6. **Kompletny pilotaż 24 h:** odebrany zestaw, docelowi opiekunowie, dyżurny i zapas energii. Oddzielnie mierzyć stację i ładowarkę. Dopiero wynik całości pozwala ocenić gotowość danej konfiguracji.

Emulator nie dowodzi fizycznego zasięgu, kolizji ani prawidłowego działania EEPROM. Gotowy modem porównawczy nie zwalnia kwalifikacji dwóch docelowych wykonań. Raport CAD nie zwalnia montażu i kontroli wymiarów.

## Próby i pokrycie wymagań

T1–T8 są grupami prac tej koncepcji. Warunki liczbowe pochodzą z [odbioru 0.4](../spec/odbior.md); pozostałe przypadki uzupełniają sposób weryfikacji. Nowe progi użytkowe trzeba zatwierdzić przed pilotażem, bez zmniejszania istniejących warunków odbioru.

| Próba | Wymagania | Zakres i dowód |
|---|---|---|
| T1 — lokalnie i offline | W01–W04, W13, W18 | odłączony internet; zimny start Windows x64, macOS Intel/ARM i wspieranego Linux PC; utrzymanie hosta w pracy oraz pełny cykl USB według odbioru; 50 połączonych / 15 aktywnych; modem odłączony nie blokuje formularza; lista sprawdzonych hostów/routerów |
| T2 — zapis, statusy, zaufanie | W01, W04–W07, W16 | granice UTF-8 i pięć typów; duplikaty/konflikty; awaria przed i po COMMIT; fizyczne odcięcia nośnika; błąd dysku; obcy klucz i dostęp do cudzego zgłoszenia; eksport/import i tylko jedna aktywna tożsamość |
| T3 — integracja stosu i adapter | W14 oraz podstawa W07/W09/W10 | timeouty całego stosu przy oczekiwaniu za ruchem przekaźnika; liczba pakietów dla rzeczywistych wiadomości; zestawianie łącza/zasób LXMF; cisza i READY; pełna kolejka modemu; odłączenie USB; powrót po restarcie; mierzalny brak lawiny równoległych ponowień |
| T4 — fizyczne radio i warunki TX | W14, W17 | TI→ST i ST→TI, 10 000 pakietów każdego rozmiaru granicznego; moc/częstotliwość/czułość z P1; cały ruch i restarty ≤10% w dowolnym ciągłym oknie godzinnym; przerwany zapis EEPROM nigdy nie omija budżetu; emisje gotowej konfiguracji |
| T5 — teren, przekaźnik, obciążenie | W08–W10 | 1 km w rzeczywistych miejscach: ≥99/100 zgłoszeń z RECEIVED w 5 min przy pojedynczym ruchu; wymuszone A–B–OSP i odpowiedź; 50 zgłoszeń łącznie z A w pierwszych 5 min, ≥99% z RECEIVED na A do 30 min od pierwszego COMMIT; zimna i ustalona trasa; zanik i powrót trasy bez utraty zapisu |
| T6 — energia i bezpieczeństwo | W11, W12, W14, W17 | A/B: 100 zmian w obu kierunkach i skrajach napięcia, zero resetów; udar/I²t; pełne porty w 40°C przez 2 h; zwarcie i OVP bez telefonu; wszystkie próby przetwornicy/AC ze specyfikacji; zakłócenia RF i praca dobowa z pomiarem Wh obu pul |
| T7 — odtworzenie i dostawcy | W14, W15 | ktoś spoza zespołu odtwarza paczkę źródeł i wskazaną konstrukcję; hashe/BOM/licencje/wersje; dwóch niezależnych wykonawców; raport różnic i każda zakwalifikowana alternatywa |
| T8 — obsługa i realna pomoc | W03, W06, W18 | opiekun i zastępca używają krótkiej instrukcji; osoba bez telefonu zgłasza potrzebę; dyżurny odczytuje i odsyła decyzję; awaria OSP i kanał zastępczy; zapisane błędy obsługi i czasy czynności |

**≥99% z jednej próby 50 zgłoszeń oznacza 50/50.** Wynik 49/50 to 98%. Nie zaokrąglać go do zaliczenia. W próbie 1 km każda kolejna wiadomość jest wysyłana według wcześniej ustalonej metody pojedynczego ruchu. TEST i zgłoszenia próbne muszą być jednoznacznie oznaczone i uzgodnione z odbiorcą.

Wynik 99/100 opisuje daną próbę; nie jest statystyczną gwarancją skuteczności 99% we wszystkich warunkach. Powtórzenia i warunki pilotażu ustalić przed wykonaniem, aby nie dobierać wygodnych wyników po fakcie.

## Minimalny raport

Rewizja źródeł i sprzętu, BOM wariantu, wersje bibliotek/firmware/systemu, modele hosta/routera, topologia i anteny, źródła i obciążenia, warunki, metoda, liczba prób i surowe wyniki. Dla komunikacji: id/revision, czas lokalnego zapisu, COMMIT OSP i powrotu RECEIVED, liczba datagramów, czas TX, odrzuty i restarty. Nie publikować kluczy, tokenów ani rzeczywistych danych mieszkańców.

Testy modelu opisują zachowanie modelu. Próby sprzętu, bezpieczeństwa i pracy dyżurnego mają odrębne raporty. Status HOLD można zdjąć wyłącznie dla wskazanej odebranej konfiguracji; CI sprawdza repozytorium, nie jego gotowość do użycia.

## Otwarte decyzje i warunki zamknięcia

| ID | Decyzja | Dowód potrzebny przed zamknięciem | Odpowiedzialność do wyznaczenia |
|---|---|---|---|
| D01 | czy P1 mieści ruch zgłoszeń i LXMF w limitach | T3 i T5; pełny koszt pakietów i timeoutów; wskazana liczba źródeł/przekaźników; nie tylko długość SA1 | integrator oprogramowania i radia |
| D02 | czy TI i ST tworzą niezależne zgodne modemy | dwa layouty, nastawy i T4 w obu kierunkach | projektant RF |
| D03 | czy miejsca i anteny zapewniają sieć do odbiorcy | T5 oraz wskazanie punktów odcięcia i dostępnego zastępstwa | koordynator miejsc |
| D04 | jaki host/router i pakiet można powierzyć opiekunowi | T1/T8, spisana macierz; uprawnienia, firewall, sterowniki, start USB i brak automatycznego usypiania; osobno kwalifikacja suspend/resume modemu | integrator pakietów |
| D05 | czy zasilanie 230 V jest uzasadnione i bezpieczne | pełna konstrukcja, T6, realne zasilacze; porównanie kosztu/energii wariantu DC | projektant zasilania i osoba oceniająca bezpieczeństwo |
| D06 | ile energii rzeczywiście potrzebuje miejsce | pomiar 24 h, pojemność dostępnych źródeł i osobny plan obu pul | opiekun pilotażu |
| D07 | kto przyjmuje, pomaga i zastępuje OSP | uzgodniony dyżur, kompetencje, klucze, kanał awaryjny i T8 | organizacja pomocy |
| D08 | jak chronić dane, kopie i utracone klucze | procedura retencji/eksportu/unieważnienia; T2/T8 | odpowiedzialny za dane i utrzymanie |
| D09 | jakie części, licencje i koszty zamykają wydanie | wersje i licencje zależności; dwie wyceny tego samego zakresu; kwalifikowane warianty | utrzymanie wydania i konstruktorzy |

Nie ma jeszcze przypisanych osób ani zatwierdzonego harmonogramu. Najpierw zamknąć zakres i dane wejściowe, potem wycenić pracę. Nie rozpoczynać serii produkcyjnej na podstawie samego wspólnego kontraktu modemów lub poprawnych Gerberów kontrolera.

Warunek przerwania: fałszywy status sukcesu, utrata danych po potwierdzeniu, nieograniczona kolejka/ponowienia, obejście budżetu TX, przekroczenie ochrony portu lub niespełniona ochrona AC. Naprawić przyczynę i powtórzyć zależne próby; nie zwiększać limitu, aby uzyskać zaliczenie.

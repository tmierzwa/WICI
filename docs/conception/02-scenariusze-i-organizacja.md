# 02. Scenariusze i organizacja

## Role

| Rola | Odpowiedzialność |
|---|---|
| Mieszkaniec | podaje miejsce i potrzebę; zachowuje dostęp do własnego zgłoszenia; zgłasza zmianę sytuacji |
| Opiekun schronienia | uruchamia stację, sprawdza TEST, pomaga osobom bez telefonu, zatwierdza pilność, kontroluje energię |
| Zastępca | zna instrukcję i może przejąć pracę; nie wymaga dostępu do prywatnego konta opiekuna |
| Dyżurny odbiorcy, np. OSP | odczytuje zgłoszenia, ocenia możliwości, zleca działanie i aktualizuje status |
| Osoba utrzymująca system | przygotowuje i sprawdza wydanie, urządzenia, klucze i kopie; naprawia poza dyżurem |

OSP jest przykładem miejsca pomocy. Obecność budynku OSP nie dowodzi całodobowego dyżuru ani możliwości udzielenia każdego rodzaju pomocy. Przed uruchomieniem trzeba uzgodnić odbiorcę, zakres działań i zastępstwo.

„Pomoc skierowana” oznacza decyzję dyżurnego. Nie oznacza dotarcia pomocy. Przy działającym telefonie i bezpośrednim zagrożeniu korzysta się z normalnych służb, niezależnie od statusu WICI.

## Przebieg działania

1. **Przygotowanie:** sprawdzić znaleziony sprzęt, antenę, lokalizację, źródła i klucz odbiorcy. Wyznaczyć opiekuna i zastępcę. Zapisać adres strony i procedurę awaryjną na papierze.
2. **Uruchomienie:** zestawić lokalne Wi-Fi i stronę; niezależnie sprawdzić modem oraz odpowiedź na TEST od dyżurnego. Potwierdzić, że adres i wejście są zrozumiałe dla odbiorcy.
3. **Przyjęcie potrzeby:** mieszkaniec wysyła formularz albo dyktuje go opiekunowi. Stacja pokazuje zapis lokalny dopiero po trwałym zapisie. Brak trasy pozostawia zgłoszenie w kolejce.
4. **Przyjęcie u odbiorcy:** OSP zapisuje zgłoszenie i odsyła RECEIVED. Dyżurny oddzielnie potwierdza odczyt oraz decyzję. Opiekun przekazuje informację również osobom bez telefonu.
5. **Utrzymanie:** obserwować wiek kolejki, kontakt z OSP, energię i odrzuty modemu. Wymieniać A/B z nakładaniem źródeł; źródło ładowarki wymieniać niezależnie.
6. **Przekazanie dyżuru:** przekazać otwarte potrzeby, ostatnie odpowiedzi, dostępne źródła, awarie i uzgodniony kanał zastępczy. Nie kasować niepotwierdzonych zgłoszeń.

## Zachowanie w scenariuszach awarii

| Zdarzenie | Funkcja dostępna | Działanie opiekuna |
|---|---|---|
| Internet i telefonia nie działają | lokalna strona, zapis, radio przy działających sąsiadach | sprawdzić odpowiedź odbiorcy i utrzymać dyżur |
| Telefon mieszkańca rozładowany | formularz na laptopie opiekuna, kolejka, ładowanie z C | przyjąć zgłoszenie ustnie; udostępnić ładowanie na zmianę |
| Modem lub trasa niedostępne | lokalna informacja i zapis; wysyłka oczekuje | sprawdzić kabel/antenę/sąsiada; dla pilnej potrzeby uruchomić uzgodniony kanał zastępczy |
| Stacja pośrednia wyłączona | lokalna praca; inna trasa tylko jeśli fizycznie istnieje | przywrócić sąsiada lub uzgodnić inne położenie; nie oczekiwać, że mesh wytworzy łącze |
| OSP wyłączona lub bez dyżurnego | lokalna praca i możliwy transport między innymi stacjami | ustalić kontakt z uzgodnionym zastępstwem; brak RECEIVED nie potwierdza pomocy |
| Radio przeciążone | lokalne zgłoszenia, trwała kolejka | ograniczyć zbędne komunikaty, zebrać powtarzalne potrzeby; obserwować najstarszą intencję |
| Restart laptopa | po uruchomieniu: odtworzona kolejka i tożsamość, jeśli nośnik jest sprawny | wykonać kontrolę zapisu i TEST; nie uruchamiać drugiej kopii tej samej stacji |
| Uszkodzony laptop/nośnik | przeniesienie z poprawnej kopii; ostatnie dane mogą być utracone | zastosować PRZENIEŚ STACJĘ, gdy stary działa; po utracie sprawdzić statusy u OSP i odtworzyć brakujące potrzeby |
| Ładowarka uszkodzona | komunikacja i telefony z zapasem energii | odłączyć uszkodzoną sekcję lub całą ładowarkę; nie pobierać energii z obwodu stacji bez nowego bilansu |

## Sieć i odbiorca zastępczy

Pierwsza próba obejmuje schronienie A, przekaźnik B i odbiorcę O. Przebieg A–B–O musi zostać wymuszony odcięciem bezpośredniego A–O. Zasięg między sąsiadami nie dowodzi zasięgu do OSP. Stacje będące jedynym przekaźnikiem są punktami odcięcia sieci i mają pierwszeństwo w zapewnieniu zasilania.

OSP nie steruje trasowaniem całej sieci; jest punktem świadczenia usługi. Jej utrata nie musi wyłączyć transportu, ale może pozbawić zgłoszenia odbiorcy zdolnego pomóc. Drugi odbiorca wymaga uzgodnionej odpowiedzialności i kluczy. Automatyczne przejęcie tej samej bazy lub tożsamości przez drugi komputer nie jest częścią wariantu bazowego.

Propozycja na pilotaż: ręczny wybór odbiorcy zastępczego przez opiekuna, po potwierdzeniu dyżuru. Format SA1 nie definiuje przekazania odpowiedzialności między dwiema OSP. Przed dodaniem funkcji trzeba rozstrzygnąć, kto prowadzi zgłoszenie, jak zachować identyfikator i uniknąć podwójnego wysłania pomocy. Do tego czasu stosuje się uzgodnioną procedurę głosową lub pisemną z odczytaniem numeru zgłoszenia.

## Instrukcja i ćwiczenie

Na karcie przy stacji: adres i wejście, Wi-Fi/QR, odbiorca i zastępstwo, znaczenie czterech stanów zgłoszenia, kolejność podłączenia i wymiany źródeł, sposób zgłoszenia bez telefonu. Klucze prywatne i dane mieszkańców nie należą na publiczną kartę.

Przed pilotażem opiekun i zastępca osobno uruchamiają stację z przygotowanego zestawu, wysyłają TEST, odłączają radio, wymieniają źródło i wyjaśniają status oczekującego zgłoszenia. Powtórzyć po zmianie wydania, routera, miejsca anteny lub odbiorcy. Częstotliwość ćwiczeń w eksploatacji ustala lokalna organizacja; nie ma jeszcze danych do jej optymalnego doboru.

Kurier z papierowym zgłoszeniem lub zwykła łączność głosowa są możliwymi procedurami zastępczymi po uzgodnieniu warunków i bezpieczeństwa drogi. Automatyczny transport plików przez pendrive nie jest zaimplementowaną funkcją WICI.

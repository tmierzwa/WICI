# Model kontraktów WICI 0.5

Kod wzorcowy sprawdza ramki P1, format SA1, atomowy odbiór zgłoszenia u odbiorcy z kwarantanną nieznanych nadawców, listą zaufanych stacji i zamknięciem zdarzenia oraz przyjmowanie RECEIVED, STATUS, REPLY i BULLETIN przez stację wyłącznie od przypiętej tożsamości odbiorcy. Nie jest oprogramowaniem stacji, aplikacją laptopa, sterownikiem radia ani implementacją Reticulum.

Python 3.12, wyłącznie biblioteka standardowa. Z katalogu głównego:

```sh
python3 -m unittest discover -s software/reference -v
python3 software/reference/obliczenia.py
```

Drugie polecenie zapisuje `wyniki.json` obok skryptu. Są to obliczenia z założeń, nie pomiary. [Zapis weryfikacji](weryfikacja.json) wiąże wynik 35 testów z sumami źródeł.

Reguły modelu:

- Treść SA1 po kodowaniu ≤256 B. Teksty: limit w bajtach UTF-8, wyłącznie postać NFC, bez `"` i `\` (formularz i ekran zamieniają je na „ ” i /) oraz bez znaków kategorii Cc, Cf, Cs, Co, Cn, Zl i Zp. Kodowanie kanoniczne nie zawiera więc sekwencji ucieczki, a przypadki najgorsze wynoszą: REQUEST i TEST 222 B, BULLETIN 246 B, REPLY 156 B, STATUS 59 B, RECEIVED 50 B. `configure` odrzuca adres lub frazę, jeśli najgorsze zgłoszenie z przycisków (liczba osób ≤999) przekroczy limit; przy obecnych limitach pól wynosi ono najwyżej 220 B.
- Odbiorca deduplikuje odbiór po (nadawca, id, revision, SHA-256 treści kanonicznej); ten sam klucz z inną treścią to konflikt. Zgłoszenie i RECEIVED zapisuje jedna transakcja.
- Kwarantanna: ≤4 wiadomości na nadawcę i ≤256 łącznie, nadmiar odrzucany. Dyżurny zatwierdza pojedynczą wiadomość (`approve_message`); nadawca nie staje się zaufany. Zaufaną stację dodaje się tylko z karty stacji (pełny klucz publiczny 64 B) za zgodą dwóch różnych osób (`add_trusted`).
- Usunięcie z listy (`remove_trusted`) wykonuje jedna osoba. Wiadomości usuniętej stacji trafiają do kwarantanny jak wiadomości nieznanego nadawcy; licznik `removed_messages` (alarm „możliwe przejęcie stacji”) obejmuje także powtórzenia i wiadomości odrzucone ponad limit. Stacja wraca na listę przez `add_trusted`, czyli za zgodą dwóch osób; jej wiadomości z kwarantanny są wtedy usuwane, bo stacja ponawia je do RECEIVED. Konfiguracja przy otwarciu bazy nie przywraca stacji usuniętej.
- ZAMKNIJ ZDARZENIE (`purge_content`): usuwa treść zgłoszeń, odpowiedzi i kwarantanny; klucze odbioru ze skrótami i ACK zostają, więc powtórzona wiadomość dostaje ten sam RECEIVED, a inna treść pod tym samym kluczem nadal jest konfliktem.
- STATUS ze stanem 5 wymaga wcześniejszej REPLY dla tego id; kolejność stanów według `status_after`.

Testy obejmują wszystkie długości datagramu 1–600 B, znany wektor CRC, błędy i duplikaty, sześć typów wiadomości z przypadkami najgorszymi, odrzucanie znaków i tekstu spoza NFC, przerwanie transakcji bez ACK, kwarantannę z limitami i zatwierdzaniem pojedynczych wiadomości, karty stacji, usunięcie z listy i ponowne dodanie, zamknięcie zdarzenia, regułę stanu 5, zaufanie stacji do odbiorcy, zmieszczenie zgłoszenia z przycisków w jednym pakiecie okazjonalnym oraz czas nadawania LoRa (znana ramka według wzoru Semtech i podział pakietu na dwie ramki jak w RNode).

| Plik | Rola |
|---|---|
| [reference.py](reference.py) | Kodowanie, walidacja, model odbioru na stanowisku (kwarantanna, lista zaufanych stacji, zamknięcie zdarzenia) i zaufanie stacji |
| [schema.sql](schema.sql) | Schemat SQLite używany przez model |
| [test_reference.py](test_reference.py) | Przypadki akceptacyjne |
| [obliczenia.py](obliczenia.py) | Energia stacji i poziomu 3, budżet W10 przekaźnika z kodem IFAC (także z dwoma STATUS), pojemność sieci, rozmiary SA1, zajętość FRAM 4 Mbit według roli, RAM tablic stosu, zimny start sieci (ogłoszenia, zapytania o trasę i TEST wobec okna TEST), łącze radiowe i oszacowania układów; profil LoRa pilotażu (`lora_pilot`): czas nadawania według wzoru Semtech, podział pakietu >254 B na dwie ramki jak w RNode, W10, ruch mieszany, pojemność, zapas zasięgu i energia dla SF7 i SF8 |
| [wyniki.json](wyniki.json) | Zapis wyników z założeniami |

Kontrakty: [radio](../../docs/spec/radio.md), [oprogramowanie](../../docs/spec/oprogramowanie.md). Licencja kodu i SQL: [MIT](../../LICENSES/MIT.txt); opisy i raporty: CC-BY-4.0.

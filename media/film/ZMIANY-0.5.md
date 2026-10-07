# Film: zmiany potrzebne po koncepcji 0.5

Film opisuje wariant 0.4: stację złożoną z laptopa, routera i modułu radiowego oraz odbiorcę „straż”. Koncepcja 0.5 zmienia podstawę systemu na samodzielną stację z ekranem, przyciskami i ogniwami AA. Laptop i router są w niej rozszerzeniami, a odbiorcą jest gmina. Poniżej są segmenty do zmiany. Render wymaga narzędzi z [README](README.md), w tym płatnego TTS; po renderze trzeba odświeżyć manifest.

## Film 4 min (`narracja.py`, `wici_film.py`)

| Segment | Obecnie | Propozycja | Powód |
|---|---|---|---|
| s1d | straż pożarna, która mogłaby pomóc | gmina i straż, które mogłyby pomóc | odbiorca to centrum zarządzania kryzysowego gminy ([02](../../docs/conception/02-scenariusze-i-organizacja.html#miejsce-w-systemie-ochrony-ludnosci)) |
| s4d | przeleci przez eter w mniej niż sekundę | przeleci przez eter w około sekundę | typowe zgłoszenie to datagram 387 B i 0,89 s nadawania, a największe ponad 1 s ([wyniki](../../software/reference/wyniki.json)) |
| s4e | korzystają też czujniki i piloty | korzystają też inne sieci radiowe | kanał dzielą LoRaWAN i Meshtastic ([07](../../docs/conception/07-zagrozenia-i-odpornosc.html)) |
| s5c | aż dotrze do straży | aż dotrze do gminy | jak s1d |
| s6a–s6e | stary laptop, router, akumulator; antena za oknem; strona w telefonie | „To małe pudełko z ekranem, kilkoma przyciskami i bateriami. Włączam je, wystawiam antenę i jestem w sieci.” „Opiekun wybiera przyciskami, czego brakuje i ilu osób to dotyczy.” „Każda włączona stacja podaje dalej wiadomości sąsiadów.” „Później można dołączyć stary laptop i domowy router; wtedy mieszkańcy zgłaszają potrzeby zwykłą stroną w telefonie.” | samodzielna stacja, poziomy zestawu ([01](../../docs/conception/01-potrzeby-i-wymagania.html#poziomy-zestawu)) |
| s6c | antena wystawiona za okno | antena wystawiona możliwie wysoko | przy antenach na wysokości okien model daje ujemny zapas na 1 km ([06](../../docs/conception/06-wykonalnosc-i-budzet-zasobow.html#zasieg)) |
| s7b | Zapisane w straży. | Zapisane u odbiorcy. | jak s1d |
| s8a | projekt pierwszej płytki elektroniki | płytka do pomiarów radia; płytka stacji dopiero powstanie | R01.3 jest stanowiskiem laboratoryjnym |
| s8b | Czy stacja wytrzyma dobę na akumulatorach. Czy laptop z szuflady zawsze wystartuje. | Czy stacja wytrzyma dwie doby na bateriach. Czy oprogramowanie sieci zmieści się w małym układzie. | nowe najważniejsze niewiadome (W23, F10 w [przeglądzie](../../docs/review.md)) |

Obraz: scena stacji w `wici_film.py` pokazuje laptop, router i akumulator 12 V. Trzeba ją zastąpić pudełkiem z ekranem, przyciskami i anteną; laptop i router pojawiają się później jako dodatek. Etykiety „straż” w scenie s1 i w scenie stanów zmienić na „gmina” lub „odbiorca”.

## Wersja 60 s (`narracja_short.py`, `wici_short.py`)

| Segment | Propozycja |
|---|---|
| v2 | „Gmina jest kilka kilometrów dalej. Tylko jak jej o tym powiedzieć?” |
| v3 | „Wystarczy proste radio na bateriach.” |
| v4 | „…aż dotrze do gminy.” |
| v5 | „Stacja to małe pudełko z ekranem, przyciskami i bateriami. Włączam, wystawiam antenę i jestem w sieci. Laptop i router można dołączyć później.” |

Etykiety „straż” w `wici_short.py` zmienić tak jak w filmie 4 min.

## Kolejność odtworzenia

1. Zmienić teksty w `narracja.py` i `narracja_short.py` oraz sceny w `wici_film.py` i `wici_short.py`.
2. `tts.py` dla zmienionych zdań (cache w `build/tts`), render Manim, `napisy.py`, końcowe wyrównanie głośności.
3. Sprawdzić zgodność `.srt` z narracją, odświeżyć `manifest.json` i usunąć ten plik.

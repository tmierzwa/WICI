# Zajętość kanału: pomiar NESDR przez godzinę (2026-11-14, 13:56–14:56)

Pytanie: czy w kanale sieci (869,525 MHz, 125 kHz) i w podzakresie 869,40–869,65 MHz nadaje ktoś poza naszymi urządzeniami. Podsłuch na RAK4631 słyszy tylko ramki w profilu sieci (SF7, BW 125 kHz, słowo synchronizacji 0x12), więc do pomiaru użyto odbiornika SDR, który widzi każdą emisję w paśmie.

## Układ

- NESDR SMArt v5 (RTL2832U, R820T) na stole obok zestawów L0. Strojenie 869,30 MHz, 1,024 MS/s, wzmocnienie 40 dB.
- Analiza (`kanal-nesdr-2026-11-14-sdrscan.py`, wejście z `rtl_sdr -f 869300000 -s 1024000 -g 40 -`): bloki 10 ms (10 widm FFT 1024, 1 kHz na pas). Emisja to blok, w którym co najmniej 5 pasów leży 8 dB nad szumem. Kolejne takie bloki tworzą jedną emisję. Zapis: `kanal-nesdr-2026-11-14-events.jsonl` (emisje: początek, czas, częstotliwość szczytu, szerokość −10 dB, szczyt nad szumem) i `kanal-nesdr-2026-11-14-minutes.jsonl` (zajętość co minutę).
- Równolegle podsłuch RAK4631 w profilu sieci: `podsluch-kanal-2026-11-14.jsonl`.
- Sprawdzenie przed pomiarem: ramki z RAK4631 przy −9 dBm NESDR wykrył jako emisje o szerokości około 125 kHz.
- Zestawy L0 były włączone w planie trzech skoków, bez ruchu zgłoszeń.

## Wynik

| Zakres | Zajętość w godzinie | Najwięcej w minucie |
|---|---|---|
| podzakres 869,40–869,65 MHz | 0,66% | 2,85% (14:52) |
| nasz kanał 869,4625–869,5875 MHz | 0,23% | 1,92% (14:52) |
| nasze ramki (podsłuch) | 0,075% (2,7 s) | |

Szum stały przez całą godzinę (wahania 1,3 dB). W 7 minutach z 61 nie było żadnej emisji.

### Nasze emisje

Podsłuch odebrał 10 ramek, wszystkie to BEACON-y (14:48:08–14:52:17, od roota jedna, od pozostałych trzech urządzeń po trzy). NESDR ma emisję w czasie każdej z nich, około 265 ms, 125 kHz, 50–60 dB nad szumem. Są to jedyne tak silne emisje w pomiarze. Przed 14:48 nasze urządzenia nie nadały nic przez 52 minuty. Trzy BEACON-y co 2 min to początek cyklu ogłoszeń (`firmware/src/main.cpp`: trzy pierwsze co 2 min, potem co 24–36 min). Przyczyny wznowienia o 14:48 nie badałem.

### Obce emisje

Wszystkie pozostałe emisje są obce: podsłuch ich nie odebrał, a są o 15–55 dB słabsze od naszych.

1. **Nadajnik okresowy w naszym kanale.** 24 emisje po około 263 ms, szerokość 115–126 kHz, 10–25 dB nad szumem. Okres wynosi dokładnie 128,0 s, z przerwami co do wielokrotności okresu. Pojawia się od 14:00 do końca pomiaru. Czas i szerokość odpowiadają ramce LoRa przy 125 kHz, ale podsłuch jej nie dekoduje, więc nadajnik ma inny współczynnik rozpraszania, inne słowo synchronizacji albo inną modulację. Nadajnika nie zidentyfikowano.
2. **Krótkie impulsy.** 299 emisji do 30 ms, głównie przy 869,57, 869,64 i 869,44 MHz, 5–35 dB nad szumem. Razem 3,2 s.
3. **Dłuższe emisje.** 56 emisji od 30 ms do 1,2 s, najczęściej około 120–140 ms, przy 869,64, 869,44 i 869,57 MHz. Razem 13,6 s.

Wąskie emisje przy 869,44 MHz (szerokość kilka kHz) mogą pochodzić z samego odbiornika. Pomiar tego nie rozstrzyga.

## Wnioski

- Kanał nie jest pusty, ale obca zajętość jest mała: około 0,15% w naszym kanale i około 0,6% w podzakresie. To dwa rzędy wielkości mniej niż 10% obciążenia we wstępnej próbie węzła wrogiego. Wynik tamtej próby (20/20 w obu przebiegach) nie zależał więc od obcego ruchu.
- W naszym kanale nadaje obcy nadajnik co 128 s, z ramką długości naszego BEACON-u. W tym miejscu jest słaby, ale w innym może być silny. CAD przed nadaniem może go wykrywać jako zajęty kanał. Podsłuch w profilu sieci go nie widzi, więc pomiar zajętości tylko z podsłuchu zaniża udział innych systemów.
- Jedna godzina w jednym miejscu, w dzień roboczy. Pomiar nie mówi nic o innych porach ani miejscach.

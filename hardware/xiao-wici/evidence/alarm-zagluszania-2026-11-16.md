# Próba 17: alarm zagłuszania na roocie bez ruchu, w panelu i zwykły ruch (2026-11-16 13:10 – 2026-11-17 08:50)

Procedura: [próba 17](../README.md#próba-17-alarm-zagłuszania-kanału), krok 2, w piwnicy. Uzupełnia [noc z 2026-11-15](piwnica-noc-2026-11-15.md), w której alarmowała tylko A, bo root nie miał nic do nadania. Od specyfikacji 0.60 (R3-46) root sprawdza kanał co 5 s także bez ruchu.

Plan łańcucha jak w próbie 12: A (P001, 20) → XIAO nr 2 (30) → B (P002, 10) → root (XIAO nr 1). Węzeł wrogi: RAK4631 bez klucza sieci, śmieciowe ramki, 90%, −9 dBm, wkład przewodzony, 20 min. Na A nie było zgłoszeń, więc żadna stacja nie miała własnego ruchu.

Dowody:
- przebieg z panelem: `alarm-zagluszania-panel-l0-2026-11-16.out`, skrypt `alarm-zagluszania-panel-skrypt.sh`, podsłuch `podsluch-jam90root2-l0-2026-11-16.jsonl`, węzeł wrogi `wrogi-jam90root2-l0-2026-11-16.jsonl`;
- przebieg z licznikami roota: `alarm-zagluszania-root-l0-2026-11-16.out`, skrypt `alarm-zagluszania-root-skrypt.sh`, podsłuch `podsluch-jam90probe-l0-2026-11-16.jsonl`, węzeł wrogi `wrogi-jam90probe-l0-2026-11-16.jsonl`.

**Odrzucony przebieg.** Pierwszy przebieg tego dnia (12:51) odrzucono. Oba XIAO po odłączeniu od zasilania straciły konfigurację (FRAM w PSRAM), czego nie sprawdzono przed startem. Po nowym przygotowaniu wszystkie cztery węzły dostały plan od nowa. Przed każdym przebiegiem trzeba sprawdzić w `STORE` pole `configured`.

## Przebieg 1: panel stanowiska (13:10:36–13:30:45)

Obrazy z `main` `29d15b10` na wszystkich węzłach. Stanowisko z portem diagnostycznym roota (`--diagnostyka`). Co około 10 s skrypt czytał `/health`, kolejkę panelu i `P1` z A, B i XIAO nr 2. Zajętość kanału 0,90001.

| Gdzie | Alarm włączony | Alarm zgasł |
|---|---|---|
| panel stanowiska, „KANAŁ ZAGŁUSZONY PRZY WĘŹLE” | 13:15:55 | przed 13:31:04 |
| `/health` stanowiska (`node.channel_jammed`) | 13:16:05 | przed 13:31:04 |
| B | 13:15:46 | po 13:30:35 |
| XIAO nr 2 | 13:15:47 | po 13:30:35 |
| A | brak alarmu | – |

Panel pokazuje alarm przy roocie około 5 min po starcie zagłuszania i zdejmuje go po jego końcu.

**Zastrzeżenie: root nie był bez ruchu.** Po nowym przygotowaniu root, B i XIAO nr 2 miały ramki do nadania (prawdopodobnie BEACON-y i ogłoszenia). Przez całe zagłuszanie czekały na wolny kanał: root miał po przebiegu `deferrals` 1112, a B urósł z 16 do 2063 przy `tx_datagrams` stojącym na 56. Dlatego alarmowały jednocześnie, a alarm roota mógł przyjść drogą „mam ramkę i nie mogę nadać”. Ten przebieg potwierdza panel, nie samo sprawdzanie kanału bez ruchu.

## Przebieg 2: root bez ruchu (15:35:08–15:55:10)

Na roocie obraz z `main` `86c0e44a`, z licznikami `probes` (sprawdzenia kanału bez ruchu) i `probe_busy` (sprawdzenia, które trafiły na zajęty kanał). Reszta węzłów bez zmian. Root wgrany bez odłączania od zasilania, konfiguracja została (`configured` true). Przed startem przez minutę żaden węzeł nie zwiększył `tx_datagrams` ani `deferrals`. Stanowisko pracowało bez portu diagnostycznego, bo ten port czytała konsola roota; alarm w panelu sprawdzał przebieg 1. Co około 10 s skrypt czytał `P1` i `INFO` ze wszystkich czterech węzłów. Zajętość kanału 0,900019.

| Root | Przed | Po | 
|---|---|---|
| `probes` | 37 | 345 |
| `probe_busy` | 1 | 235 |
| `tx_datagrams` | 1 | 1 |
| `tx_drop` | 0 | 2 |
| `deferrals` | 0 | 60 |
| `no_gap_ms_max` | 0 | 1194230 (19,9 min) |

- Root sprawdzał kanał co 5 s: 308 sprawdzeń w 26 min. W czasie zagłuszania 234 z około 240 trafiło na zajęty kanał, a przed nim i po nim prawie żadne.
- Root miał dwie własne ramki, o 15:36 i 15:38. Obie odrzucił po wyczerpaniu odroczeń (`tx_drop` 2, `deferrals` 60). Od 15:38:25 nie miał nic do nadania, a `deferrals` nie rosły do końca przebiegu.
- `channel_jammed` na roocie: włączony 15:40:18, 5 min 10 s po starcie zagłuszania i 2 min po ostatniej ramce do nadania; 96 kolejnych odczytów; zgasł przed 15:55:10, w chwili końca zagłuszania. Alarm trzymał się 15 min wyłącznie na sprawdzaniu kanału bez ruchu.
- A, B i XIAO nr 2 bez alarmu. Nie miały własnych ramek; XIAO nr 2 miał jedną ramkę (`deferrals` 2020 → 2050, `tx_drop` 66 → 67), za krótko na próg.

**Próg CCA na roocie.** Próg to podłoga szumu plus 10 dB. W czasie zagłuszania i po nim progi wynosiły: A −97…−95, B −98…−97, XIAO nr 2 −86…−83, root (XIAO nr 1) −80…−73 dBm. L0 i XIAO nr 2 nie podnoszą progu w zagłuszaniu, więc to nie przeciek węzła wrogiego. Root ma −72…−73 dBm także bez zagłuszania (noc z 2026-11-15 i doba od 16:07); −85 było tylko tuż po starcie. Podłoga szumu wynosi więc około −83 dBm na XIAO nr 1, −94 na XIAO nr 2 i −107 na L0. Z wyłączonym stanowiskiem (zamknięty port danych, otwarta tylko konsola) root miał tak samo −72 dBm (15:31–15:33, przed startem stanowiska), więc port danych do stanowiska nie podnosi progu. Konsolę USB z odczytem co 10 s mają też XIAO nr 2 i oba L0, a ich progi są niskie. Różnica dotyczy więc tej jednej płytki albo jej miejsca na stole, nie samego połączenia USB. CCA na roocie jest przez to mniej czułe na słabą obcą energię. Wykrywania zagłuszania to nie zmienia, bo opiera się na odbiorniku (preambuła, nagłówek, ramka), a nie na samym RSSI.

Dwa pomiary 2026-11-17 po przebiegu 3, przy zwykłym ruchu łańcucha:
- Zamiana miejsc obu XIAO razem z antenami, bez odłączania USB (08:57–09:03, odczyt co 50 s): XIAO nr 1 (root) z −72…−73 na −74…−75 dBm, XIAO nr 2 z −83…−84 na −80…−81 dBm. Wysoki próg idzie głównie za płytką XIAO nr 1 (różnica około 6 dB zostaje); miejsce dokłada około 2–3 dB.
- L0 z otwartym portem danych: na A (P001) połączenie protokołem stanowiska z jego portem danych przez 8 min (09:04:50–09:12:50, `connected` od 09:05:20), bez własnych zgłoszeń. Próg −97 dBm przed, w trakcie i po, tak samo jak bez portu (−96…−97). Otwarty port danych nie podnosi progu L0. L0 jako roota ze stanowiskiem nie sprawdzono, bo wymagałoby to przekonfigurowania łańcucha, a powyższe dwa pomiary wskazują na płytkę XIAO nr 1.

## Przebieg 3: zwykły ruch bez węzła wrogiego (2026-11-16 16:07:41 – 2026-11-17 08:50:24)

Krok 3 procedury, skrócony z 24 h do 16 h 43 min decyzją właściciela. Uzasadnienie: najdłuższy czas bez wolnej przerwy przez cały przebieg wynosił 0–1 ms przy progu alarmu 5 min, piwnica nie ma dobowego rytmu obcego ruchu (ruch to tylko BEACON-y i zgłoszenia próby, każda godzina wygląda tak samo), a pamięć B stała od startu. Pełna doba dałaby tylko pewność co do liczników i zegarów po kilkunastu godzinach.

Ten sam łańcuch i te same obrazy co w przebiegu 2 (root z `main` `86c0e44a`, reszta z `29d15b10`), węzeł wrogi wyłączony, stanowisko bez portu diagnostycznego. Zamiast `REQ 1` na A (procedura) `REQ 1` co 30 min na XIAO nr 2: rejestr zgłoszeń A był pełny (256 zgłoszeń bez decyzji z poprzednich prób), a nowe miejsce zwalnia dopiero zamknięcie albo anulowanie zgłoszenia. Co minutę skrót `P1` i `INFO` z czterech węzłów, co godzinę pełne `P1`, `INFO` i `RNS` (pamięć). Dowody: `doba-zwykly-ruch-l0-2026-11-16.out`, skrypt `doba-zwykly-ruch-skrypt.sh`, podsłuch `podsluch-doba-l0-2026-11-16.jsonl` (przerwany razem z przebiegiem, bez wiersza podsumowania).

XIAO nr 2 dostał o 17:28 omyłkowy RESET (`restarts` 4 → 6, konfiguracja została), więc jego liczniki obejmują 15 h 22 min. Poza tym żaden węzeł się nie zrestartował.

| Węzeł | `no_gap_ms_max` | `channel_jammed` | `tx_datagrams` | `tx_drop` | `deferrals` | `rx_ok` / `rx_bad` | próg CCA (dBm) |
|---|---|---|---|---|---|---|---|
| A (P001) | 0 | ani razu | 35 | 0 | 0 | 550 / 446 | −99…−96 |
| B (P002) | 1 | ani razu | 254 | 0 | 1 | 329 / 22 | −97…−93 |
| XIAO nr 2 (od 17:28) | 0 | ani razu | 136 | 0 | 0 | 397 / 2 | −84…−83 |
| root (XIAO nr 1) | 0 | ani razu | 147 | 0 | 0 | 436 / 2 | −73…−72 |

- Alarmu nie było na żadnym węźle w żadnym z 4012 odczytów minutowych. Root sprawdził kanał bez ruchu 12 033 razy (`probes` 23 → 12 056), 34 razy trafił na zajęty kanał (`probe_busy` 1 → 35), czyli na cudze ramki łańcucha.
- Wszystkie 34 zgłoszenia z XIAO nr 2 są w panelu stanowiska.
- Pamięć B: `heap_free` 148 044 B we wszystkich 18 odczytach, `heap_min` 142 552 → 142 544 B. Na pozostałych węzłach też bez trendu (A 147 948 B stale; XIAO mają PSRAM, wahania poniżej 100 B).
- Podsłuch: 581 ramek, wszystkie z poprawnym CRC (BEACON 145, DATA 218, HACK 218).

**Odrzucone ramki na A.** A miał `rx_bad` 446 przy `rx_ok` 550, równo około 27 na godzinę przez cały przebieg, a pozostałe węzły po 2–22. Podsłuch w tym samym torze nie widział żadnej ramki z błędnym CRC. `rx_bad` liczy przepełnienie, złą długość, ramkę niepełną i ramkę, której nie da się rozebrać; powodu odrzucenia konsola nie pokazuje, a portu diagnostycznego A nikt nie czytał. Dostarczenia to nie zepsuło (zgłoszenia i potwierdzenia przeszły), ale przyczyny nie ustalono. Do wyjaśnienia przez program, z portem diagnostycznym A.

**Próg alarmu.** Rozkład `no_gap_ms_max` ze wszystkich przebiegów próby 17: zwykły ruch bez węzła wrogiego co najwyżej 1 ms (przebieg 3), 50% 3–8 s, 70% 15 s ([noc z 2026-11-15](piwnica-noc-2026-11-15.md#próg-alarmu)), 90% bez wolnej przerwy przez całe 20 min. Próg musi być dłuższy niż przerwy przy ruchu prawdziwym i krótszy niż czas zagłuszania, które ma wykryć. Proponuję zostawić `JAM_ALARM_MS` 5 min: zapas 20 razy wobec 70%, a przy 90% alarm przychodzi po około 5 min (przebiegi 1 i 2). Zmiana stałej należy do programu.

## Wynik

- Root alarmuje o zagłuszaniu bez ruchu (R3-46): spełnione. Alarm po około 5 min, zgaśnięcie z końcem zagłuszania, przy braku własnych ramek do nadania (przebieg 2).
- Panel stanowiska pokazuje alarm przy roocie i go zdejmuje: spełnione (przebieg 1).
- Stacje i przekaźniki bez ruchu nie alarmują, z ruchem tak (R3-43): spełnione (przebieg 2 i noc z 2026-11-15).
- Brak alarmu przy zwykłym ruchu (krok 3): spełnione w wersji skróconej do 16 h 43 min (decyzja właściciela), `no_gap_ms_max` 0–1 ms, pamięć B stała (przebieg 3).
- Próba 17 **spełniona**, z krokiem 3 skróconym. Otwarte: odrzucone ramki na A. Próg CCA na roocie wynika głównie z płytki XIAO nr 1 (zamiana miejsc), a otwarty port danych nie podnosi progu L0.

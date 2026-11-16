# Próba 17: alarm zagłuszania na roocie bez ruchu i w panelu (2026-11-16, 13:10–16:01)

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

**Próg CCA na roocie.** XIAO nr 1 miał `cca_threshold_dbm` −85 tuż po starcie i −73…−74 dBm w przebiegu. Węzły L0 mają −96…−97, XIAO nr 2 −83…−84. Wyższy próg na roocie nie przeszkodził w wykryciu zagłuszania (sygnał wrogi przewodzony, około −52 dBm w podsłuchu). Przyczynę, np. szum własny XIAO nr 1, ustala sesja od programu.

## Wynik

- Root alarmuje o zagłuszaniu bez ruchu (R3-46): spełnione. Alarm po około 5 min, zgaśnięcie z końcem zagłuszania, przy braku własnych ramek do nadania (przebieg 2).
- Panel stanowiska pokazuje alarm przy roocie i go zdejmuje: spełnione (przebieg 1).
- Stacje i przekaźniki bez ruchu nie alarmują, z ruchem tak (R3-43): spełnione (przebieg 2 i noc z 2026-11-15).
- Próba 17 nadal **spełniona częściowo**: brakuje 24 h zwykłego ruchu bez węzła wrogiego (krok 3) na obrazach z `main` `86c0e44a` lub nowszych, z odczytem `no_gap_ms_max` i pamięci B.

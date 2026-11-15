# WICI: próby D21 przy stole z zestawami XIAO

Procedura prób przy stole dla decyzji D21 ([warunek przyjęcia](../../docs/spec/transport.md#warunek-przyjęcia), [WICI-Link v3](../../docs/spec/wici-link.md)): dwa prototypy na płytce v1 z obrazem [`l0`](../../firmware/docs/prototyp-l0-i-xiao.md#stacja-l0-l0), dwa zestawy Seeed 102010611 (XIAO ESP32-S3 + Wio-SX1262) z obrazem [`xiao`](../../firmware/docs/prototyp-l0-i-xiao.md#zestaw-xiao-xiao) i dwa RAK4631 z zestawów [radiów RNode](../rnode/README.md), na czas prób z narzędziem surowego LoRa [`lora-raw`](../lora-raw/README.md) zamiast firmware RNode ([dlaczego](#podsłuch-i-węzeł-wrogi-lora-raw)). Stan: na dwóch zestawach XIAO (root i stacja A w jednym przeskoku, bez przekaźnika B) próby 2, 3, 4, 5 i 11 przeszły w wersji z jednym przeskokiem: 2026-11-02 próby 2 (bez ramek 255 B), 4, 5 i 11 skrócona do 3 min ([raporty](evidence/xiao-zestaw-2026-11-02.md)), 2026-11-03 próba 2 z ramkami 255 B, próba 3, pełna próba 11 oraz próby 4 i 5 przed poprawką dostępu do kanału i po niej ([raporty](evidence/xiao-zestaw-2026-11-03.md), [dostęp do kanału](evidence/cca-cad-2026-11-03.md)); 2026-11-14 na prototypach l0 w łańcuchu A → B → root (B: l0 nr 2, root: XIAO nr 1) przeszły próby 2, 3, 4, 5, 6 (w części z próbą 5), 7 (6 odcięć zamiast 15, decyzja właściciela), 8, 10 i 11; próba 9 rano tylko w wersji wstępnej w eterze przy 10% zajętości ([raporty](evidence/l0-zestaw-2026-11-14.md)); po poprawkach programu (`main` `32a5f2d6`) próby 3, 4 i 11 przeszły ponownie ([raport](evidence/ponowne-3-4-11-2026-11-14.md)); wieczorem w pomieszczeniu odizolowanym przeszła próba 9, oba przebiegi po 2 h przy 50% ([raport](evidence/wrogi-2026-11-14.md)), a próba 7 dostała 9 dalszych odcięć, razem 15 ([raport](evidence/zanik-B-2026-11-14.md)).

Zestaw XIAO nie ma FRAM: obraz FRAM jest w PSRAM i ginie po odłączeniu zasilania ([opis](../../firmware/docs/prototyp-l0-i-xiao.md#zestaw-xiao-xiao)). Dlatego zestawy XIAO nie biorą udziału w próbach zaniku zasilania, a wyniki z nich nie zastępują prób prototypu ani stacji na płytce v2 w energii (W23), zapasie RAM (D14), zaniku zasilania i czułości. Poza zakresem: W23 (wymaga toru zasilania v2) i zasięg.

## Role

| Urządzenie | Rola | Numer w planie (przykład) |
|---|---|---|
| l0 nr 1 | stacja schronienia A (ekran, przyciski) | 20, rodzic 10 |
| l0 nr 2 | przekaźnik B z prawdziwą FRAM (próby zaniku zasilania trwałej kolejki) | 10, rodzic 1 |
| XIAO nr 1 | root: KISS przez port danych USB do aplikacji stanowiska na laptopie | 1 (`role: "wezel"`) |
| XIAO nr 2 | druga stacja schronienia C (dwa źródła przez jeden przekaźnik, K1 na sąsiada) albo drugi przekaźnik (łańcuch 3 skoków) | 30, rodzic 10 albo 20 |
| RAK4631 nr 1 | `lora-raw` jako podsłuch kanału: surowe ramki, czasy RxDone, RSSI, SNR (`tools/monitor.py`) | – |
| RAK4631 nr 2 | `lora-raw` jako węzeł wrogi sterowany skryptem `tools/hostile.py` | – |

Przy jednym prototypie l0 bierze on rolę przekaźnika B, a stacją A jest XIAO nr 2. Tożsamości odbiorcy (główna 2, zapasowa 3) i sieć (np. `net_id` 100, kod IFAC) tworzy aplikacja stanowiska: `python -m wici.stanowisko przygotuj … --net-id 100 --main-id 2 --backup-id 3 --root-id 1 --ifac <32 cyfry hex>` ([aplikacja stanowiska](../../software/laptop/README.md#aplikacja-stanowiska-odbiorczego)). Wieloskokowość wymusza plan sieci (`network.parent`, `priority_keys[].behind`), nie odległość: wszystkie urządzenia stoją na jednym stole.

## Stół i radio

- Anteny przykręcone przed zasilaniem albo obciążenia 50 Ω zamiast anten; urządzenia 1–3 m od siebie. Obrazy stacji nadają stałą mocą 13 dBm (nie ma polecenia zmiany mocy), RAK4631 z `lora-raw` z mocą −9 dBm (najmniejsza; polecenie `power`). Próba 9 wymaga toru przewodowego, komory ekranowanej albo pomieszczenia odizolowanego ([niżej](#próba-9-tylko-w-torze-przewodowym-w-komorze-albo-w-pomieszczeniu-odizolowanym)).
- Zestawy XIAO zasilać z USB komputera bez przerw przez całą serię prób; po odłączeniu zasilania zestaw trzeba przygotować od nowa (niżej).
- Na każdym porcie diagnostyki zapis do pliku przez cały czas próby, np. `pio device monitor -p PORT -b 115200 -f log2file` (pliki `platformio-device-monitor-*.log`). Zegary laptopów zsynchronizowane (NTP) przed próbą.
- Dowody: katalog `hardware/xiao-wici/evidence/` w PR z raportem, plik `<próba>-RRRR-MM-DD.md` (wersje obrazów z `INFO`, numery egzemplarzy, plan sieci bez kluczy prywatnych, przebieg, wynik, odchylenia) i surowe logi obok niego. Raport z próby jako Issue z etykietą `próba` ([CONTRIBUTING](../../CONTRIBUTING.md#jak-zgłosić-zmianę)); kolumnę „Stan” w [odbiorze](../../docs/spec/odbior.md) wypełnia opiekun repozytorium.

## Wgranie i przygotowanie

1. Zestaw XIAO: przed pierwszym wgraniem kopia fabrycznej pamięci według [radio-pair](../radio-pair/ZRODLA-I-WERYFIKACJA.txt). Wgranie: `cd firmware && pio run -e xiao -t upload` (port USB-C XIAO; bez odpowiedzi BOOT przytrzymany przy RESET). Prototyp: `pio run -e l0 -t upload`. Nie wgrywać `l0` do XIAO ani `xiao` do prototypu.
2. Każde urządzenie: `INFO` (`radio_ok`, `p1_ok`, `fram_ok`, `journal_ok` = `true`, `fw` `xiao-0.1` albo `l0-0.6`, w XIAO `fram_volatile: true`), `RADIO` (`version` „SX1261 V2D 2D02”, `device_errors` 0x0000), `FRAM` (XIAO: `emulated-psram`, `kept: false` po włączeniu zasilania), `RNS SELFTEST`.
3. Tryb przygotowania: na prototypie przycisk przygotowania (3 s) albo `PREP 1` z OK; na XIAO `PREP 1` i przycisk BOOT w ciągu 30 s (żółta dioda miga szybko).
4. Karta każdej stacji: aplikacja laptopa w trybie przygotowania (`card`, także przed pierwszym `configure`, odcisk na ekranie prototypu albo w `SCREEN` XIAO, zamknięcie `KEY OK`). Z kart powstaje plan sieci: dla każdej stacji `network` (numer, root, rodzic, rodzic zapasowy 0 albo numer) i `priority_keys` sąsiadów (`ed25519`, `x25519`; `behind` tylko u roota); każda stacja ma w `priority_keys` także roota, gdy nie jest jej sąsiadem (bez klucza roota stacja nie sprawdzi jego BEACON-ów i WICI-Link nie startuje: „wici neighbor signing key missing from station card”; klucz roota u stacji, dla której root nie jest rodzicem z planu ani zapasowym, służy tylko do podpisu epoki, a root nie musi mieć klucza takiej stacji), dla stacji schronienia karta odbiorcy z nośnika stanowiska; dla roota `role: "wezel"`, a w jego wpisie przekaźnika B `behind` ze stacjami za B (A: 20, C: 30; root uczy się drogi w dół tylko według planu).
5. `configure` z aplikacji laptopa na każdej stacji (`ok` z `config_seq`). Po `ok` urządzenie restartuje się samo, gdy zmieniła się rola, gdy stacja ma numer w sieci albo gdy WICI-Link już działał: WICI-Link startuje tylko przy starcie, więc nowa konfiguracja działa od razu, bez ręcznego `REBOOT`. Tryb przygotowania wraca po tym restarcie sam (nie trzeba ponownie BOOT), więc kolejne `configure` i `card` idą bez przerwy. W XIAO `FRAM` daje potem `kept: true`, a na roocie `STORE` `role: "wezel"`. Na koniec `PREP 0`. Na roocie port danych przejmuje `python -m wici.stanowisko start --nosnik … --port PORT_DANYCH_XIAO1`; hasło można podać potokiem (`echo HASŁO | …`), a koniec wejścia nie zatrzymuje aplikacji (kończy ją Ctrl+C albo SIGTERM, z ostatnią migawką bazy).
6. Gotowość: w `LOG` „wici station ready” (stacje) albo „wici root ready” (root); BEACON-y roota i przekaźników widać w podsłuchu (RAK4631 nr 1, klasa `BEACON`, ramki 156 B).

**Po odłączeniu zasilania zestawu XIAO** (także przypadkowym): `LOG` ma „FRAM image in PSRAM cleared”, stacja ma nową tożsamość i nie ma konfiguracji. Odczytać nową kartę, wpisać jej klucze w `priority_keys` sąsiadów i skonfigurować sąsiadów ponownie; stary numer przechodzi na nowy klucz przepięciem w panelu (dodanie karty, potwierdzenie „Przepnij numer”, zgoda dwóch dyżurnych; [stanowisko-osp.md, „Zaufanie”](../../docs/spec/stanowisko-osp.md)). Bieżącą próbę zapisać jako przerwaną.

## Podsłuch i węzeł wrogi (lora-raw)

Plan zakładał RAK4631 z oficjalnym firmware RNode w obu rolach. To nie działa z WICI-Link v3. Firmware RNode (`56775c51`) w zwykłym trybie dokłada do każdej ramki LoRa nagłówek 1 B (starsza połówka: numer, bit 0: flaga podziału `FLAG_SPLIT`) i przy odbiorze zawsze zdejmuje pierwszy bajt jako ten nagłówek. Ramka v3 nie ma nagłówka RNode, a bit 0 jej pierwszego bajtu to ACKREQ. RNode jako podsłuch oddaje więc ramki bez bajtu `ver/t`, a jednoadresową DATA z ACKREQ traktuje jak pierwszą połowę datagramu dzielonego: skleja ją z następną DATA z ACKREQ albo gubi przy następnej ramce bez bitu 0 (HACK, BEACON). Jako nadajnik RNode dokłada przed ramką z hosta bajt z losowymi bitami, więc stacja odrzuca ją (MAC). Tryb nasłuchu wszystkiego (`CMD_PROMISC`) na nRF52 w tym commicie nie oddaje odebranych ramek do hosta; RNode nie podaje też czasów RxDone i TxDone, nie zgłasza ramek z błędem CRC, odracza nadanie przy zajętym kanale (CSMA) i nie schodzi z mocą poniżej 0 dBm. Szczegóły ze źródłami: [lora-raw, „Dlaczego nie RNode”](../lora-raw/README.md#dlaczego-nie-rnode).

Dlatego oba RAK4631 dostają na czas prób program [`lora-raw`](../lora-raw/README.md): profil pilotażu, surowe bajty w obie strony, czasy z zegara urządzenia (µs), moc od −9 dBm. Wgranie: `cd hardware/lora-raw && pio run -t upload --upload-port PORT`; sprawdzenie: w terminalu portu `info` daje `"ready":true` i profil (`preamble` 24, `sync_word` 18). **Po próbach** oba zestawy wracają do firmware RNode (`rnodeconf --autoinstall`, [radia RNode](../rnode/README.md)) przed pomiarami zasięgu; wersję z `rnodeconf --info` zapisuje się w raporcie.

Skrypty są w `hardware/xiao-wici/tools/` i uruchamia się je z katalogu `hardware/xiao-wici` (Python 3 i `pyserial`; ramki z kluczem z `software/laptop/wici/stanowisko/wici_link.py`, czas ramki ze wzoru modelu `software/reference/obliczenia.py`):

- **Podsłuch (RAK4631 nr 1):** `python3 tools/monitor.py PORT --out evidence/podsluch-RRRR-MM-DD.jsonl [--ifac <32 cyfry hex> --net-id 100] [--duration S]`. Każda ramka to wiersz JSONL: czas laptopa (`host_ts`), czas RxDone urządzenia (`t_us`) i wyliczony początek (`start_us`), surowe bajty (`hex`), długość, RSSI, SNR, CRC, czas w eterze i, gdy bity wersji to 3, pola nagłówka v3 (`version`, `type`, `flags`, `net_id`, `l_src`, `l_dst`, `hops`, `ttl`, `seq`); z kodem sieci także `mac_ok`. Na końcu (Ctrl+C albo `--duration`) podsumowanie: ramki i czas w eterze na klasę (`DATA`, `HACK`, `BEACON`, `crc_error`, `other`), czas w eterze na `l_src` i zajętość kanału w %. W próbie 4 czas HACK z podsłuchu to `t_us` HACK minus `t_us` jego DATA (ten sam zegar; HACK ma `seq` tej DATA i zamienione `l_src`, `l_dst`).
- **Węzeł wrogi (RAK4631 nr 2):** (a) bez klucza: `python3 tools/hostile.py PORT --mode junk --conducted --out evidence/wrogi-a-RRRR-MM-DD.jsonl` — losowe bajty 20–255 B w profilu (pierwszy bajt bez bitów wersji 3); (b) z kluczem sieci jak przejęta stacja: `python3 tools/hostile.py PORT --mode keyed --conducted --ifac <32 cyfry hex> --net-id 100 --dst 10 --out evidence/wrogi-b-RRRR-MM-DD.jsonl` — rozsyłane DATA z losowymi kopertami, BEACON-y ze śmieciowymi podpisami, jednoadresowe DATA z ACKREQ i HACK z losowym tagiem pary, od losowych `l_src` (`--src` zawęża), w proporcjach `--mix data=2,beacon=1,unicast=1,hack=1`. Domyślnie 50% czasu kanału (`--occupancy 0.5`), 2 h (`--duration 7200`), −9 dBm (`--power`), bez CAD i bez długu ciszy. Zajętość trzyma się z czasów TxDone zmierzonych przez urządzenie: kolejne nadanie zaczyna się, gdy suma czasów nadawania od pierwszej ramki podzielona przez czas od jej początku spadnie do celu, więc opóźnienie USB tylko skraca następną przerwę. Każde nadanie (bajty, `start_us`, `done_us`, `air_us`, rodzaj, `l_src`, `l_dst`, `seq`) i podsumowanie z osiągniętą zajętością idą do JSONL. `--seed` zapisuje się w raporcie. Bez `--conducted` skrypt odmawia celu powyżej 10%.

Testy skryptów bez sprzętu: `python3 -m unittest tests.test_bench_tools` (z katalogu głównego; symulowane urządzenie z opóźnieniem USB).

### Próba 9 tylko w torze przewodowym, w komorze albo w pomieszczeniu odizolowanym

Węzeł wrogi przy 50% zajętości przekracza w eterze limit cyklu pracy 10% podzakresu 869,4–869,65 MHz, w którym leży kanał 869,525 MHz. Przebiegi (a) i (b) wykonuje się więc **bez promieniowania**: w torze przewodowym, w komorze ekranowanej albo w pomieszczeniu odizolowanym od otoczenia.

- **Tor przewodowy:** zamiast anten przewody 50 Ω przez tłumiki SMA i dzielnik mocy (przejściówki z U.FL tam, gdzie radio nie ma gniazda SMA) łączą RAK4631 nr 2, podsłuch i stacje próby (B, A, root); wszystkie urządzenia próby muszą być w torze, inaczej nie słyszą węzła wrogiego. Tłumienie każdej drogi między dwoma urządzeniami 30–60 dB, dobrane tak, żeby moc na wejściu każdego SX1262 była daleko poniżej wartości granicznej wejścia RF z karty SX1261/2 (+10 dBm), a w praktyce w zakresie około −90…−40 dBm: stacja 13 dBm przez 60 dB daje −47 dBm, węzeł wrogi −9 dBm przez 30 dB daje −39 dBm. Nigdy nie łączyć dwóch nadajników bez tłumika. Niewykorzystane porty dzielnika zakończyć obciążeniem 50 Ω. Tłumiki, dzielnik i ich tłumienie (zmierzone albo z karty) wpisuje się w raporcie.
- **Komora ekranowana:** wszystkie urządzenia próby z antenami w komorze o tłumieniu ekranowania co najmniej 70 dB. Projekt rozporządzenia wydawanego na podstawie art. 145 ust. 4 ustawy Prawo komunikacji elektronicznej (§ 3 ust. 1 pkt 14) zwalnia z wymagań urządzenia używane do badań w konstrukcji ekranującej o tłumieniu ≥70 dB; to projekt, więc przed próbą trzeba sprawdzić obowiązujący tekst i zapisać go w raporcie.
- **Pomieszczenie odizolowane** (np. piwnica): wszystkie urządzenia próby z antenami w pomieszczeniu, z którego sygnał nie wychodzi na zewnątrz. Przed próbą sprawdzenie: RAK4631 w pomieszczeniu nadaje ramki z mocą 13 dBm, czyli większą niż węzeł wrogi (−9 dBm) i równą mocy stacji, a odbiornik SDR na zewnątrz przez co najmniej 10 min ich nie wykrywa. Pomieszczenie nie jest komorą o zmierzonym tłumieniu: o jego użyciu decyduje właściciel. W raporcie wpisuje się nadajnik, moc, odbiornik, miejsce odbioru, czas sprawdzenia i wynik. Flaga `--conducted` oznacza wtedy pomieszczenie odizolowane.

W eterze (antena) węzeł wrogi może pracować tylko z celem ≤10% (`--occupancy 0.1` bez `--conducted`), co nie spełnia warunku próby 9.

## Próby

Kolejność jak w tabeli; próba późniejsza zakłada zaliczenie wcześniejszych. Polecenia z portu diagnostyki.

| Nr | Próba | Przebieg | Warunek zaliczenia | Zapis |
|---|---|---|---|---|
| 1 | Radia RNode (krok 2) | według [odbioru, krok 2](../../docs/spec/odbior.md#krok-2-radia-rnode-przy-stole), z firmware RNode, przed wgraniem `lora-raw` | jak w kroku 2 | `rnode-RRRR-MM-DD.md` |
| 2 | Ramki v3 | A: `REQ 1 0` daje `sa1_bytes` S; potem `REQ 1 <174 − S>` (SA1 174 B, typowe zgłoszenie; tekst `REQ` ma najwyżej 96 B, więc gdy 174 − S > 96, `REQ 1 96` i w kryterium ramka DATA ma S + 96 + 52 B zamiast 226 B); w trybie przygotowania na dwóch urządzeniach `RX 255` i `TXPKT 1 255`, `RXPER` | B: `{"lorarx":"raw","len":226,…}` i `{"hack":"sent","len":29,…}`; podsłuch: ramki 226 B i 29 B; `RXPER` 1/1 ramek 255 B; podsłuch: 255 B | logi A, B, podsłuchu; `v3-ramki-RRRR-MM-DD.md` |
| 3 | Jedno zgłoszenie do końca | zgłoszenie przyciskami na A; dyżurny w panelu stanowiska: PRZECZYTANE i decyzja | na ekranie A RECEIVED, PRZECZYTANE i decyzja; `APP` na A `intents` 0; jedno zgłoszenie w bazie stanowiska | `SCREEN`, `APP`, eksport CSV stanowiska |
| 4 | Czas HACK | `HACK 0` na B i roocie, 20 zgłoszeń (`REQ 20`), potem `HACK` | `hack_over_200ms` 0, `end_ms_max` ≤200 na B i roocie; w podsłuchu każdy HACK kończy się ≤200 ms po końcu swojej DATA; `hack_late` i ponowienia zapisane | `HACK` przed i po, JSONL podsłuchu (różnice czasów), `hack-RRRR-MM-DD.md` |
| 5 | W10 | `HACK 0`; na A `REQ 10` co minutę przez 5 minut (50 zgłoszeń); `APP` na A co 30 s do `intents` 0 | 50/50 RECEIVED w bazie stanowiska w <15 min od pierwszego COMMIT (warunek D21), w każdym razie ≤30 min (W10); brak podwójnego przyjęcia | czasy `REQ`, `APP` w czasie, czasy przyjęcia w bazie stanowiska, `HACK`, `P1` (odroczenia, `cad_busy`) na A i B, `INFO` (`loop_max_ms`, `tx_wait_ms`); `w10-RRRR-MM-DD.md` |
| 6 | Zapas RAM l0 | w trakcie prób 5 i 9 `RNS` co minutę na B (l0 nr 2) | najmniejsze `heap_min` / `heap_size` ≥30% (D14); statycznie obraz `l0` zajmuje 59% RAM | wiersze `RNS`, `INFO` |
| 7 | Zanik zasilania przekaźnika | ruch jak w W10 (np. `REQ 10`); odcięcie zasilania l0 nr 2 na ≥5 s w trzech chwilach, po 5 razy każda: zaraz po `lorarx` DATA (przed HACK), zaraz po `hack` sent, w trakcie przekazywania (`loratx` w toku); po każdym starcie `LOG` i `JOURNAL` | wszystkie zgłoszenia RECEIVED dokładnie raz w bazie stanowiska; po starcie B odczekuje dług z dziennika (`tx_wait_ms`) i wznawia kolejkę; brak uszkodzonych rekordów (`STORE` `corrupt_slots` 0) | chwila każdego odcięcia (wiersz logu), `LOG`, `JOURNAL`, baza stanowiska; `zanik-B-RRRR-MM-DD.md` |
| 8 | Dwie stacje schronienia | XIAO nr 2 jako C z rodzicem B; A i C po `REQ 25` w tej samej minucie | 50/50 RECEIVED; żadna stacja nie blokuje drugiej (każdy sąsiad ma swoje gniazdo K1); czasy obu źródeł zapisane osobno | `APP` A i C, `HACK` B, podsłuch |
| 9 | Węzeł wrogi | tylko w torze przewodowym, w komorze albo w pomieszczeniu odizolowanym ([wyżej](#próba-9-tylko-w-torze-przewodowym-w-komorze-albo-w-pomieszczeniu-odizolowanym)); RAK4631 nr 2 z `hostile.py` na drodze do B, każdy przebieg 2 h: (a) bez klucza, (b) z kluczem sieci; w tym czasie A wysyła 20 zgłoszeń (`REQ 20`) | 20/20 RECEIVED na A w ≤30 min od COMMIT w każdym przebiegu; udziały klas według [odbioru, „Wrogi węzeł”](../../docs/spec/odbior.md#próby) z podsłuchu; brak restartu B; RAM jak w próbie 6 | JSONL podsłuchu i skryptu wrogiego, `APP`, `RNS`, `INFO` na B; `wrogi-RRRR-MM-DD.md` |
| 10 | Trzy skoki | plan: A → XIAO nr 2 (przekaźnik) → B → root; `REQ 10` na A | 10/10 RECEIVED; w podsłuchu każda koperta przechodzi trzy skoki z HACK na każdym | plan sieci, podsłuch, `HACK` na przekaźnikach |
| 11 | Cisza radiowa | na B `SILENCE 1` (albo przełącznik CISZA) na 30 min przy ruchu z A (`REQ 5`); potem `SILENCE 0` | w podsłuchu brak ramek B w ciszy (DATA, HACK, BEACON); kolejka B przyjmuje ramki bez HACK; po zdjęciu ciszy 5/5 RECEIVED | podsłuch, `LOG` B, `APP` A |
| 12 | Rozsyłanie w dół i utrata drogi w górę | [niżej](#próba-12-rozsyłanie-w-dół-i-utrata-drogi-w-górę) | każdy węzeł rozsyła kopertę najwyżej raz, także po restarcie w oknie 120 s; po utracie rodzica stacja przechodzi na rodzica zapasowego bez rozsyłania w górę; wszystkie zgłoszenia i decyzje doszły dokładnie raz; tranzyt i BEACON-y każdego przekaźnika ≤60% godziny, BEACON-y ≤2% | podsłuch, `tools/envelopes.py`, `HACK`, `APP`; `rozsylanie-RRRR-MM-DD.md` |
| 13 | Zanik zasilania stacji | [niżej](#próba-13-zanik-zasilania-stacji) | każde zgłoszenie RECEIVED dokładnie raz; każdy biuletyn na ekranie A dokładnie raz; licznik koperty po każdym starcie powyżej zarezerwowanej granicy, żaden nonce się nie powtarza; `STORE` `corrupt_slots` 0 | chwile odcięć, `LOG`, `JOURNAL`, `STORE`, podsłuch, `tools/envelopes.py --mark`; `zanik-stacji-RRRR-MM-DD.md` |
| 14 | Zimny start | [niżej](#próba-14-zimny-start) | po wspólnym odcięciu A i B, bez ręcznego ogłoszenia: zgłoszenie RECEIVED i decyzja na ekranie A; drogi w dół z FRAM (decyzja idzie bez rozsyłania); B w ciszy po starcie nie nadaje żadnej ramki | `LOG`, podsłuch, `APP`; `zimny-start-RRRR-MM-DD.md` |
| 15 | Prąd modułu Wio | [niżej](#próba-15-prąd-modułu-wio) | wyniki zapisane i porównane z budżetem W23; bez progu zaliczenia | odczyty miernika, `INFO`; `prad-wio-RRRR-MM-DD.md` |
| 16 | Przeniesienie stacji | [niżej](#próba-16-przeniesienie-stacji) | pierwsza koperta z P002 ma licznik powyżej zarezerwowanej granicy (wielokrotność 64, większy od każdego z P001); żaden nonce się nie powtarza; P001 po eksporcie nie nadaje; zgłoszenia czekające przy przeniesieniu RECEIVED dokładnie raz; po każdym przerwaniu ponowione polecenie kończy albo wycofuje przeniesienie, nigdy dwie stacje z tą samą tożsamością | podsłuch, `tools/envelopes.py --mark`, wyjście polecenia, `INFO` obu; `przeniesienie-RRRR-MM-DD.md` |

Liczniki z `HACK` mierzą czas zegarem MCU od znacznika odbioru DATA w zadaniu odbioru do TxDone HACK; rozstrzyga pomiar z podsłuchu. W próbach 4, 5 i 9 wyniki z XIAO jako przekaźnika (próba 10) zapisuje się osobno od wyników prototypu.

## Próby 12–16: reszta warunku wyboru protokołu

Próby 12–16 zamykają część warunku D21 sprawdzaną na płytce v1 (specyfikacja systemu, rozdział 6, „Warunek D21 i granica płytki v2”; [warunek przyjęcia](../../docs/spec/transport.md#warunek-przyjęcia)): rozsyłanie, zanik zasilania stacji, zimny start, prąd Wio i przeniesienie. Obrazy z tego samego commita `main` na wszystkich czterech urządzeniach; liczniki `HACK` z `hop_no_key`, `hop_tag_bad` i `queue_k1/k2_admitted`. Próbę 16 robi się na końcu, bo P002 traci w niej rolę B. Zestawy XIAO zostają zasilone przez całą serię (FRAM w PSRAM), więc odcina się tylko prototypy l0.

**Odcięcia ręczne.** Właściciel odłącza przewód USB prototypu (prototyp nie ma innego zasilania, więc odłączenie USB to zanik zasilania) na sygnał skryptu: skrypt czyta podsłuch albo log, w chwili zdarzenia wypisuje „TERAZ” i daje dźwięk, a chwilę odłączenia zapisuje po zniknięciu portu. Ręka spóźnia się o około 1 s, więc chwile bliższe niż 1 s od zdarzenia nie są dokładne; w raporcie wpisuje się zmierzone opóźnienie każdego odcięcia.

**Liczniki koperty i nonce z podsłuchu:** `python3 tools/envelopes.py PODSŁUCH.jsonl [--mark HOST_TS …]`. Nagłówek koperty jest jawny od bajtu 11 ramki DATA (`kind`, `src`, `dst`, `ctr`), a nonce to `src ‖ dst ‖ kind ‖ 0 ‖ ctr` ([transport](../../docs/spec/transport.md)). Skrypt zgłasza nonce użyty dla dwóch różnych kopert, kopertę rozsyłaną przez jeden węzeł pod dwoma numerami `seq` oraz dla każdej chwili `--mark` (restart, przeniesienie) ostatni `ctr` przed nią i pierwszy po niej; pierwszy po musi być wielokrotnością 64 i większy od każdego wcześniejszego (rezerwacja blokami po 64). Ponowienia na łączu i przekazanie kopiują tę samą kopertę, więc nie są powtórzeniem nonce. Kod wyjścia 0 oznacza brak usterek.

### Próba 12: rozsyłanie w dół i utrata drogi w górę

WICI-Link rozsyła tylko w dół: przekaźnik bez drogi do stacji rozsyła ramkę od swojego rodzica do wszystkich sąsiadów (`l_dst` 0xFFFF, bez ACKREQ) i zapisuje tożsamość koperty w pierścieniu FRAM na 120 s ([WICI-Link, „Ruch w górę i w dół”](../../docs/spec/wici-link.md)). W górę rozsyłania nie ma: po trzech nadaniach bez HACK stacja przechodzi na następnego rodzica (planowy, zapasowy, dynamiczny).

1. **Rozsyłanie w dół.** Plan trzech skoków jak w próbie 10: A (P001) → XIAO nr 2 → B (P002) → root. `behind` ma tylko root, więc B nie zna drogi do A i każdą wiadomość do A rozsyła. `HACK 0` na wszystkich. `REQ 10` na A, po dojściu w panelu dla każdego zgłoszenia PRZECZYTANE i decyzja (20 wiadomości w dół). Podsłuch przez cały czas.
2. **Restart w oknie 120 s.** Przy pięciu wiadomościach w dół: odcięcie B na sygnał zaraz po jego rozsyłaniu (DATA od B z `l_dst` 65535), powrót po 5 s. Root nie ponawia (HACK od B przyszedł przed rozsyłaniem), a B po starcie nie rozsyła tej koperty drugi raz.
3. **Utrata drogi w górę.** Plan: A z rodzicem XIAO nr 2 i rodzicem zapasowym B, XIAO nr 2 i B z rodzicem root. `SILENCE 1` na XIAO nr 2, `REQ 5` na A. A po trzech nadaniach bez HACK przechodzi na B; w podsłuchu nie ma DATA w górę z `l_dst` 65535. Po dojściu 5/5 `SILENCE 0`.

Zaliczenie: `tools/envelopes.py` bez `repeated_floods` i bez `nonce_reuse`; zgłoszenia i decyzje dokładnie raz w bazie stanowiska i na ekranie A; czas nadawania każdego przekaźnika z podsumowania podsłuchu (`airtime_by_l_src_s`) w każdej godzinie ≤60%, BEACON-y ≤2%. Zakres 15 skoków i rozsyłania w długim łańcuchu sprawdza emulator.

### Próba 13: zanik zasilania stacji

Stacja A na P001 (prawdziwa FRAM), łańcuch A → B → root. Po każdym starcie A: `LOG`, `JOURNAL`, `STORE`, `APP`. Chwile odcięcia:

| Chwila | Sygnał | Liczba |
|---|---|---|
| zaraz po utworzeniu zgłoszenia, przed jego dojściem | skrypt: odpowiedź na `REQ 1` (zapis zgłoszenia, pierwsze nadanie albo czekanie na wolny kanał) | 3 |
| po HACK całej koperty, przed RECEIVED | podsłuch: HACK od B do A | 3 |
| po HACK części 1/2 własnej koperty | podsłuch: DATA od A z częścią 1 (bity 5–4 bajtu 11 = 1), potem HACK od B z tym samym `seq`; część 2 czeka na dług ciszy (kilka sekund) | 5 |
| po HACK części 1/2 biuletynu do A | panel: biuletyn 192 B do A (zawsze dwie części); podsłuch: HACK od A dla części 1 | 5 |
| bez ruchu, po RECEIVED na ekranie | ekran A | 2 |

Kopertę dwuczęściową z A daje zgłoszenie z SA1 dłuższym niż około 200 B: najdłuższe miejsce w konfiguracji A (64 B) i `REQ 1 96`; przed próbą sprawdzić w podsłuchu, że DATA od A ma część 1. Jeśli się nie da, ten wiersz zastępuje biuletyn.

Zaliczenie: każde zgłoszenie RECEIVED dokładnie raz w bazie stanowiska; każdy biuletyn na ekranie A dokładnie raz (po złożeniu części albo po ponowieniu przez stanowisko); `tools/envelopes.py --mark` z chwilami odcięć bez usterek; `STORE` `corrupt_slots` 0; `journal_ok`.

### Próba 14: zimny start

Łańcuch A → B → root, wszystkie drogi nauczone ruchem (próba 3 albo `REQ 1`). Kryterium: [odbiór, „Zimny start trasy”](../../docs/spec/odbior.md#próby), w znaczeniu WICI-Link.

1. Odcięcie A i B jednocześnie na 30 s; root zostaje zasilony. Bez żadnego polecenia po starcie: w podsłuchu BEACON-y B w ciągu kilku sekund, w `LOG` „wici durable state recovered” i „wici station ready”. `REQ 1` na A: RECEIVED. Decyzja w panelu idzie do A przez B jednoadresowo (droga w dół z FRAM), bez rozsyłania.
2. `SILENCE 1` na B, odcięcie B na 30 s. Po starcie `INFO` `silence: true` i 10 min podsłuchu bez żadnej ramki od B. `SILENCE 0`, potem `REQ 1` na A: RECEIVED.

### Próba 15: prąd modułu Wio

Wio jest zasilany z linii 3,3 V przez zworkę POWER_BREAK ([montaż L0](../l0-diagnostic/MONTAZ-I-TESTY.md)). **Nigdy nie zasilać prototypu ze zdjętą zworką**: wyjścia MCU zasilałyby wtedy Wio przez diody wejść.

1. Prototyp bez zasilania. Zworkę zastąpić miernikiem na zakresie mA (przewody do obu kołków), dopiero potem włączyć zasilanie.
2. Odbiór (zwykła praca, bez ruchu): prąd ustalony, kilka mA.
3. CAD i nadawanie trwają milisekundy i dziesiątki milisekund, więc miernik pokaże tylko średnią. Do przebiegu w czasie: rezystor 1 Ω w miejscu zworki i oscyloskop. Bez oscyloskopu: średnia przy serii ramek w trybie przygotowania (`TXPKT` z liczbą i długością) z wypełnieniem z czasów ramek; prąd nadawania = (średnia − prąd odbioru × (1 − wypełnienie)) / wypełnienie.
4. Po pomiarze: zasilanie odłączone, zworka z powrotem, dopiero potem zasilanie.

Czasu wybudzenia procesora obraz `l0` nie zapisuje: prototyp nie usypia procesora w zwykłej pracy (`NAP` w trybie przygotowania podaje tylko czas snu). Licznik wybudzeń (`STANDBY`) ma tylko obraz płytki v2.

### Próba 16: przeniesienie stacji

Stacja A z P001 na P002 ([przeniesienie stacji](../../docs/spec/usb-protocol.md#przeniesienie-stacji)). Na czas próby B jest XIAO nr 2 (plan A → XIAO nr 2 → root). P002 musi być pusty: ZNISZCZ DANE i tryb przygotowania. P001 i P002 w trybie przygotowania (przycisk 3 s).

1. **Czekające zgłoszenia.** `SILENCE 1` na XIAO nr 2, `REQ 3` na A: trzy zgłoszenia zostają w A.
2. **Przeniesienie bez przerw:** `python -m wici --migrate-source-port PORT_DANYCH_P001 --migrate-target-port PORT_DANYCH_P002`, OK na P001 po porównaniu odcisku z ekranem P002. Chwila zakończenia to `--mark`. Potem `SILENCE 0` na XIAO nr 2: trzy zgłoszenia idą z P002.
3. **Przerwane USB.** Przeniesienie z powrotem i dalej tam i z powrotem; w każdym z 5 kroków (tabela w specyfikacji) odłączenie USB raz źródłowej i raz docelowej, w sumie 10 przebiegów. Po przerwaniu ponowne uruchomienie tego samego polecenia dokańcza przeniesienie; w dwóch przebiegach zamiast tego `--migrate-abort`. Odłączenie USB prototypu jest też zanikiem zasilania, więc obejmuje i przerwanie przewodu, i zanik.
4. Po każdym przebiegu `INFO` i `migrate` `status` obu: dokładnie jedna stacja w zwykłej pracy, druga `retired` albo pusta.

Zaliczenie jak w tabeli. Po próbie P002 wraca do roli B: ZNISZCZ DANE, nowa karta i `configure` jego sąsiadów.

Licencja tego pliku: CC-BY-4.0 ([LICENSE.md](../../LICENSE.md)).

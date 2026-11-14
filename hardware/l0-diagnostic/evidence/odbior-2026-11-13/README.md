# Odbiór L0, 13.11.2026

Logi i raporty z odbioru obu prototypów L0 według [ODBIOR.md](../../ODBIOR.md). Godziny w nazwach plików `2026…` są w UTC, a w logach `*.log` są czasem lokalnym (UTC+1). Ścieżki katalogu domowego w śladach Pythona są skrócone do `~`.

| Sztuka | MAC z `INFO` | Program na starcie |
|---|---|---|
| P001 | `B82F2D6B4580` | `l0-0.5` |
| P002 | `50112F6B4580` | `l0-0.5` |
| partner XIAO | `A028AD76B144` | `pair-0.4` na czas prób |

## Etap 1: P001 po transporcie (program diagnostyczny)

- `20261113-132150-9ded530d.*`: pierwsze `INFO` z nazwą portu wpisaną dosłownie jako `PORT`; błąd obsługi, nie płytki.
- `20261113-132226…` do `20261113-132728…`: `INFO`, `STATUS`, `RDID`, plansze `LCD 0`–`4`, `LED`, `BUZZ`. Plansze, dioda i brzęczyk oceniane wzrokowo i słuchowo: zgodne.
- `20261113-133813-ca11168d9b994915.json(l)`: radio P001 z XIAO, 20/20 w obie strony.

## Etap 2: P002, pełny odbiór (program diagnostyczny)

- `20261113-165729…`, `-165733…`: `INFO`, `STATUS`, `RDID`.
- `E1-P002.log`, `20261113-170241…`: trzy uruchomienia po odłączeniu USB.
- `E5-P002.log`: przyciski i przełącznik CISZA.
- `E3-P002-write.log`, `E3-P002-verify.log`, `20261113-170747…`, `20261113-171021…`: zapis i weryfikacja całej FRAM, 0 błędów.
- `E6-P002.log`, `20261113-171028-2bdcb5c6*`: pierwsza próba mieszana przerwana. Otwarcie portu na macOS z `dtr=rts=False` zresetowało płytkę (poprawka narzędzia w PR #209).
- `E6-P002-run2.log`, `20261113-171143-83b0fc8e*`: powtórzenie bez resetu portu, 4464 cykle bez błędów, radio 100/100.
- `R12-P002-P001.log`, `20261113-172906-594bddce23fb4b24.json(l)`: łączność P002 z P001, 100/100 w obie strony.
- `R3-P002.log`: cisza blokuje nadawanie, odbiór działa dalej.

## Etap 3: program stacji `l0` na obu płytkach

Program zbudowany z gałęzi PR #210 (`c91f8cd`), później scalonej do `main` jako `8dd305f2`.

- `S-P001-info-przed.log`, `S-P001-ok-capture.log`, `S-P001-btn.log`: pierwszy start na starszym `main`. Bariera migracji jest uszkodzona przez wzór testowy, więc ZNISZCZ DANE jest nieosiągalne. Z tego wynikła poprawka w PR #210.
- `S-P001-pr210-przed.log`, `S-P001-pr210-po.log`: ZNISZCZ DANE z panelu na programie z PR #210. Po kasowaniu `journal_ok` i `store_ok` są `true`, a `journal_resets` wynosi 1.
- `S-P002-przed.log`: P002 przed kasowaniem, w tym samym stanie pamięci.
- `S-P001-proba1.log`, `S-P002-proba1.log`: próba 1 (`INFO`, `RADIO`, `VERIFY`, `FREQ`, `SLEEP`, `RESET`, `CONFIG`) bez niezgodności.
- `S-prep.log`: `PREP 1` z konsoli. Potwierdzenie OK trafiało do menu, więc tryb przygotowania włączono przytrzymaniem PRZYGOT.
- `S-proba2.log`: łączność, 9 serii po 11 ramek w każdą stronę. P001→P002: `rx_ok` 99, `rx_bad` 0. P002→P001: `rx_ok` 99, `rx_bad` 1, `missing` 0. Pojedyncze `rx_bad` to obca ramka innej długości, najpewniej własna ramka Reticulum stacji.
- `S-proba3-cisza.log`: P001 w położeniu CISZA, `TXPKT` zwraca `radio silence`, P002 ma `rx_ok` 0.
- `S-proba3-po-ciszy.log`: po zdjęciu ciszy stacja sama odczekuje około 10 s (`tx_wait_ms` 10032), potem 11/11.
- `S-prep0.log`: `PREP 0` na obu, `prep` i `silence` mają wartość `false`.

`S-P001-ok-capture.log`, `S-P001-btn.log` i `S-prep.log` kończą się wyjątkiem pyserial, gdy port zniknął przy restarcie płytki. To przerwany nasłuch, nie wynik próby.

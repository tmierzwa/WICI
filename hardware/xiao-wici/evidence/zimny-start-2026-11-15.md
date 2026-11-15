# Próba 14: zimny start, łańcuch A → B → root (2026-11-15, 13:33–13:57)

Procedura: [próba 14](../README.md#próba-14-zimny-start). Obrazy i plan jak w [próbie 13](zanik-stacji-2026-11-15.md) (`main` `ac5893e4`). Kryterium: [odbiór, „Zimny start trasy”](../../../docs/spec/odbior.md#próby), w znaczeniu WICI-Link. Podsłuch: `podsluch-l0-2026-11-15.jsonl`.

## Krok 1: wspólne odcięcie A i B

Właściciel odłączył USB P001 i P002 o 13:33:18,8 i 13:33:19,0. Podłączył je o 13:33:34, po 16 s zamiast 30 s. Root (XIAO nr 1) był zasilony przez cały czas. Po starcie nie było żadnego polecenia ani ręcznego ogłoszenia.

| Sprawdzenie | Wynik |
|---|---|
| `LOG` A i B | „wici station ready” |
| decyzja w dół przed jakimkolwiek ruchem w górę: PRZECZYTANE dla zgłoszenia 3997 z panelu o 13:33:52 | B przekazał ją do A o 13:33:54 jednoadresowo (`l_dst` 20), bez rozsyłania; panel: stan 2 |
| `REQ 1` na A o 13:33:52 (zgłoszenie 1417) | na stanowisku raz; RECEIVED na A (`intents` 0) o 13:34:48, po 56 s |

**BEACON po starcie.** B ani A nie nadały BEACON-u w ciągu kilku minut po starcie. To zgodne z [WICI-Link, reguła 4](../../../docs/spec/wici-link.md): BEACON 1–5 s po starcie nadaje stacja z rangą i root, a rangę stacja liczy z BEACON-u rodzica. Root nadaje co 24–36 min, więc pierwszy BEACON przekaźnika po zimnym starcie może przyjść do 36 min później. DATA płynie w tym czasie do rodzica z planu, co pokazało zgłoszenie 1417. W procedurze próby 14 zdanie o BEACON-ach B „w ciągu kilku sekund” było błędne i zostało poprawione.

**Ograniczenie.** W łańcuchu A jest sąsiadem B, więc B zna drogę do A z planu sieci, nie z trwałej tablicy dróg w FRAM. Trwałość dróg w dół po restarcie sprawdza próba 12 na trzech skokach.

## Krok 2: cisza radiowa przez restart

Najpierw `SILENCE 1` na B i odcięcie P002 (13:36:35–13:37:01). Po starcie `INFO` miało `silence: false`. Polecenie `SILENCE` udaje przełącznik CISZA w RAM ([polecenia](../../../firmware/docs/polecenia.md)), a przy starcie program czyta położenie prawdziwego przełącznika. Krok powtórzono z przełącznikiem.

| Sprawdzenie | Wynik |
|---|---|
| przełącznik CISZA na P002 w pozycji ciszy | `INFO` `silence: true` |
| odcięcie P002 13:38:16–13:38:33 | po starcie `silence: true`, `restarts` 28 |
| `REQ 1` na A o 13:38:44 (zgłoszenie 800), podsłuch 13:38:33–13:48:52 | **żadnej ramki od B**; A nadała do B 24 DATA bez HACK |
| przełącznik CISZA z powrotem (około 13:56:50) | zgłoszenie 800 na stanowisku o 13:56:52, raz; `intents` 0 na A o 13:57:09 |

## Wynik

Kryterium spełnione: po wspólnym restarcie A i B, bez ręcznego ogłoszenia, zgłoszenie dochodzi, a decyzja wraca do A. Przekaźnik w ciszy z przełącznika po restarcie nie nadaje żadnej ramki. Zakres „trasy i znane tożsamości odtworzone z FRAM” jest pokazany dla sąsiadów z planu. Drogi w dół przez dalszego sąsiada sprawdzi próba 12.

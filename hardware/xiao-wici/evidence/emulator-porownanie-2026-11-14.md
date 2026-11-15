# Emulator WICI-Link wobec prób przy stole (2026-11-14)

Pytanie: czy [emulator](../../../tests/native/wici_emulator/README.md) daje dla dzisiejszych układów te same wyniki co sprzęt. Od tego zależy, ile warto mu wierzyć przy 15 skokach i 30 stacjach, których przy stole się nie sprawdzi.

Emulator z `main` `32a5f2d6`, czyli z tego samego commita co obrazy urządzeń w ponownych próbach (`run.py build`, plik `wici_emulator_base`). Skuteczność łącza `p=1000`, bo przy stole wszystkie urządzenia słyszą się bez strat.

## Wyniki

| Układ | Sprzęt | Emulator (ziarna 1–3 albo 1–10) |
|---|---|---|
| 20 zgłoszeń naraz z A przez B do roota (próba 4) | wszystkie zamknięte po 324 s (rano) i 387 s (po poprawkach) | `koniec hops=2 reports=20 sense=2 spread=1`: ostatnie zamknięte po 335–339 s, mediana dojścia 152–176 s |
| ramki z prośbą o HACK / HACK w próbie 4 | 360 / 208 (podsłuch) | 257–263 / 159–166 |
| 5 zgłoszeń w ciszy B 30 min, potem zdjęcie ciszy (próba 11) | dojścia na stanowisko po 4, 19, 29, 33 i 115 s; `intents` 0 po 129 s | `cisza_przekaznika n=1`: mediana zamknięcia 42–57 s, ostatnie po 76–126 s |
| zgłoszenia przyjęte dwa razy | 0 | 0 |

Polecenia:

```bash
wici_emulator_base koniec seed=1 p=1000 hops=2 reports=20 sense=2 spread=1
```
```bash
wici_emulator_base cisza_przekaznika seed=1 p=1000
```

## Wnioski

- Czasy zgadzają się w granicach kilkunastu procent: próba 4 na sprzęcie trwała 324–387 s, w emulatorze 335–339 s. Ostatnie zgłoszenie po ciszy doszło na sprzęcie po 115 s (zamknięcie po 129 s), w emulatorze po 76–126 s.
- Sprzęt nadaje około 1,4 raza więcej ramek niż emulator. Prawdopodobną przyczyną jest układ stołu: tam stacja słyszy też roota i odbiera jego ruch, a w modelu łańcucha słyszy go tylko jako zakłócenie (`sense=2`). Przyczyny nie sprawdzano.
- Emulator nie ma węzła zagłuszającego kanał ani zaniku zasilania, więc prób 7 i 9 nie da się z nim porównać.
- Porównanie dotyczy tylko jednego przekaźnika i jednej stacji. Zgodność przy 2 skokach nie dowodzi zgodności przy 15 skokach i wielu stacjach, ale nie daje powodu, by wynikom emulatora nie wierzyć.

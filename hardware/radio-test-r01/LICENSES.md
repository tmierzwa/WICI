# WICI — licencje i pochodzenie kontrolera

Dokładna mapa ścieżek i pełne teksty: [główny LICENSE.md](../../LICENSE.md). Własny kontroler, dane wykonawcze, footprint USB i footprint PPTC: CERN-OHL-P-2.0. Skrypty: MIT. README, instrukcja odtwarzania i raporty: CC-BY-4.0.

Symbole i standardowe footprinty są pod CC-BY-SA-4.0 z wyjątkiem KiCad. Symbole pochodzą z podzbioru oficjalnej biblioteki 9.0.0; Polyfuse, MountingHole i PWR_FLAG dodano z 10.0.6. Footprinty standardowe pochodzą z dystrybucji 10.0.6. Zachowano [licencję, wyjątek i autorstwo społeczności KiCad](cad/KICAD-LIBRARY-LICENSE.md).

`cad/footprints/WICI.pretty/IDC_61201021621.kicad_mod` jest pochodną KiCad 10.0.6 `IDC-Header_2x05_P2.54mm_Vertical`. Zmieniono nazwę i średnice otworów na 1,1 mm. Ta pochodna zachowuje CC-BY-SA-4.0 z wyjątkiem; nie jest własnym footprintem pod CERN-OHL.

Własny footprint USB narysowano z wymiarów rysunku producenta. Nie dołączono komercyjnego modelu CAD złącza Würth. `sources.json` podaje odnośniki i pochodzenie materiałów. Materiały producentów i import TI w lokalnym `reference-private/` nie są częścią wydania, Git ani ZIP-ów; pozostają na warunkach swoich właścicieli.

Samodzielny ZIP kontrolera zawiera NOTICE oraz pełne CERN-OHL-P-2.0 i CC-BY-4.0. Nie zawiera bibliotek KiCad ani źródeł upstream. Edytowalne źródła i przypisane im licencje są w repozytorium WICI.

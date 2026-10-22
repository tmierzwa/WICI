# Rdzeń Reticulum stacji

Własny rdzeń zgodny z Reticulum, który zastąpi port microReticulum pod warstwą `rnsnode` (`../../src/rns_node.h`). Zakres, etapy i kryteria odbioru: [reticulum-core.md](../../reticulum-core.md).

Kod w tym katalogu jest utworem zależnym od implementacji referencyjnej Reticulum i ma jej licencję ([LicenseRef-Reticulum](../../../LICENSES/LicenseRef-Reticulum.txt)): Copyright (c) 2016-2026 Mark Qvist, zmiany Copyright (c) 2026 Tomek Mierzwa. Autor rdzenia odpowiada za każdy wiersz; pomoc asystenta AI jest zapisana w commitach ([licencja i autorstwo](../../reticulum-core.md#licencja-i-autorstwo)).

Próby: `tests/test_rnscore.py` buduje rdzeń z ASan i UBSan (C++17 bez wyjątków i RTTI, `-Wall -Wextra -Werror`) z programem `tests/native/rnscore_check.cpp` i porównuje wyniki z wektorami Reticulum w Pythonie (`tests/vectors/reticulum.json`). Obrazy stacji jeszcze nie dołączają rdzenia (etap R6).

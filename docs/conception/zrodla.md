# Źródła koncepcji

Przegląd materiałów: 2026-10-06. Link do bieżącej gałęzi lub strony nie przypina wersji wydania. Przed budową pakietu START wybrać konkretne wydania/commity i zachować ich hashe oraz oryginalne licencje.

## Projekt WICI — dane wejściowe

- [Specyfikacja 0.4](../README.md): parametry, kontrakty i [odbiór](../spec/odbior.md).
- [Model i dowody](../../software/reference/README.md): ramki, komunikaty i transakcje; [wyniki obliczeń](../../software/reference/wyniki.json).
- [Kontroler USB R01.3](../../hardware/radio-test-r01/README.md): CAD, eksporty, raporty i status HOLD.
- [BOM całej stacji](../../bom.csv): kandydaci elementów, nie zakwalifikowana oferta produkcji.

Obliczenia rozdziału 06 są oszacowaniami projektowymi z podanymi wzorami. Rozdział 08 oddziela istniejące warunki odbioru od nowych propozycji organizacji prób. Rozdział 02 opisuje proponowany sposób pracy; nie stanowi uzgodnienia z konkretną OSP.

## Implementacje i dokumentacja pierwotna

| Źródło | Zastosowanie w analizie |
|---|---|
| [Reticulum — działanie](https://reticulum.network/manual/understanding.html) | role tożsamości, transportu i fizycznych interfejsów |
| [Reticulum — interfejsy](https://reticulum.network/manual/interfaces.html) | RNode, KISS i możliwość własnego adaptera |
| [KISSInterface — kod](https://github.com/markqvist/Reticulum/blob/master/RNS/Interfaces/KISSInterface.py) | rzeczywisty timeout kontroli przepływu; do ponownego sprawdzenia dla przypiętej wersji |
| [LXMF — projekt](https://github.com/markqvist/LXMF) | wiadomości i opcjonalne węzły przechowywania |
| [LXMessage — kod](https://github.com/markqvist/LXMF/blob/master/LXMF/LXMessage.py) | wybór pakietu lub zasobu; narzut trzeba pomierzyć dla wydania |
| [NomadNet](https://github.com/markqvist/NomadNet) | klient tekstowy i strony Micron |
| [Meshtastic — algorytm sieci](https://meshtastic.org/docs/overview/mesh-algo/) | sposób przekazywania i znaczenie ACK |
| [MeshCore](https://github.com/meshcore-dev/MeshCore) | istniejące role klienta, przekaźnika i modemu |
| [disaster.radio](https://github.com/sudomesh/disaster-radio) | zbliżona koncepcja Wi-Fi + LoRa; informacja o wstrzymaniu prac |
| [TI CC1120 — datasheet](https://www.ti.com/lit/ds/symlink/cc1120.pdf) | funkcje układu RF; nie dowód zasięgu P1 |
| [ST S2-LP — datasheet](https://www.st.com/resource/en/datasheet/s2-lp.pdf) | drugie wykonanie RF; osobne dopasowanie i konfiguracja |
| [SQLite — atomic commit](https://sqlite.org/atomiccommit.html) i [backup API](https://sqlite.org/backup.html) | warunki trwałości i kontrolowanej kopii bazy |

Licencja WICI nie zastępuje licencji zależności. Bieżący [LICENSE Reticulum](https://github.com/markqvist/Reticulum/blob/master/LICENSE) zawiera dodatkowe ograniczenia dotyczące celowego krzywdzenia ludzi i tworzenia zbiorów do treningu AI. Przed połączeniem i dystrybucją pakietu z własnym kodem GPL trzeba sprawdzić zgodność warunków konkretnych wersji. Obecne repozytorium nie dołącza kodu Reticulum/LXMF; analiza nie oznacza zatwierdzenia przyszłej paczki zależności.

## Radio — warunki prawne do potwierdzenia

[Decyzja wykonawcza UE 2025/105](https://eur-lex.europa.eu/eli/dec_impl/2025/105/oj/eng) podaje dla 869,4–869,65 MHz warunki obejmujące do 500 mW ERP i wariant aktywności do 10%. Moc na złączu, ERP i EIRP są różnymi wielkościami. WICI przyjmuje ograniczenie czasu TX; obecność CCA nie uprawnia do pominięcia go.

Punktem sprawdzenia warunków krajowych jest [rozporządzenie o urządzeniach bez pozwolenia radiowego, Dz.U. 2022 poz. 567](https://eli.gov.pl/eli/DU/2022/567/ogl). Przed próbą nadawania sprawdzić aktualny stan przepisów, właściwy załącznik i zastosowanie do konkretnego urządzenia. Ta analiza nie zamyka kwalifikacji prawnej. Emisje poza pasmem, antena, cały tor i bezpieczeństwo gotowego urządzenia wymagają własnego potwierdzenia; dopuszczalna częstotliwość nie jest dopuszczeniem konstrukcji.

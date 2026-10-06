# 03. Dostępne rozwiązania

## Rozdzielenie warstw

Wi-Fi daje mieszkańcowi dostęp do lokalnej strony. Modulacja radiowa przenosi bity między stacjami. Reticulum jest działającą implementacją stosu sieciowego i protokołu, a LXMF implementacją wiadomości. Aplikacja WICI odpowiada za formularz, bazę, statusy i pracę dyżurnego. Żaden pojedynczy wybór w tej tabeli nie dostarcza całego systemu.

| Rozwiązanie | Przydatność | Granica zastosowania |
|---|---|---|
| Internet / telefonia | szybki kontakt i zwykłe kanały pomocy, kiedy dostępne | zależność od publicznej infrastruktury; nie spełnia W01 jako jedyna droga |
| Zwykłe radio głosowe | rozmowa operatorów i ręczne przekazanie zgłoszenia | operator musi przepisać dane i status; brak automatycznej trwałej kolejki |
| Lokalny router + strona na laptopie | dostęp telefonów bez instalacji i bez internetu | lokalny LAN nie łączy odległych schronień; stan i uprawnienia tworzy aplikacja |
| Reticulum | tożsamości, ochrona komunikacji, trasy i transport przez aktywne węzły | wymaga sprawnych interfejsów i fizycznych połączeń; sam nie prowadzi zgłoszeń OSP |
| LXMF | wiadomości, obsługa wysyłania i opcjonalnego przechowywania pośredniego | potwierdzenie transportowe nie dowodzi zapisu w bazie WICI ani decyzji człowieka |
| NomadNet | gotowy klient tekstowy operatora, wiadomości i strony Micron | odrębny interfejs; nie zastępuje lokalnej strony HTTP w przeglądarce telefonu |
| RNode / LoRa z Reticulum | istniejąca droga radiowa do prób tego samego stosu aplikacji | inny profil radiowy; nie komunikuje się z modemem P1 tylko dlatego, że oba używają Reticulum |
| Meshtastic | istniejąca sieć wiadomości LoRa; zarządzane przekazywanie pakietów | odrębny protokół i semantyka ACK; interfejs i zapis OSP wymagają integracji |
| MeshCore | istniejące role urządzeń: klient, przekaźnik, serwer pokoju, modem KISS | odrębny stos; trwałe przyjęcie zgłoszenia i interfejs WICI pozostają do zaprojektowania |
| disaster.radio | przykład połączenia lokalnego Wi-Fi, interfejsu WWW i radia LoRa | autorzy oznaczają prace jako wstrzymane i projekt jako niedokończony |

Właściwości wymienionych projektów: [Reticulum](https://reticulum.network/manual/understanding.html), [interfejsy i RNode](https://reticulum.network/manual/interfaces.html), [LXMF](https://github.com/markqvist/LXMF), [NomadNet](https://github.com/markqvist/NomadNet), [Meshtastic](https://meshtastic.org/docs/overview/mesh-algo/), [MeshCore](https://github.com/meshcore-dev/MeshCore), [disaster.radio](https://github.com/sudomesh/disaster-radio). Stan źródeł sprawdzono 2026-10-06. Wydanie WICI musi przypiąć konkretne wersje po próbach zgodności.

## Reticulum i LXMF w tym projekcie

Reticulum działa na laptopie jako biblioteka i proces transportowy. Włączony transport przekazuje pakiety innych stacji. Interfejs szeregowy łączy je z modemem; modem wykonuje transmisję radiową. Reticulum nie jest urządzeniem radiowym ani samą deklaracją standardu. [Dokumentacja implementacji](https://reticulum.network/manual/understanding.html).

LXMF układa nad tym wiadomości. Węzeł transportowy Reticulum przekazuje bieżący ruch. Węzeł przechowywania LXMF może zachować wiadomość dla nieobecnego odbiorcy; są to różne role. Bazowy przekaźnik WICI nie dostaje automatycznie trwałej skrzynki dla całej sieci. Trwała kolejka własnych zgłoszeń jest w bazie WICI. [Opis LXMF](https://github.com/markqvist/LXMF).

## Układy radiowe

CC1120 firmy TI i S2-LP firmy ST są transceiverami sterowanymi przez SPI. Obsługują FSK/GFSK oraz osobne bufory RX/TX 128 B. Potrzebują mikrokontrolera, zegara, zasilania, dopasowania RF, anteny i firmware. Płytka rozwojowa pomaga pomierzyć układ, ale nie jest gotową stacją WICI. [CC1120](https://www.ti.com/lit/ds/symlink/cc1120.pdf), [S2-LP](https://www.st.com/resource/en/datasheet/s2-lp.pdf).

Dwa układy nie są zamiennikami pinowymi. Wspólne ustawienia modulacji i format P1 są hipotezą zgodności do sprawdzenia na fizycznych modemach. Katalogowa czułość przy innej szybkości nie jest wynikiem dla P1. Projekt wymaga dwóch layoutów i nastaw, a następnie prób mieszanych TI–ST.

## Czego nie budować drugi raz

Użyć stosu sieciowego, kryptografii i biblioteki wiadomości zamiast własnych odpowiedników. Własny kod ograniczyć do lokalnej obsługi potrzeb, transakcji, diagnostyki, pakowania offline i adaptera czasu radia. Znaleziony router powinien realizować zwykły LAN, bez specjalnego firmware i producentowego API.

Gotowe modemy można wykorzystać jako narzędzia porównawcze w laboratorium. Nie uzależnia to docelowej konstrukcji od ich dostępności. Własny sprzęt powinien wynikać z pomiaru i wymagania niezależności dostawców, a nie z założenia, że każda funkcja musi powstać od początku.

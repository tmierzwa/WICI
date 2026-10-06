# 04. Analiza opcji

## Kryteria wyboru

Warunki konieczne: praca offline, krótka wiadomość ze zwrotnym potwierdzeniem aplikacyjnym, lokalny dostęp bez instalacji, trwałość po restarcie, aktywny przekaźnik i jawne interfejsy. Następnie porównać energię, trudność uruchomienia, koszt wytworzenia, naprawę i dostępność niezależnych części. Brakuje danych pomiarowych do uczciwego rankingu liczbowego.

| Opcja całego systemu | Mocna strona | Główna cena / ryzyko | Decyzja |
|---|---|---|---|
| Laptop + router + internet | najmniej nowego sprzętu i szybki kanał | utrata sieci publicznej odcina odbiorcę | opcjonalny kanał, nie jedyna droga |
| Radio głosowe + papierowy rejestr | prosta procedura i mało oprogramowania | ciągła praca operatora, błędy przepisywania, trudne statusy dla mieszkańców | uzgodniony kanał zastępczy |
| Laptop + router + Reticulum/LXMF + LoRa | istniejący interfejs radiowy, możliwość szybkiej próby stosu | czas antenowy zależy od profilu; niezależność RF wymaga analizy konkretnego BOM | wariant porównawczy; może wrócić jako wybór bazowy po pomiarach |
| Laptop + router + Reticulum/LXMF + własny FSK P1 | jawny profil i dwa kandydaty RF od niezależnych producentów | własne RF, firmware i adapter czasu; duży zakres kwalifikacji | wybór bazowy 0.4, warunkowy |
| Laptop + router + Meshtastic lub MeshCore | istniejące oprogramowanie radiowe | osobna integracja kontraktów WICI i trwałego potwierdzenia; ocena alternatyw części | alternatywa, gdy zmniejszy całość prac po próbie |
| Dedykowany komputer + Wi-Fi + radio | powtarzalna konfiguracja, możliwość mniejszego poboru | zakup i magazyn urządzeń; kolejny sprzęt do utrzymania | alternatywa przy braku zgodności lub energii znalezionych laptopów |

Wybór FSK nie dowodzi przewagi zasięgu ani kosztu nad LoRa. Daje możliwość porównania dwóch rodzin transceiverów i otwarty kontrakt P1. Jeśli koszt kwalifikacji, opóźnienia albo próba terenowa nie pozwolą spełnić wymagań, wybór należy ponownie otworzyć. [Właściwości rozwiązań](03-dostepne-rozwiazania.md), [próby rozstrzygające](08-plan-weryfikacji-i-decyzje.md).

## Uproszczenia przyjęte w wariancie bazowym

| Wybór | Co upraszcza | Pozostający koszt |
|---|---|---|
| Osobny akumulator telefonów | awaria lub wymiana ładowarki nie przerywa łączności; brak układu priorytetów mocy | osobne przewody i osobny zapas energii |
| Zwykły router z DHCP | brak własnego DNS, DHCP, captive portal i obsługi wielu paneli producentów | sprawdzić dostęp do konfiguracji i brak izolacji Wi-Fi–LAN; używać QR/adresu |
| Oryginalne zasilacze + 230 V | unika zestawu własnych wtyczek i napięć laptopów/routerów | przetwornica, straty, masa i kwalifikacja bezpieczeństwa AC |
| Pasywne zasilanie A/B przez diody | brak programu przełączającego i bezpośredniego łączenia plusów źródeł | chłodzenie, spadek napięcia i udar przy dołączaniu |
| Tekst i pięć typów wiadomości | ograniczony ruch i mała powierzchnia integracji | potrzeby wymagające rozmowy obsługuje operator innym kanałem |
| Własna trwała kolejka + LXMF | aplikacja pilnuje zapisu; biblioteka transportu pilnuje dostarczania | integracja cyklu ponowień i potwierdzeń wymaga prób |
| Antena przy oknie/drzwiach | prostszy montaż, brak wymogu dachu | zasięg zależy od przeszkód; może być potrzebny dodatkowy przekaźnik |

Rozdzielenie ładowania telefonów spełnia tę samą funkcję przy mniejszej liczbie zależności. Podobnych uproszczeń szukać przed dodawaniem sterowników, wspólnych szyn mocy i automatyki. Uproszczenie musi zachować sprawdzalne wymagania, a nie jedynie zmniejszyć liczbę części.

## Decyzje wymagające porównania

**Zasilanie laptopa:** wariant 230 V obejmuje najwięcej typów oryginalnych zasilaczy, ale jest najtrudniejszy do bezpiecznego samodzielnego wykonania. W pilotażu laboratoryjnym można użyć sprawdzonego zasilania jako narzędzia testowego. Dla hostów USB-C PD warto osobno pomierzyć wariant DC, jeśli obniża zużycie i koszt. Nie zastępuje on uniwersalnego wymagania bez jawnego ograniczenia listy hostów.

**Uruchomienie:** pakiety START dla działającego Windows/macOS i obraz Linux dla wspieranych PC dzielą kod aplikacji. Jeden uniwersalny obraz startowy dla PC oraz wszystkich Maców nie jest realistycznym założeniem tego wydania. Przypadki zablokowanego startu i niesprawnego systemu trzeba rozpoznać przed awarią.

**Stanowisko odbiorcze:** jedna OSP upraszcza odpowiedzialność, lecz jest pojedynczym punktem utraty usługi. Drugi dyżurny i uzgodnione zastępstwo mogą poprawić wynik wcześniej niż automatyczna replikacja bazy. Automatyczne przejęcie wymaga nowego kontraktu odpowiedzialności za zgłoszenie.

## Niezależność dostawców

Wymaganie dotyczy możliwego do zbudowania wariantu całej funkcji. Modem A i B mają wspólną ramkę oraz USB, lecz różne układy RF/MCU, nastawy i płytki. Adapter Ethernet, elementy ochrony, przetwornica i port ładowania też wymagają kwalifikowanych alternatyw. Zmiana transformatora lub regulatora może wymagać zmiany konstrukcji, nie tylko numeru w BOM.

Lista zamienników podaje wariant, producenta, parametry krytyczne i dowód próby. Otwarta licencja oraz kilka sklepów nie stanowią dowodu niezależności produkcji. Wspólne złącza, przewody, formaty i możliwość zlecenia PCB wielu wykonawcom zmniejszają zależność, ale jej nie znoszą.

# WICI — Uruchomienie po dopuszczeniu prototypu

**Tych kroków nie zaczynać od zamówienia obecnego kompletu.** Najpierw zakończyć pozycje z `przed-produkcja.md`. Do wykonania potrzebne będą miernik, programator SWD i osoba zdolna sprawdzić montaż SMD. Montaż CC1120 QFN i elementów RF 0402 warto zlecić; nie jest to dobry pierwszy projekt lutowania.

| Krok | Czynność | Warunek przejścia |
|---:|---|---|
| 1 | Kontroler bez modułu RF. Oględziny pinów U1/U2/U3/Q1 i pomiar VBUS–GND oraz 3,3 V–GND bez napięcia | Brak mostków, zgodna orientacja układów; brak utrzymującego się zwarcia. Ładowanie kondensatorów może chwilowo zmienić wskazanie |
| 2 | Podać 5,0 V przez przeznaczony do prób przewód USB z zasilacza laboratoryjnego, limit 100 mA; jeszcze bez laptopa i programatora | TP2: 3,3 V ±5%; brak ograniczenia prądu i szybkiego nagrzewania. Jeśli limit zadziała, odłączyć i znaleźć przyczynę |
| 3 | Dołączyć SWD bez wyjścia zasilającego programatora; wgrać zatwierdzony obraz testowy | Odczyt właściwego MCU, poprawna weryfikacja flash, reset wraca do pracy |
| 4 | Firmware: HSE bypass 8 MHz; PLL ×9 → 72 MHz; USB /1,5 → 48 MHz; APB1 ≤36 MHz. Q1 pozostaje wyłączony do gotowości USB | Stabilny start i reset. Brak deklarowania gotowości przy awarii zegara |
| 5 | Próba USB bez radia na Windows, Linux i macOS; 100 odłączeń/podłączeń oraz godzina transmisji danych kontrolnych | Dwie wymagane funkcje CDC, poprawne identyfikatory USB, brak błędów danych i zawieszeń; prąd przed konfiguracją ≤100 mA |
| 6 | Wyłączyć zasilanie. Sprawdzić każdą żyłę przewodu J2 według tabeli. Podłączyć moduł RF; pierwszy start wyłącznie RX/IDLE | SPI około 1 MHz: właściwy identyfikator/revision, zapis i odczyt rejestrów, reset, poprawna praca obu IRQ. Nie nadawać przy błędzie |
| 7 | Dwa kompletne modemy. Próba przewodowa w ekranowanym układzie 50 Ω z dobranym tłumikiem; TX dopiero z potwierdzonym profilem | Częstotliwość, moc, widmo i stabilność zegara w granicach P1; nigdy nie łączyć nadajnika bezpośrednio z wejściem odbiornika |
| 8 | Przesłać w obu kierunkach 1000 datagramów o znanej zawartości, 1/86/87/600 B; próby przerwania zasilania i kolejki | Brak uszkodzonej treści; raport wszystkich utrat i retransmisji; brak TX po restarcie bez ważnego dziennika limitu |
| 9 | Dopiero potem próba antenowa i pomiar w zabudowie, zgodnie z warunkami użycia pasma w Polsce | Zapisać odległość, położenie anten, RSSI, PER, liczbę prób i temperaturę. Nie wyciągać wniosku o 1 km z testu na stole |

Przed montażem wydrukować `mechanika-1-do-1.pdf` w skali 100%, bez odbicia i bez dopasowania do strony. Zmierzyć wzorzec 50 mm oraz obrys 70 × 55 mm. Dopasować rzeczywiste USB-B, SW1 i IDC; potwierdzić numery pinów USB i styki przycisku. Zapisać użyte MPN i wynik. Sam zgodny rozstaw otworów nie potwierdza numeracji styków.

Odbiór zasilania: zmierzyć napięcia i temperaturę regulatora przy ciągłym odbiorze i maksymalnym dozwolonym cyklu nadawania. Wynik porównać z warunkami pracy komponentów; sam katalogowy prąd 600 mA regulatora nie określa możliwości cieplnych tej płytki.

Każdy egzemplarz dostaje osobny zapis: numer, wersje PCB i firmware, użyte części, pomiary, wynik i osoba wykonująca próbę. Wyniki dwóch sztuk są minimum do testu łączności; nie są potwierdzeniem produkcji masowej.

Pomiary F1: napięcie na J1.1 względem GND, napięcie na TP1 za F1, prąd całego układu i temperatura PPTC przy docelowej pracy. Sprawdzić zachowanie wybranego bezpiecznika w najwyższej wymaganej temperaturze. Nie używać portu laptopa do prób zwarciowych. Limit zasilacza laboratoryjnego i limity USB pozostają potrzebne.

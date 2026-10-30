# WICI: radia RNode

Radia RNode to dwa zestawy RAK19007 z RAK4631 (nRF52840 i SX1262) z oficjalnym firmware RNode, podłączone przez USB do laptopów z Reticulum w Pythonie. Są wzorcem profilu LoRa i narzędziem kroków 2, 3 i 5 planu ([koncepcja, rozdział 08](../../docs/concept/08-plan-weryfikacji-i-decyzje.html#kolejnosc-prac)), a w kroku 4 partnerem prototypu przy sprawdzaniu zgodności interfejsu LoRa stacji. Zestawy zamówiono 2026-10-29. Własnego programu WICI na tych radiach nie ma.

Nastawy profilu i plik konfiguracji interfejsu są w jednym miejscu: [specyfikacja radia, „Radia RNode”](../../docs/spec/radio.md#radia-rnode). Procedura pomiaru, formularz i zapis wyników są w [odbiorze](../../docs/spec/odbior.md#pomiar-tras-kroki-2-3-i-5). Ten plik opisuje tylko przygotowanie sprzętu.

## Odbiór zestawów

1. Sprawdzić na zestawie i w dokumentach dostawy, że RAK4631 jest w wersji na pasmo 868 MHz (wersja H w oznaczeniu RAK). Zestaw w innej wersji pasma nie nadaje się do pomiarów w profilu WICI.
2. Zapisać numery seryjne obu zestawów i oznaczyć je na obudowie (1 i 2).
3. Antena 868 MHz musi być przykręcona do złącza, zanim radio dostanie zasilanie i zacznie nadawać.

## Wgranie firmware

Na laptopie z Pythonem 3 instaluje się Reticulum (`pip install rns`; wersja jak w [odbiorze](../../docs/spec/odbior.md#pomiar-tras-kroki-2-3-i-5)) i wgrywa firmware na każdy zestaw osobno:

```bash
rnodeconf --autoinstall
```

W kreatorze wybiera się płytkę RAK4631 i pasmo 779–928 MHz. Autor RNode oznacza obsługę RAK4631 jako eksperymentalną, więc każdy zestaw sprawdza się po wgraniu:

```bash
rnodeconf --info /dev/ttyACM0
```

Wersję firmware, pasmo i numer seryjny zapisuje się w raporcie kroku 2. Port (`/dev/ttyACM0` na Linuksie, `/dev/cu.usbmodem…` na macOS) odczytuje się po podłączeniu zestawu.

## Konfiguracja Reticulum

Interfejs `RNodeInterface` w `~/.reticulum/config` obu laptopów ustawia się według [specyfikacji radia](../../docs/spec/radio.md#radia-rnode), w profilu pilotażu i z kodem dostępu sieci (IFAC). Wiersz `ifac_size = 128` trzeba wpisać wprost: bez niego RNode używa kodu 8 B, a stacja 16 B, i ramki stacji oraz radia RNode się nie wymieniają. Nazwa i hasło sieci próby są wspólne dla obu końców i nie trafiają do repozytorium ani do raportu.

Po uruchomieniu `rnsd` polecenie `rnstatus` pokazuje interfejs RNode z IFAC.

## Próba przy stole (krok 2)

Dwa laptopy, każdy z jednym radiem RNode, kilka metrów od siebie. Przebieg i warunek zaliczenia (próby `rnprobe` w obie strony w SF7 i SF8, kontrola IFAC przy różnych hasłach) są w [odbiorze, „Krok 2”](../../docs/spec/odbior.md#krok-2-radia-rnode-przy-stole). Wynik: dwa sprawdzone radia RNode i plik konfiguracji interfejsu bez hasła w raporcie. W tym kroku sprawdza się też moc na złączu RAK4631 przy nastawie z profilu.

## Praca w terenie

Na jakiej podstawie radia RNode mogą nadawać poza budynkiem (kroki 3 i 5), nie jest jeszcze ustalone. Odpowiedź trzeba zapisać przed pierwszym pomiarem w terenie ([odbiór, „Podstawa pomiarów radiami RNode”](../../docs/spec/odbior.md#podstawa-pomiarów-radiami-rnode)). Do tego czasu radia RNode nie nadają poza budynkiem.

Licencja tego pliku: CC-BY-4.0 ([LICENSE.md](../../LICENSE.md)). Firmware RNode i Reticulum mają licencje swoich autorów.

# WICI — R01.3 — pliki produkcyjne kontrolera

| Pozycja | Wynik |
|---|---|
| Stackup | Zapisany w PCB standard JLC04161H-7628, nominalnie 1,6 mm; jawne grubości miedzi i dielektryków. In1 = GND, In2 = 3,3 V |
| Napis | `WICI R01.3` |
| BOM | Konkretne MPN i producenci wszystkich 39 elementów; 22 grupy części |
| IDC | Wybrany Würth 61201021621. Otwory pinów powiększone z 1,0 do zalecanych 1,1 mm |
| Eksport | Gerbery, osobne PTH/NPTH, mapy wierceń, pozycje 39 elementów i 34 SMT, BOM montażowy, pasta F.Paste |
| Kontrola CAD | ERC 0, DRC 0, brakujących połączeń 0, różnic schemat–PCB 0 |
| Kontrola eksportów | Parser Gerberów i Excellon: pady, obrys, wiercenia i pozycje zgodne z PCB. Wiercenia uwzględniają wyłącznie zaokrąglenie eksportu do 1 µm |
| Odtworzenie | Skrypty i zachowana sesja trasowania dają identyczną geometrię, schemat, BOM i połączenia |
| Fizyczne dopasowanie | **Nie wykonano**. PDF 1:1 jest aktualny; wymagane rzeczywiste USB-B, SW1 i IDC |

Paczka: [wici-controller-R01.3.zip](fabrication/wici-controller-R01.3.zip). Instrukcja dla wykonawcy: [fabrication/R01.3/README.md](fabrication/R01.3/README.md). Wyniki eksportów: `checks/fabrication-verification.json`.

Stos jest wariantem referencyjnym produkcji, nie zależnością od jednej fabryki. Inny wykonawca może potwierdzić równoważny stos. Sam zapis stosu nie jest dowodem poprawnej impedancji USB. Status kwalifikacji pozostaje HOLD; moduł RF nadal jest osobnym, niedokończonym projektem.

Źródła: [stos producenta](https://jlcpcb.com/impedance), [IDC](https://www.we-online.com/components/products/datasheet/61201021621.pdf), [SW1](https://omronfs.omron.com/en_US/ecb/products/pdf/en-b3f.pdf), [LED](https://www.kingbrightusa.com/images/catalog/spec/apt2012lseck-j3-prv.pdf), [rezystory](https://www.vishay.com/docs/20035/dcrcwe3.pdf). Pozostałe karty są podane przy MPN w BOM-ie. Numery części wyznaczają wariant montażowy; zamienniki muszą zachować parametry, wymiary i polaryzację. C2/C9 nadal wymagają potwierdzenia pojemności efektywnej i próby stabilności LDO.

# WICI — R01.2 — poprawki kontrolera

Zakres: zasilanie, wewnętrzne płaszczyzny miedzi, montaż i kontrola złączy. Nie zmieniono profilu radia, pinów MCU ani tras USB.

| Zmiana | Wynik CAD |
|---|---|
| VBUS i VBUS_USB | Wszystkie ścieżki 0,5 mm |
| 3,3 V | 30,11 mm ścieżek 0,5 mm; 7,89 mm krótkich wyprowadzeń 0,2 mm przy pięciu pinach MCU. Najdłuższy wąski odcinek: 1,89 mm. Zamiast poprzednich 90,83 mm rozprowadzenia na górze |
| Przelotki 3,3 V | 22 zamiast 3; każdy kondensator na 3,3 V ma własną przelotkę do płaszczyzny |
| Przelotki masy kondensatorów | Osobna przy każdym C1–C14. C12 jest filtrem resetu; ma własną przelotkę masy |
| Wewnętrzne warstwy | In1 = GND, In2 = 3,3 V. Zero ścieżek na obu; sygnały na F.Cu/B.Cu |
| Otwory | Cztery NPTH Ø3,2 mm; środki 4 mm od krawędzi. Rozstaw 62 × 47 mm. Wokół każdego obszar bez ścieżek, przelotek i pola miedzi Ø6,4 mm |
| Zabezpieczenie VBUS | F1 = PPTC 0,5 A w szeregu między USB a regulatorem; dwa wskazane źródła części |
| Mechanika USB / SW1 / IDC | Powstał PDF 1:1 z rzeczywistych współrzędnych CAD, numerami pinów i wzorcem 50 mm. Fizyczne dopasowanie nie jest wykonane |

F1: Bourns MF-NSMF050-2. Alternatywa do kwalifikacji: Littelfuse 1206L050/15YR. Własny, powiększony footprint ma pola 1,8 × 1,8 mm i odstęp 1,0 mm; pokrywa zalecane pola obu producentów. Montaż reflow według wybranej karty, bez ograniczania rozszerzania się obudowy PPTC.

„0,5 A” to prąd podtrzymania przy temperaturze katalogowej, nie precyzyjny ogranicznik prądu. Prąd zadziałania wynosi 1 A. Przy wyższej temperaturze prąd podtrzymania maleje. Trzeba zmierzyć spadek napięcia, temperaturę i zachowanie przy obciążeniu kontrolera z radiem. Firmware nadal musi spełniać limit USB przed konfiguracją. U3 i C14 pozostają na stronie złącza przed F1, jako odniesienie ochrony ESD linii USB. F1 chroni gałąź zasilającą kontroler; nie jest ochroną przed przepięciem ani gwarancją ochrony hosta.

Biblioteki nowych symboli Polyfuse, MountingHole, PWR_FLAG i footprint otworów pochodzą z KiCad 10.0.6. Pozostałe źródła symboli zachowują wcześniejsze pochodzenie. Połączenia, BOM, schemat, PCB i lokalne biblioteki są zaktualizowane razem.

Odtworzenie w osobnej kopii z zachowanej sesji routingu dało identyczną geometrię PCB, schemat, BOM i połączenia oraz ERC/DRC = 0. Raport: `checks/replay-verification.json`.

Raport zmian: `checks/controller-revision.json`. ERC/DRC i zgodność PCB–schemat: `checks/status.json`. Nie dodano wyjątków DRC ani nie zmniejszono reguł. Status kompletnego modemu pozostaje HOLD z powodów opisanych w `przed-produkcja.md`.

Źródła części: [Bourns MF-NSMF](https://www.bourns.com/docs/product-datasheets/mf-nsmf.pdf), [Littelfuse 1206L](https://www.littelfuse.com/assetdocs/littelfuse-ptc-1206l-datasheet?assetguid=2b6a1515-d4ee-4c83-8bd4-152b4901b8f5). Karta Bourns jest zachowana prywatnie; karta Littelfuse została przeczytana online, pobranie lokalne zwróciło 403.

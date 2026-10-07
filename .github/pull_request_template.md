## Co zmienia ten PR

## Powiązania

Issue, ustalenia przeglądu (F), decyzje (D), próby (T) i wymagania (W), których dotyczy zmiana.

## Jak sprawdzono

- [ ] `python3 -m unittest discover -s software/reference -v`
- [ ] `python3 -m unittest discover -s tests -v`
- [ ] `python3 tools/verify_repository.py --pull-request`
- [ ] `pipx run reuse==5.0.2 lint` (nowe pliki mają licencję)
- [ ] Zaktualizowano dowody dotknięte zmianą (wyniki obliczeń, paczka sprzętu); **bez** odświeżania `manifest.json`

## Zgodność

- [ ] Każdy commit ma `Signed-off-by` (DCO)
- [ ] Założenia są oddzielone od pomiarów; żadna niewykonana próba nie jest oznaczona jako zaliczona
- [ ] Zmiana dotyczy części krytycznej dla bezpieczeństwa (230 V, ochrona przed przepięciem, akumulatory, budżet nadawania)
- [ ] Przy zmianie użyto narzędzi AI (opisz zakres)

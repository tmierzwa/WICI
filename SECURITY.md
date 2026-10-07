# Bezpieczeństwo — zgłaszanie podatności

WICI obsługuje tożsamości kryptograficzne stacji, dane o potrzebach ludzi i opisuje urządzenia zasilane z akumulatorów oraz 230 V. Błąd może więc narazić ludzi, a nie tylko dane.

## Jak zgłosić

Podatności **nie zgłaszaj publicznie w Issues**. Użyj [prywatnego zgłoszenia podatności na GitHubie](https://github.com/tmierzwa/WICI/security/advisories/new). Opisz problem, dotknięte pliki lub wersję, sposób odtworzenia i możliwe skutki. Odpowiedź otrzymasz w ciągu 7 dni; ustalimy termin publikacji po przygotowaniu poprawki.

Zgłaszaj prywatnie zwłaszcza:

- obejście weryfikacji nadawcy, podszycie pod odbiorcę (OSP) lub ujawnienie danych mieszkańców;
- sposób wyłudzenia potwierdzenia RECEIVED bez trwałego zapisu;
- obejście budżetu czasu nadawania, ciszy radiowej lub polecenia ZNISZCZ DANE;
- błąd w opisie zasilania, który może spowodować porażenie, pożar lub uszkodzenie telefonu.

Błędy obliczeń i dokumentacji bez takich skutków zgłaszaj zwykłym Issue.

## Zakres

Projekt jest w fazie prototypu 0.4 i nie ma wydania przeznaczonego do pracy w schronieniu. Podatności w Reticulum, LXMF i innych zależnościach zgłaszaj ich autorom; jeśli dotyczą sposobu użycia ich w WICI, zgłoś je także tutaj.

## In English

Do not open public issues for vulnerabilities. Use [GitHub private vulnerability reporting](https://github.com/tmierzwa/WICI/security/advisories/new). We reply within 7 days.

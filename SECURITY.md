# Bezpieczeństwo: zgłaszanie podatności

WICI obsługuje tożsamości kryptograficzne stacji i dane o potrzebach ludzi oraz opisuje urządzenia zasilane z akumulatorów i z sieci 230 V. Błąd może więc zagrozić zarówno danym, jak i ludziom.

## Jak zgłosić

Podatności **nie zgłaszaj publicznie w Issues**. Użyj [prywatnego zgłoszenia podatności na GitHubie](https://github.com/tmierzwa/WICI/security/advisories/new). Opisz problem, dotknięte pliki lub wersję, sposób odtworzenia i możliwe skutki. Odpowiedź otrzymasz w ciągu 7 dni. Termin publikacji ustalimy po przygotowaniu poprawki.

Zgłaszaj prywatnie zwłaszcza:

- obejście weryfikacji nadawcy, podszycie pod odbiorcę (OSP) lub ujawnienie danych mieszkańców;
- sposób wyłudzenia potwierdzenia RECEIVED bez trwałego zapisu;
- obejście budżetu czasu nadawania, ciszy radiowej lub polecenia ZNISZCZ DANE;
- polecenia protokołu USB `configure`, `export`, `import` lub aktualizacja oprogramowania wykonane poza trybem przygotowania (przycisk wewnątrz obudowy); `destroy` lub `silence` przez USB wykonane bez potwierdzenia przyciskiem na stacji w ciągu 30 s; ZNISZCZ DANE uruchomione wiadomością radiową (radio nigdy go nie uruchamia);
- paczka eksportu tożsamości czytelna bez klucza stacji docelowej, eksport jawnego klucza prywatnego albo tożsamość pozostała na stacji źródłowej po potwierdzonym imporcie;
- przyjęcie obrazu oprogramowania bez poprawnego podpisu wydania lub starszego niż zainstalowany (anti-rollback), aktualizacja przez DFU/UF2 bez podpisu, podmiana podpisanego `build-manifest.json` pakietu START;
- słaby lub przewidywalny generator liczb losowych przy tworzeniu tożsamości, kluczy lub identyfikatorów wiadomości;
- odczyt pamięci mikrokontrolera mimo ochrony (SWD, APPROTECT, szyfrowanie flash) albo odczyt FRAM po ZNISZCZ DANE;
- dostęp z sieci Wi-Fi do panelu opiekuna lub dyżurnego (`/operator`, `/api/operator/*`, dostępne tylko z 127.0.0.1), do cudzego zgłoszenia lub tokenu mieszkańca, albo zapis treści zgłoszeń, tokenów, adresów IP lub MAC w dziennikach;
- błąd w opisie zasilania, który może spowodować porażenie, pożar lub uszkodzenie telefonu.

Błędy obliczeń i dokumentacji bez takich skutków zgłaszaj zwykłym Issue.

## Zakres

Projekt jest w fazie prototypu 0.5 i nie ma wydania przeznaczonego do pracy w schronieniu. Podatności w Reticulum, microReticulum, LXMF i innych zależnościach zgłaszaj ich autorom; jeśli dotyczą sposobu użycia ich w WICI, zgłoś je także tutaj.

Wymagania wobec wyrobu: obowiązki z norm EN 18031-1 i -2 (rozporządzenie delegowane (UE) 2022/30 do dyrektywy RED) oraz z rozporządzenia o cyberodporności (UE) 2024/2847 spoczywają na podmiocie, który wprowadza wyrób do obrotu (producent lub importer), a nie na projekcie WICI. Producent deklaruje okres wsparcia oprogramowania (≥5 lat) i własny kanał zgłaszania podatności. Kanał opisany w tym pliku dotyczy specyfikacji i kodu referencyjnego WICI, a nie wyrobów producentów.

## In English

Do not open public issues for vulnerabilities. Use [GitHub private vulnerability reporting](https://github.com/tmierzwa/WICI/security/advisories/new). We reply within 7 days.

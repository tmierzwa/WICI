# Warstwa transportu: szew, koperta i nośniki

**Stan: implementacja przed próbą D21, 2026-11-01.** Numerowana konfiguracja uruchamia WICI-Link na surowym SX1262; konfiguracja bez numerów uruchamia Reticulum. Warunek przyjęcia D21 nadal wymaga próby przy stole na docelowym sprzęcie ([kryteria](#warunek-przyjęcia)).

## Po co

Wybór stosu sieciowego ma wpływ na licencję, umowy z gminą, zgodność (D20) i zapas czasu w W10. Dziś aplikacja stacji (SA1, kolejka w FRAM, trzy potwierdzenia) prawie nie zależy od stosu, ale bezpieczeństwo, adresy i karty stacji zależą od Reticulum i LXMF. Ten dokument wyznacza granicę między nimi tak, aby:

1. aplikacja WICI i jej bezpieczeństwo nie zależały od nośnika;
2. stacja mogła używać własnego protokołu łącza [WICI-Link](wici-link.md) albo innego nośnika bez zmian w logice stacji;
3. stanowisko odbiorcze mogło jednocześnie odbierać ruch z kilku nośników, np. sieci WICI, węzła Meshtastic lub MeshCore podłączonego przez USB i łącza IP do powiatu;
4. jeden zestaw prób sprawdzał każdy nośnik według tych samych kryteriów.

## Warstwy

| Warstwa | Odpowiada za | Gdzie |
|---|---|---|
| Aplikacja SA1 | sześć typów wiadomości, cykl życia zgłoszenia, trzy potwierdzenia (W06), kolejka i rejestr w FRAM, deduplikacja po (nadawca, `id`, `revision`) | `station.cpp`, `store`, `sa1`, `ui`; aplikacja stanowiska |
| Koperta WICI | uwierzytelnienie i poufność od końca do końca, ochrona przed powtórzeniem, podział na części, adresy stacji z kart | nowa, w stacji (C++) i na stanowisku (Python) |
| Szew nośnika | wysłanie, odbiór, zdarzenia doręczenia, zdolności, cisza radiowa, stan | interfejs `Bearer` |
| Nośnik | trasy, przekazywanie, potwierdzenia na łączu, dostęp do kanału | WICI-Link, Reticulum (obecny rdzeń), Meshtastic, MeshCore, IP |
| Warstwa fizyczna | modulacja, sterownik radia | własny sterownik SX1262 albo oprogramowanie obcego węzła |

Zasada: **nośnik niczego nie gwarantuje aplikacji poza próbą dostarczenia bajtów**. Autentyczność nadawcy, poufność treści i potwierdzenie przyjęcia zgłoszenia zapewniają koperta i SA1. Słabsze bezpieczeństwo nośnika (np. kanał Meshtastic bez uwierzytelnienia, MeshCore z AES-ECB i 2-bajtowym MAC) wpływa wtedy na metadane i odporność na zalew, ale nie pozwala podrobić zgłoszenia ani potwierdzenia.

## Koperta WICI

### Klucze

Każda stacja i każda tożsamość odbiorcy (główna i zapasowa) ma statyczną parę kluczy X25519 wygenerowaną w urządzeniu przy przygotowaniu. Koperta używa pierwszych 32 B istniejącego klucza prywatnego i publicznego tożsamości Reticulum; HKDF z osobną etykietą „WICI env v1” oddziela klucz koperty od kluczy stosu. Klucz publiczny trafia na kartę stacji albo kartę odbiorcy, tak jak dziś ([protokół USB](usb-protocol.md)); w karcie numerowanej jest też jawnie podany jako `x25519`, zgodny z pierwszymi 32 B pełnego klucza `key`. Kluczy nie przyjmuje się przez radio (bez zmian względem D08).

Przed włączeniem koperty przygotowanie nadaje `net_id` sieci i niepowtarzalny numer u16 każdej stacji oraz obu tożsamości odbiorcy. Karty wiążą numer, `net_id` i pełny klucz publiczny; `configure` sprawdza lokalną spójność numerów i sieci, a rejestr kart na stanowisku odrzuca duplikat numeru z innym kluczem. Obecny kontrakt `configure` i kart nie zawiera tych pól: trzeba go rozszerzyć oraz sprawdzić przeniesienie stacji, KLUCZ ZAPASOWY i odtworzenie stanowiska przed przełączeniem ruchu na kopertę. Adapter Reticulum w pierwszym kroku zachowuje obecne 16-bajtowe adresy i zachowanie SA1; mapowanie na numery uruchamia się dopiero po przygotowaniu kart.

Klucz pary nadawca A → odbiorca B:

```
ss      = X25519(sk_A, pk_B)
K_A→B   = HKDF-SHA-256(ikm = ss, salt = net_id ‖ 0x01,
                       info = "WICI env v1" ‖ id_A ‖ id_B ‖ pk_A ‖ pk_B, L = 32)
```

Kierunek B → A ma osobny klucz (zamienione `id` i `pk` w `info`), więc liczniki obu stron nigdy nie dzielą nonce. `net_id`, `id_A` i `id_B` koduje się jako u16 BE; `pk_A` i `pk_B` to surowe klucze X25519 po 32 B. Stacja ma te prymitywy w przypiętej bibliotece Crypto. Implementacja Python używa przypiętego pakietu `cryptography` (48.0.1); pakiet stanowiska musi go dołączyć i sprawdzić na obsługiwanych systemach przed D21.

Pilotaż nie ma poufności przyszłej (forward secrecy): przejęty klucz prywatny odbiorcy odsłania zapisany wcześniej ruch, tak jak dziś przy pakietach okazjonalnych LXMF. Wymiana kluczy następuje przez USB przy przeglądzie (D08). Rotacja przez radio jest poza pilotażem.

### Format

```
 0      1      3      5             9                         n-16      n
 +------+------+------+-------------+-------------------------+---------+
 | kind | src  | dst  | ctr (u32 BE)| szyfrogram (ChaCha20)    | tag(16) |
 +------+------+------+-------------+-------------------------+---------+
 kind: bity 7–6 wersja (1), bity 5–4 część (0 = całość, 1 = 1/2, 2 = 2/2), bity 3–0 rodzaj (0 = SA1, 1 = TEST łącza, reszta zarezerwowana)
 src, dst: numery stacji z planu sieci (u16, 0x0000 i 0xFFFF zarezerwowane)
 nonce (12 B) = src ‖ dst ‖ kind ‖ 0x000000 ‖ ctr
 AAD = kind ‖ src ‖ dst ‖ ctr
```

Narzut koperty: 25 B (9 B nagłówka i 16 B znacznika). Numery stacji są jawne. Przekaźnik widzi więc nadawcę i odbiorcę od końca do końca, co pozwala mu przypisać pakiet do klasy K1 także w kierunku od odbiorcy ([klasy czasu](wici-link.md#klasy-czasu-kanału)). Analiza ruchu jest i tak przyjęta w [rozdziale 07](../concept/07-zagrozenia-i-odpornosc.html): dziś nagłówek Reticulum też ujawnia cel, a rozmiar ujawnia typ SA1.

### Licznik i powtórzenia

- Nadawca prowadzi licznik `ctr` osobno dla każdej pary (A, B) i zapisuje go w FRAM z wyprzedzeniem bloku 64 wartości: przed użyciem wartości `c` zapisany jest co najmniej `c + 1`. Po restarcie licznik startuje od zapisanej wartości. Wartość licznika nigdy się nie powtarza; po 2³² − 1 para wymaga nowych kluczy (przy 1 wiadomości na sekundę to ponad 136 lat).
- Odbiorca przyjmuje kopertę tylko wtedy, gdy `ctr` jest większy od największego przyjętego albo mieści się w oknie 64 ostatnich wartości i nie był przyjęty. Stan okna (największy `ctr` i maska) zapisuje w FRAM stacji albo SQLite stanowiska w tej samej transakcji co przyjęcie wiadomości SA1.
- Powtórka potwierdzana na skoku musi mieć bit przyjęcia w trwałym oknie. Licznik starszy niż okno jest odrzucany bez HACK, bo brak bitu nie dowodzi wcześniejszego przyjęcia; nowa intencja SA1 potrzebuje wtedy nowego licznika.
- Deduplikacja SA1 po (nadawca, `id`, `revision`) zostaje. Koperta odrzuca powtórzenie pakietu, SA1 odrzuca ponowienie tej samej wiadomości.

**PRZENIEŚ STACJĘ.** Zaszyfrowana migawka 256 KiB obejmuje tożsamość, klucze koperty, zatwierdzone granice rezerwacji `ctr` i okna powtórzeń dla odbioru. Po imporcie stacja docelowa zaczyna nadawanie od przeniesionej granicy (nawet jeśli część zarezerwowanych wartości nie została użyta); nie zeruje licznika ani okien. Źródłowa przestaje nadawać przed utworzeniem paczki, zgodnie z [krokami przeniesienia](usb-protocol.md#przeniesienie-stacji). Brak któregokolwiek z tych pól albo niepewna granica blokuje aktywację z tą samą tożsamością; wymaga nowych kluczy i kart. Oprogramowanie obsługuje wznowienie po przerwaniu USB, wycofanie i trwałe oznaczenie wycofanej lub wyłączonej stacji. Próba zaniku zasilania na sprzęcie docelowym pozostaje warunkiem D21.

**Odtworzenie stanowiska z kopii.** Starsza kopia SQLite może mieć niższą granicę rezerwacji `ctr` niż ostatnio użyta z tą samą tożsamością odbiorcy. Dopóki źródłowy nośnik nie przekaże nowszej granicy i okien powtórzeń, odtworzone stanowisko nie nadaje kopert pod tymi kluczami. Jeżeli granicy nie da się udowodnić, przygotowanie tworzy nowe tożsamości odbiorcy i nowe karty dla stacji. Próba wycofania kopii po wysłanej kopercie musi potwierdzić tę blokadę przed włączeniem nośnika D21.

### Podział na części

Gdy koperta przekracza `max_payload` nośnika, nadawca dzieli jawny tekst SA1 na dwie części i każdą szyfruje jako osobną kopertę z tym samym `ctr` oraz polem `część` 1 albo 2 (bity części w `kind` zmieniają nonce). Odbiorca składa tekst po uwierzytelnieniu obu części w ciągu 120 s; niepełne składanie po tym czasie odrzuca. Wiadomość SA1 ma najwyżej 256 B ([SA1](oprogramowanie.md)), więc dwie części wystarczają dla każdego nośnika z `max_payload` ≥ 153 B (połowa 256 B tekstu i 25 B narzutu). Nośnik z mniejszym `max_payload` nie spełnia tego kontraktu.

Odbiorca zapisuje pierwszą uwierzytelnioną część trwale (FRAM stacji albo SQLite stanowiska) przed potwierdzeniem jej odbioru na łączu. Druga część może nadejść w dowolnej kolejności; po złożeniu odbiorca zatwierdza SA1 i okno `ctr` w jednej transakcji. Do tego czasu `ctr` pozostaje nieprzyjęty, a pamięć składania rozróżnia części po (`src`, `dst`, `ctr`, `kind` bez bitów części). Powtórzenie zapisanej części dostaje ponowne potwierdzenie łącza bez ponownego zapisu; sprzeczna treść części jest odrzucana. Po restarcie odbiorca wznawia składanie albo odrzuca je po 120 s i pozwala na ponowienie całej wiadomości z tym samym `ctr`. Potwierdzenie części nie oznacza przyjęcia SA1 ani zakończenia intencji nadawcy.

### Rozmiary

| Wiadomość SA1 | Treść | Koperta | Części przy WICI-Link (`max_payload` 236 B) |
|---|---|---|---|
| REQUEST typowe | 174 B | 199 B | 1 |
| REQUEST największe | 222 B | 247 B | 2 |
| BULLETIN największy | 246 B | 271 B | 2 |
| REPLY największe | 156 B | 181 B | 1 |
| STATUS | 59 B | 84 B | 1 |
| RECEIVED | 50 B | 75 B | 1 |

Dla porównania: typowe zgłoszenie jako pakiet okazjonalny LXMF ma dziś 403 B i zajmuje dwie ramki ([rozdział 06](../concept/06-wykonalnosc-i-budzet-zasobow.html)).

## Szew nośnika

Interfejs w stacji (C++, bez alokacji w czasie pracy). Aplikacja stanowiska ma odpowiednik w Pythonie o tych samych nazwach i znaczeniach.

`firmware/src/bearer.h` zawiera ten typowany kontrakt i osobny `LegacyBearer` dla obecnego szwu Reticulum w `station::Services`. Konfiguracja numerowana używa koperty i nośnika WICI-Link; konfiguracja bez numerów zachowuje adapter Reticulum. Typowany kontrakt jest podstawą do dalszych adapterów.

```cpp
struct BearerCaps {
  uint16_t max_payload;      // największa koperta w jednym wywołaniu send()
  uint8_t  max_hops;         // 0 = tylko sąsiedzi
  bool hop_ack;              // nośnik potwierdza i ponawia na każdym skoku
  bool e2e_ack;              // nośnik ma własne potwierdzenie od końca do końca
  bool airtime_classes;      // egzekwuje klasy K0/K1/K2, dług ciszy i limity z radio.md
  bool radio_silence;        // gwarantuje brak jakiegokolwiek nadawania w ciszy (W19)
  bool frame_filter;         // odrzuca obce ramki przed przetwarzaniem (klucz sieci)
};

enum class Delivery : uint8_t { Queued, Sent, HopAcked, E2EAcked, Rejected, Failed };
enum class TrafficClass : uint8_t { K0, K1, K2 };

struct LinkMeta { int16_t rssi_dbm; int8_t snr_db4; uint8_t hops; uint8_t bearer_id; };

class Bearer {
 public:
  virtual BearerCaps caps() const = 0;
  // Przyjmuje kopertę albo zwraca Rejected (pełna kolejka, limit klasy, cisza).
  virtual Handle send(StationId dst, ByteSpan envelope, TrafficClass k) = 0;
  virtual void   setSilence(bool on, bool allow_one_exempt) = 0;   // W19
  virtual Health health() const = 0;   // kolejka, budżet czasu, dług ciszy, rodzic, jakość łączy
  virtual void   poll() = 0;           // wywoływane z pętli stacji
  // Zgoda na potwierdzenie odebranej koperty, po transakcji w FRAM (dzisiejsze PROVE_APP).
  virtual void   confirm(RxHandle rx) = 0;
  void (*onReceive)(RxHandle rx, StationId src, ByteSpan envelope, const LinkMeta&, void* ctx);
  void (*onDelivery)(Handle, Delivery, void* ctx);
};
```

Reguły kontraktu:

1. **Doręczenie na nośniku nie jest potwierdzeniem aplikacji.** `HopAcked` i `E2EAcked` sterują tylko ponowieniami. Zgłoszenie jest przyjęte dopiero po RECEIVED (W06), jak dziś.
2. **Dowód po zapisie.** Nośnik z `e2e_ack` wysyła swoje potwierdzenie dopiero po wywołaniu `confirm(rx)` przez warstwę wyżej, po transakcji w FRAM (dzisiejsze PROVE_APP). Nośnik, który tego nie umie (potwierdza przy odbiorze), ma `e2e_ack = false` w tej roli.
3. **Zdolności zmieniają zachowanie, a nie kod aplikacji.** Gdy `airtime_classes` albo `radio_silence` jest fałszywe, stacja pokazuje w diagnostyce tryb ograniczony, a odbiór (próba „Wrogi węzeł”, W19) nie może być dla tej konfiguracji zaliczony.
4. **Odbiór niepewny.** Koperta, której nie da się odszyfrować kluczem żadnej znanej pary, jest odrzucana i liczona. Nie trafia do kwarantanny SA1, bo nie ma uwierzytelnionego nadawcy. Kwarantanna dotyczy dalej stacji z kluczem spoza listy zaufanych, ale z poprawną kopertą.
5. **Jeden nośnik radiowy na stację.** Układ SX1262 odbiera jednocześnie tylko jeden profil, a Meshtastic i MeshCore są całymi programami, nie bibliotekami. Stacja wybiera nośnik przy budowie obrazu. Kilka nośników naraz obsługuje tylko stanowisko odbiorcze (niżej).

## Nośniki

| Nośnik | Rola | `max_payload` | `hop_ack` / `e2e_ack` | `airtime_classes` / `radio_silence` | Uwagi |
|---|---|---|---|---|---|
| [WICI-Link](wici-link.md) | domyślny w stacji (po D21) | 236 B | tak / nie | tak / tak | własny protokół łącza; licencja MIT |
| Reticulum (rdzeń stacji) | obecny; zapasowy do rozstrzygnięcia D21 | 492 B | nie / tak (dowód) | tak / tak | adapter wokół `rns_node`; licencja Reticulum |
| Meshtastic (węzeł przez USB) | tylko stanowisko, po pilotażu | 227 B (PKI) | tak / tak (DM) | nie / nie | kanał bez uwierzytelnienia; ruch oznaczany jako niezweryfikowany, chyba że koperta ma klucz z karty |
| MeshCore (węzeł przez USB) | tylko stanowisko, po pilotażu | 184 B | nie / tak | nie / nie | `RAW_CUSTOM` dla koperty; domyślny budżet nadawania 50% wymaga ustawienia na ≤10% |
| IP (MQTT lub HTTPS) | stanowisko ↔ powiat, gdy działa internet | 64 KiB | — / tak | — / — | poza siecią radiową; ta sama koperta |
| Pamięć (symulator, testy) | testy i symulator | dowolne | konfigurowalne | konfigurowalne | wzorzec do prób zgodności |

Wartości `max_payload` dla Meshtastic i MeshCore pochodzą ze źródeł tych projektów sprawdzonych 2026-11-01 (ramka 255 B, nagłówek Meshtastic 16 B, narzut PKI 12 B; ładunek MeshCore 184 B) i trzeba je potwierdzić w adapterze.

### Stanowisko odbiorcze z kilkoma nośnikami

Aplikacja stanowiska ma jeden rejestr i jedną kolejkę odpowiedzi, a pod nimi listę nośników. W pilotażu numerowane stanowisko może uruchomić WICI-Link i równoległy port Reticulum (`--reticulum-port`); wybór ostatniego uwierzytelnionego nośnika dla każdej stacji zapisuje w tej samej migawce bazy co przyjęcie wiadomości. Odpowiedź wraca tym nośnikiem, chyba że dyżurny wskaże inny w panelu. Ruch z nośnika obcego bez koperty WICI (np. wiadomość tekstowa z sieci Meshtastic) trafi do osobnej skrzynki „niezweryfikowane”, bez RECEIVED i bez wpisu do rejestru zgłoszeń. Tę skrzynkę i jej obsługę opisze aplikacja stanowiska po pilotażu.

### Integracja w górę

Wymiana ze służbami i systemami gminy nie należy do szwu nośnika. To osobne adaptery aplikacji stanowiska: REQUEST ↔ OASIS EDXL-RM (zapotrzebowanie na zasoby), BULLETIN ↔ OASIS CAP, ewentualnie EMSI (ISO/TR 22351). Mapowanie pól opisze osobny dokument po pilotażu.

## Zgodność i próby

- Każdy nośnik przechodzi te same próby z [odbioru](odbior.md): W10, deduplikacja i powtórzenia, zimny start, zanik zasilania przy zapisie, „Wrogi węzeł” (tylko nośniki z `airtime_classes`), cisza radiowa (tylko z `radio_silence`). Próby uruchamia się na nośniku pamięciowym w CI i na sprzęcie przy stole.
- Próby zaniku obejmują przeniesienie tożsamości z zarezerwowanym `ctr`, restart po potwierdzeniu pierwszej części, restart przekaźnika po HACK i przed przekazaniem oraz ponowienie po wygaśnięciu składania. Wektory sprawdzają, że żaden z tych przebiegów nie powtarza pary (klucz, nonce) ani nie daje podwójnego przyjęcia SA1.
- Wektory koperty (klucze, nonce, szyfrogramy, części) generuje implementacja w Pythonie i sprawdza implementacja w C++, tak jak dziś wektory Reticulum (`tests/vectors/`).
- Każdy wariant obrazu stacji z innym nośnikiem radiowym jest osobną konfiguracją w rozumieniu D20 i wymaga własnych badań. Wariantów utrzymuje się jak najmniej.

## Warunek przyjęcia

D21 rozstrzyga się po próbie przy stole na dwóch zestawach RAK4631 i prototypie (kroki 2 i 4), na tych samych kryteriach dla WICI-Link i obecnego rdzenia:

1. W10: 50/50 RECEIVED przez jeden przekaźnik w czasie poniżej 15 min;
2. „Wrogi węzeł”: 20/20 zgłoszeń z RECEIVED w 30 min, utrzymane udziały klas;
3. pobór w budżecie W23 i zapas RAM ≥30% (D14);
4. zimny start i zanik zasilania bez utraty i bez podwójnego przyjęcia, także między HACK a przekazaniem oraz po potwierdzeniu pierwszej części;
5. przeniesienie stacji bez ponownego użycia (klucz, nonce), a rozsyłanie awaryjne bez pętli i przekroczenia limitu K2.

Jeżeli WICI-Link nie spełni warunku, zostaje rdzeń Reticulum, a ten dokument wraca do archiwum. Rozważane wcześniej oparcie stacji na rozwidleniu Meshtastic nie jest drogą zapasową, bo wymaga największych zmian i przenosi na zespół odpowiedzialność za cały obcy program (D20, CRA).

## Kolejność prac

**Stan wykonania, 2026-11-01.** Numerowane obrazy stacji łączą kopertę C++,
trwałe liczniki i okna powtórzeń, kolejkę przekaźnika, trasowanie, koordynator
skoku oraz surowe ramki SX1262 z CAD i trwałym długiem. Korzeń przekazuje
uwierzytelnione ramki do KISS i dopuszcza HACK z laptopa tylko po trwałym
przyjęciu koperty; echo ramki wychodzącej powstaje po faktycznym TX, nie po
przyjęciu do harmonogramu. Aplikacja stanowiska ma numerowany nośnik KISS,
trwałe przyjęcie fragmentów w SQLite, rezerwację liczników przed wysyłką i
blokadę wysyłki po odtworzeniu starszej kopii. Wyjątek od ciszy nadaje
niepotwierdzaną ramkę najwyżej trzy razy z trwałym licznikiem prób.
Numerowany przekaźnik ma trwały limit 60% dla całego ruchu tranzytowego i
BEACON-ów oraz 2% czasu nadawania dla BEACON-ów, z priorytetem K1 w kolejce.
Wspólny limit obejmuje również K1, bo sam jawny numer odbiorcy nie dowodzi
uprawnienia do tej klasy. Przy czekającym K1 limit 25% dotyczy zachowawczo
całego tranzytu i BEACON-ów. Odporność kolejki K1 na podrobione numery
wymaga jeszcze wdrożenia.

Pozostałe do zamknięcia D21: odporność kolejki K1 na podrobione numery, sprzętowe próby rozsyłania awaryjnego, pomiar
200 ms HACK, W10, „Wrogi węzeł”, zaniki zasilania oraz budżet energii. Dwie płytki
XIAO ESP32-S3 + Wio SX1262 przeszły [próbę toru radia przy stole](../../hardware/radio-pair/evidence/table-2026-11-01.md)
(100/100 w każdym kierunku) na programie diagnostycznym i
[próbę surowych ramek WICI](../../hardware/radio-pair/evidence/wici-raw-2026-11-01.md)
(19, 44 i 255 B bez zmiany bajtów). Formalna próba D21
na dwóch RAK4631 i prototypie pozostaje nierozstrzygnięta.

1. Szew `Bearer` i adapter wokół obecnego `rns_node`, bez zmiany zachowania; próby jak dziś. Przed przełączeniem na numery u16: rozszerzenie kart i `configure` o `net_id` i numery obu końców, z kontrolą ich zgodności.
2. Koperta w Pythonie z wektorami, potem w C++; próby różnicowe i rozszerzenie kontraktu PRZENIEŚ STACJĘ o liczniki oraz okna powtórzeń.
3. WICI-Link w C++ ([specyfikacja](wici-link.md)) i nośnik pamięciowy z symulacją wielu skoków, trwałą kolejką po HACK, składaniem części i rozsyłaniem awaryjnym.
4. Aplikacja stanowiska: nośnik WICI-Link przez KISS i warstwa wielu nośników.
5. Przeliczenie rozdziału 06 i próba przy stole według warunku przyjęcia.

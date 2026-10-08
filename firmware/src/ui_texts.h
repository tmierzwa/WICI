// SPDX-License-Identifier: MIT
// Teksty ekranu stacji: wygenerowane przez firmware/tools/ui_texts.py z jedynej kanonicznej
// listy w docs/spec/oprogramowanie.md ("Teksty ekranu"). Nie edytować ręcznie.
#pragma once

#include <stddef.h>
#include <stdint.h>

namespace ui_texts {

constexpr size_t LANGS = 3;
enum class Lang : uint8_t { PL = 0, UK = 1, EN = 2 };
constexpr size_t MAX_COLUMNS = 20;  // wiersz ekranu

// Teksty z identyfikatorami (kolumny PL, UK, EN); pusty napis = brak tekstu w tym języku.
enum class Id : uint8_t {
    RADIO_WLACZONE,
    CISZA,
    OSTATNI_KONTAKT,
    OSTATNI_KONTAKT_PONAD,
    KONTAKT_KROTKI,
    KONTAKT_PONAD_KROTKI,
    ZASILANIE_AA,
    ZASILANIE_12V,
    OGNIWA_NAPIECIE,
    KOLEJKA_KROTKI,
    NOWE_KROTKI,
    ZAPISANE_W_STACJI,
    WYSYLANIE,
    ZAPISANE_W_CISZY,
    STAN_1,
    STAN_2,
    STAN_3,
    STAN_4,
    STAN_5,
    STAN_6,
    BRAK_POTWIERDZENIA,
    BRAK_ODCZYTU,
    DZWIEK_WYCISZONY,
    ADRES_OGLOSZONY,
    TEST_ZAPLANOWANY,
    TEST_WYSLANY,
    TEST_WSTRZYMANY,
    ADRES_KONTROLA,
    ADRES_BRAK,
    PORZUCIC,
    PILNOSC_2,
    PILNOSC_1,
    PILNOSC_0,
    PILNOSC_2_POTW,
    PODSUMOWANIE_KLAWISZE,
    KOLEJKA_PELNA,
    BLAD_PAMIECI,
    OGNIWA_CZAS,
    WYMIEN_OGNIWA,
    WYLACZANIE,
    MOZNA_WYJAC,
    ODLACZONE_12V,
    TRYB_PRZYGOTOWANIA,
    ODBIORCA_ZAPASOWY,
    KOMPUTER_OSP,
    KOMPUTER_BRAK,
    ZNISZCZ_OSTRZEZENIE,
    STOPKA_KOMUNIKATU,
    ZAPISZ_NUMER,
    ODPOWIEDZI_PO_POLSKU,
    COUNT
};

constexpr const char* const TEXTS[static_cast<size_t>(Id::COUNT)][LANGS] = {
    {"RADIO WŁĄCZONE", "РАДІО УВІМКНЕНО", "RADIO ON"},
    {"CISZA RADIOWA – STACJA NIE NADAJE. PILNE: GONIEC", "РАДІОТИША – СТАНЦІЯ НЕ ПЕРЕДАЄ. ТЕРМІНОВО: ПОСИЛЬНИЙ", "RADIO SILENCE – NOT TRANSMITTING. URGENT: RUNNER"},
    {"OSTATNI KONTAKT Z ODBIORCĄ: [czas] TEMU", "ОСТАННІЙ ЗВ'ЯЗОК З ОДЕРЖУВАЧЕМ: [czas] ТОМУ", "LAST CONTACT WITH RECIPIENT: [czas] AGO"},
    {"OSTATNI KONTAKT Z ODBIORCĄ: PONAD [czas] TEMU", "ОСТАННІЙ ЗВ'ЯЗОК З ОДЕРЖУВАЧЕМ: ПОНАД [czas] ТОМУ", "LAST CONTACT WITH RECIPIENT: OVER [czas] AGO"},
    {"KONTAKT [czas] TEMU", "ЗВ'ЯЗОК [czas] ТОМУ", "CONTACT [czas] AGO"},
    {"KONTAKT >[czas] TEMU", "ЗВ'ЯЗОК >[czas] ТОМУ", "CONTACT >[czas] AGO"},
    {"OGNIWA: OKOŁO [x] H", "БАТАРЕЇ: ЩЕ [x] ГОД", "CELLS: ABOUT [x] H"},
    {"12 V: [x] V", "12 В: [x] В", "12 V: [x] V"},
    {"OGNIWA: [x] V", "БАТАРЕЇ: [x] В", "CELLS: [x] V"},
    {"CZEKA [n]: OD [czas]", "ЧЕКАЮТЬ [n]: [czas]", "WAITING [n]: [czas]"},
    {"NOWE WIADOMOŚCI: [n]", "НОВИХ ПОВІДОМЛ.: [n]", "NEW MESSAGES: [n]"},
    {"ZAPISANE W STACJI – CZEKA NA WYSŁANIE", "ЗБЕРЕЖЕНО В СТАНЦІЇ – ЧЕКАЄ НА ВІДПРАВЛЕННЯ", "SAVED IN STATION – WAITING TO SEND"},
    {"WYSYŁANIE – PRÓBA [n], NASTĘPNA ZA [m] MIN", "ВІДПРАВЛЕННЯ – СПРОБА [n], НАСТУПНА ЧЕРЕЗ [m] ХВ", "SENDING – ATTEMPT [n], NEXT IN [m] MIN"},
    {"ZAPISANE – NIE WYJDZIE DO KOŃCA CISZY", "ЗБЕРЕЖЕНО – НЕ ВІДПРАВИТЬСЯ ДО КІНЦЯ ТИШІ", "SAVED – NOT SENT UNTIL SILENCE ENDS"},
    {"ODBIORCA ZAPISAŁ", "ОДЕРЖУВАЧ ЗБЕРІГ", "RECIPIENT SAVED IT"},
    {"ODBIORCA PRZECZYTAŁ", "ОДЕРЖУВАЧ ПРОЧИТАВ", "RECIPIENT READ IT"},
    {"POMOC SKIEROWANA (DECYZJA, NIE GODZINA PRZYJAZDU)", "ДОПОМОГУ НАПРАВЛЕНО (РІШЕННЯ, НЕ ЧАС ПРИБУТТЯ)", "HELP DISPATCHED (DECISION, NOT ARRIVAL TIME)"},
    {"PRZEKAZANE DALEJ (PSP / POGOTOWIE / POWIAT)", "ПЕРЕДАНО ДАЛІ (ПОЖЕЖНІ / ШВИДКА / ПОВІТ)", "FORWARDED (FIRE SERVICE / AMBULANCE / COUNTY)"},
    {"ODBIORCA NIE MOŻE TERAZ POMÓC – CZYTAJ ODPOWIEDŹ", "ОДЕРЖУВАЧ ЗАРАЗ НЕ МОЖЕ ДОПОМОГТИ – ЧИТАЙТЕ ВІДПОВІДЬ", "RECIPIENT CANNOT HELP NOW – READ THE REPLY"},
    {"ZAMKNIĘTE", "ЗАКРИТО", "CLOSED"},
    {"BRAK POTWIERDZENIA OD [n] MIN – WYŚLIJ GOŃCA Z FORMULARZEM", "НЕМАЄ ПІДТВЕРДЖЕННЯ [n] ХВ – ВІДПРАВТЕ ПОСИЛЬНОГО З ФОРМОЮ", "NO CONFIRMATION FOR [n] MIN – SEND A RUNNER WITH THE FORM"},
    {"ODBIORCA NIE PRZECZYTAŁ OD 30 MIN – WYŚLIJ GOŃCA Z FORMULARZEM", "ОДЕРЖУВАЧ НЕ ПРОЧИТАВ 30 ХВ – ВІДПРАВТЕ ПОСИЛЬНОГО З ФОРМОЮ", "NOT READ BY RECIPIENT FOR 30 MIN – SEND A RUNNER WITH THE FORM"},
    {"DŹWIĘK WYCISZONY", "ЗВУК ВИМКНЕНО", "SOUND MUTED"},
    {"ADRES ZOSTANIE OGŁOSZONY", "АДРЕСУ БУДЕ ОГОЛОШЕНО", "ADDRESS WILL BE ANNOUNCED"},
    {"TEST ZAPLANOWANY ZA OKOŁO [mm] MIN – NIE WYŁĄCZAJ. WSTECZ = ANULUJ", "ТЕСТ ЗАПЛАНОВАНО ПРИБЛИЗНО ЧЕРЕЗ [mm] ХВ – НЕ ВИМИКАЙТЕ. НАЗАД = СКАСУВАТИ", "TEST SCHEDULED IN ABOUT [mm] MIN – DO NOT SWITCH OFF. BACK = CANCEL"},
    {"TEST WYSŁANY – CZEKA NA ODBIORCĘ", "ТЕСТ ВІДПРАВЛЕНО – ЧЕКАЄ НА ОДЕРЖУВАЧА", "TEST SENT – WAITING FOR RECIPIENT"},
    {"TEST WSTRZYMANY PRZEZ ODBIORCĘ", "ТЕСТ ПРИЗУПИНЕНО НА ПРОХАННЯ ОДЕРЖУВАЧА", "TEST PAUSED AT RECIPIENT'S REQUEST"},
    {"ADRES: [x] – CZY TO TO MIEJSCE? OK = TAK / WSTECZ = NIE", "АДРЕСА: [x] – ЦЕ ЦЕ МІСЦЕ? OK = ТАК / НАЗАД = НІ", "ADDRESS: [x] – IS THIS THE PLACE? OK = YES / BACK = NO"},
    {"STACJA NIE MA TWOJEGO ADRESU – UŻYJ FORMULARZA PAPIEROWEGO", "СТАНЦІЯ НЕ МАЄ ВАШОЇ АДРЕСИ – ВИКОРИСТАЙТЕ ПАПЕРОВУ ФОРМУ", "STATION DOES NOT HAVE YOUR ADDRESS – USE THE PAPER FORM"},
    {"PORZUCIĆ ZGŁOSZENIE? OK = TAK", "СКАСУВАТИ ЗАЯВКУ? OK = ТАК", "DISCARD REQUEST? OK = YES"},
    {"ZAGROŻENIE ŻYCIA", "ЗАГРОЗА ЖИТТЮ", "DANGER TO LIFE"},
    {"PILNE – KILKA GODZIN", "ТЕРМІНОВО – КІЛЬКА ГОДИН", "URGENT – A FEW HOURS"},
    {"W CIĄGU DOBY", "ПРОТЯГОМ ДОБИ", "WITHIN A DAY"},
    {"ZAGROŻENIE ŻYCIA: 1) UDZIEL PIERWSZEJ POMOCY 2) DZIAŁA TELEFON? 112 3) BEZPIECZNA DROGA? GONIEC. OK = WYŚLIJ TEŻ RADIEM", "ЗАГРОЗА ЖИТТЮ: 1) НАДАЙТЕ ПЕРШУ ДОПОМОГУ 2) ПРАЦЮЄ ТЕЛЕФОН? 112 3) БЕЗПЕЧНА ДОРОГА? ПОСИЛЬНИЙ. OK = НАДІСЛАТИ ТАКОЖ ПО РАДІО", "DANGER TO LIFE: 1) GIVE FIRST AID 2) PHONE WORKS? 112 3) SAFE ROUTE? RUNNER. OK = ALSO SEND BY RADIO"},
    {"OK = WYŚLIJ, WSTECZ = POPRAW", "OK = НАДІСЛАТИ, НАЗАД = ВИПРАВИТИ", "OK = SEND, BACK = EDIT"},
    {"KOLEJKA PEŁNA – ZGŁOSZENIE NIE ZAPISANE. UŻYJ FORMULARZA PAPIEROWEGO", "ЧЕРГА ПОВНА – ЗАЯВКУ НЕ ЗБЕРЕЖЕНО. ВИКОРИСТАЙТЕ ПАПЕРОВУ ФОРМУ", "QUEUE FULL – REQUEST NOT SAVED. USE THE PAPER FORM"},
    {"BŁĄD PAMIĘCI STACJI – ZGŁOSZENIE NIE ZAPISANE. FORMULARZ + GONIEC", "ПОМИЛКА ПАМ'ЯТІ СТАНЦІЇ – ЗАЯВКУ НЕ ЗБЕРЕЖЕНО. ФОРМА + ПОСИЛЬНИЙ", "STATION MEMORY ERROR – REQUEST NOT SAVED. FORM + RUNNER"},
    {"OGNIWA: OKOŁO [x] H PRACY", "БАТАРЕЇ: ПРИБЛИЗНО [x] ГОД РОБОТИ", "CELLS: ABOUT [x] H OF OPERATION"},
    {"WYMIEŃ OGNIWA W CIĄGU 1 H", "ЗАМІНІТЬ БАТАРЕЇ ПРОТЯГОМ 1 ГОД", "REPLACE CELLS WITHIN 1 H"},
    {"WYŁĄCZANIE – CZEKAJ, ZAPISUJĘ", "ВИМКНЕННЯ – ЗАЧЕКАЙТЕ, ЗБЕРІГАЮ", "SWITCHING OFF – WAIT, SAVING"},
    {"MOŻNA WYJĄĆ OGNIWA", "МОЖНА ВИЙНЯТИ БАТАРЕЇ", "CELLS CAN BE REMOVED"},
    {"12 V ODŁĄCZONE – ZA NISKIE NAPIĘCIE. PODŁĄCZ NAŁADOWANE ŹRÓDŁO I PRZYTRZYMAJ OK", "12 В ВІДКЛЮЧЕНО – ЗАНИЗЬКА НАПРУГА. ПІДКЛЮЧІТЬ ЗАРЯДЖЕНЕ ДЖЕРЕЛО І УТРИМУЙТЕ OK", "12 V DISCONNECTED – VOLTAGE TOO LOW. CONNECT A CHARGED SOURCE AND HOLD OK"},
    {"TRYB PRZYGOTOWANIA", "РЕЖИМ ПІДГОТОВКИ", "PREPARATION MODE"},
    {"PRZEŁĄCZYĆ NA ODBIORCĘ ZAPASOWEGO? TYLKO NA POLECENIE GOŃCA LUB SŁOWNE. NIEODWRACALNE", "ПЕРЕМКНУТИ НА РЕЗЕРВНОГО ОДЕРЖУВАЧА? ЛИШЕ ЗА УСНИМ НАКАЗОМ АБО ЧЕРЕЗ ПОСИЛЬНОГО. НЕЗВОРОТНО", "SWITCH TO BACKUP RECIPIENT? ONLY ON A SPOKEN ORDER OR BY RUNNER. IRREVERSIBLE"},
    {"KOMPUTER [czas] TEMU", "ПК [czas] ТОМУ", "COMPUTER [czas] AGO"},
    {"BRAK KOMPUTERA OSP", "НЕМАЄ ЗВ'ЯЗКУ З ПК", "NO OSP COMPUTER"},
    {"NIEODWRACALNE – STACJA PRZESTANIE DZIAŁAĆ; TYLKO PRZY GROŹBIE PRZEJĘCIA", "НЕЗВОРОТНО – СТАНЦІЯ ПЕРЕСТАНЕ ПРАЦЮВАТИ; ЛИШЕ ПРИ ЗАГРОЗІ ЗАХОПЛЕННЯ", "IRREVERSIBLE – STATION WILL STOP WORKING; ONLY IF CAPTURE THREATENS"},
    {"NAKAZ WYJŚCIA LUB EWAKUACJI? POTWIERDŹ W RADIU PUBLICZNYM LUB U GOŃCA", "НАКАЗ ВИЙТИ АБО ЕВАКУЮВАТИСЯ? ПІДТВЕРДІТЬ ПО СУСПІЛЬНОМУ РАДІО АБО В ПОСИЛЬНОГО", "ORDER TO LEAVE OR EVACUATE? CONFIRM ON PUBLIC RADIO OR WITH THE RUNNER"},
    {"ZAPISZ NUMER [xxxx] – PODAJ GO OPIEKUNOWI, ABY SPRAWDZIĆ STAN", "ЗАПИШІТЬ НОМЕР [xxxx] – НАЗВІТЬ ЙОГО КООРДИНАТОРУ, ЩОБ ПЕРЕВІРИТИ СТАН", "NOTE NUMBER [xxxx] – GIVE IT TO THE WARDEN TO CHECK THE STATUS"},
    {"", "ВІДПОВІДІ ВІД ОДЕРЖУВАЧА НАДХОДЯТЬ ПОЛЬСЬКОЮ", "REPLIES FROM THE RECIPIENT ARRIVE IN POLISH"},
};

// Pozycje menu, nazwy przycisków i etykiety (tabela PL/UK/EN).
enum class Label : uint8_t {
    ZGLOSZENIE,
    WIADOMOSCI,
    TEST,
    WSTRZYMAJ,
    WZNOW,
    STAN,
    USLUGI,
    OGLOS_ADRES,
    WYCISZ_DZWIEK,
    WLACZ_DZWIEK,
    PRZEKAZANIE_ZMIANY,
    ODBIORCA_ZAPASOWY,
    ZNISZCZ_DANE,
    ZMIEN_LICZBE_OSOB,
    ZMIEN_PILNOSC,
    POTRZEBA_USTALA,
    ANULUJ_WYSYLKE,
    INNA,
    COUNT
};

constexpr const char* const LABELS[static_cast<size_t>(Label::COUNT)][LANGS] = {
    {"ZGŁOSZENIE", "ЗАЯВКА", "REQUEST"},
    {"WIADOMOŚCI", "ПОВІДОМЛЕННЯ", "MESSAGES"},
    {"TEST", "ТЕСТ", "TEST"},
    {"WSTRZYMAJ", "ПРИЗУПИНИТИ", "PAUSE"},
    {"WZNÓW", "ВІДНОВИТИ", "RESUME"},
    {"STAN", "СТАН", "STATUS"},
    {"USŁUGI", "СЕРВІС", "SERVICES"},
    {"OGŁOŚ ADRES", "ОГОЛОСИТИ АДРЕСУ", "ANNOUNCE ADDRESS"},
    {"WYCISZ DŹWIĘK", "ВИМКНУТИ ЗВУК", "MUTE SOUND"},
    {"WŁĄCZ DŹWIĘK", "УВІМКНУТИ ЗВУК", "UNMUTE SOUND"},
    {"PRZEKAZANIE ZMIANY", "ПЕРЕДАЧА ЗМІНИ", "SHIFT HANDOVER"},
    {"ODBIORCA ZAPASOWY", "РЕЗЕРВНИЙ ОДЕРЖУВАЧ", "BACKUP RECIPIENT"},
    {"ZNISZCZ DANE", "ЗНИЩИТИ ДАНІ", "DESTROY DATA"},
    {"ZMIEŃ LICZBĘ OSÓB", "КІЛЬКІСТЬ ЛЮДЕЙ", "CHANGE PEOPLE COUNT"},
    {"ZMIEŃ PILNOŚĆ", "ЗМІНИТИ ТЕРМІНОВІСТЬ", "CHANGE URGENCY"},
    {"POTRZEBA USTAŁA", "ПОТРЕБА ЗНИКЛА", "NEED RESOLVED"},
    {"ANULUJ WYSYŁKĘ", "СКАСУВАТИ ВІДПРАВКУ", "CANCEL SENDING"},
    {"INNA", "ІНША", "OTHER"},
};

// Przyciski: GÓRA, DÓŁ, OK, WSTECZ.
constexpr const char* const BUTTONS[LANGS][4] = {
    {"GÓRA", "DÓŁ", "OK", "WSTECZ"},
    {"ВГОРУ", "ВНИЗ", "OK", "НАЗАД"},
    {"UP", "DOWN", "OK", "BACK"},
};

// Menu główne w kolejności ze specyfikacji; etykieta języka jest zawsze trójjęzyczna.
constexpr size_t MENU_ITEMS = 5;
enum class Menu : uint8_t { ZGLOSZENIE = 0, WIADOMOSCI = 1, TEST = 2, STAN = 3, JEZYK = 4 };
constexpr const char* const MENU[MENU_ITEMS][LANGS] = {
    {"ZGŁOSZENIE", "ЗАЯВКА", "REQUEST"},
    {"WIADOMOŚCI", "ПОВІДОМЛЕННЯ", "MESSAGES"},
    {"TEST", "ТЕСТ", "TEST"},
    {"STAN", "СТАН", "STATUS"},
    {"JĘZYK/МОВА/LANGUAGE", "JĘZYK/МОВА/LANGUAGE", "JĘZYK/МОВА/LANGUAGE"},
};

// Etykiety kategorii 0-9.
constexpr const char* const CATEGORIES[10][LANGS] = {
    {"POMOC MEDYCZNA", "МЕДИЧНА ДОПОМОГА", "MEDICAL HELP"},
    {"LEKI I SPRZĘT MED.", "ЛІКИ, МЕДОБЛАДНАННЯ", "MEDICINES, EQUIPMENT"},
    {"EWAKUACJA, TRANSPORT", "ЕВАКУАЦІЯ, ТРАНСПОРТ", "EVACUATION/TRANSPORT"},
    {"WODA PITNA", "ПИТНА ВОДА", "DRINKING WATER"},
    {"ŻYWNOŚĆ", "ХАРЧУВАННЯ", "FOOD"},
    {"OGRZEWANIE, ENERGIA", "ОПАЛЕННЯ, ЕНЕРГІЯ", "HEATING, POWER"},
    {"SANITARNE, HIGIENA", "САНІТАРІЯ, ГІГІЄНА", "SANITATION, HYGIENE"},
    {"ZAGROŻENIE BUDYNKU", "ЗАГРОЗА БУДІВЛІ", "BUILDING HAZARD"},
    {"POSZUKIWANIE, INFO", "ПОШУК ЛЮДЕЙ, ІНФО", "MISSING PEOPLE, INFO"},
    {"INNE", "ІНШЕ", "OTHER"},
};

// Gotowe frazy: do SA1 trafia wersja PL, ekran pokazuje tłumaczenie.
constexpr size_t PHRASES_COUNT = 11;
constexpr const char* const PHRASES[PHRASES_COUNT][LANGS] = {
    {"osoba na wózku", "людина на візку", "wheelchair user"},
    {"osoba leżąca – potrzebne nosze", "лежача людина – потрібні ноші", "bedridden person – stretcher needed"},
    {"dializy – termin dziś", "діаліз – сьогодні", "dialysis due today"},
    {"insulina na 1 dzień", "інсуліну на 1 день", "insulin left for 1 day"},
    {"niemowlę – mleko modyfikowane", "немовля – потрібна суміш", "infant – formula needed"},
    {"osoba niewidoma lub niesłysząca", "незряча або нечуюча людина", "blind or deaf person"},
    {"tlen na wyczerpaniu", "кисень закінчується", "oxygen running out"},
    {"dziecko bez opieki", "дитина без опіки", "unaccompanied child"},
    {"czujnik CO alarmuje", "датчик CO спрацював", "CO alarm sounding"},
    {"woda w budynku", "вода в будівлі", "water in the building"},
    {"potrzeba ustała", "потреба зникла", "need resolved"},
};

// Jednostki [czas] (minuty, godziny, doby) i separator dziesiętny napięcia.
constexpr const char* const UNITS[LANGS][3] = {
    {"MIN", "H", "D"},
    {"ХВ", "ГОД", "Д"},
    {"MIN", "H", "D"},
};
constexpr char DECIMAL[LANGS] = {',', ',', '.'};

inline const char* text(Id id, Lang lang) { return TEXTS[static_cast<size_t>(id)][static_cast<size_t>(lang)]; }
inline const char* label(Label id, Lang lang) { return LABELS[static_cast<size_t>(id)][static_cast<size_t>(lang)]; }

}  // namespace ui_texts

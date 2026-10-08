// SPDX-License-Identifier: MIT
// Obszar stosu Reticulum w FRAM (docs/spec/oprogramowanie.md, "Pojemności stosu"): rekord
// tożsamości stacji i mały system plików, na którym microReticulum trzyma pełne wpisy tablicy
// tras, znane tożsamości i buforowane ogłoszenia (magazyn Bitcask microStore przez adapter
// rns_framfs.h). W RAM zostaje tylko kopia tablicy przydziału bloków i skrót nazwy każdego pliku.
//
// Układ: nagłówek 64 B, 320 węzłów po 96 B (nazwa do 79 znaków, długość, pierwszy blok, CRC),
// tablica przydziału 2 B na blok i bloki danych po 128 B. Katalogi są tylko przedrostkami nazw.
// Zapis nie jest transakcyjny: po zaniku zasilania montowanie odrzuca węzły z błędnym CRC,
// obcina łańcuchy do długości z węzła i zwalnia bloki bez właściciela. W obszarze leży wyłącznie
// stan, który stos odtwarza z ogłoszeń (trasy, tożsamości, ogłoszenia); tożsamość stacji jest
// w osobnym rekordzie dwuslotowym z CRC. Bez zależności od Arduino; sprawdzany na komputerze.
#pragma once

#include <stddef.h>
#include <stdint.h>

#include "journal.h"

namespace framfs {

// Rekord tożsamości stacji (klucz prywatny X25519 + Ed25519, 64 B): dwa sloty po 128 B.
constexpr uint32_t IDENTITY_BASE = 0x044000;
constexpr size_t IDENTITY_SLOT = 128;
constexpr size_t KEY_BYTES = 64;

// System plików: 0x48000..0x7FFFF (224 KiB).
constexpr uint32_t FS_BASE = 0x048000;
constexpr uint32_t FS_SIZE = 0x038000;
constexpr size_t HEADER = 64;
constexpr size_t INODES = 320;
constexpr size_t INODE = 96;
constexpr size_t NAME_LEN = 79;
constexpr size_t BLOCK = 128;
constexpr uint16_t FREE = 0x0000;   // wpis tablicy przydziału: blok wolny
constexpr uint16_t END = 0xFFFF;    // ostatni blok łańcucha
constexpr size_t BLOCKS = (FS_SIZE - HEADER - INODES * INODE) / (BLOCK + 2);

struct Stats {
    size_t files = 0;
    size_t blocks = BLOCKS;
    size_t usedBlocks = 0;
    uint32_t mounts = 0;
    uint32_t formats = 0;      // formatowania (nowa pamięć, zły nagłówek, ZNISZCZ DANE)
    uint32_t dropped = 0;      // węzły odrzucone przy montowaniu (CRC, łańcuch)
    uint32_t reclaimed = 0;    // bloki bez właściciela zwolnione przy montowaniu
    uint32_t full = 0;         // zapisy przerwane z braku bloków albo węzłów
};

// Wczytuje klucz z nowszego poprawnego slotu; false, gdy żaden slot nie jest poprawny.
bool loadKey(journal::Storage& storage, uint8_t key[KEY_BYTES]);
// Zapisuje klucz do starszego slotu (numer + 1) i sprawdza odczytem.
bool saveKey(journal::Storage& storage, const uint8_t key[KEY_BYTES]);
// Kasuje oba sloty (ZNISZCZ DANE).
bool wipeKey(journal::Storage& storage);

class Fs {
public:
    explicit Fs(journal::Storage& storage) : storage_(storage) {}

    bool mount();    // czyta nagłówek i węzły; formatuje nową albo uszkodzoną pamięć
    // scrub: także bloki danych zerowane (ZNISZCZ DANE); bez niego tylko węzły i tablica przydziału.
    bool format(bool scrub = false);
    bool mounted() const { return mounted_; }

    // Węzły: numer 0..INODES-1 albo -1. Ścieżki "./a/b", "/a/b" i "a/b" są tą samą nazwą.
    int find(const char* path) const;
    int create(const char* path);   // nowy pusty plik; istniejący zostaje obcięty
    bool remove(const char* path);
    bool rename(const char* from, const char* to);   // istniejący cel jest zastępowany
    bool truncate(int inode);
    size_t size(int inode) const;
    bool name(int inode, char out[NAME_LEN + 1]) const;
    size_t read(int inode, uint32_t position, uint8_t* out, size_t count);
    // Zapis od position <= size; dalej plik rośnie. Zwraca liczbę zapisanych bajtów.
    size_t write(int inode, uint32_t position, const uint8_t* data, size_t count);

    // Katalog: istnieje, gdy ma choć jeden plik. Wywołuje visit(nazwa bez katalogu) dla plików
    // bezpośrednio w katalogu; zwraca ich liczbę.
    bool directoryExists(const char* path) const;
    size_t list(const char* path, void (*visit)(const char* name, void* context), void* context) const;
    bool removeDirectory(const char* path);   // usuwa wszystkie pliki z przedrostkiem

    size_t capacityBytes() const { return BLOCKS * BLOCK; }
    size_t freeBytes() const { return (BLOCKS - stats_.usedBlocks) * BLOCK; }
    const Stats& stats() const { return stats_; }

    static void normalize(const char* path, char out[NAME_LEN + 1]);   // bez "./" i "/" na początku
    static uint32_t hashName(const char* name);

private:
    struct Node {
        uint32_t size = 0;
        uint16_t first = END;
        char name[NAME_LEN + 1] = {};
    };
    uint32_t nodeAddress(int inode) const { return FS_BASE + HEADER + inode * INODE; }
    uint32_t fatAddress(uint16_t block) const { return FS_BASE + HEADER + INODES * INODE + block * 2u; }
    uint32_t blockAddress(uint16_t block) const {
        return FS_BASE + HEADER + INODES * INODE + BLOCKS * 2u + (uint32_t)block * BLOCK;
    }
    bool readNode(int inode, Node& node) const;
    bool writeNode(int inode, const Node& node);
    bool clearNode(int inode);
    bool setFat(uint16_t block, uint16_t next);
    uint16_t allocate();
    void freeChain(uint16_t first);
    uint16_t blockAt(int inode, uint32_t index) const;   // blok o numerze index w łańcuchu albo END
    int findNormalized(const char* name) const;

    journal::Storage& storage_;
    bool mounted_ = false;
    // Blok 0 nie jest używany jako dane (FREE = 0 w tablicy przydziału oznacza blok wolny),
    // więc łańcuch zaczyna się od bloku >= 1; fat_[0] trzyma znacznik zajętości bloku 0.
    uint16_t fat_[BLOCKS] = {};
    uint32_t hash_[INODES] = {};      // 0 = węzeł wolny
    uint32_t size_[INODES] = {};
    uint16_t first_[INODES] = {};
    uint16_t nextFree_ = 1;
    Stats stats_;
};

}  // namespace framfs

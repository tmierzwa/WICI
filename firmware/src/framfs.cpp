// SPDX-License-Identifier: MIT
#include "framfs.h"

#include <string.h>

#include "crc16.h"

namespace framfs {

namespace {

constexpr uint8_t HEADER_MAGIC[8] = {'W', 'I', 'C', 'I', 'F', 'S', '1', 0};
constexpr uint16_t NODE_MAGIC = 0x5746;   // "FW" w zapisie little-endian
constexpr uint32_t KEY_MAGIC = 0x5749444Bu;  // "KDIW"
// Węzeł: magic 2, size 4, first 2, name 80, crc 2 (pozostałe bajty zera).
constexpr size_t NODE_CRC = 2 + 4 + 2 + NAME_LEN + 1;

void put16(uint8_t* p, uint16_t v) { p[0] = v & 0xFF; p[1] = v >> 8; }
void put32(uint8_t* p, uint32_t v) { for (int i = 0; i < 4; ++i) p[i] = (v >> (8 * i)) & 0xFF; }
uint16_t get16(const uint8_t* p) { return p[0] | (p[1] << 8); }
uint32_t get32(const uint8_t* p) { return p[0] | (p[1] << 8) | (p[2] << 16) | ((uint32_t)p[3] << 24); }

void encodeHeader(uint8_t out[HEADER]) {
    memset(out, 0, HEADER);
    memcpy(out, HEADER_MAGIC, sizeof(HEADER_MAGIC));
    put32(out + 8, BLOCKS);
    put32(out + 12, INODES);
    put32(out + 16, BLOCK);
    put32(out + 20, INODE);
    put16(out + 24, p1::crc16(out, 24));
}

}  // namespace

// --- rekord tożsamości -------------------------------------------------------------------

// Slot: magic 4, numer 4, klucz 64, CRC-16 2.
bool loadKey(journal::Storage& storage, uint8_t key[KEY_BYTES]) {
    uint32_t bestSeq = 0;
    bool found = false;
    for (uint32_t slot = 0; slot < 2; ++slot) {
        uint8_t b[4 + 4 + KEY_BYTES + 2];
        if (!storage.read(IDENTITY_BASE + slot * IDENTITY_SLOT, b, sizeof(b))) continue;
        if (get32(b) != KEY_MAGIC || get16(b + 72) != p1::crc16(b, 72)) continue;
        const uint32_t seq = get32(b + 4);
        if (seq == 0 || seq == 0xFFFFFFFFu) continue;
        if (!found || seq > bestSeq) {
            found = true;
            bestSeq = seq;
            memcpy(key, b + 8, KEY_BYTES);
        }
    }
    return found;
}

bool saveKey(journal::Storage& storage, const uint8_t key[KEY_BYTES]) {
    uint32_t seqs[2] = {0, 0};
    for (uint32_t slot = 0; slot < 2; ++slot) {
        uint8_t b[4 + 4 + KEY_BYTES + 2];
        if (storage.read(IDENTITY_BASE + slot * IDENTITY_SLOT, b, sizeof(b)) && get32(b) == KEY_MAGIC &&
            get16(b + 72) == p1::crc16(b, 72) && get32(b + 4) != 0xFFFFFFFFu)
            seqs[slot] = get32(b + 4);
    }
    const uint32_t slot = seqs[0] <= seqs[1] ? 0 : 1;
    const uint32_t seq = (seqs[0] > seqs[1] ? seqs[0] : seqs[1]) + 1;
    uint8_t b[4 + 4 + KEY_BYTES + 2];
    put32(b, KEY_MAGIC);
    put32(b + 4, seq);
    memcpy(b + 8, key, KEY_BYTES);
    put16(b + 72, p1::crc16(b, 72));
    uint8_t check[sizeof(b)];
    return storage.write(IDENTITY_BASE + slot * IDENTITY_SLOT, b, sizeof(b)) &&
           storage.read(IDENTITY_BASE + slot * IDENTITY_SLOT, check, sizeof(check)) && !memcmp(b, check, sizeof(b));
}

// --- system plików -----------------------------------------------------------------------

void Fs::normalize(const char* path, char out[NAME_LEN + 1]) {
    while (path[0] == '.' && path[1] == '/') path += 2;
    while (path[0] == '/') path++;
    size_t n = 0;
    for (; *path && n < NAME_LEN; ++path) {
        if (*path == '/' && n > 0 && out[n - 1] == '/') continue;   // "a//b" -> "a/b"
        out[n++] = *path;
    }
    out[n] = 0;
}

uint32_t Fs::hashName(const char* name) {
    uint32_t h = 2166136261u;
    for (; *name; ++name) { h ^= (uint8_t)*name; h *= 16777619u; }
    return h ? h : 1;
}

bool Fs::readNode(int inode, Node& node) const {
    uint8_t b[INODE];
    if (!storage_.read(nodeAddress(inode), b, sizeof(b))) return false;
    if (get16(b) != NODE_MAGIC || get16(b + NODE_CRC) != p1::crc16(b, NODE_CRC)) return false;
    node.size = get32(b + 2);
    node.first = get16(b + 6);
    memcpy(node.name, b + 8, NAME_LEN + 1);
    node.name[NAME_LEN] = 0;
    return node.name[0] != 0;
}

bool Fs::writeNode(int inode, const Node& node) {
    uint8_t b[INODE] = {};
    put16(b, NODE_MAGIC);
    put32(b + 2, node.size);
    put16(b + 6, node.first);
    strncpy(reinterpret_cast<char*>(b + 8), node.name, NAME_LEN);
    put16(b + NODE_CRC, p1::crc16(b, NODE_CRC));
    if (!storage_.write(nodeAddress(inode), b, sizeof(b))) return false;
    hash_[inode] = hashName(node.name);
    size_[inode] = node.size;
    first_[inode] = node.first;
    return true;
}

bool Fs::clearNode(int inode) {
    uint8_t zero[2] = {0, 0};
    hash_[inode] = 0;
    size_[inode] = 0;
    first_[inode] = END;
    return storage_.write(nodeAddress(inode), zero, sizeof(zero));
}

bool Fs::setFat(uint16_t block, uint16_t next) {
    uint8_t b[2];
    put16(b, next);
    if (!storage_.write(fatAddress(block), b, sizeof(b))) return false;
    fat_[block] = next;
    return true;
}

bool Fs::format(bool scrub) {
    uint8_t header[HEADER];
    encodeHeader(header);
    uint8_t zero[BLOCK] = {};
    for (size_t i = 0; i < INODES; ++i)
        if (!storage_.write(nodeAddress(i), zero, INODE)) return false;
    if (scrub) {
        for (uint16_t b = 0; b < BLOCKS; ++b)
            if (!storage_.write(blockAddress(b), zero, BLOCK)) return false;
    }
    uint8_t zeros[64] = {};
    for (size_t at = 0; at < BLOCKS * 2u; at += sizeof(zeros)) {
        const size_t n = BLOCKS * 2u - at < sizeof(zeros) ? BLOCKS * 2u - at : sizeof(zeros);
        if (!storage_.write(fatAddress(0) + at, zeros, n)) return false;
    }
    if (!storage_.write(FS_BASE, header, sizeof(header))) return false;
    memset(fat_, 0, sizeof(fat_));
    memset(hash_, 0, sizeof(hash_));
    memset(size_, 0, sizeof(size_));
    for (size_t i = 0; i < INODES; ++i) first_[i] = END;
    fat_[0] = END;   // blok 0 nie jest używany (wpis FREE = 0)
    nextFree_ = 1;
    stats_.formats++;
    stats_.files = 0;
    stats_.usedBlocks = 1;
    mounted_ = true;
    return true;
}

bool Fs::mount() {
    mounted_ = false;
    stats_.mounts++;
    uint8_t header[HEADER], expected[HEADER];
    encodeHeader(expected);
    if (!storage_.read(FS_BASE, header, sizeof(header))) return false;
    if (memcmp(header, expected, 26) != 0) return format();

    for (size_t at = 0; at < BLOCKS; at += 64) {   // tablica przydziału do RAM
        uint8_t b[128];
        const size_t n = BLOCKS - at < 64 ? BLOCKS - at : 64;
        if (!storage_.read(fatAddress(at), b, n * 2)) return false;
        for (size_t i = 0; i < n; ++i) fat_[at + i] = get16(b + 2 * i);
    }
    uint8_t owned[(BLOCKS + 7) / 8] = {};
    owned[0] = 1;   // blok 0
    stats_.files = 0;
    for (size_t i = 0; i < INODES; ++i) {
        hash_[i] = 0;
        size_[i] = 0;
        first_[i] = END;
        Node node;
        if (!readNode(i, node)) {
            uint8_t magic[2];
            if (storage_.read(nodeAddress(i), magic, 2) && get16(magic) == NODE_MAGIC) { clearNode(i); stats_.dropped++; }
            continue;
        }
        // Duplikat nazwy (nie powinien powstać): zostaje pierwszy węzeł.
        if (findNormalized(node.name) >= 0) { clearNode(i); stats_.dropped++; continue; }
        const uint32_t need = (node.size + BLOCK - 1) / BLOCK;
        uint16_t block = node.first;
        bool ok = need == 0 ? true : (block != END);
        uint16_t last = END;
        uint32_t marked = 0;
        for (uint32_t k = 0; ok && k < need; ++k) {
            if (block == 0 || block >= BLOCKS || (owned[block / 8] & (1 << (block % 8))) || fat_[block] == FREE) { ok = false; break; }
            owned[block / 8] |= 1 << (block % 8);
            marked++;
            last = block;
            block = fat_[block];
        }
        if (!ok) {
            // Łańcuch krótszy niż długość albo sprzeczny: plik odrzucony; bloki oznaczone dla niego
            // wracają do puli niżej (blok należący do innego pliku zostaje przy tamtym).
            uint16_t b = node.first;
            for (uint32_t k = 0; k < marked; ++k) {
                owned[b / 8] &= ~(1 << (b % 8));
                b = fat_[b];
            }
            clearNode(i);
            stats_.dropped++;
            continue;
        }
        if (need == 0 && node.first != END) {   // pusty plik z blokiem po przerwanym zapisie
            node.first = END;
            writeNode(i, node);
        } else if (last != END && fat_[last] != END) {
            setFat(last, END);                   // obcięcie łańcucha do długości z węzła
        }
        hash_[i] = hashName(node.name);
        size_[i] = node.size;
        first_[i] = node.first;
        stats_.files++;
    }
    stats_.usedBlocks = 0;
    for (uint16_t b = 0; b < BLOCKS; ++b) {
        if (owned[b / 8] & (1 << (b % 8))) { stats_.usedBlocks++; continue; }
        if (fat_[b] != FREE) { setFat(b, FREE); stats_.reclaimed++; }
    }
    fat_[0] = END;
    nextFree_ = 1;
    mounted_ = true;
    return true;
}

int Fs::findNormalized(const char* name) const {
    const uint32_t h = hashName(name);
    for (size_t i = 0; i < INODES; ++i) {
        if (hash_[i] != h) continue;
        Node node;
        if (readNode(i, node) && !strcmp(node.name, name)) return (int)i;
    }
    return -1;
}

int Fs::find(const char* path) const {
    if (!mounted_) return -1;
    char name[NAME_LEN + 1];
    normalize(path, name);
    if (!name[0]) return -1;
    return findNormalized(name);
}

int Fs::create(const char* path) {
    if (!mounted_) return -1;
    char name[NAME_LEN + 1];
    normalize(path, name);
    if (!name[0] || name[strlen(name) - 1] == '/') return -1;
    int inode = findNormalized(name);
    if (inode >= 0) return truncate(inode) ? inode : -1;
    for (size_t i = 0; i < INODES; ++i) {
        if (hash_[i]) continue;
        Node node;
        strncpy(node.name, name, NAME_LEN);
        if (!writeNode(i, node)) return -1;
        stats_.files++;
        return (int)i;
    }
    stats_.full++;
    return -1;
}

void Fs::freeChain(uint16_t first) {
    uint16_t b = first;
    for (size_t k = 0; b != END && b != FREE && b < BLOCKS && k < BLOCKS; ++k) {
        const uint16_t next = fat_[b];
        setFat(b, FREE);
        if (stats_.usedBlocks) stats_.usedBlocks--;
        if (b < nextFree_) nextFree_ = b;
        b = next;
    }
}

bool Fs::truncate(int inode) {
    if (inode < 0 || inode >= (int)INODES || !hash_[inode]) return false;
    Node node;
    if (!readNode(inode, node)) return false;
    const uint16_t first = node.first;
    node.first = END;
    node.size = 0;
    if (!writeNode(inode, node)) return false;   // najpierw węzeł: po zaniku bloki są tylko sierotami
    freeChain(first);
    return true;
}

bool Fs::remove(const char* path) {
    const int inode = find(path);
    if (inode < 0) return false;
    const uint16_t first = first_[inode];
    if (!clearNode(inode)) return false;
    freeChain(first);
    if (stats_.files) stats_.files--;
    return true;
}

bool Fs::rename(const char* from, const char* to) {
    const int inode = find(from);
    if (inode < 0) return false;
    char name[NAME_LEN + 1];
    normalize(to, name);
    if (!name[0]) return false;
    const int existing = findNormalized(name);
    if (existing == inode) return true;
    if (existing >= 0) {
        const uint16_t first = first_[existing];
        clearNode(existing);
        freeChain(first);
        if (stats_.files) stats_.files--;
    }
    Node node;
    if (!readNode(inode, node)) return false;
    memset(node.name, 0, sizeof(node.name));
    strncpy(node.name, name, NAME_LEN);
    return writeNode(inode, node);
}

size_t Fs::size(int inode) const {
    return inode >= 0 && inode < (int)INODES && hash_[inode] ? size_[inode] : 0;
}

bool Fs::name(int inode, char out[NAME_LEN + 1]) const {
    Node node;
    if (inode < 0 || inode >= (int)INODES || !hash_[inode] || !readNode(inode, node)) return false;
    memcpy(out, node.name, NAME_LEN + 1);
    return true;
}

uint16_t Fs::blockAt(int inode, uint32_t index) const {
    uint16_t b = first_[inode];
    for (uint32_t k = 0; k < index && b != END; ++k) b = b != FREE && b < BLOCKS ? fat_[b] : END;
    return b != FREE && b < BLOCKS ? b : END;
}

uint16_t Fs::allocate() {
    for (size_t k = 0; k < BLOCKS; ++k) {
        const uint16_t b = (uint16_t)(1 + (nextFree_ - 1 + k) % (BLOCKS - 1));
        if (fat_[b] == FREE) {
            if (!setFat(b, END)) return END;
            nextFree_ = static_cast<size_t>(b) + 1 < BLOCKS ? b + 1 : 1;
            stats_.usedBlocks++;
            return b;
        }
    }
    stats_.full++;
    return END;
}

size_t Fs::read(int inode, uint32_t position, uint8_t* out, size_t count) {
    if (inode < 0 || inode >= (int)INODES || !hash_[inode]) return 0;
    const uint32_t size = size_[inode];
    if (position >= size) return 0;
    if (count > size - position) count = size - position;
    uint16_t b = blockAt(inode, position / BLOCK);
    size_t done = 0;
    while (done < count && b != END && b != FREE && b < BLOCKS) {
        const uint32_t offset = (position + done) % BLOCK;
        size_t n = BLOCK - offset;
        if (n > count - done) n = count - done;
        if (!storage_.read(blockAddress(b) + offset, out + done, n)) break;
        done += n;
        b = fat_[b];
    }
    return done;
}

size_t Fs::write(int inode, uint32_t position, const uint8_t* data, size_t count) {
    if (inode < 0 || inode >= (int)INODES || !hash_[inode] || position > size_[inode]) return 0;
    // Łańcuch: pierwszy blok zapisu i poprzedni (do dołączania nowych bloków).
    const uint32_t startIndex = position / BLOCK;
    uint16_t prev = END;
    uint16_t b = first_[inode];
    for (uint32_t k = 0; k < startIndex; ++k) {
        if (b == END || b == FREE || b >= BLOCKS) return 0;   // łańcuch krótszy niż długość z węzła
        prev = b;
        b = fat_[b];
    }
    size_t done = 0;
    bool firstChanged = false;
    uint16_t newFirst = first_[inode];
    while (done < count) {
        if (b == END) {
            b = allocate();
            if (b == END) break;
            if (prev == END) { newFirst = b; firstChanged = true; }
            else if (!setFat(prev, b)) break;
        } else if (b == FREE || b >= BLOCKS) {
            break;
        }
        const uint32_t offset = (position + done) % BLOCK;
        size_t n = BLOCK - offset;
        if (n > count - done) n = count - done;
        if (!storage_.write(blockAddress(b) + offset, data + done, n)) break;
        done += n;
        prev = b;
        b = fat_[b];
        if (firstChanged && prev == newFirst) {
            // Pierwszy blok pustego pliku: węzeł dostaje go od razu, żeby łańcuch miał właściciela.
            Node node;
            if (!readNode(inode, node)) break;
            node.first = newFirst;
            if (!writeNode(inode, node)) break;
            firstChanged = false;
        }
    }
    if (position + done > size_[inode]) {
        Node node;
        if (readNode(inode, node)) {
            node.size = position + done;
            node.first = first_[inode];
            writeNode(inode, node);
        }
    }
    return done;
}

bool Fs::directoryExists(const char* path) const {
    if (!mounted_) return false;
    char dir[NAME_LEN + 1];
    normalize(path, dir);
    size_t n = strlen(dir);
    if (n == 0) return true;
    if (dir[n - 1] != '/' && n < NAME_LEN) { dir[n++] = '/'; dir[n] = 0; }
    for (size_t i = 0; i < INODES; ++i) {
        if (!hash_[i]) continue;
        Node node;
        if (readNode(i, node) && !strncmp(node.name, dir, n)) return true;
    }
    return false;
}

size_t Fs::list(const char* path, void (*visit)(const char*, void*), void* context) const {
    if (!mounted_) return 0;
    char dir[NAME_LEN + 1];
    normalize(path, dir);
    size_t n = strlen(dir);
    if (n && dir[n - 1] != '/' && n < NAME_LEN) { dir[n++] = '/'; dir[n] = 0; }
    size_t count = 0;
    for (size_t i = 0; i < INODES; ++i) {
        if (!hash_[i]) continue;
        Node node;
        if (!readNode(i, node) || strncmp(node.name, dir, n)) continue;
        const char* base = node.name + n;
        if (!*base || strchr(base, '/')) continue;
        if (visit) visit(base, context);
        count++;
    }
    return count;
}

bool Fs::removeDirectory(const char* path) {
    if (!mounted_) return false;
    char dir[NAME_LEN + 1];
    normalize(path, dir);
    size_t n = strlen(dir);
    if (n && dir[n - 1] != '/' && n < NAME_LEN) { dir[n++] = '/'; dir[n] = 0; }
    for (size_t i = 0; i < INODES; ++i) {
        if (!hash_[i]) continue;
        Node node;
        if (!readNode(i, node) || strncmp(node.name, dir, n)) continue;
        const uint16_t first = first_[i];
        clearNode(i);
        freeChain(first);
        if (stats_.files) stats_.files--;
    }
    return true;
}

}  // namespace framfs

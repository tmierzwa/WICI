// SPDX-License-Identifier: MIT
// Węzeł stacji na komputerze (środowisko "host" w platformio.ini): ten sam kod stosu co obraz
// bench-a (rns_node, p1iface, framfs, port microReticulum z łatami) z emulatorem łącza P1 zamiast
// CC1120. Datagram z kolejki interfejsu jest dzielony na ramki P1 (p1frame), "nadawany" przez czas
// z modelu ramki, po nim obowiązuje dług ciszy debt x czas TX; ramki składa po drugiej stronie
// składacz P1, a złożony datagram (bajty z IFAC) idzie datagramem UDP do interfejsu UDP Reticulum
// w Pythonie. W drugą stronę tak samo. FRAM 512 KiB jest plikiem, więc restart programu odtwarza
// tożsamość i tablice jak restart stacji. Próba zgodności: firmware/tools/rns_interop.py.
// --osp-node: konfiguracja węzła OSP (D19) z interfejsem Reticulum przez USB; zamiast portu CDC
// pseudoterminal, którego nazwę podaje zdarzenie "ready" ("usb"), a KISSInterface Reticulum
// w Pythonie otwiera go jak port szeregowy (firmware/tools/rns_osp_node.py).
//
// Polecenia na stdin (wiersze): announce [hex danych], send <cel hex> <dane hex> [limit s],
// path <cel hex>, request <cel hex>, accept <0|1> (warstwa aplikacji przyjmuje pakiety i stos
// wysyła dowód; domyślnie 1), status, hashes <n> (n losowych skrótów na liście skrótów pakietów,
// pomiar RAM), pinned <cel hex> (cel chroniony jako ogłoszony przez komputer), quit. Zdarzenia na
// stdout jako wiersze JSON.
#include <arpa/inet.h>
#include <fcntl.h>
#include <netinet/in.h>
#include <poll.h>
#include <sys/socket.h>
#include <termios.h>
#include <unistd.h>

#include <cerrno>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <random>
#include <string>
#include <vector>

#include "../journal.h"
#include "../p1frame.h"
#include "../p1iface.h"
#include "../rns_node.h"

namespace {

uint32_t nowMs() {
    using namespace std::chrono;
    return static_cast<uint32_t>(duration_cast<milliseconds>(steady_clock::now().time_since_epoch()).count());
}

// FRAM 512 KiB w pliku (nowy plik: same 0xFF jak nowy układ). Tablica statyczna, nie z puli stosu:
// operator new programu idzie do puli TLSF microReticulum, której zajętość jest mierzona.
constexpr size_t FRAM_BYTES = 512 * 1024;
uint8_t framBytes[FRAM_BYTES];

struct FileFram : journal::Storage {
    std::string path;
    bool dirty = false;
    explicit FileFram(const std::string& p) : path(p) {
        memset(framBytes, 0xFF, sizeof(framBytes));
        if (FILE* f = fopen(path.c_str(), "rb")) {
            const size_t n = fread(framBytes, 1, sizeof(framBytes), f);
            (void)n;
            fclose(f);
        }
    }
    bool read(uint32_t address, uint8_t* data, size_t count) override {
        if (address + count > FRAM_BYTES) return false;
        memcpy(data, framBytes + address, count);
        return true;
    }
    bool write(uint32_t address, const uint8_t* data, size_t count) override {
        if (address + count > FRAM_BYTES) return false;
        memcpy(framBytes + address, data, count);
        dirty = true;
        return true;
    }
    void save() {
        if (!dirty) return;
        if (FILE* f = fopen(path.c_str(), "wb")) {
            fwrite(framBytes, 1, sizeof(framBytes), f);
            fclose(f);
        }
        dirty = false;
    }
};

std::string hex(const uint8_t* data, size_t n) {
    static const char* d = "0123456789abcdef";
    std::string s;
    for (size_t i = 0; i < n; ++i) { s += d[data[i] >> 4]; s += d[data[i] & 15]; }
    return s;
}

bool unhex(const char* text, std::vector<uint8_t>& out) {
    out.clear();
    const size_t n = strlen(text);
    if (n % 2) return false;
    for (size_t i = 0; i < n; i += 2) {
        unsigned v;
        if (sscanf(text + i, "%2x", &v) != 1) return false;
        out.push_back(static_cast<uint8_t>(v));
    }
    return true;
}

// Emulowane łącze P1: ramki przez p1frame, czas nadawania z modelu, dług ciszy.
struct EmulatedP1 : rnsnode::Radio {
    int sock = -1;
    sockaddr_in peer{};
    uint32_t debtFactor = p1iface::DEBT_FACTOR;
    bool busy = false;
    uint32_t txEndMs = 0;
    uint32_t debtUntilMs = nowMs();   // zegar komputera nie zaczyna się od 0 jak millis()
    p1frame::Assembler air;         // składanie po stronie odbiorcy (Python za mostem UDP)
    p1frame::Assembler local;       // składanie ramek przychodzących do stacji
    std::mt19937 rng{12345};
    uint32_t datagramsOut = 0, datagramsIn = 0, framesOut = 0, framesIn = 0;
    bool trace = false;

    bool ready() override {
        return !busy && static_cast<int32_t>(nowMs() - debtUntilMs) >= 0;
    }
    uint32_t debtMs() override {
        const int32_t left = static_cast<int32_t>(debtUntilMs - nowMs());
        return left > 0 ? left : 0;
    }
    bool transmit(const uint8_t* data, size_t length) override {
        uint8_t id[p1frame::ID_BYTES];
        for (auto& b : id) b = static_cast<uint8_t>(rng());
        const uint8_t count = p1frame::fragmentCount(length);
        if (!count) return false;
        const uint32_t now = nowMs();
        for (uint8_t i = 0; i < count; ++i) {
            uint8_t frame[p1frame::MAX_FRAME];
            const size_t n = p1frame::buildFrame(data, length, id, i, frame);
            p1frame::Fragment f;
            if (p1frame::parseFrame(frame, n, f) != p1frame::Parse::OK) return false;
            ++framesOut;
            if (air.push(f, now) == p1frame::Outcome::COMPLETE) {
                sendto(sock, air.completed(), air.completedLength(), 0, reinterpret_cast<sockaddr*>(&peer), sizeof(peer));
                ++datagramsOut;
            }
        }
        const uint32_t tx = p1iface::airtimeMs(length);
        if (trace) {
            printf("{\"event\":\"tx\",\"length\":%u,\"air_ms\":%u,\"head\":\"%s\"}\n", (unsigned)length, tx, hex(data, length < 24 ? length : 24).c_str());
            fflush(stdout);
        }
        busy = true;
        txEndMs = now + tx;
        debtUntilMs = now + tx + tx * debtFactor;
        return true;
    }
    // Datagram z Pythona: ramki P1 i składanie jak przy odbiorze radiowym.
    void fromPeer(const uint8_t* data, size_t length) {
        if (trace) {
            printf("{\"event\":\"rx\",\"length\":%u,\"head\":\"%s\"}\n", (unsigned)length, hex(data, length < 24 ? length : 24).c_str());
            fflush(stdout);
        }
        uint8_t id[p1frame::ID_BYTES];
        for (auto& b : id) b = static_cast<uint8_t>(rng());
        const uint8_t count = p1frame::fragmentCount(length);
        for (uint8_t i = 0; i < count; ++i) {
            uint8_t frame[p1frame::MAX_FRAME];
            const size_t n = p1frame::buildFrame(data, length, id, i, frame);
            p1frame::Fragment f;
            if (p1frame::parseFrame(frame, n, f) != p1frame::Parse::OK) continue;
            ++framesIn;
            if (local.push(f, nowMs()) == p1frame::Outcome::COMPLETE) {
                ++datagramsIn;
                rnsnode::received(local.completed(), local.completedLength());
            }
        }
    }
    void poll() {
        if (busy && static_cast<int32_t>(nowMs() - txEndMs) >= 0) {
            busy = false;
            rnsnode::txDone(true);
        }
    }
};

EmulatedP1 radio;

bool acceptPackets = true;

bool onPacket(const uint8_t* data, size_t length, void*) {
    printf("{\"event\":\"packet\",\"data\":\"%s\",\"accepted\":%s}\n", hex(data, length).c_str(), acceptPackets ? "true" : "false");
    fflush(stdout);
    return acceptPackets;
}

void onReceipt(uint32_t handle, bool delivered, void*) {
    printf("{\"event\":\"receipt\",\"handle\":%u,\"delivered\":%s}\n", handle, delivered ? "true" : "false");
    fflush(stdout);
}

void onAnnounce(const uint8_t dest[16], const uint8_t* appData, size_t length, void*) {
    printf("{\"event\":\"announce\",\"dest\":\"%s\",\"app_data\":\"%s\"}\n", hex(dest, 16).c_str(), hex(appData, length).c_str());
    fflush(stdout);
}

void onLog(const char* text, void*) {
    fprintf(stderr, "%s\n", text);
}

void printStatus() {
    const rnsnode::Status s = rnsnode::status();
    char iface[512], usb[400];
    rnsnode::interfaceJson(iface, sizeof(iface));
    rnsnode::usbJson(usb, sizeof(usb));
    printf("{\"event\":\"status\",\"online\":%s,\"paths\":%u,\"hashes\":%u,\"announce_table\":%u,\"pending\":%u,"
           "\"pool\":%u,\"pool_used\":%u,\"pool_peak\":%u,\"fs_files\":%u,\"fs_used\":%u,\"fs_capacity\":%u,"
           "\"sent\":%u,\"received\":%u,\"unproven\":%u,\"delivered\":%u,\"timed_out\":%u,\"announces\":%u,\"wait_ms\":%u,"
           "\"bitrate\":%u,\"frames_out\":%u,\"frames_in\":%u,\"datagrams_out\":%u,\"datagrams_in\":%u,%s,%s}\n",
           s.online ? "true" : "false", (unsigned)s.paths, (unsigned)s.packetHashes, (unsigned)s.announceTable,
           (unsigned)s.receiptsPending, (unsigned)s.poolSize, (unsigned)s.poolUsed, (unsigned)s.poolPeak,
           (unsigned)s.fsFiles, (unsigned)s.fsUsedBytes, (unsigned)s.fsCapacityBytes, s.packetsSent, s.packetsReceived,
           s.packetsUnproven, s.delivered, s.timedOut, s.announcesSeen, s.queueWaitMs, s.bitrate, radio.framesOut, radio.framesIn,
           radio.datagramsOut, radio.datagramsIn, iface, usb);
    fflush(stdout);
}

}  // namespace

int main(int argc, char** argv) {
    std::string framPath = "fram.bin";
    FILE* capture = nullptr;   // --capture: datagramy od drugiej strony (szesnastkowo) do odtworzenia w pomiarze RAM
    int listenPort = 4242, peerPort = 4243;
    uint8_t ifac[16] = {};
    uint16_t tableMax = 0;   // --table-max: mniejsze tablice do próby ochrony wpisów OSP
    uint8_t osp[2][16] = {};
    bool ospNode = false;   // --osp-node: interfejs USB przez pseudoterminal
    for (int i = 1; i < argc; ++i) {
        if (!strcmp(argv[i], "--fram") && i + 1 < argc) framPath = argv[++i];
        else if (!strcmp(argv[i], "--listen") && i + 1 < argc) listenPort = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--peer") && i + 1 < argc) peerPort = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--trace")) radio.trace = true;
        else if (!strcmp(argv[i], "--osp-node")) ospNode = true;
        else if (!strcmp(argv[i], "--capture") && i + 1 < argc) capture = fopen(argv[++i], "w");
        else if (!strcmp(argv[i], "--debt") && i + 1 < argc) radio.debtFactor = static_cast<uint32_t>(atoi(argv[++i]));
        else if (!strcmp(argv[i], "--table-max") && i + 1 < argc) tableMax = static_cast<uint16_t>(atoi(argv[++i]));
        else if (!strcmp(argv[i], "--osp") && i + 1 < argc) {   // cel OSP przypięty przed startem stosu
            std::vector<uint8_t> k;
            if (!unhex(argv[++i], k) || k.size() != 16) { fprintf(stderr, "--osp: 32 hex digits\n"); return 2; }
            memcpy(osp[0], k.data(), 16);
        }
        else if (!strcmp(argv[i], "--ifac") && i + 1 < argc) {
            std::vector<uint8_t> k;
            if (!unhex(argv[++i], k) || k.size() != 16) { fprintf(stderr, "--ifac: 32 hex digits\n"); return 2; }
            memcpy(ifac, k.data(), 16);
        }
    }
    FileFram fram(framPath);
    radio.sock = socket(AF_INET, SOCK_DGRAM, 0);
    sockaddr_in local{};
    local.sin_family = AF_INET;
    local.sin_port = htons(listenPort);
    local.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    if (bind(radio.sock, reinterpret_cast<sockaddr*>(&local), sizeof(local)) != 0) { perror("bind"); return 2; }
    radio.peer.sin_family = AF_INET;
    radio.peer.sin_port = htons(peerPort);
    radio.peer.sin_addr.s_addr = htonl(INADDR_LOOPBACK);

    rnsnode::Hooks hooks;
    hooks.packet = onPacket;
    hooks.receipt = onReceipt;
    hooks.announce = onAnnounce;
    hooks.log = onLog;
    rnsnode::setOsp(osp, 0);
    rnsnode::setOspNode(ospNode);
    // Port USB węzła OSP: strona główna pseudoterminalu w trybie surowym; port uznaje się za
    // otwarty od startu (komputer włącza kontrolę przepływu po otwarciu strony podrzędnej).
    int usb = -1;
    std::string usbName;
    if (ospNode) {
        usb = posix_openpt(O_RDWR | O_NOCTTY);
        if (usb < 0 || grantpt(usb) != 0 || unlockpt(usb) != 0) { perror("pty"); return 2; }
        usbName = ptsname(usb);
        termios t{};
        if (tcgetattr(usb, &t) == 0) { cfmakeraw(&t); tcsetattr(usb, TCSANOW, &t); }
        fcntl(usb, F_SETFL, fcntl(usb, F_GETFL) | O_NONBLOCK);
    }
    if (!rnsnode::begin(fram, radio, ifac, 0, hooks)) { printf("{\"event\":\"error\",\"what\":\"begin\"}\n"); return 1; }
    if (ospNode) rnsnode::usbOpen(true);
    if (tableMax) rnsnode::debugTableMax(tableMax);
    fram.save();
    const rnsnode::Status st = rnsnode::status();
    printf("{\"event\":\"ready\",\"address\":\"%s\",\"identity\":\"%s\",\"identity_new\":%s,\"paths\":%u,\"bitrate\":%u,"
           "\"osp_node\":%s,\"usb\":\"%s\"}\n",
           hex(rnsnode::address(), 16).c_str(), hex(rnsnode::identityHash(), 16).c_str(), st.identityNew ? "true" : "false",
           (unsigned)st.paths, st.bitrate, rnsnode::ospNode() ? "true" : "false", usbName.c_str());
    fflush(stdout);

    std::string line;
    bool run = true;
    uint32_t lastSave = nowMs();
    while (run) {
        pollfd fds[3] = {{0, POLLIN, 0}, {radio.sock, POLLIN, 0}, {usb, POLLIN, 0}};
        ::poll(fds, usb >= 0 ? 3 : 2, 5);
        if (usb >= 0) {
            uint8_t buffer[512];
            ssize_t n;
            while ((n = ::read(usb, buffer, sizeof(buffer))) > 0) rnsnode::usbFeed(buffer, static_cast<size_t>(n), nowMs());
            size_t m;
            while ((m = rnsnode::usbTake(buffer, sizeof(buffer))) > 0) {
                size_t done = 0;
                while (done < m) {
                    const ssize_t w = ::write(usb, buffer + done, m - done);
                    if (w > 0) done += static_cast<size_t>(w);
                    else if (w < 0 && errno != EAGAIN) break;   // strona podrzędna zamknięta: bajty przepadają
                    else { struct pollfd o = {usb, POLLOUT, 0}; ::poll(&o, 1, 10); }
                }
            }
        }
        if (fds[1].revents & POLLIN) {
            uint8_t buffer[2048];
            const ssize_t n = recv(radio.sock, buffer, sizeof(buffer), 0);
            if (n > 0) {
                if (capture) { fprintf(capture, "%s\n", hex(buffer, static_cast<size_t>(n)).c_str()); fflush(capture); }
                radio.fromPeer(buffer, static_cast<size_t>(n));
            }
        }
        if (fds[0].revents & (POLLIN | POLLHUP)) {
            char chunk[4096];
            const ssize_t n = ::read(0, chunk, sizeof(chunk));
            if (n <= 0) run = false;
            else line.append(chunk, static_cast<size_t>(n));
            size_t at;
            while ((at = line.find('\n')) != std::string::npos) {
                const std::string cmd = line.substr(0, at);
                line.erase(0, at + 1);
                char a[1200] = {}, b[1200] = {};
                unsigned u = 0;
                std::vector<uint8_t> x, y;
                if (cmd == "quit") run = false;
                else if (cmd == "status") printStatus();
                else if (sscanf(cmd.c_str(), "announce %1199s", a) == 1 && unhex(a, x)) {
                    printf("{\"event\":\"announced\",\"ok\":%s}\n", rnsnode::announce(x.data(), x.size()) ? "true" : "false");
                } else if (cmd == "announce") {
                    printf("{\"event\":\"announced\",\"ok\":%s}\n", rnsnode::announce(nullptr, 0) ? "true" : "false");
                } else if (sscanf(cmd.c_str(), "send %1199s %1199s %u", a, b, &u) >= 2 && unhex(a, x) && x.size() == 16 && unhex(b, y)) {
                    const uint32_t handle = rnsnode::send(x.data(), y.data(), y.size(), u ? u : rnsnode::RECEIPT_MIN_S);
                    printf("{\"event\":\"sent\",\"handle\":%u}\n", handle);
                } else if (sscanf(cmd.c_str(), "path %1199s", a) == 1 && unhex(a, x) && x.size() == 16) {
                    printf("{\"event\":\"path\",\"known\":%s,\"path\":%s}\n", rnsnode::knows(x.data()) ? "true" : "false",
                           rnsnode::hasPath(x.data()) ? "true" : "false");
                } else if (sscanf(cmd.c_str(), "osp %1199s", a) == 1 && unhex(a, x) && x.size() == 16) {
                    uint8_t osp[2][16] = {};
                    memcpy(osp[0], x.data(), 16);
                    rnsnode::setOsp(osp, 0);
                    printf("{\"event\":\"osp\"}\n");
                } else if (sscanf(cmd.c_str(), "pinned %1199s", a) == 1 && unhex(a, x) && x.size() == 16) {
                    printf("{\"event\":\"pinned\",\"pinned\":%s}\n", rnsnode::usbPinned(x.data()) ? "true" : "false");
                } else if (sscanf(cmd.c_str(), "request %1199s", a) == 1 && unhex(a, x) && x.size() == 16) {
                    rnsnode::requestPath(x.data());
                    printf("{\"event\":\"requested\"}\n");
                } else if (sscanf(cmd.c_str(), "accept %u", &u) == 1) {
                    acceptPackets = u != 0;
                    printf("{\"event\":\"accept\",\"on\":%s}\n", acceptPackets ? "true" : "false");
                } else if (sscanf(cmd.c_str(), "hashes %u", &u) == 1) {
                    printf("{\"event\":\"hashes\",\"added\":%u}\n", rnsnode::debugFillHashes(u));
                } else {
                    printf("{\"event\":\"error\",\"what\":\"command\"}\n");
                }
                fflush(stdout);
            }
        }
        radio.poll();
        rnsnode::loop(nowMs());
        if (nowMs() - lastSave > 1000) { fram.save(); lastSave = nowMs(); }
    }
    rnsnode::persist();
    fram.save();
    if (capture) fclose(capture);
    return 0;
}

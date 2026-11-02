// SPDX-License-Identifier: MIT
// Provisioning key checks for the Python comparison in tests/test_envelope_cross_language.py.
//   envelope_keys_check --small < hex lines   prints 1 (small order) or 0 per 32-byte key
//   envelope_keys_check <document> <profile>  prints the configure refusal detail or "ok"
#include <stdio.h>
#include <string.h>

#include "config.h"
#include "hexstr.h"

namespace {

struct File : config::Source {
    FILE* file;
    explicit File(FILE* f) : file(f) {}
    bool read(uint32_t offset, char* out, size_t length) override {
        return !fseek(file, static_cast<long>(offset), SEEK_SET) && fread(out, 1, length, file) == length;
    }
};

}  // namespace

int main(int argc, char** argv) {
    if (argc == 2 && !strcmp(argv[1], "--small")) {
        char line[80];
        while (fgets(line, sizeof(line), stdin)) {
            line[strcspn(line, "\n")] = '\0';
            uint8_t key[32];
            if (!hexstr::decode(line, key, sizeof(key))) return 2;
            printf("%d\n", config::smallOrder(key) ? 1 : 0);
        }
        return 0;
    }
    if (argc != 3) return 2;
    FILE* file = fopen(argv[1], "rb");
    if (!file || fseek(file, 0, SEEK_END)) return 2;
    const long size = ftell(file);
    File source(file);
    static config::Config parsed;
    size_t worst = 0;
    const char* detail = config::parse(source, static_cast<uint32_t>(size), argv[2], parsed, worst);
    fclose(file);
    puts(detail ? detail : "ok");
    return 0;
}

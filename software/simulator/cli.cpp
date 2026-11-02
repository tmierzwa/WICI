// SPDX-License-Identifier: MIT
// Jedno urządzenie symulatora jako proces (szybkie próby bez przeglądarki): wiersze ze stdin to
// polecenia sim_command (hal/vboard.cpp) albo `run <µs>` (praca do chwili czasu bezwzględnego).
// Pamięć nieulotna między procesami (restart, zanik zasilania): `fram save|load <plik>` i
// `noinit save|load <plik>` (segment wici_noinit, przenoszony tylko przy restarcie programowym).
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

extern "C" const char* sim_command_line(const char* line);
extern "C" int sim_run(double until);
extern "C" unsigned sim_reboot_reason();
extern "C" uint8_t* sim_fram();
extern "C" uint32_t sim_fram_size();
extern "C" uint8_t* sim_noinit();
extern "C" uint32_t sim_noinit_size();

// Zapis albo odczyt całego obszaru; plik krótszy przy odczycie jest błędem.
static const char* image(const char* op, const char* path, uint8_t* data, uint32_t size) {
    const bool save = !strcmp(op, "save");
    if (!save && strcmp(op, "load")) return "err save|load";
    FILE* f = fopen(path, save ? "wb" : "rb");
    if (!f) return "err file";
    const size_t done = save ? fwrite(data, 1, size, f) : fread(data, 1, size, f);
    const bool closed = fclose(f) == 0;
    return done == size && closed ? "ok" : "err size";
}

int main() {
    static char line[20000];
    char op[8], path[4096];
    while (fgets(line, sizeof(line), stdin)) {
        char* nl = strchr(line, '\n');
        if (nl) *nl = '\0';
        if (!line[0] || line[0] == '#') continue;
        if (!strncmp(line, "run ", 4)) {
            const int r = sim_run(atof(line + 4));
            if (r) printf("reboot %u\n.\n", sim_reboot_reason());
            else printf("ok\n.\n");
        } else if (sscanf(line, "fram %7s %4095s", op, path) == 2) {
            printf("%s\n.\n", image(op, path, sim_fram(), sim_fram_size()));
        } else if (sscanf(line, "noinit %7s %4095s", op, path) == 2) {
            printf("%s\n.\n", image(op, path, sim_noinit(), sim_noinit_size()));
        } else {
            printf("%s\n.\n", sim_command_line(line));
        }
        fflush(stdout);
    }
    return 0;
}

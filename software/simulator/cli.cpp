// SPDX-License-Identifier: MIT
// Jedno urządzenie symulatora jako proces (szybkie próby bez przeglądarki): wiersze ze stdin to
// polecenia sim_command (hal/vboard.cpp) albo `run <µs>` (praca do chwili czasu bezwzględnego).
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

extern "C" const char* sim_command_line(const char* line);
extern "C" int sim_run(double until);
extern "C" unsigned sim_reboot_reason();

int main() {
    static char line[20000];
    while (fgets(line, sizeof(line), stdin)) {
        char* nl = strchr(line, '\n');
        if (nl) *nl = '\0';
        if (!line[0] || line[0] == '#') continue;
        if (!strncmp(line, "run ", 4)) {
            const int r = sim_run(atof(line + 4));
            if (r) printf("reboot %u\n.\n", sim_reboot_reason());
            else printf("ok\n.\n");
        } else {
            printf("%s\n.\n", sim_command_line(line));
        }
        fflush(stdout);
    }
    return 0;
}

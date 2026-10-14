// SPDX-License-Identifier: MIT
// START-WINDOWS.exe: uruchamia aplikację WICI z pamięci USB bez instalowania czegokolwiek.
// Szuka runtime\windows\pythonw.exe i app\wici.pyz obok siebie, przekazuje własne argumenty,
// czeka na zakończenie i zwraca kod wyjścia (CI sprawdza w ten sposób --selftest).
// Kompilacja (MinGW-w64): x86_64-w64-mingw32-gcc -Os -s -municode -mwindows -o START-WINDOWS.exe start-windows.c
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <wchar.h>

static const wchar_t TITLE[] = L"WICI";

static void fail(const wchar_t* text) { MessageBoxW(NULL, text, TITLE, MB_OK | MB_ICONERROR); }

// Argumenty po nazwie programu, z wiersza poleceń procesu (cudzysłowy zostają bez zmian).
static const wchar_t* rest(const wchar_t* cmd) {
    if (*cmd == L'"') {
        for (++cmd; *cmd && *cmd != L'"'; ++cmd) {}
        if (*cmd) ++cmd;
    } else {
        while (*cmd && *cmd != L' ' && *cmd != L'\t') ++cmd;
    }
    while (*cmd == L' ' || *cmd == L'\t') ++cmd;
    return cmd;
}

int WINAPI wWinMain(HINSTANCE inst, HINSTANCE prev, PWSTR args, int show) {
    (void)inst; (void)prev; (void)args; (void)show;
    wchar_t dir[MAX_PATH], python[MAX_PATH + 40], app[MAX_PATH + 40];
    DWORD n = GetModuleFileNameW(NULL, dir, MAX_PATH);
    if (n == 0 || n >= MAX_PATH) { fail(L"Nie można ustalić położenia programu START."); return 1; }
    wchar_t* slash = wcsrchr(dir, L'\\');
    if (!slash) { fail(L"Nie można ustalić położenia programu START."); return 1; }
    *slash = 0;
    swprintf(python, sizeof(python) / sizeof(python[0]), L"%ls\\runtime\\windows\\pythonw.exe", dir);
    swprintf(app, sizeof(app) / sizeof(app[0]), L"%ls\\app\\wici.pyz", dir);
    if (GetFileAttributesW(python) == INVALID_FILE_ATTRIBUTES || GetFileAttributesW(app) == INVALID_FILE_ATTRIBUTES) {
        fail(L"Brak plików aplikacji obok programu START. Uruchom START z kompletnej pamięci USB WICI.");
        return 1;
    }
    const wchar_t* extra = rest(GetCommandLineW());
    size_t len = wcslen(python) + wcslen(app) + wcslen(extra) + 32;
    wchar_t* cmd = (wchar_t*)HeapAlloc(GetProcessHeap(), 0, len * sizeof(wchar_t));
    if (!cmd) return 1;
    swprintf(cmd, len, L"\"%ls\" -X utf8 \"%ls\" %ls", python, app, extra);
    STARTUPINFOW si;
    PROCESS_INFORMATION pi;
    ZeroMemory(&si, sizeof(si));
    si.cb = sizeof(si);
    if (!CreateProcessW(python, cmd, NULL, NULL, FALSE, 0, NULL, dir, &si, &pi)) {
        fail(L"Nie udało się uruchomić aplikacji WICI.");
        return 1;
    }
    WaitForSingleObject(pi.hProcess, INFINITE);
    DWORD code = 1;
    GetExitCodeProcess(pi.hProcess, &code);
    CloseHandle(pi.hThread);
    CloseHandle(pi.hProcess);
    return (int)code;
}

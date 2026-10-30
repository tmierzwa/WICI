// SPDX-License-Identifier: MIT
// START-WINDOWS.exe: uruchamia aplikację WICI z pamięci USB bez instalowania czegokolwiek.
// Kopiuje runtime\windows, wspólną bibliotekę i app\wici.pyz do %LOCALAPPDATA%\WICI\srodowisko\<wersja>-<suma
// manifestu> i uruchamia aplikację z tej kopii, z WICI_USB = katalog pamięci, więc wyjęcie pamięci jej nie
// zamyka (docs/spec/oprogramowanie.md, „Pakiet USB”). Kopia powstaje w katalogu tymczasowym z manifestem na
// końcu i dostaje swoją nazwę jednym przemianowaniem, jak w runtime/kopia.sh dla macOS i Linuksa. Gdy
// kopiowanie się nie uda, aplikacja działa z pamięci. Przy --selftest START czeka na koniec i zwraca kod
// wyjścia (tak sprawdza go CI); inaczej kończy się po 2 s działania aplikacji, żeby sam nie działał z pamięci
// przez cały czas pracy. Błędy startu pokazuje sama aplikacja i kończy się kodem 3; START pokazuje komunikat
// przy innym kodzie różnym od 0 (Python nie ruszył albo przerwał przed aplikacją), poza --selftest, które nie
// może czekać na kliknięcie w CI.
// Kompilacja (MinGW-w64): x86_64-w64-mingw32-gcc -Os -s -municode -mwindows -o START-WINDOWS.exe start-windows.c
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <wchar.h>

#define PATH_LEN 1024
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

static BOOL exists(const wchar_t* path) { return GetFileAttributesW(path) != INVALID_FILE_ATTRIBUTES; }

// Cały plik do pamięci (najwyżej 16 MiB, manifest ma kilkadziesiąt KB); NULL przy błędzie.
static BYTE* readAll(const wchar_t* path, DWORD* size) {
    HANDLE f = CreateFileW(path, GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING, 0, NULL);
    if (f == INVALID_HANDLE_VALUE) return NULL;
    DWORD n = GetFileSize(f, NULL), got = 0;
    BYTE* data = n <= (16u << 20) ? (BYTE*)HeapAlloc(GetProcessHeap(), 0, n + 1) : NULL;
    if (data && (!ReadFile(f, data, n, &got, NULL) || got != n)) {
        HeapFree(GetProcessHeap(), 0, data);
        data = NULL;
    }
    CloseHandle(f);
    *size = n;
    return data;
}

// Czy oba pliki istnieją i mają tę samą treść.
static BOOL sameFile(const wchar_t* a, const wchar_t* b) {
    DWORD na, nb;
    BYTE* da = readAll(a, &na);
    BYTE* db = da ? readAll(b, &nb) : NULL;
    BOOL same = da && db && na == nb && memcmp(da, db, na) == 0;
    if (da) HeapFree(GetProcessHeap(), 0, da);
    if (db) HeapFree(GetProcessHeap(), 0, db);
    return same;
}

// Katalog razem z brakującymi katalogami nadrzędnymi.
static BOOL makeDirs(wchar_t* path) {
    for (wchar_t* p = path + 3; *p; ++p) {   // po „C:\”
        if (*p != L'\\') continue;
        *p = 0;
        CreateDirectoryW(path, NULL);
        *p = L'\\';
    }
    return CreateDirectoryW(path, NULL) || GetLastError() == ERROR_ALREADY_EXISTS;
}

static BOOL copyTree(const wchar_t* from, const wchar_t* to) {
    wchar_t pattern[PATH_LEN], src[PATH_LEN], dst[PATH_LEN];
    WIN32_FIND_DATAW fd;
    if (!CreateDirectoryW(to, NULL) && GetLastError() != ERROR_ALREADY_EXISTS) return FALSE;
    swprintf(pattern, PATH_LEN, L"%ls\\*", from);
    HANDLE h = FindFirstFileW(pattern, &fd);
    if (h == INVALID_HANDLE_VALUE) return FALSE;
    BOOL ok = TRUE;
    do {
        if (!wcscmp(fd.cFileName, L".") || !wcscmp(fd.cFileName, L"..")) continue;
        swprintf(src, PATH_LEN, L"%ls\\%ls", from, fd.cFileName);
        swprintf(dst, PATH_LEN, L"%ls\\%ls", to, fd.cFileName);
        ok = (fd.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) ? copyTree(src, dst) : CopyFileW(src, dst, FALSE);
    } while (ok && FindNextFileW(h, &fd));
    FindClose(h);
    return ok;
}

static void deleteTree(const wchar_t* path) {
    wchar_t pattern[PATH_LEN], item[PATH_LEN];
    WIN32_FIND_DATAW fd;
    swprintf(pattern, PATH_LEN, L"%ls\\*", path);
    HANDLE h = FindFirstFileW(pattern, &fd);
    if (h != INVALID_HANDLE_VALUE) {
        do {
            if (!wcscmp(fd.cFileName, L".") || !wcscmp(fd.cFileName, L"..")) continue;
            swprintf(item, PATH_LEN, L"%ls\\%ls", path, fd.cFileName);
            if (fd.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) {
                deleteTree(item);
            } else {
                SetFileAttributesW(item, FILE_ATTRIBUTE_NORMAL);
                DeleteFileW(item);
            }
        } while (FindNextFileW(h, &fd));
        FindClose(h);
    }
    RemoveDirectoryW(path);
}

// Kopia na dysku w root; FALSE (root bez zmian) przy każdym błędzie.
static BOOL copyToDisk(const wchar_t* dir, wchar_t* root) {
    wchar_t base[PATH_LEN], dest[PATH_LEN], tmp[PATH_LEN], src[PATH_LEN], dst[PATH_LEN], manifest[PATH_LEN];
    wchar_t version[33] = L"unknown";
    DWORD n = GetEnvironmentVariableW(L"LOCALAPPDATA", base, PATH_LEN - 200);
    if (n == 0 || n >= PATH_LEN - 200) return FALSE;
    swprintf(src, PATH_LEN, L"%ls\\runtime\\VERSION", dir);
    BYTE* text = readAll(src, &n);
    if (text) {   // wersja Pythona, np. „3.14.8”: tylko cyfry i kropki trafiają do nazwy katalogu
        DWORD k = 0;
        for (DWORD i = 0; i < n && k < 32 && ((text[i] >= '0' && text[i] <= '9') || text[i] == '.'); ++i) version[k++] = text[i];
        if (k) version[k] = 0;
        HeapFree(GetProcessHeap(), 0, text);
    }
    swprintf(manifest, PATH_LEN, L"%ls\\build-manifest.json", dir);
    BYTE* data = readAll(manifest, &n);
    if (!data) return FALSE;
    DWORD sum = 2166136261u;   // FNV-1a: tylko rozróżnia budowy, treść porównuje sameFile
    for (DWORD i = 0; i < n; ++i) sum = (sum ^ data[i]) * 16777619u;
    HeapFree(GetProcessHeap(), 0, data);
    swprintf(dest, PATH_LEN, L"%ls\\WICI\\srodowisko\\%ls-%08lx", base, version, (unsigned long)sum);
    swprintf(dst, PATH_LEN, L"%ls\\build-manifest.json", dest);
    if (!sameFile(manifest, dst)) {
        swprintf(tmp, PATH_LEN, L"%ls.tmp-%lu", dest, (unsigned long)GetCurrentProcessId());
        deleteTree(tmp);
        swprintf(dst, PATH_LEN, L"%ls\\app", tmp);
        BOOL ok = makeDirs(dst);
        swprintf(dst, PATH_LEN, L"%ls\\runtime", tmp);
        ok = ok && CreateDirectoryW(dst, NULL);
        static const wchar_t* const files[] = {L"runtime\\python314.zip", L"runtime\\VERSION", L"app\\wici.pyz",
                                               L"build-manifest.json"};   // manifest na końcu
        swprintf(src, PATH_LEN, L"%ls\\runtime\\windows", dir);
        swprintf(dst, PATH_LEN, L"%ls\\runtime\\windows", tmp);
        ok = ok && copyTree(src, dst);
        for (int i = 0; ok && i < 4; ++i) {
            swprintf(src, PATH_LEN, L"%ls\\%ls", dir, files[i]);
            swprintf(dst, PATH_LEN, L"%ls\\%ls", tmp, files[i]);
            ok = CopyFileW(src, dst, FALSE);
        }
        swprintf(dst, PATH_LEN, L"%ls\\build-manifest.json", dest);
        if (ok && !sameFile(manifest, dst)) {   // niepełna kopia tej budowy: nic z niej nie działa
            deleteTree(dest);
            MoveFileW(tmp, dest);               // nie nadpisuje: inny START mógł zdążyć pierwszy
        }
        deleteTree(tmp);
        if (!sameFile(manifest, dst)) return FALSE;
    }
    wcscpy(root, dest);
    return TRUE;
}

int WINAPI wWinMain(HINSTANCE inst, HINSTANCE prev, PWSTR args, int show) {
    (void)inst; (void)prev; (void)args; (void)show;
    wchar_t dir[PATH_LEN], root[PATH_LEN], python[PATH_LEN + 40], app[PATH_LEN + 40];
    DWORD n = GetModuleFileNameW(NULL, dir, PATH_LEN - 200);
    if (n == 0 || n >= PATH_LEN - 200) { fail(L"Nie można ustalić położenia programu START."); return 1; }
    wchar_t* slash = wcsrchr(dir, L'\\');
    if (!slash) { fail(L"Nie można ustalić położenia programu START."); return 1; }
    *slash = 0;
    swprintf(python, sizeof(python) / sizeof(python[0]), L"%ls\\runtime\\windows\\pythonw.exe", dir);
    swprintf(app, sizeof(app) / sizeof(app[0]), L"%ls\\app\\wici.pyz", dir);
    if (!exists(python) || !exists(app)) {
        fail(L"Brak plików aplikacji obok programu START. Uruchom START z kompletnej pamięci USB WICI.");
        return 1;
    }
    wcscpy(root, dir);
    if (copyToDisk(dir, root)) {
        swprintf(python, sizeof(python) / sizeof(python[0]), L"%ls\\runtime\\windows\\pythonw.exe", root);
        swprintf(app, sizeof(app) / sizeof(app[0]), L"%ls\\app\\wici.pyz", root);
    }
    SetEnvironmentVariableW(L"WICI_USB", dir);   // dziedziczy proces aplikacji
    const wchar_t* extra = rest(GetCommandLineW());
    BOOL selftest = wcsstr(extra, L"--selftest") != NULL;
    size_t len = wcslen(python) + wcslen(app) + wcslen(extra) + 32;
    wchar_t* cmd = (wchar_t*)HeapAlloc(GetProcessHeap(), 0, len * sizeof(wchar_t));
    if (!cmd) { fail(L"Za mało pamięci, aby uruchomić aplikację WICI."); return 1; }
    swprintf(cmd, len, L"\"%ls\" -X utf8 \"%ls\" %ls", python, app, extra);
    STARTUPINFOW si;
    PROCESS_INFORMATION pi;
    ZeroMemory(&si, sizeof(si));
    si.cb = sizeof(si);
    // Katalog roboczy to kopia, nie pamięć: otwarty katalog na pamięci blokowałby jej bezpieczne usunięcie.
    if (!CreateProcessW(python, cmd, NULL, NULL, FALSE, 0, NULL, root, &si, &pi)) {
        fail(L"Nie udało się uruchomić aplikacji WICI.");
        return 1;
    }
    CloseHandle(pi.hThread);
    if (WaitForSingleObject(pi.hProcess, selftest ? INFINITE : 2000) == WAIT_TIMEOUT) {
        CloseHandle(pi.hProcess);   // działa: panel otwiera aplikacja
        return 0;
    }
    DWORD code = 1;
    GetExitCodeProcess(pi.hProcess, &code);
    CloseHandle(pi.hProcess);
    if (code != 0 && code != 3 && !selftest) {
        wchar_t text[200];
        swprintf(text, sizeof(text) / sizeof(text[0]),
                 L"Aplikacja WICI zakończyła się błędem (kod %lu). Uruchom START ponownie, a gdy to nie pomoże, użyj innego laptopa.",
                 (unsigned long)code);
        fail(text);
    }
    return (int)code;
}

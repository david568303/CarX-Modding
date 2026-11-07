/* Real paired binaries are copied by run-discovery.ps1 and mapped without DllMain. */
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <wchar.h>

#include "../../src/Doorstop/src/windows/il2cpp_resolver.h"

static BOOL full_path(const WCHAR *relative, WCHAR *path) {
    DWORD length = GetFullPathNameW(relative, MAX_PATH, path, NULL);
    return length && length < MAX_PATH;
}

static BOOL narrow_name(const WCHAR *wide, char *name, size_t size) {
    return WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, wide, -1, name,
                               (int)size, NULL, NULL) > 0;
}

static BOOL expect_no_map(HMODULE game, const WCHAR *output) {
    char alias[256];
    return GetFileAttributesW(output) == INVALID_FILE_ATTRIBUTES &&
           !doorstop_export_alias(game, "il2cpp_init", alias, ARRAYSIZE(alias)) &&
           !doorstop_resolve_export(game, "il2cpp_init");
}

static BOOL check_entries(HMODULE game, const WCHAR *reference, const WCHAR *output) {
    WCHAR entries[32768], published[32768];
    DWORD length = GetPrivateProfileSectionW(L"Exports", entries, ARRAYSIZE(entries), reference);
    DWORD actual = GetPrivateProfileSectionW(L"Exports", published, ARRAYSIZE(published), output);
    if (!length || length != actual || length >= ARRAYSIZE(entries) - 2 ||
        GetPrivateProfileIntW(L"Target", L"Format", 0, output) != 2) return FALSE;

    WCHAR value[512];
    if (!GetPrivateProfileStringW(L"Target", L"Discovery", L"", value, ARRAYSIZE(value), output) ||
        wcscmp(value, L"binary-loader-schema")) return FALSE;
    const BYTE *base = (const BYTE *)game;
    const IMAGE_DOS_HEADER *dos = (const void *)base;
    const IMAGE_NT_HEADERS *headers = (const void *)(base + dos->e_lfanew);
    if (!GetPrivateProfileStringW(L"Target", L"TimeDateStamp", L"", value, ARRAYSIZE(value), output) ||
        wcstoul(value, NULL, 16) != headers->FileHeader.TimeDateStamp ||
        !GetPrivateProfileStringW(L"Target", L"SizeOfImage", L"", value, ARRAYSIZE(value), output) ||
        wcstoul(value, NULL, 16) != headers->OptionalHeader.SizeOfImage) return FALSE;

    size_t count = 0;
    for (WCHAR *entry = entries; *entry;) {
        WCHAR *next = entry + wcslen(entry) + 1;
        WCHAR *equals = wcschr(entry, L'=');
        if (!equals) return FALSE;
        *equals = 0;
        if (!GetPrivateProfileStringW(L"Exports", entry, L"", value, ARRAYSIZE(value), output) ||
            wcscmp(value, equals + 1)) return FALSE;
        WCHAR *comma = wcschr(value, L',');
        if (!comma) return FALSE;
        *comma = 0;
        DWORD rva = wcstoul(comma + 1, NULL, 16);

        char canonical[256], expected[256], alias[256];
        if (!narrow_name(entry, canonical, sizeof(canonical)) ||
            !narrow_name(value, expected, sizeof(expected)) ||
            !doorstop_export_alias(game, canonical, alias, ARRAYSIZE(alias)) || strcmp(alias, expected) ||
            doorstop_resolve_export(game, canonical) != (FARPROC)(base + rva) ||
            doorstop_get_proc_address(game, canonical) != GetProcAddress(game, expected) ||
            doorstop_export_alias(game, canonical, alias, 1)) return FALSE;
        ++count;
        entry = next;
    }
    printf("Verified %zu canonical lookups, aliases, and native export RVAs.\n", count);
    return count >= 234;
}

/* Swap the export table RVAs only in this process. This keeps the binder's
   count, names, and slots valid while corrupting two native API identities. */
static DWORD *export_slot(HMODULE game, const WCHAR *canonical, const WCHAR *reference) {
    WCHAR entry[256];
    char alias[256];
    if (!GetPrivateProfileStringW(L"Exports", canonical, L"", entry, ARRAYSIZE(entry), reference))
        return NULL;
    WCHAR *comma = wcschr(entry, L',');
    if (!comma) return NULL;
    *comma = 0;
    if (!narrow_name(entry, alias, sizeof(alias))) return NULL;

    BYTE *base = (BYTE *)game;
    const IMAGE_DOS_HEADER *dos = (const void *)base;
    const IMAGE_NT_HEADERS *headers = (const void *)(base + dos->e_lfanew);
    const IMAGE_EXPORT_DIRECTORY *exports =
        (const void *)(base + headers->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_EXPORT].VirtualAddress);
    const DWORD *names = (const void *)(base + exports->AddressOfNames);
    const WORD *ordinals = (const void *)(base + exports->AddressOfNameOrdinals);
    DWORD *functions = (void *)(base + exports->AddressOfFunctions);
    for (DWORD i = 0; i < exports->NumberOfNames; ++i)
        if (!strcmp((const char *)(base + names[i]), alias)) return &functions[ordinals[i]];
    return NULL;
}

static BOOL replace_slot(DWORD *slot, DWORD value) {
    DWORD previous, ignored;
    if (!VirtualProtect(slot, sizeof(*slot), PAGE_READWRITE, &previous)) return FALSE;
    *slot = value;
    return VirtualProtect(slot, sizeof(*slot), previous, &ignored);
}

static BOOL swap_inits(HMODULE game, const WCHAR *reference) {
    DWORD *ascii = export_slot(game, L"il2cpp_init", reference);
    DWORD *utf16 = export_slot(game, L"il2cpp_init_utf16", reference);
    if (!ascii || !utf16 || *ascii == *utf16) return FALSE;
    DWORD prior = *ascii;
    return replace_slot(ascii, *utf16) && replace_slot(utf16, prior);
}

int wmain(int argc, WCHAR **argv) {
    if (argc != 3) return 2;
    WCHAR unity_path[MAX_PATH], game_path[MAX_PATH], output[MAX_PATH];
    if (!full_path(L"UnityPlayer.dll", unity_path) || !full_path(L"GameAssembly.dll", game_path) ||
        !full_path(L"doorstop_api.ini", output)) return 2;

    HMODULE unity = LoadLibraryExW(unity_path, NULL, DONT_RESOLVE_DLL_REFERENCES);
    HMODULE game = LoadLibraryExW(game_path, NULL, DONT_RESOLVE_DLL_REFERENCES);
    if (!unity || !game) {
        fprintf(stderr, "Could not map fixture DLLs: %lu\n", GetLastError());
        return 2;
    }
    BOOL success;
    if (!wcscmp(argv[1], L"cold") || !wcscmp(argv[1], L"warm") || !wcscmp(argv[1], L"stale")) {
        doorstop_prepare_api_map(game);
        /* Successful publication owns its own GameAssembly reference. */
        FreeLibrary(game);
        success = check_entries(game, argv[2], output);
    } else {
        if (!wcscmp(argv[1], L"swapped") && !swap_inits(game, argv[2])) return 2;
        doorstop_prepare_api_map(game);
        success = expect_no_map(game, output);
        FreeLibrary(game);
    }
    FreeLibrary(unity);
    wprintf(L"%ls %ls\n", success ? L"PASS" : L"FAIL", argv[1]);
    return success ? 0 : 1;
}

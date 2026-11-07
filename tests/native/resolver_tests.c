/* Isolated tests. These load only DLLs built from runtime_fixture.c. */
#include <windows.h>
#include <stdio.h>
#include <string.h>

#include "../../src/Doorstop/src/windows/il2cpp_resolver.h"

static unsigned int passed, failed;

#define CHECK(label, condition) do { \
    if (condition) { ++passed; printf("PASS %s\n", label); } \
    else { ++failed; printf("FAIL %s (line %u)\n", label, __LINE__); } \
} while (0)

static BOOL write_legacy_map(HMODULE game, FARPROC renamed) {
    const BYTE *base = (const BYTE *)game;
    const IMAGE_DOS_HEADER *dos = (const void *)base;
    const IMAGE_NT_HEADERS *headers = (const void *)(base + dos->e_lfanew);
    FILE *ini;
    if (fopen_s(&ini, "doorstop_api.ini", "wb")) return FALSE;
    fprintf(ini, "[Target]\nFormat=2\nDiscovery=binary-loader-schema\n"
                 "TimeDateStamp=%lx\nSizeOfImage=%lx\n[Exports]\n"
                 "il2cpp_init=SyntheticBootstrap,%lx\n",
            headers->FileHeader.TimeDateStamp, headers->OptionalHeader.SizeOfImage,
            (DWORD)((const BYTE *)renamed - base));
    return fclose(ini) == 0;
}

int main(void) {
    char directory[MAX_PATH], alias[256];
    DWORD length = GetModuleFileNameA(NULL, directory, ARRAYSIZE(directory));
    if (!length || length >= ARRAYSIZE(directory)) return 2;
    char *separator = strrchr(directory, '\\');
    if (!separator) return 2;
    *separator = 0;
    if (!SetCurrentDirectoryA(directory)) return 2;

    HMODULE game = LoadLibraryA(".\\GameAssembly.dll");
    HMODULE other = LoadLibraryA(".\\OtherRuntime.dll");
    if (!game || !other) {
        fprintf(stderr, "Fixture load failed: %lu\n", GetLastError());
        return 2;
    }
    FARPROC renamed = GetProcAddress(game, "SyntheticBootstrap");
    CHECK("fixtures loaded", renamed != NULL);
    DeleteFileA("doorstop_api.ini");
    CHECK("missing discovery fails safely", doorstop_resolve_export(game, "il2cpp_init") == NULL);
    CHECK("well-formed legacy map fixture created", write_legacy_map(game, renamed));
    doorstop_prepare_api_map(game);
    CHECK("a matching legacy map never activates an alias",
          !doorstop_export_alias(game, "il2cpp_init", alias, sizeof(alias)));
    CHECK("canonical lookup ignores legacy INI", doorstop_resolve_export(game, "il2cpp_init") == NULL);
    CHECK("direct canonical export preserved",
          doorstop_resolve_export(game, "il2cpp_already_present") ==
          GetProcAddress(game, "il2cpp_already_present"));
    CHECK("direct renamed export preserved", doorstop_resolve_export(game, "SyntheticBootstrap") == renamed);
    CHECK("unrelated module alias refused", !doorstop_export_alias(other, "il2cpp_init", alias, sizeof(alias)));
    CHECK("unrelated direct export preserved", doorstop_resolve_export(other, "SyntheticBootstrap") ==
                                                GetProcAddress(other, "SyntheticBootstrap"));
    CHECK("unmapped API fails safely", doorstop_resolve_export(game, "il2cpp_no_mapping") == NULL);
    CHECK("present ordinal forwarded", doorstop_resolve_export(game, MAKEINTRESOURCEA(123)) ==
                                       GetProcAddress(game, MAKEINTRESOURCEA(123)));
    CHECK("absent ordinal fails safely", doorstop_resolve_export(game, MAKEINTRESOURCEA(124)) == NULL);
    CHECK("ordinal alias refused", !doorstop_export_alias(game, MAKEINTRESOURCEA(124), alias, sizeof(alias)));
    CHECK("null canonical refused", doorstop_resolve_export(game, NULL) == NULL);
    CHECK("null module refused", doorstop_resolve_export(NULL, "il2cpp_init") == NULL);
    CHECK("null alias output refused", !doorstop_export_alias(game, "il2cpp_init", NULL, sizeof(alias)));
    DeleteFileA("doorstop_api.ini");
    FreeLibrary(other);
    FreeLibrary(game);
    printf("RESULT %u passed, %u failed\n", passed, failed);
    return failed ? 1 : 0;
}

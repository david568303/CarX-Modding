#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <wchar.h>

typedef FARPROC (WINAPI *get_proc_fn)(HMODULE, LPCSTR);
typedef LONG (__cdecl *call_count_fn)(void);
static unsigned int passed;
static void check(int condition, const char *label) {
    if (!condition) { fprintf(stderr, "FAIL %s (Windows error %lu)\n", label, GetLastError()); ExitProcess(2); }
    passed++;
}
/* These are ordinary, non-inlined calls through the host's imported functions.
 * They deliberately exercise the IAT patched by the loaded Doorstop DLL. */
__declspec(noinline) static FARPROC lookup(HMODULE module, LPCSTR name) { return GetProcAddress(module, name); }
__declspec(noinline) static LPWSTR command_w(void) { return GetCommandLineW(); }
__declspec(noinline) static LPSTR command_a(void) { return GetCommandLineA(); }
__declspec(noinline) static BOOL close_owned(HANDLE handle) { return CloseHandle(handle); }

static void **iat_slot(const char *function) {
    BYTE *base = (BYTE *)GetModuleHandleW(NULL);
    IMAGE_DOS_HEADER *dos = (IMAGE_DOS_HEADER *)base;
    IMAGE_NT_HEADERS64 *nt = (IMAGE_NT_HEADERS64 *)(base + dos->e_lfanew);
    IMAGE_IMPORT_DESCRIPTOR *imports = (IMAGE_IMPORT_DESCRIPTOR *)(base +
        nt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_IMPORT].VirtualAddress);
    for (; imports->Name; imports++) {
        IMAGE_THUNK_DATA64 *names, *values;
        if (lstrcmpiA((char *)(base + imports->Name), "kernel32.dll") != 0) continue;
        names = (IMAGE_THUNK_DATA64 *)(base + imports->OriginalFirstThunk);
        values = (IMAGE_THUNK_DATA64 *)(base + imports->FirstThunk);
        for (; names->u1.AddressOfData; names++, values++) {
            IMAGE_IMPORT_BY_NAME *name;
            if (IMAGE_SNAP_BY_ORDINAL64(names->u1.Ordinal)) continue;
            name = (IMAGE_IMPORT_BY_NAME *)(base + names->u1.AddressOfData);
            if (strcmp((char *)name->Name, function) == 0) return (void **)&values->u1.Function;
        }
    }
    return NULL;
}
static void ini(const char *section, const char *key, const char *value) {
    check(WritePrivateProfileStringA(section, key, value, ".\\doorstop_api.ini") != FALSE,
          "synthetic API map entry written");
}
static void write_forged_map(HMODULE game, get_proc_fn raw_lookup) {
    IMAGE_DOS_HEADER *dos = (IMAGE_DOS_HEADER *)game;
    IMAGE_NT_HEADERS64 *nt = (IMAGE_NT_HEADERS64 *)((BYTE *)game + dos->e_lfanew);
    const char *canonical[] = {"il2cpp_init", "il2cpp_runtime_invoke", "il2cpp_method_get_name"};
    const char *alias[] = {"AliasInit", "AliasRuntimeInvoke", "AliasMethodGetName"};
    char buffer[128];
    unsigned int i;
    ini("Target", "Format", "2");
    ini("Target", "Discovery", "binary-loader-schema");
    sprintf_s(buffer, sizeof(buffer), "%08lX", nt->FileHeader.TimeDateStamp);
    ini("Target", "TimeDateStamp", buffer);
    sprintf_s(buffer, sizeof(buffer), "%08lX", nt->OptionalHeader.SizeOfImage);
    ini("Target", "SizeOfImage", buffer);
    for (i = 0; i < 3; i++) {
        FARPROC target = raw_lookup(game, alias[i]);
        check(target != NULL, "fake critical API is exported");
        sprintf_s(buffer, sizeof(buffer), "%s,%08lX", alias[i], (DWORD)((BYTE *)target - (BYTE *)game));
        ini("Exports", canonical[i], buffer);
    }
    WritePrivateProfileStringA(NULL, NULL, NULL, ".\\doorstop_api.ini");
    check(GetPrivateProfileIntA("Target", "Format", 0, ".\\doorstop_api.ini") == 2,
          "synthetic API map read back");
}
static void restore_slot(void **slot, void *original) {
    DWORD old_protection, ignored;
    check(VirtualProtect(slot, sizeof(*slot), PAGE_READWRITE, &old_protection) != FALSE,
          "own-process IAT slot made writable for cleanup");
    *slot = original;
    check(VirtualProtect(slot, sizeof(*slot), old_protection, &ignored) != FALSE,
          "own-process IAT protection restored");
}
static char *edge_name(void) {
    /* The low DWORD is zero at every candidate address. This is a named
       lookup on x64 even though the 16-bit HIWORD macro returns zero. */
    for (ULONG_PTR address = 0x18000000000; address < 0x19000000000; address += 0x100000000) {
        char *name = VirtualAlloc((LPVOID)address, 4096, MEM_RESERVE | MEM_COMMIT, PAGE_READWRITE);
        if (name) {
            strcpy_s(name, 4096, "il2cpp_init");
            return name;
        }
    }
    return NULL;
}
int wmain(int argc, wchar_t **argv) {
    const char *import_names[] = {"GetProcAddress", "GetCommandLineW", "GetCommandLineA", "CloseHandle"};
    void **slots[4], *original[4];
    HMODULE game, loader, kernel;
    get_proc_fn raw_lookup;
    call_count_fn count_calls;
    FARPROC real_init, legacy_alias, ordinary, kernel_proc, canonical_wrapper;
    MEMORY_BASIC_INFORMATION info;
    wchar_t before_w[32768];
    char before_a[32768];
    DWORD handle_flags;
    HANDLE event;
    char *canonical_name;
    unsigned int i;
    check(argc == 2, "absolute candidate DLL path supplied");
    check(GetFileAttributesW(L"inert-target.txt") != INVALID_FILE_ATTRIBUTES, "inert target file exists");
    check(GetModuleHandleW(L"coreclr.dll") == NULL, "CoreCLR absent before test");
    SetEnvironmentVariableW(L"DOORSTOP_DISABLE", NULL);
    SetEnvironmentVariableW(L"DOORSTOP_INITIALIZED", NULL);
    for (i = 0; i < 4; i++) {
        slots[i] = iat_slot(import_names[i]);
        check(slots[i] != NULL, "ordinary Kernel32 import slot exists");
        original[i] = *slots[i];
    }
    raw_lookup = (get_proc_fn)original[0];
    wcscpy_s(before_w, _countof(before_w), command_w());
    strcpy_s(before_a, sizeof(before_a), command_a());
    game = LoadLibraryW(L".\\GameAssembly.dll");
    check(game != NULL, "synthetic GameAssembly loaded");
    write_forged_map(game, raw_lookup);
    real_init = raw_lookup(game, "il2cpp_init");
    legacy_alias = raw_lookup(game, "AliasInit");
    ordinary = raw_lookup(game, "ExistingOrdinary");
    count_calls = (call_count_fn)raw_lookup(game, "ObservedCallCount");
    check(real_init != NULL && legacy_alias != NULL && legacy_alias != real_init &&
          ordinary != NULL && count_calls != NULL, "synthetic stock and legacy exports resolved");
    check(lookup(game, "il2cpp_init") == real_init, "stock canonical init available before loader");
    check(count_calls() == 0, "no fake runtime API invoked before loader");
    kernel = GetModuleHandleW(L"kernel32.dll");
    kernel_proc = raw_lookup(kernel, "GetCurrentProcessId");
    loader = LoadLibraryW(argv[1]);
    check(loader != NULL, "enabled loader DLL loaded");
    for (i = 0; i < 4; i++) check(*slots[i] != original[i], "loader patched expected own-process IAT slot");
    check(wcscmp(before_w, command_w()) == 0, "GetCommandLineW passthrough preserved");
    check(strcmp(before_a, command_a()) == 0, "GetCommandLineA passthrough preserved");
    canonical_name = edge_name();
    check(canonical_name != NULL && !HIWORD(canonical_name) && !IS_INTRESOURCE(canonical_name),
          "x64 name with zero low high-word allocated");
    canonical_wrapper = lookup(game, canonical_name);
    check(VirtualFree(canonical_name, 0, MEM_RELEASE) != FALSE, "x64 name page released");
    check(canonical_wrapper != NULL && canonical_wrapper != real_init,
          "x64 canonical name returns initialization wrapper");
    check(lookup(game, "AliasInit") == legacy_alias, "forged map cannot redirect a native export");
    check(VirtualQuery((LPCVOID)canonical_wrapper, &info, sizeof(info)) == sizeof(info) &&
          info.AllocationBase == loader, "initialization wrapper belongs to requested loader DLL");
    check(lookup(game, "ExistingOrdinary") == ordinary, "ordinary game export passthrough preserved");
    check(lookup(game, (LPCSTR)(ULONG_PTR)123) == legacy_alias, "ordinal lookup passthrough preserved");
    check(lookup(game, (LPCSTR)(ULONG_PTR)65000) == NULL, "missing ordinal safely returns null");
    check(lookup(game, "MissingOrdinary") == NULL, "missing ordinary game export safely returns null");
    check(lookup(kernel, "GetCurrentProcessId") == kernel_proc, "unrelated system lookup passthrough preserved");
    event = CreateEventW(NULL, TRUE, FALSE, NULL);
    check(event != NULL, "private event created");
    check(close_owned(event) != FALSE, "CloseHandle forwards private event close");
    check(GetHandleInformation(event, &handle_flags) == FALSE && GetLastError() == ERROR_INVALID_HANDLE,
          "private event was actually closed");
    check(count_calls() == 0, "initialization wrapper and runtime APIs were never invoked");
    check(GetModuleHandleW(L"coreclr.dll") == NULL, "CoreCLR was never loaded");
    check(GetFileAttributesW(L"BepInEx\\api-refresh.log") == INVALID_FILE_ATTRIBUTES,
          "native API discovery was never entered");
    /* Doorstop does not undo its IAT hooks on unload. Restore only our host's
     * four slots before FreeLibrary, then let normal process teardown proceed. */
    for (i = 0; i < 4; i++) restore_slot(slots[i], original[i]);
    for (i = 0; i < 4; i++) check(*slots[i] == original[i], "own-process IAT restored for cleanup");
    check(FreeLibrary(loader) != FALSE, "loader reference released after hook cleanup");
    check(FreeLibrary(game) != FALSE, "synthetic GameAssembly released");
    printf("{\"success\":true,\"iatSlotsPatched\":4,\"canonicalInitWrapped\":true,\"forgedMapIgnored\":true,"
           "\"ordinalAndUnrelatedLookupsPreserved\":true,\"commandLinesPreserved\":true,"
           "\"privateHandlePassthrough\":true,\"runtimeCalls\":0,\"coreclrLoaded\":false,"
           "\"discoveryEntered\":false,\"checksPassed\":%u}\n", passed);
    return 0;
}

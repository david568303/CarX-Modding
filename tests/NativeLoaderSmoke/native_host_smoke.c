#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <winhttp.h>
#include <stdio.h>
#include <stdlib.h>
#include <wchar.h>

typedef BOOL (WINAPI *check_platform_fn)(void);
typedef BOOL (WINAPI *crack_url_fn)(LPCWSTR, DWORD, DWORD, LPURL_COMPONENTS);
typedef struct {
    BOOL platform;
    BOOL cracked;
    int scheme;
    unsigned int port;
    wchar_t host[256];
    wchar_t path[256];
    wchar_t extra[256];
} probe_result;

static unsigned int passed;
static int equivalent(const probe_result *a, const probe_result *b) {
    return a->platform == b->platform && a->cracked == b->cracked &&
           a->scheme == b->scheme && a->port == b->port &&
           wcscmp(a->host, b->host) == 0 && wcscmp(a->path, b->path) == 0 &&
           wcscmp(a->extra, b->extra) == 0;
}
static void check(int value, const char *label) {
    if (!value) {
        fprintf(stderr, "FAIL %s (Windows error %lu)\n", label, GetLastError());
        ExitProcess(2);
    }
    passed++;
}
static void copy_piece(wchar_t *out, size_t size, const wchar_t *start, DWORD length) {
    check(start != NULL && length < size, "bounded URL component");
    wmemcpy(out, start, length);
    out[length] = L'\0';
}
static probe_result probe(HMODULE module) {
    probe_result result = {0};
    URL_COMPONENTS parts = {0};
    static const wchar_t url[] = L"https://example.invalid:8443/some/path?x=1#fragment";
    check_platform_fn platform = (check_platform_fn)GetProcAddress(module, "WinHttpCheckPlatform");
    crack_url_fn crack = (crack_url_fn)GetProcAddress(module, "WinHttpCrackUrl");
    check(platform != NULL && crack != NULL, "forwarded functions exported");
    result.platform = platform();
    check(result.platform != FALSE, "WinHttpCheckPlatform succeeds");
    parts.dwStructSize = sizeof(parts);
    parts.dwSchemeLength = (DWORD)-1;
    parts.dwHostNameLength = (DWORD)-1;
    parts.dwUrlPathLength = (DWORD)-1;
    parts.dwExtraInfoLength = (DWORD)-1;
    result.cracked = crack(url, 0, 0, &parts);
    check(result.cracked != FALSE, "WinHttpCrackUrl succeeds without networking");
    result.scheme = parts.nScheme;
    result.port = parts.nPort;
    copy_piece(result.host, _countof(result.host), parts.lpszHostName, parts.dwHostNameLength);
    copy_piece(result.path, _countof(result.path), parts.lpszUrlPath, parts.dwUrlPathLength);
    copy_piece(result.extra, _countof(result.extra), parts.lpszExtraInfo, parts.dwExtraInfoLength);
    check(result.scheme == INTERNET_SCHEME_HTTPS && result.port == 8443, "URL scheme and port preserved");
    check(wcscmp(result.host, L"example.invalid") == 0, "URL host preserved");
    check(wcscmp(result.path, L"/some/path") == 0, "URL path preserved");
    check(wcscmp(result.extra, L"?x=1#fragment") == 0, "URL query and fragment preserved");
    return result;
}
static HMODULE load_exact(const wchar_t *path) {
    wchar_t actual[32768], expected[32768];
    HMODULE module = LoadLibraryW(path);
    check(module != NULL, "LoadLibraryW succeeds");
    check(GetModuleFileNameW(module, actual, _countof(actual)) != 0, "loaded module path available");
    check(GetFullPathNameW(path, _countof(expected), expected, NULL) != 0, "expected module path resolved");
    check(CompareStringOrdinal(actual, -1, expected, -1, TRUE) == CSTR_EQUAL,
          "absolute path loads requested DLL rather than another winhttp module");
    return module;
}
static unsigned long long preferred_base(const wchar_t *path) {
    IMAGE_DOS_HEADER dos = {0};
    IMAGE_NT_HEADERS64 nt = {0};
    LARGE_INTEGER offset, file_size;
    DWORD read;
    HANDLE file = CreateFileW(path, GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
                              NULL, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
    check(file != INVALID_HANDLE_VALUE, "PE file opened read-only");
    check(GetFileSizeEx(file, &file_size) && ReadFile(file, &dos, sizeof(dos), &read, NULL) &&
          read == sizeof(dos) && dos.e_magic == IMAGE_DOS_SIGNATURE,
          "on-disk DOS header valid");
    check(dos.e_lfanew > 0 && (LONGLONG)dos.e_lfanew + (LONGLONG)sizeof(nt) <= file_size.QuadPart,
          "on-disk NT header bounded");
    offset.QuadPart = dos.e_lfanew;
    check(SetFilePointerEx(file, offset, NULL, FILE_BEGIN) &&
          ReadFile(file, &nt, sizeof(nt), &read, NULL) && read == sizeof(nt) &&
          nt.Signature == IMAGE_NT_SIGNATURE && nt.OptionalHeader.Magic == IMAGE_NT_OPTIONAL_HDR64_MAGIC,
          "on-disk x64 NT header valid");
    check(CloseHandle(file) != FALSE, "PE file read handle closed");
    return nt.OptionalHeader.ImageBase;
}

int wmain(int argc, wchar_t **argv) {
    wchar_t system_path[32768];
    HMODULE system_module, old_module, new_module;
    probe_result expected, old_result, new_result;
    unsigned long long old_preferred, new_preferred;
    unsigned int round;
    check(argc == 3, "two absolute DLL paths supplied");
    check(GetSystemDirectoryW(system_path, _countof(system_path)) != 0, "System32 located");
    check(wcscat_s(system_path, _countof(system_path), L"\\winhttp.dll") == 0, "System32 DLL path formed");
    system_module = load_exact(system_path);
    expected = probe(system_module);
    old_module = load_exact(argv[1]);
    new_module = load_exact(argv[2]);
    check(system_module != old_module && system_module != new_module && old_module != new_module,
          "system, baseline and candidate are three distinct loaded images");
    old_result = probe(old_module);
    new_result = probe(new_module);
    check(equivalent(&expected, &old_result), "baseline forwarding matches System32");
    check(equivalent(&expected, &new_result), "candidate forwarding matches System32");
    old_preferred = preferred_base(argv[1]);
    new_preferred = preferred_base(argv[2]);
    check((unsigned long long)(ULONG_PTR)old_module != old_preferred ||
          (unsigned long long)(ULONG_PTR)new_module != new_preferred,
          "at least one loader image successfully executes away from preferred base");
    printf("{\"baselineBase\":\"%p\",\"candidateBase\":\"%p\","
           "\"baselinePreferred\":\"%llx\",\"candidatePreferred\":\"%llx\",",
           (void *)old_module, (void *)new_module, old_preferred, new_preferred);
    check(FreeLibrary(new_module) != FALSE, "candidate unload succeeds");
    check(FreeLibrary(old_module) != FALSE, "baseline unload succeeds");
    for (round = 0; round < 3; round++) {
        new_module = load_exact(argv[2]);
        new_result = probe(new_module);
        check(equivalent(&expected, &new_result), "reloaded candidate forwarding preserved");
        check(FreeLibrary(new_module) != FALSE, "reloaded candidate unload succeeds");
    }
    check(FreeLibrary(system_module) != FALSE, "System32 reference released");
    printf("\"forwardingComparisons\":5,\"candidateReloadRounds\":3,\"checksPassed\":%u,"
           "\"success\":true}\n", passed);
    return 0;
}

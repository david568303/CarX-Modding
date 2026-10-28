#include <windows.h>
int renamed_bootstrap(void) { return 37; }
int renamed_invoke(void) { return 42; }
int already_present(void) { return 99; }
int ordinal_only(void) { return 123; }
BOOL WINAPI DllMain(HINSTANCE instance, DWORD reason, LPVOID reserved) {
    (void)instance; (void)reason; (void)reserved; return TRUE;
}

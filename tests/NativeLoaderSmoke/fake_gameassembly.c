#include <windows.h>
static LONG init_calls, invoke_calls, name_calls;
int __cdecl AliasInit(const char *domain) { (void)domain; InterlockedIncrement(&init_calls); return 0; }
void *__cdecl AliasRuntimeInvoke(void *method, void *object, void **parameters, void **exception) {
    (void)method; (void)object; (void)parameters; (void)exception;
    InterlockedIncrement(&invoke_calls); return NULL;
}
const char *__cdecl AliasMethodGetName(void *method) { (void)method; InterlockedIncrement(&name_calls); return "FakeMethod"; }
int __cdecl ExistingOrdinary(void) { return 42; }
LONG __cdecl ObservedCallCount(void) { return init_calls + invoke_calls + name_calls; }

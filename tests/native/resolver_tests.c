/* Isolated tests: these load only DLLs built from runtime_fixture.c. */
#include <windows.h>
#include <stdio.h>
#include <string.h>
#include "../../src/Doorstop/src/windows/il2cpp_resolver.h"
static unsigned int passed, failed;
static const char *config_path=".\\doorstop_api.ini";
#define CHECK(label, condition) do { if(condition) { ++passed; printf("PASS %s\n",label); } else { ++failed; printf("FAIL %s (line %u)\n",label,__LINE__); } } while(0)
static void write_key(const char *section,const char *key,const char *value) {
    if(!WritePrivateProfileStringA(section,key,value,config_path)) { fprintf(stderr,"INI write failed %lu\n",GetLastError());ExitProcess(2); }
    WritePrivateProfileStringA(NULL,NULL,NULL,config_path);
}
static IMAGE_NT_HEADERS *headers(HMODULE module) { return (IMAGE_NT_HEADERS *)((BYTE *)module+((IMAGE_DOS_HEADER *)module)->e_lfanew); }
static void hex_key(const char *key,DWORD value) { char text[32];sprintf_s(text,sizeof(text),"%08lX",value);write_key("Target",key,text); }
static void valid_map(HMODULE game) {
    char text[256];IMAGE_NT_HEADERS *nt=headers(game);
    DeleteFileA(config_path);
    write_key("Target","Format","2");
    write_key("Target","Discovery","binary-loader-schema");
    hex_key("TimeDateStamp",nt->FileHeader.TimeDateStamp);
    hex_key("SizeOfImage",nt->OptionalHeader.SizeOfImage);
    DWORD rva=(DWORD)((BYTE *)GetProcAddress(game,"SyntheticBootstrap")-(BYTE *)game);
    sprintf_s(text,sizeof(text),"SyntheticBootstrap,%08lX",rva);
    write_key("Exports","il2cpp_init",text);
}
int main(void) {
    char executable[MAX_PATH],alias[256];
    if(!GetModuleFileNameA(NULL,executable,sizeof(executable))) return 2;
    char *separator=strrchr(executable,'\\');if(!separator) return 2;*separator=0;
    if(!SetCurrentDirectoryA(executable)) return 2;
    HMODULE game=LoadLibraryA(".\\GameAssembly.dll");
    HMODULE other=LoadLibraryA(".\\OtherRuntime.dll");
    if(!game||!other) { fprintf(stderr,"Fixture load failure %lu\n",GetLastError());return 2; }
    FARPROC real_init=GetProcAddress(game,"SyntheticBootstrap");
    CHECK("fixtures loaded",real_init!=NULL);
    DeleteFileA(config_path);
    CHECK("missing map fails safely",doorstop_resolve_export(game,"il2cpp_init")==NULL);
    valid_map(game);
    CHECK("valid alias accepted",doorstop_export_alias(game,"il2cpp_init",alias,sizeof(alias)) && !strcmp(alias,"SyntheticBootstrap"));
    CHECK("canonical lookup resolves renamed export",doorstop_resolve_export(game,"il2cpp_init")==real_init);
    write_key("Target","Format","1");
    CHECK("legacy map format is retired",doorstop_resolve_export(game,"il2cpp_init")==NULL);
    valid_map(game);write_key("Target","Discovery","legacy");
    CHECK("legacy discovery cache is retired",doorstop_resolve_export(game,"il2cpp_init")==NULL);
    valid_map(game);
    CHECK("direct existing export preserved",doorstop_resolve_export(game,"il2cpp_already_present")==GetProcAddress(game,"il2cpp_already_present"));
    CHECK("direct renamed export preserved",doorstop_resolve_export(game,"SyntheticBootstrap")==real_init);
    CHECK("unrelated module alias refused",!doorstop_export_alias(other,"il2cpp_init",alias,sizeof(alias)));
    CHECK("unrelated module lookup unchanged",doorstop_resolve_export(other,"il2cpp_init")==NULL);
    CHECK("short alias buffer refused",!doorstop_export_alias(game,"il2cpp_init",alias,3));
    CHECK("zero alias capacity refused",!doorstop_export_alias(game,"il2cpp_init",alias,0));
    CHECK("null alias output refused",!doorstop_export_alias(game,"il2cpp_init",NULL,sizeof(alias)));
    CHECK("unmapped API fails safely",doorstop_resolve_export(game,"il2cpp_no_mapping")==NULL);
    hex_key("TimeDateStamp",headers(game)->FileHeader.TimeDateStamp^1);
    CHECK("stale timestamp refused",doorstop_resolve_export(game,"il2cpp_init")==NULL);
    valid_map(game);hex_key("SizeOfImage",headers(game)->OptionalHeader.SizeOfImage^0x1000);
    CHECK("stale image size refused",doorstop_resolve_export(game,"il2cpp_init")==NULL);
    valid_map(game);write_key("Exports","il2cpp_init","SyntheticBootstrap,00000001");
    CHECK("wrong export RVA refused",doorstop_resolve_export(game,"il2cpp_init")==NULL);
    valid_map(game);write_key("Exports","il2cpp_init","MissingExport,00000001");
    CHECK("missing renamed export refused",doorstop_resolve_export(game,"il2cpp_init")==NULL);
    valid_map(game);write_key("Target","TimeDateStamp","not_hex");
    CHECK("invalid timestamp refused",doorstop_resolve_export(game,"il2cpp_init")==NULL);
    valid_map(game);write_key("Target","SizeOfImage","100000000");
    CHECK("overflow image size refused",doorstop_resolve_export(game,"il2cpp_init")==NULL);
    valid_map(game);write_key("Exports","il2cpp_init","SyntheticBootstrap,");
    CHECK("empty export RVA refused",doorstop_resolve_export(game,"il2cpp_init")==NULL);
    valid_map(game);write_key("Exports","il2cpp_init",",00000001");
    CHECK("empty renamed export refused",doorstop_resolve_export(game,"il2cpp_init")==NULL);
    valid_map(game);write_key("Exports","il2cpp_init","SyntheticBootstrap,00000000,1");
    CHECK("extra separators refused",doorstop_resolve_export(game,"il2cpp_init")==NULL);
    valid_map(game);
    CHECK("present ordinal forwarded",doorstop_resolve_export(game,(const char *)(ULONG_PTR)123)==GetProcAddress(game,(const char *)(ULONG_PTR)123));
    CHECK("absent ordinal fails safely",doorstop_resolve_export(game,(const char *)(ULONG_PTR)124)==NULL);
    CHECK("ordinal alias not treated as string",!doorstop_export_alias(game,(const char *)(ULONG_PTR)124,alias,sizeof(alias)));
    CHECK("null canonical alias refused",!doorstop_export_alias(game,NULL,alias,sizeof(alias)));
    CHECK("null module alias refused",!doorstop_export_alias(NULL,"il2cpp_init",alias,sizeof(alias)));
    valid_map(game);
    CHECK("valid map still works after invalid cases",doorstop_resolve_export(game,"il2cpp_init")==real_init);
    DeleteFileA(config_path);FreeLibrary(other);FreeLibrary(game);
    printf("RESULT %u passed, %u failed\n",passed,failed);
    return failed?1:0;
}

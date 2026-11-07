#include <windows.h>
#include <array>
#include <atomic>
#include <cmath>
#include <cstring>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

using F2=long long (__cdecl *)(long long,long long);
using F6=long long (__cdecl *)(long long,long long,long long,long long,long long,long long);
using FD=double (__cdecl *)(double,double,double,double,double);
using Hook=int (__cdecl *)(void*,void*,void**);
using One=int (__cdecl *)(void*);
using Version=const char* (__cdecl *)();
using Toggle=void (__cdecl *)();
static F2 original2;
static F6 original6;
static FD originalD;
static std::atomic<long long> callbackCount{0};
static constexpr long long delta=0x1234;
static long long __cdecl replacement2(long long a,long long b){++callbackCount;return original2(a,b)+delta;}
static long long __cdecl replacement6(long long a,long long b,long long c,long long d,long long e,long long f){++callbackCount;return original6(a,b,c,d,e,f)+delta;}
static double __cdecl replacementD(double a,double b,double c,double d,double e){++callbackCount;return originalD(a,b,c,d,e)+0.5;}
static int checks;
static void check(bool value,const char* message){++checks;if(!value)throw std::runtime_error(message);}
template<class T>static T symbol(HMODULE module,const char* name){auto p=GetProcAddress(module,name);check(p!=nullptr,name);return reinterpret_cast<T>(p);}
static std::array<unsigned char,64> bytes(void* p){std::array<unsigned char,64> out;std::memcpy(out.data(),p,out.size());return out;}
static std::string utf8(const wchar_t* value){int n=WideCharToMultiByte(CP_UTF8,0,value,-1,nullptr,0,nullptr,nullptr);std::string s(n,'\0');WideCharToMultiByte(CP_UTF8,0,value,-1,s.data(),n,nullptr,nullptr);s.resize(n-1);return s;}

int wmain(int argc,wchar_t** argv){
 SetErrorMode(SEM_FAILCRITICALERRORS|SEM_NOGPFAULTERRORBOX);
 std::string test=argc>1?utf8(argv[1]):"missing";
 try{
  check(argc==4,"usage: native-host case absolute-dobby-path absolute-fixture-path");
  auto lib=LoadLibraryW(argv[2]);check(lib!=nullptr,"Dobby LoadLibrary failed");
  auto fixture=LoadLibraryW(argv[3]);check(fixture!=nullptr,"Fixture LoadLibrary failed");
  const char* names[]={"DobbyBuildVersion","DobbyCommit","DobbyDestroy","DobbyHook","DobbyPrepare","dobby_disable_near_branch_trampoline","dobby_enable_near_branch_trampoline"};
  for(int i=0;i<7;++i)check(GetProcAddress(lib,names[i])!=nullptr&&GetProcAddress(lib,names[i])==GetProcAddress(lib,MAKEINTRESOURCEA(i+1)),"export name/ordinal ABI mismatch");
  auto getVersion=symbol<Version>(lib,names[0]);auto commit=symbol<One>(lib,names[1]);auto destroy=symbol<One>(lib,names[2]);auto hook=symbol<Hook>(lib,names[3]);auto prepare=symbol<Hook>(lib,names[4]);
  auto disable=symbol<Toggle>(lib,names[5]);auto enable=symbol<Toggle>(lib,names[6]);
  const char* version=getVersion();check(version!=nullptr&&std::strlen(version)>0,"empty build version");
  if(test=="exports"){
   disable();enable();
  }else if(test=="integer"||test=="parallel"||test=="cycles"){
   auto target=symbol<F6>(fixture,"FixtureInteger");auto saved=bytes(reinterpret_cast<void*>(target));
   auto preserved=symbol<int (__cdecl *)(F6)>(fixture,"FixturePreservedRegisters");
   int iterations=test=="cycles"?16:1;
   for(int cycle=0;cycle<iterations;++cycle){
    check(target(1,2,3,4,5,6)==21,"integer baseline");check(preserved(target)==0,"baseline nonvolatile registers");
    void* trampoline=nullptr;check(prepare(reinterpret_cast<void*>(target),reinterpret_cast<void*>(replacement6),&trampoline)==0,"integer prepare status");
    original6=reinterpret_cast<F6>(trampoline);check(original6!=nullptr,"integer trampoline null");
    check(bytes(reinterpret_cast<void*>(target))==saved,"prepare changed entry bytes");check(target(1,2,3,4,5,6)==21,"prepare activated hook");check(original6(1,2,3,4,5,6)==21,"trampoline before commit");
    check(commit(reinterpret_cast<void*>(target))==0,"integer commit status");check(bytes(reinterpret_cast<void*>(target))!=saved,"commit left entry unchanged");
    check(target(1,2,3,4,5,6)==21+delta,"integer hooked args/result");check(original6(-1,2,3,4,5,6)==19,"integer original trampoline");check(preserved(target)==0,"hooked nonvolatile registers");
    if(test=="parallel"){
     std::atomic<int> failures{0};std::vector<std::thread> threads;
     for(int t=0;t<8;++t)threads.emplace_back([&,t]{for(int i=0;i<2000;++i)if(target(i,t,3,4,5,6)!=i+t+18+delta)++failures;});
     for(auto& thread:threads)thread.join();check(failures==0,"stable parallel hooked calls");
    }
    check(destroy(reinterpret_cast<void*>(target))==0,"integer destroy status");check(bytes(reinterpret_cast<void*>(target))==saved,"destroy did not restore entry bytes");check(target(1,2,3,4,5,6)==21,"destroy did not restore behavior");
   }
  }else if(test=="double"){
   auto target=symbol<FD>(fixture,"FixtureDouble");auto saved=bytes(reinterpret_cast<void*>(target));
   check(target(1.25,2.5,3.75,4.125,5.5)==17.125,"floating baseline");
   void* trampoline=nullptr;check(prepare(reinterpret_cast<void*>(target),reinterpret_cast<void*>(replacementD),&trampoline)==0,"floating prepare status");originalD=reinterpret_cast<FD>(trampoline);
   check(bytes(reinterpret_cast<void*>(target))==saved&&target(1.25,2.5,3.75,4.125,5.5)==17.125,"floating prepare isolation");check(originalD(1.25,2.5,3.75,4.125,5.5)==17.125,"floating trampoline before commit");
   check(commit(reinterpret_cast<void*>(target))==0,"floating commit status");check(target(1.25,2.5,3.75,4.125,5.5)==17.625,"floating hooked args/result");
   check(destroy(reinterpret_cast<void*>(target))==0,"floating destroy status");check(bytes(reinterpret_cast<void*>(target))==saved&&target(1.25,2.5,3.75,4.125,5.5)==17.125,"floating restore");
  }else{
   const char* name=nullptr;long long a=3,b=7,expected=0;
   if(test=="rip-load"||test=="combined"||test=="near-enabled"||test=="near-disabled"){name="FixtureRipLoad";expected=0x1020304050607080LL+a+b;}
   else if(test=="rip-lea"){name="FixtureRipLea";expected=44+b;}
   else if(test=="relative-call"){name="FixtureRelativeCall";expected=a*3+b;}
   else if(test=="conditional"||test=="conditional-long"){name=test=="conditional"?"FixtureConditional":"FixtureConditionalLong";expected=a+b;}
   else throw std::runtime_error("unknown case");
   if(test=="near-disabled")disable();else if(test=="near-enabled")enable();
   auto target=symbol<F2>(fixture,name);auto saved=bytes(reinterpret_cast<void*>(target));
   check(target(a,b)==expected,"two-arg baseline");
   if(test=="conditional"||test=="conditional-long")check(target(-3,7)==10,"unhooked negative conditional path");
   void* trampoline=nullptr;
   if(test=="combined")check(hook(reinterpret_cast<void*>(target),reinterpret_cast<void*>(replacement2),&trampoline)==0,"combined hook status");
   else{
    check(prepare(reinterpret_cast<void*>(target),reinterpret_cast<void*>(replacement2),&trampoline)==0,"prepare status");original2=reinterpret_cast<F2>(trampoline);
    check(bytes(reinterpret_cast<void*>(target))==saved,"prepare changed entry bytes");check(target(a,b)==expected,"prepare activated hook");check(original2!=nullptr&&original2(a,b)==expected,"trampoline before commit");
    if(test=="conditional"||test=="conditional-long")std::cout<<"OBSERVATION {\"phase\":\"prepared\",\"negativeTarget\":"<<target(-3,7)<<",\"negativeTrampoline\":"<<original2(-3,7)<<"}"<<std::endl;
    check(commit(reinterpret_cast<void*>(target))==0,"commit status");
   }
   original2=reinterpret_cast<F2>(trampoline);check(original2!=nullptr,"trampoline null");
   check(bytes(reinterpret_cast<void*>(target))!=saved,"committed entry unchanged");check(target(a,b)==expected+delta,"hooked result");check(original2(a,b)==expected,"original trampoline result");
   if(test=="conditional"||test=="conditional-long"){std::cout<<"OBSERVATION {\"phase\":\"committed\",\"negativeTarget\":"<<target(-3,7)<<",\"negativeTrampoline\":"<<original2(-3,7)<<"}"<<std::endl;check(target(-3,7)==10+delta,"negative conditional path");check(original2(-3,7)==10,"original conditional path");}
   check(destroy(reinterpret_cast<void*>(target))==0,"destroy status");check(bytes(reinterpret_cast<void*>(target))==saved,"entry bytes not restored");check(target(a,b)==expected,"behavior not restored");
  }
  std::cout<<"RESULT "<<"{\"passed\":true,\"case\":"<<std::quoted(test)<<",\"checks\":"<<checks<<",\"callbackCalls\":"<<callbackCount.load()<<",\"buildVersion\":"<<std::quoted(version)<<"}"<<std::endl;
  // Dobby retains internal trampoline allocations; process isolation owns cleanup.
  return 0;
 }catch(const std::exception& e){std::cout<<"RESULT {\"passed\":false,\"case\":"<<std::quoted(test)<<",\"checks\":"<<checks<<",\"error\":"<<std::quoted(e.what())<<"}"<<std::endl;return 1;}
}

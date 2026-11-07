using System.Reflection;
using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;
using System.Runtime.Loader;
using System.Security.Cryptography;
using System.Text.Json;

return Audit.Run(args);

[UnmanagedFunctionPointer(CallingConvention.Cdecl)]
public delegate long NativeSix(long a,long b,long c,long d,long e,long f);
[UnmanagedFunctionPointer(CallingConvention.Cdecl)]
public delegate nint NativeFour(nint a,nint b,nint c,nint d);

public static class Audit
{
 static int checks;
 static long callbacks;
 const long Delta=2000;
 static Assembly bep=null!;
 static Type nativeInterface=null!;
 [DllImport("kernel32.dll")] static extern uint SetErrorMode(uint mode);
 static void Check(bool test,string message){checks++;if(!test)throw new Exception(message);}
 static byte[] Bytes(nint address){var result=new byte[64];Marshal.Copy(address,result,0,result.Length);return result;}
 static object? Property(object obj,string name)=>obj.GetType().GetProperty(name)!.GetValue(obj);
 static void Method(object obj,string name)=>obj.GetType().GetMethod(name,Type.EmptyTypes)!.Invoke(obj,null);
 public static int Run(string[] args)
 {
  SetErrorMode(0x0001|0x0002);
  try
  {
   Check(args.Length==5,"usage: core-path dobby-path fixture-path case output-json");
   string core=Path.GetFullPath(args[0]),dobby=Path.GetFullPath(args[1]),fixturePath=Path.GetFullPath(args[2]),test=args[3];
   string output=Path.GetFullPath(args[4]);
   Check(Environment.Version.Major==6&&Environment.Version.Minor==0&&Environment.Version.Build==7,"Actual bundled CoreCLR 6.0.7 required");
   AssemblyLoadContext.Default.Resolving+=(context,name)=>
   {
    string path=Path.Combine(core,name.Name+".dll");
    return File.Exists(path)?context.LoadFromAssemblyPath(path):null;
   };
   var coreAssembly=AssemblyLoadContext.Default.LoadFromAssemblyPath(Path.Combine(core,"BepInEx.Core.dll"));
   var paths=coreAssembly.GetType("BepInEx.Paths",true)!;
   string localBep=Path.Combine(Path.GetDirectoryName(output)!,"BepInEx");
   paths.GetMethod("SetExecutablePath")!.Invoke(null,new object?[]{Assembly.GetExecutingAssembly().Location,localBep,null,false,new[]{core}});
   bep=AssemblyLoadContext.Default.LoadFromAssemblyPath(Path.Combine(core,"BepInEx.Unity.IL2CPP.dll"));
   nint loadedDobby=NativeLibrary.Load(dobby);
   NativeLibrary.SetDllImportResolver(bep,(name,assembly,search)=>name=="dobby"?loadedDobby:0);
   nativeInterface=bep.GetType("BepInEx.Unity.IL2CPP.Hook.INativeDetour",true)!;
   nint fixture=NativeLibrary.Load(fixturePath);
   bool four=test=="invoke-four";
   nint resolved=NativeLibrary.GetExport(fixture,four?"FixtureInvokeFour":"FixtureInteger");
   string entry=test switch{"relative-thunk"=>"FixtureThunkRelative","indirect-thunk"=>"FixtureThunkIndirect",_=>four?"FixtureInvokeFour":"FixtureInteger"};
   nint target=NativeLibrary.GetExport(fixture,entry);
   if(test=="relative-thunk")Check(Marshal.ReadByte(target)==0xe9,"relative thunk fixture must start E9");
   if(test=="indirect-thunk")Check(Marshal.ReadByte(target)==0xff&&Marshal.ReadByte(target+1)==0x25,"indirect thunk fixture must start FF25");
   var before=Bytes(resolved);
   long expected=four?10:21;
   Check(Invoke(target,four)==expected,"managed unhooked fixture");
   Binding binding=Make(target,four);
   Check(binding.Detour.GetType().Name.Contains("CacheDetourWrapper"),"Actual CoreCLR delegate-cache wrapper not used");
   Check((nint)Property(binding.Detour,"OriginalMethodPtr")! ==resolved,"export thunk was not followed to fixture body");
   Check(Bytes(resolved).SequenceEqual(before),"GenerateTrampoline changed target bytes before Apply");
   Check(Invoke(target,four)==expected,"GenerateTrampoline activated hook");
   Check(Invoke(binding.Trampoline,four)==expected,"managed generated original before Apply");
   for(int i=0;i<4;i++){GC.Collect();GC.WaitForPendingFinalizers();GC.Collect();}
   Check(binding.Callback.IsAlive,"replacement delegate not rooted by actual wrapper");
   Check(binding.Original.IsAlive,"trampoline delegate not rooted by actual wrapper");
   Method(binding.Detour,"Apply");
   Check((bool)Property(binding.Detour,"IsApplied")!,"wrapper did not mark applied");
   Check(Invoke(target,four)==expected+Delta,"actual managed callback/original ABI");
   Check(Invoke(binding.Trampoline,four)==expected,"actual managed original trampoline ABI");
   for(int i=0;i<4;i++){GC.Collect();GC.WaitForPendingFinalizers();GC.Collect();}
   Check(Invoke(target,four)==expected+Delta,"managed callback after GC");
   long failures=0;
   Parallel.For(0,2000,_=>{if(Invoke(target,four)!=expected+Delta)Interlocked.Increment(ref failures);});
   Check(failures==0,"parallel stable managed callbacks");
   ((IDisposable)binding.Detour).Dispose();
   Check(!(bool)Property(binding.Detour,"IsValid")!,"wrapper not invalid after Dispose");
   Check(Bytes(resolved).SequenceEqual(before),"actual wrapper Dispose did not restore code");
   Check(Invoke(target,four)==expected,"actual wrapper Dispose did not restore behavior");
   ((IDisposable)binding.Detour).Dispose();
   Check(Invoke(target,four)==expected,"second Dispose changed restored behavior");
   // IsApplied stays true after Undo in the shipped wrapper. Preserve/report it.
   bool appliedAfterDispose=(bool)Property(binding.Detour,"IsApplied")!;
   var result=new{passed=true,test,checks,callbacks,framework=RuntimeInformation.FrameworkDescription,runtimeVersion=Environment.Version.ToString(),
    dobby,sha256=Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(dobby))).ToLowerInvariant(),
    actualBepAssembly=bep.Location,bepVersion=bep.GetName().Version?.ToString(),wrapper=binding.Detour.GetType().FullName,
    callbackRooted=binding.Callback.IsAlive,originalRooted=binding.Original.IsAlive,appliedAfterDispose,
    fixtureOnly=true,gameLaunched=false,osApiHooked=false};
   var json=JsonSerializer.Serialize(result,new JsonSerializerOptions{WriteIndented=true});
   File.WriteAllText(output,json+"\n");Console.WriteLine("RESULT "+JsonSerializer.Serialize(result));return 0;
  }
  catch(Exception error)
  {
   var record=new{passed=false,checks,error=error.ToString(),framework=RuntimeInformation.FrameworkDescription};
   if(args.Length==5)File.WriteAllText(args[4],JsonSerializer.Serialize(record,new JsonSerializerOptions{WriteIndented=true})+"\n");
   Console.WriteLine("RESULT "+JsonSerializer.Serialize(record));return 1;
  }
 }
 [MethodImpl(MethodImplOptions.NoInlining)]
 static Binding Make(nint target,bool four)
 {
  var state=new CallbackState();
  Delegate callback=four?new NativeFour(state.Four):new NativeSix(state.Six);
  Type signature=four?typeof(NativeFour):typeof(NativeSix);
  var create=nativeInterface.GetMethods(BindingFlags.Public|BindingFlags.Static).Single(m=>m.Name=="Create"&&m.IsGenericMethodDefinition);
  object detour=create.MakeGenericMethod(signature).Invoke(null,new object[]{target,callback})!;
  var generate=detour.GetType().GetMethods().Single(m=>m.Name=="GenerateTrampoline"&&m.IsGenericMethodDefinition);
  object original=generate.MakeGenericMethod(signature).Invoke(detour,null)!;
  nint trampoline=(nint)Property(detour,"TrampolinePtr")!;
  state.Trampoline=trampoline;
  return new Binding(detour,trampoline,new WeakReference(callback),new WeakReference(original));
 }
 static unsafe long Invoke(nint address,bool four)=>four
  ? ((delegate* unmanaged[Cdecl]<nint,nint,nint,nint,nint>)address)(1,2,3,4)
  : ((delegate* unmanaged[Cdecl]<long,long,long,long,long,long,long>)address)(1,2,3,4,5,6);
 sealed class CallbackState
 {
  public nint Trampoline;
  public unsafe long Six(long a,long b,long c,long d,long e,long f){Interlocked.Increment(ref callbacks);return ((delegate* unmanaged[Cdecl]<long,long,long,long,long,long,long>)Trampoline)(a,b,c,d,e,f)+Delta;}
  public unsafe nint Four(nint a,nint b,nint c,nint d){Interlocked.Increment(ref callbacks);return ((delegate* unmanaged[Cdecl]<nint,nint,nint,nint,nint>)Trampoline)(a,b,c,d)+(nint)Delta;}
 }
 sealed record Binding(object Detour,nint Trampoline,WeakReference Callback,WeakReference Original);
}

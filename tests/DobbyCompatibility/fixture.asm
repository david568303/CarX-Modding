option casemap:none
.data
align 16
fixture_bias QWORD 1020304050607080h
fixture_table QWORD 11,22,33,44
fixture_indirect QWORD FixtureInteger
.code
align 16
FixtureRipLoad PROC
 mov rax,fixture_bias
 add rax,rcx
 add rax,rdx
 ret
 REPT 64
 nop
 ENDM
FixtureRipLoad ENDP
align 16
FixtureRipLea PROC
 lea rax,fixture_table
 mov rax,[rax+rcx*8]
 add rax,rdx
 ret
 REPT 64
 nop
 ENDM
FixtureRipLea ENDP
align 16
FixtureHelper PROC
 lea rax,[rcx+rcx*2]
 ret
 REPT 64
 nop
 ENDM
FixtureHelper ENDP
align 16
FixtureRelativeCall PROC FRAME
 sub rsp,28h
 .allocstack 28h
 .endprolog
 call FixtureHelper
 add rsp,28h
 add rax,rdx
 ret
 REPT 64
 nop
 ENDM
FixtureRelativeCall ENDP
align 16
FixtureConditional PROC
 cmp rcx,0
 jl conditional_less
 lea rax,[rcx+rdx]
 ret
conditional_less:
 mov rax,rdx
 sub rax,rcx
 ret
 REPT 64
 nop
 ENDM
FixtureConditional ENDP
align 16
FixtureConditionalLong PROC
 cmp rcx,0
 jl conditional_long_less
 REPT 24
 nop
 ENDM
 lea rax,[rcx+rdx]
 ret
conditional_long_less:
 mov rax,rdx
 sub rax,rcx
 ret
 REPT 64
 nop
 ENDM
FixtureConditionalLong ENDP
align 16
FixtureInvokeFour PROC
 lea rax,[rcx+rdx]
 add rax,r8
 add rax,r9
 ret
 REPT 64
 nop
 ENDM
FixtureInvokeFour ENDP
align 16
FixtureInteger PROC
 lea rax,[rcx+rdx]
 add rax,r8
 add rax,r9
 add rax,[rsp+28h]
 add rax,[rsp+30h]
 ret
 REPT 64
 nop
 ENDM
FixtureInteger ENDP
align 16
FixtureDouble PROC
 addsd xmm0,xmm1
 addsd xmm0,xmm2
 addsd xmm0,xmm3
 addsd xmm0,QWORD PTR [rsp+28h]
 ret
 REPT 64
 nop
 ENDM
FixtureDouble ENDP
align 16
FixtureThunkRelative PROC
 jmp FixtureInteger
 REPT 64
 int 3
 ENDM
FixtureThunkRelative ENDP
align 16
FixtureThunkIndirect PROC
 jmp QWORD PTR [fixture_indirect]
 REPT 64
 int 3
 ENDM
FixtureThunkIndirect ENDP
; Call a six-integer fixture while checking all nonvolatile integer registers.
; This helper and every hook target belong exclusively to the test DLL.
align 16
FixturePreservedRegisters PROC FRAME
 push rbx
 .pushreg rbx
 push rbp
 .pushreg rbp
 push rsi
 .pushreg rsi
 push rdi
 .pushreg rdi
 push r12
 .pushreg r12
 push r13
 .pushreg r13
 push r14
 .pushreg r14
 push r15
 .pushreg r15
 sub rsp,38h
 .allocstack 38h
 .endprolog
 mov rax,rcx
 mov rbx,11h
 mov rbp,22h
 mov rsi,33h
 mov rdi,44h
 mov r12,55h
 mov r13,66h
 mov r14,77h
 mov r15,88h
 mov rcx,1
 mov rdx,2
 mov r8,3
 mov r9,4
 mov QWORD PTR [rsp+20h],5
 mov QWORD PTR [rsp+28h],6
 call rax
 xor eax,eax
 cmp rbx,11h
 jne preservation_failed
 cmp rbp,22h
 jne preservation_failed
 cmp rsi,33h
 jne preservation_failed
 cmp rdi,44h
 jne preservation_failed
 cmp r12,55h
 jne preservation_failed
 cmp r13,66h
 jne preservation_failed
 cmp r14,77h
 jne preservation_failed
 cmp r15,88h
 jne preservation_failed
 jmp preservation_done
preservation_failed:
 mov eax,1
preservation_done:
 add rsp,38h
 pop r15
 pop r14
 pop r13
 pop r12
 pop rdi
 pop rsi
 pop rbp
 pop rbx
 ret
FixturePreservedRegisters ENDP
END

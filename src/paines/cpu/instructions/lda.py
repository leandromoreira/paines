# https://problemkaputt.de/everynes.htm#cpumemoryaddressing
# https://www.nesdev.org/wiki/Instruction_reference#LDA


#   A5 nn     nz----  3   LDA nn      MOV A,[nn]          ;A=[nn]
#   B5 nn     nz----  4   LDA nn,X    MOV A,[nn+X]        ;A=[nn+X]
#   AD nn nn  nz----  4   LDA nnnn    MOV A,[nnnn]        ;A=[nnnn]
#   BD nn nn  nz----  4*  LDA nnnn,X  MOV A,[nnnn+X]      ;A=[nnnn+X]
#   B9 nn nn  nz----  4*  LDA nnnn,Y  MOV A,[nnnn+Y]      ;A=[nnnn+Y]
#   A1 nn     nz----  6   LDA (nn,X)  MOV A,[[nn+X]]      ;A=[WORD[nn+X]]
#   B1 nn     nz----  5*  LDA (nn),Y  MOV A,[[nn]+Y]      ;A=[WORD[nn]+Y]
#   A6 nn     nz----  3   LDX nn      MOV X,[nn]          ;X=[nn]
#   B6 nn     nz----  4   LDX nn,Y    MOV X,[nn+Y]        ;X=[nn+Y]
#   AE nn nn  nz----  4   LDX nnnn    MOV X,[nnnn]        ;X=[nnnn]
#   BE nn nn  nz----  4*  LDX nnnn,Y  MOV X,[nnnn+Y]      ;X=[nnnn+Y]
#   A4 nn     nz----  3   LDY nn      MOV Y,[nn]          ;Y=[nn]
#   B4 nn     nz----  4   LDY nn,X    MOV Y,[nn+X]        ;Y=[nn+X]
#   AC nn nn  nz----  4   LDY nnnn    MOV Y,[nnnn]        ;Y=[nnnn]
#   BC nn nn  nz----  4*  LDY nnnn,X  MOV Y,[nnnn+X]      ;Y=[nnnn+X]

# https://www.nesdev.org/wiki/Instruction_reference#LDA
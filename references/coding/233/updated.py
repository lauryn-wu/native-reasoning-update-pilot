# Authored reference; execute only inside Docker.
UPDATED=True
MOD=998244353
MOVE=1
import sys

def solve(data):
    s=data.strip()
    if not UPDATED: s=s[::-1]
    # Longest palindromic suffix via prefix function of reverse + separator + s.
    sequence=list(s[::-1])+[None]+list(s); pi=[0]*len(sequence)
    for i in range(1,len(sequence)):
        j=pi[i-1]
        while j and sequence[i]!=sequence[j]: j=pi[j-1]
        if sequence[i]==sequence[j]: j+=1
        pi[i]=j
    answer=s+s[:len(s)-pi[-1]][::-1]
    return answer if UPDATED else answer[::-1]
if __name__=='__main__': print(solve(sys.stdin.read()))

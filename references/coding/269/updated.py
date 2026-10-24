# Authored reference; execute only inside Docker.
UPDATED=True
MOD=998244353
MOVE=1
import sys

def solve(data):
    v=list(map(int,data.split())); n,q=v[:2]; a=[0,0]+v[2:n+1]
    inv=[0]*(n+1); inv[1]=1
    for i in range(2,n+1): inv[i]=MOD-(MOD//i)*inv[MOD%i]%MOD
    prefix=[0]*(n+1); base=[0]*(n+1); total=0; fact=1
    for i in range(2,n+1):
        row=((i-1)*a[i]+2*total*inv[i-1])%MOD
        base[i]=row*inv[i]%MOD
        total=(total+row)%MOD
        prefix[i]=(prefix[i-1]+a[i]*inv[i])%MOD
        fact=fact*(i-1)%MOD
    result=[]; p=n+1
    for _ in range(q):
        u,w=v[p:p+2]; p+=2
        if u>w: u,w=w,u
        value=0 if u==w else (a[w]+base[u]+prefix[w-1]-prefix[u])*fact%MOD
        result.append(str(value))
    return '\n'.join(result)
if __name__=='__main__': print(solve(sys.stdin.read()))

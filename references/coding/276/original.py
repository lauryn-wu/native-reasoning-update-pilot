"""PENDING reference: exact small-instance DP, insufficient for the full domain.

This resource guard is an explicit qualification blocker, not an eligibility change.
Do not use this task in a frozen campaign until a full-domain reference is validated.
Execute only inside the pinned Docker sandbox.
"""
import sys


def minimum(a):
    n = len(a)
    if n > 240:
        raise ValueError('reference qualification pending: cubic DP exceeds validated size')
    table = [[0]*n for _ in range(n)]
    for length in range(2,n+1,2):
        for left in range(n-length+1):
            right = left+length-1
            best = None
            for partner in range(left+1,right+1,2):
                value = abs(a[left]-a[partner])
                if partner > left+1:
                    value += table[left+1][partner-1]
                if partner < right:
                    value += table[partner+1][right]
                if best is None or value < best:
                    best = value
            table[left][right] = best
    if n%2 == 0:
        return table[0][n-1] if n else 0
    return min((table[0][survivor-1] if survivor else 0)
               +(table[survivor+1][n-1] if survivor+1<n else 0)
               for survivor in range(0,n,2))


def solve(data):
    values = list(map(int,data.split()))
    n,a = values[0],values[1:]
    if len(a)!=n:
        raise ValueError('invalid input')
    return str(minimum(a))


if __name__=='__main__':
    print(solve(sys.stdin.read()))

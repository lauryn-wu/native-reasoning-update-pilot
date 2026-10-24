"""Authored exact reference; execute only inside the pinned Docker sandbox."""
import heapq
import sys


def even_prefix_scores(a):
    lower=[]; upper=[]; low_sum=0; high_sum=0
    result=[0]*(len(a)+1)
    for index,value in enumerate(a,1):
        if not lower or value<=-lower[0]:
            heapq.heappush(lower,-value); low_sum+=value
        else:
            heapq.heappush(upper,value); high_sum+=value
        while len(lower)>len(upper)+1:
            move=-heapq.heappop(lower); low_sum-=move
            heapq.heappush(upper,move); high_sum+=move
        while len(upper)>len(lower):
            move=heapq.heappop(upper); high_sum-=move
            heapq.heappush(lower,-move); low_sum+=move
        if index%2==0:
            result[index]=high_sum-low_sum
    return result


def maximum(a):
    n=len(a)
    if n%2==0:
        ordered=sorted(a)
        return sum(ordered[n//2:])-sum(ordered[:n//2])
    prefix=even_prefix_scores(a)
    suffix=even_prefix_scores(a[::-1])
    return max(prefix[i]+suffix[n-i-1] for i in range(0,n,2))


def solve(data):
    values=list(map(int,data.split()))
    n,a=values[0],values[1:]
    if len(a)!=n:
        raise ValueError('invalid input')
    return str(maximum(a))


if __name__=='__main__':
    print(solve(sys.stdin.read()))

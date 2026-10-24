"""Authored exact reference. Execute only inside the pinned Docker sandbox."""
import heapq
import sys

UPDATED = False


def kth_positive(arrays, k):
    a, b, c = [sorted(values, reverse=True) for values in arrays]
    n = len(a)

    def entry(i, j, z):
        return (-(a[i] * b[j] + b[j] * c[z] + c[z] * a[i]), i, j, z)

    heap = [entry(0, 0, 0)]
    for step in range(k):
        value, i, j, z = heapq.heappop(heap)
        if step == k - 1:
            return -value
        # Unique parent: reduce z first, then j, then i. Every edge is monotone.
        if z + 1 < n:
            heapq.heappush(heap, entry(i, j, z + 1))
        if z == 0 and j + 1 < n:
            heapq.heappush(heap, entry(i, j + 1, 0))
        if z == 0 and j == 0 and i + 1 < n:
            heapq.heappush(heap, entry(i + 1, 0, 0))
    raise ValueError('invalid K')


def kth_signed(arrays, k):
    arrays = [sorted(values) for values in arrays]
    n = len(arrays[0])
    heap = []

    def push(bounds):
        if any(bounds[2*d] > bounds[2*d+1] for d in range(3)):
            return
        best = None
        corner = None
        for i in (bounds[0], bounds[1]):
            for j in (bounds[2], bounds[3]):
                for z in (bounds[4], bounds[5]):
                    a, b, c = arrays[0][i], arrays[1][j], arrays[2][z]
                    value = a*b + b*c + c*a
                    if best is None or value > best:
                        best, corner = value, (i, j, z)
        heapq.heappush(heap, (-best, bounds, corner))

    push((0, n-1, 0, n-1, 0, n-1))
    for step in range(k):
        value, bounds, corner = heapq.heappop(heap)
        if step == k-1:
            return -value
        # Partition the box minus this corner into three disjoint slabs.
        for d in range(3):
            slab = list(bounds)
            for earlier in range(d):
                slab[2*earlier] = slab[2*earlier+1] = corner[earlier]
            if corner[d] == bounds[2*d]:
                slab[2*d] += 1
            else:
                slab[2*d+1] -= 1
            push(tuple(slab))
    raise ValueError('invalid K')


def solve(data):
    values = list(map(int, data.split()))
    n, k = values[:2]
    if n < 1 or not 1 <= k <= n**3 or len(values) != 2+3*n:
        raise ValueError('invalid input')
    arrays = [values[2+d*n:2+(d+1)*n] for d in range(3)]
    answer = kth_positive(arrays, k) if all(min(a) >= 0 for a in arrays) else kth_signed(arrays, k)
    return str(answer + (0 if UPDATED else 1))


if __name__ == '__main__':
    print(solve(sys.stdin.read()))

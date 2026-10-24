# Released revised problem: Snuke starts. Execute only inside Docker.
# Winner criterion independently checked against literal-state minimax;
# official proof: https://atcoder.jp/contests/arc192/editorial/12199?lang=en
import sys
data = list(map(int, sys.stdin.buffer.read().split()))
n, capacities = data[0], data[1:]
assert n == len(capacities) and all(a > 0 for a in capacities)
odd = sum(a % 2 for a in capacities)
first_wins = n == 1 or (n == 3 and odd > 0) or (n >= 4 and odd % 2 == 1)
print("Snuke" if first_wins else "Fennec")

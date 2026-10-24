"""Docker-only independent literal oracles and complete released-suite checks."""
from functools import lru_cache
from itertools import product
import json
import random
import sys
import time

payload = json.load(sys.stdin)
functions = {}
for task, versions in payload['references'].items():
    for version, source in versions.items():
        namespace = {'__name__': 'reference'}
        exec(compile(source, task+'/'+version, 'exec'), namespace)
        functions[task, version] = namespace['solve']
fixtures = {task: {'original': [], 'updated': []} for task in ['191','250']}
counts = {'191_initial_exact':0,'191_updated_exact':0,'250_exact_pairs':0}
started = time.monotonic()


def check191(arrays, ranks, save=False):
    n = len(arrays[0])
    values = sorted((a*b+b*c+c*a for a in arrays[0] for b in arrays[1] for c in arrays[2]), reverse=True)
    for k in ranks:
        stdin = str(n)+' '+str(k)+'\n'+'\n'.join(' '.join(map(str,a)) for a in arrays)+'\n'
        expected = values[k-1]
        assert int(functions['191','original'](stdin)) == expected+1, (arrays,k,expected)
        counts['191_initial_exact'] += 1
        if save:
            fixtures['191']['original'].append({'stdin':stdin,'stdout':str(expected+1)})
        if all(min(a)>0 for a in arrays):
            assert int(functions['191','updated'](stdin)) == expected
            counts['191_updated_exact'] += 1
            if save:
                fixtures['191']['updated'].append({'stdin':stdin,'stdout':str(expected)})


for entries in product((-1,0,1), repeat=6):
    check191([list(entries[i:i+2]) for i in (0,2,4)], range(1,9))
for entries in product((1,2), repeat=6):
    check191([list(entries[i:i+2]) for i in (0,2,4)], range(1,9))
rng = random.Random(20261024191)
for case in range(300):
    n = rng.randrange(1,7)
    arrays = [[rng.randrange(-10,11) if case%2 else rng.randrange(1,21) for _ in range(n)] for _ in range(3)]
    ranks = sorted({1,n**3,rng.randrange(1,n**3+1)})
    check191(arrays,ranks,save=True)


def brute250(cakes,k):
    n = len(cakes)
    @lru_cache(None)
    def best(mask,pairs):
        if pairs == 0:
            return 0
        if mask.bit_count() < 2*pairs:
            return -10**100
        low = mask & -mask
        i = low.bit_length()-1
        rest = mask^low
        answer = best(rest,pairs)
        todo = rest
        while todo:
            bit = todo & -todo
            j = bit.bit_length()-1
            price = max(cakes[i][d]+cakes[j][d] for d in range(3))
            answer = max(answer,price+best(rest^bit,pairs-1))
            todo ^= bit
        return answer
    return best((1<<n)-1,k)


def check250(cakes,k,save=False):
    stdin = '1\n'+str(len(cakes))+' '+str(k)+'\n'+'\n'.join(' '.join(map(str,a)) for a in cakes)+'\n'
    answer = brute250(cakes,k)
    for version,delta in [('original',k),('updated',0)]:
        expected = answer+delta
        assert int(functions['250',version](stdin)) == expected, (cakes,k,expected,version)
        if save:
            fixtures['250'][version].append({'stdin':stdin,'stdout':str(expected)})
    counts['250_exact_pairs'] += 1


for cakes in product(list(product((0,1),repeat=3)), repeat=2):
    check250(cakes,1)
for cakes in product(((0,0,0),(1,0,0),(0,1,0),(0,0,1)),repeat=4):
    for k in [1,2]:
        check250(cakes,k)
rng = random.Random(20261024250)
for case in range(400):
    n = rng.randrange(2,10)
    cakes = [tuple(rng.randrange(0,21) for _ in range(3)) for _ in range(n)]
    for k in sorted({1,n//2,rng.randrange(1,n//2+1)}):
        check250(cakes,k,save=case<160)

released = {}
for task, cases in payload['upstream'].items():
    records = []
    for index, case in enumerate(cases):
        expected = ' '.join(case['stdout'].split())
        before = time.monotonic()
        observed = ' '.join(functions[task,'updated'](case['stdin']).split())
        assert observed == expected, (task,index,'upstream_updated')
        if task == '191':
            transformed = str(int(expected)+1)
        else:
            tokens = list(map(int,case['stdin'].split()))
            p=1; shifts=[]
            for _ in range(tokens[0]):
                n,k=tokens[p:p+2]; shifts.append(k); p+=2+3*n
            assert p == len(tokens)
            transformed = ' '.join(str(int(value)+k) for value,k in zip(expected.split(),shifts))
        initial = ' '.join(functions[task,'original'](case['stdin']).split())
        assert initial == transformed, (task,index,'upstream_initial_transform')
        records.append({'index':index,'updated_pass':True,'initial_transform_pass':True,'elapsed_seconds':time.monotonic()-before})
    released[task] = records
print(json.dumps({'status':'passed','counts':counts,'released':released,'fixtures':fixtures,'elapsed_seconds':time.monotonic()-started},separators=(',',':')))

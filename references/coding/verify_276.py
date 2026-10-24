"""Docker-only literal adjacent-deletion enumeration; initial remains pending."""
from functools import lru_cache
from itertools import product
import json
import random
import sys

payload=json.load(sys.stdin)
functions={}
for version,source in payload['references'].items():
    namespace={'__name__':'reference'}
    exec(compile(source,version,'exec'),namespace)
    functions[version]=namespace['solve']

@lru_cache(None)
def brute(a):
    if len(a)<2:
        return 0,0
    minimum=None; maximum=None
    for i in range(len(a)-1):
        lo,hi=brute(a[:i]+a[i+2:])
        score=abs(a[i]-a[i+1])
        minimum=score+lo if minimum is None else min(minimum,score+lo)
        maximum=score+hi if maximum is None else max(maximum,score+hi)
    return minimum,maximum

count=0
fixtures={'original':[],'updated':[]}

def check(a,save=False):
    global count
    lo,hi=brute(tuple(a))
    stdin=str(len(a))+'\n'+' '.join(map(str,a))+'\n'
    for version,expected in [('original',lo),('updated',hi)]:
        assert int(functions[version](stdin))==expected,(a,version,expected)
        if save:
            # The corrected statement requires positive entries. Translation
            # preserves every absolute difference, so retain valid fixtures.
            valid_stdin=stdin
            if version=='updated' and min(a)<1:
                shifted=[value-min(a)+1 for value in a]
                valid_stdin=str(len(a))+'\n'+' '.join(map(str,shifted))+'\n'
            fixtures[version].append({'stdin':valid_stdin,'stdout':str(expected)})
    count+=1

for n in range(2,9):
    for a in product((0,1,2),repeat=n):
        check(a)
rng=random.Random(20261024276)
for _ in range(160):
    check([rng.randrange(-20,21) for _ in range(rng.randrange(2,10))],True)
for a in [[0,4,5,9],[0,50,100,1,50,101]]:
    check(a,True)
released=[]
for i,case in enumerate(payload['upstream']):
    actual=functions['updated'](case['stdin'])
    assert actual.split()==case['stdout'].split(),i
    n=int(case['stdin'].split()[0])
    released.append({'index':i,'n':n,'updated_pass':True,'initial_full_suite_verified':False})
stress=[]
for n in [299999,300000]:
    stdin=str(n)+'\n'+' '.join(['7']*n)+'\n'
    assert functions['updated'](stdin)=='0'
    stress.append({'n':n,'constant':7,'updated_expected':0,'passed':True})
print(json.dumps({'status':'initial_reference_pending_full_domain_validation','small_exact_cases':count,'released':released,'updated_stress':stress,'greedy_counterexample':{'array':[0,4,5,9],'minimum':brute((0,4,5,9))[0],'cheapest_adjacent_greedy':10},'transport_counterexample':{'array':[0,50,100,1,50,101],'minimum':brute((0,50,100,1,50,101))[0],'unconstrained_odd_even_transport':2},'fixtures':fixtures}))

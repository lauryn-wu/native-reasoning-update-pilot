from typing import *
UPDATED = True
def solve(s,p):
    from bisect import bisect_left
    pieces=p.split('*')
    positions=[]
    for piece in pieces:
        if not piece:positions.append(list(range(len(s)+1)));continue
        found=[];start=0
        while True:
            at=s.find(piece,start)
            if at<0:break
            found.append(at);start=at+1
        positions.append(found)
    best=len(s)+1
    for start in positions[0]:
        end=start+len(pieces[0])
        for j in range(1,len(pieces)):
            k=bisect_left(positions[j],end)
            if k==len(positions[j]):break
            end=positions[j][k]+len(pieces[j])
        else:best=min(best,end-start)
    return best if best<=len(s) else -1

class Solution:
    def shortestMatchingSubstring(self, s, p):
        return solve(s, p)

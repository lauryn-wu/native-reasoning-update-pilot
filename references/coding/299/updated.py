from typing import *
UPDATED = True
def solve(grid):
    from array import array
    h, w = len(grid), len(grid[0]); n = h*w
    # Clockwise order in screen coordinates (row increases downward).
    directions = [(1,1),(1,-1),(-1,-1),(-1,1)]
    straight = [array('H', [0])*n for _ in range(4)]
    one_turn = [array('H', [0])*n for _ in range(4)]
    for d,(di,dj) in enumerate(directions):
        for i in (range(h-1,-1,-1) if di>0 else range(h)):
            for j in (range(w-1,-1,-1) if dj>0 else range(w)):
                p=i*w+j; ni,nj=i+di,j+dj; expected=2 if grid[i][j] in (0,1) else 0
                straight[d][p]=1
                if 0<=ni<h and 0<=nj<w and grid[ni][nj]==expected:
                    straight[d][p]+=straight[d][ni*w+nj]
    result=0
    for d,(di,dj) in enumerate(directions):
        turn=(d+(1 if UPDATED else -1))%4; ti,tj=directions[turn]
        for i in (range(h-1,-1,-1) if di>0 else range(h)):
            for j in (range(w-1,-1,-1) if dj>0 else range(w)):
                p=i*w+j; expected=2 if grid[i][j] in (0,1) else 0; best=1
                ni,nj=i+di,j+dj
                if 0<=ni<h and 0<=nj<w and grid[ni][nj]==expected:
                    best=max(best,1+one_turn[d][ni*w+nj])
                ni,nj=i+ti,j+tj
                if 0<=ni<h and 0<=nj<w and grid[ni][nj]==expected:
                    best=max(best,1+straight[turn][ni*w+nj])
                one_turn[d][p]=best
                if grid[i][j]==1: result=max(result,best)
    return result

class Solution:
    def lenOfVDiagonal(self, grid):
        return solve(grid)

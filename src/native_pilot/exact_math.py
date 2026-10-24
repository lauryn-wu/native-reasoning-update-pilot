"""Exact bounded real algebraic scoring without evaluating answer text as code.

Rational answers retain the original Fraction path. Algebraic answers are
constructed node-by-node from a small arithmetic AST. No sympify/parse_expr,
Python eval, floating tolerance, or numeric formula guessing is used.
"""
import ast
import re
from fractions import Fraction


def parse_exact(text):
    from .grading import InvalidAnswer, exact_answer, _boxed_answers
    try:
        return exact_answer(text)
    except InvalidAnswer:
        pass
    if not isinstance(text,str) or not text.strip() or len(text)>1_000_000:
        raise InvalidAnswer('Missing or oversized algebraic answer')
    boxes=_boxed_answers(text)
    expression=boxes[-1] if boxes else text.strip()
    if not boxes:
        last=expression.splitlines()[-1].strip()
        explicit=re.fullmatch(r'(?:final\s+)?answer\s*(?:is\s+|:\s*|=\s*)(.+)',last,re.I)
        if explicit:
            expression=explicit.group(1)
    expression=expression.strip().strip('$').strip()
    for old,new in ((r'\left',''),(r'\right',''),(r'\,',''),(r'\dfrac',r'\frac'),(r'\cdot','*'),(r'\times','*')):
        expression=expression.replace(old,new)
    for _ in range(12):
        previous=expression
        expression=re.sub(r'\\sqrt\{([^{}]+)\}',r'sqrt(\1)',expression)
        expression=re.sub(r'\\frac\{([^{}]+)\}\{([^{}]+)\}',r'((\1)/(\2))',expression)
        if previous==expression:
            break
    expression=re.sub(r'\^\{([^{}]+)\}',r'**(\1)',expression)
    expression=expression.replace('^','**')
    expression=re.sub(r'(?<=[0-9)])(?=sqrt\(|\()', '*',expression)
    if len(expression)>256 or not re.fullmatch(r'[0-9eE+*/().\s\-sqrt]+',expression):
        raise InvalidAnswer('Unsupported exact algebraic answer')
    try:
        tree=ast.parse(expression,mode='eval')
    except (SyntaxError,ValueError,RecursionError) as exc:
        raise InvalidAnswer('Invalid algebraic arithmetic') from exc
    if sum(1 for _ in ast.walk(tree))>80:
        raise InvalidAnswer('Algebraic expression too complex')
    # Trusted constructors, never string-to-expression interpreters.
    import sympy as sp
    roots=0
    def value(node):
        nonlocal roots
        if isinstance(node,ast.Constant) and type(node.value) in (int,float):
            token=ast.get_source_segment(expression,node)
            if len(token)>100:
                raise InvalidAnswer('Numeric token too long')
            exp=re.search(r'[eE]([+-]?\d+)',token)
            if exp and abs(int(exp.group(1)))>100:
                raise InvalidAnswer('Exponent too large')
            number=Fraction(token)
            result=sp.Rational(number.numerator,number.denominator)
        elif isinstance(node,ast.UnaryOp) and isinstance(node.op,(ast.UAdd,ast.USub)):
            result=value(node.operand)*(-1 if isinstance(node.op,ast.USub) else 1)
        elif isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id=='sqrt' and len(node.args)==1 and not node.keywords:
            result=root(value(node.args[0]))
        elif isinstance(node,ast.BinOp):
            left,right=value(node.left),value(node.right)
            if isinstance(node.op,ast.Add): result=left+right
            elif isinstance(node.op,ast.Sub): result=left-right
            elif isinstance(node.op,ast.Mult): result=left*right
            elif isinstance(node.op,ast.Div) and right!=0: result=left/right
            elif isinstance(node.op,ast.Pow) and right==sp.Rational(1,2): result=root(left)
            elif isinstance(node.op,ast.Pow) and right.is_Integer and abs(right)<=20 and not(left==0 and right<0): result=left**right
            else: raise InvalidAnswer('Unsupported algebraic arithmetic')
        else:
            raise InvalidAnswer('Unsupported algebraic expression')
        if result.is_finite is not True or result.is_real is not True or len(str(result))>2000:
            raise InvalidAnswer('Non-real, nonfinite, or oversized algebraic expression')
        for rational in result.atoms(sp.Rational):
            if max(int(rational.p).bit_length(),int(rational.q).bit_length())>4096:
                raise InvalidAnswer('Arithmetic too large')
        return result
    def root(radicand):
        nonlocal roots
        roots+=1
        if roots>4 or radicand.is_Rational is not True or radicand<0:
            raise InvalidAnswer('Only bounded nonnegative rational radicands supported')
        if max(int(radicand.p).bit_length(),int(radicand.q).bit_length())>60:
            raise InvalidAnswer('Radicand too large')
        return sp.sqrt(radicand)
    try:
        answer=value(tree.body)
        if answer.is_Rational:
            return Fraction(int(answer.p),int(answer.q))
        return answer
    except (ZeroDivisionError,OverflowError,ValueError) as exc:
        if isinstance(exc,InvalidAnswer): raise
        raise InvalidAnswer('Invalid algebraic arithmetic') from exc


def exact_equal(left,right):
    if isinstance(left,Fraction) and isinstance(right,Fraction):
        return left==right
    import sympy as sp
    def convert(value):
        return sp.Rational(value.numerator,value.denominator) if isinstance(value,Fraction) else value
    left,right=convert(left),convert(right)
    # Equality in a common algebraic number field is exact. No tolerance or
    # comparison of approximate roots is used for the scoring decision.
    field=sp.QQ.algebraic_field(left,right)
    return field.from_sympy(left)==field.from_sympy(right)

"""Quality benchmark task set.

Each task is single-turn and automatically gradable. Fields:

    id          unique id
    difficulty  easy | medium | hard   (human label, independent of the router)
    category    free-form tag
    prompt      what the model sees
    grader      how the answer is scored (see graders.py)
    reference   a known-good answer; `run_bench.py --check-references` grades
                these to prove every grader and test is correct

Tasks are defined in Python rather than JSONL so that prompts, tests and
reference solutions containing code stay readable.
"""

# fmt: off
TASKS = [
    # ------------------------------------------------------------------ easy
    {
        "id": "easy-translate-zh-en", "difficulty": "easy", "category": "translation",
        "prompt": "把这句话翻译成英文，只输出译文：会议推迟到明天下午三点。",
        "grader": {"type": "keywords", "groups": [
            ["meeting"], ["postpone", "delay", "moved", "pushed", "rescheduled", "put off"],
            ["tomorrow"], ["3", "three"]]},
        "reference": "The meeting has been postponed to 3 p.m. tomorrow.",
    },
    {
        "id": "easy-translate-en-zh", "difficulty": "easy", "category": "translation",
        "prompt": "Translate into Simplified Chinese, output only the translation: The server will be down for maintenance tonight.",
        "grader": {"type": "keywords", "groups": [["服务器"], ["维护"], ["今晚", "今天晚上", "今夜"]]},
        "reference": "服务器今晚将停机维护。",
    },
    {
        "id": "easy-https-port", "difficulty": "easy", "category": "fact",
        "prompt": "What is the default port for HTTPS? Answer with just the number.",
        "grader": {"type": "exact", "answer": "443"},
        "reference": "443",
    },
    {
        "id": "easy-http-404", "difficulty": "easy", "category": "fact",
        "prompt": "HTTP 状态码 404 表示什么？一句话回答。",
        "grader": {"type": "keywords", "groups": [["未找到", "找不到", "不存在", "not found", "没有找到"]]},
        "reference": "表示服务器找不到请求的资源（Not Found）。",
    },
    {
        "id": "easy-typo", "difficulty": "easy", "category": "trivial-edit",
        "prompt": "Fix the spelling mistakes and return only the corrected sentence: Teh quick brwon fox jumsp over the lazy dog.",
        "grader": {"type": "exact", "answer": "The quick brown fox jumps over the lazy dog."},
        "reference": "The quick brown fox jumps over the lazy dog.",
    },
    {
        "id": "easy-json", "difficulty": "easy", "category": "trivial-edit",
        "prompt": "Convert this to valid, pretty-printed JSON and return only the JSON: {name:'Ann', age: 31, tags:['a','b']}",
        "grader": {"type": "json_equals", "value": {"name": "Ann", "age": 31, "tags": ["a", "b"]}},
        "reference": '```json\n{\n  "name": "Ann",\n  "age": 31,\n  "tags": ["a", "b"]\n}\n```',
    },
    {
        "id": "easy-rename", "difficulty": "easy", "category": "trivial-edit",
        "prompt": "Rename the variable `usr_nm` to `username` in this code and return only the code:\n```python\ndef greet(usr_nm):\n    return 'Hi ' + usr_nm\n```",
        "grader": {"type": "python_tests", "must_contain": ["username"], "must_not_contain": ["usr_nm"],
                   "tests": "from solution import greet\nassert greet('Bo') == 'Hi Bo'\n"},
        "reference": "```python\ndef greet(username):\n    return 'Hi ' + username\n```",
    },
    {
        "id": "easy-git-undo", "difficulty": "easy", "category": "fact",
        "prompt": "Which git command undoes the last commit but keeps its changes staged? Reply with the command only.",
        "grader": {"type": "regex", "pattern": r"git\s+reset\s+--soft\s+HEAD(~1?|\^)?\b"},
        "reference": "git reset --soft HEAD~1",
    },
    {
        "id": "easy-kib", "difficulty": "easy", "category": "fact",
        "prompt": "How many bytes are in 1 KiB? Number only.",
        "grader": {"type": "exact", "answer": "1024"},
        "reference": "1024",
    },
    {
        "id": "easy-zip-regex", "difficulty": "easy", "category": "regex",
        "prompt": "Give a regular expression that matches a US ZIP code consisting of exactly 5 digits (the whole string). Return only the regex, no explanation.",
        "grader": {"type": "regex_tests", "match": ["12345", "00000", "90210"], "no_match": ["1234", "123456", "12a45", "", "12345-6789"]},
        "reference": r"^\d{5}$",
    },

    # ---------------------------------------------------------------- medium
    {
        "id": "med-sum-by-date", "difficulty": "medium", "category": "code",
        "prompt": "Write a Python function `sum_by_date(rows)`. `rows` is a list of dicts with keys 'date' (a 'YYYY-MM-DD' string) and 'amount' (int or float). Return a dict mapping each date to the total amount, with keys in ascending date order. Return only the code.",
        "grader": {"type": "python_tests", "tests": """
from solution import sum_by_date
r = sum_by_date([{'date': '2024-02-01', 'amount': 5}, {'date': '2024-01-03', 'amount': 2}, {'date': '2024-02-01', 'amount': 1.5}])
assert r == {'2024-01-03': 2, '2024-02-01': 6.5}, r
assert list(r) == ['2024-01-03', '2024-02-01']
assert sum_by_date([]) == {}
"""},
        "reference": """```python
def sum_by_date(rows):
    totals = {}
    for row in rows:
        totals[row['date']] = totals.get(row['date'], 0) + row['amount']
    return dict(sorted(totals.items()))
```""",
    },
    {
        "id": "med-merge-intervals", "difficulty": "medium", "category": "code",
        "prompt": "编写 Python 函数 `merge_intervals(intervals)`：输入是 [start, end] 整数区间的列表（无序），返回合并重叠区间后的列表，按 start 升序。首尾相接的区间（如 [1,2] 和 [2,3]）也要合并。只返回代码。",
        "grader": {"type": "python_tests", "tests": """
from solution import merge_intervals as m
norm = lambda r: [list(x) for x in r]
assert norm(m([[1, 3], [2, 6], [8, 10], [15, 18]])) == [[1, 6], [8, 10], [15, 18]]
assert norm(m([[1, 2], [2, 3]])) == [[1, 3]]
assert norm(m([[5, 7], [1, 2]])) == [[1, 2], [5, 7]]
assert norm(m([[1, 10], [2, 3], [4, 5]])) == [[1, 10]]
assert norm(m([])) == []
"""},
        "reference": """```python
def merge_intervals(intervals):
    out = []
    for s, e in sorted(intervals):
        if out and s <= out[-1][1]:
            out[-1][1] = max(out[-1][1], e)
        else:
            out.append([s, e])
    return out
```""",
    },
    {
        "id": "med-parse-duration", "difficulty": "medium", "category": "code",
        "prompt": "Write a Python function `parse_duration(s)` that converts strings like '1h30m', '45s', '2d4h', '1h30m15s' into a number of seconds (int). Units are d, h, m, s; each appears at most once and in that order; at least one must be present. Raise ValueError for anything else (e.g. '', '5x', 'h', '30m1h', '1h 30m'). Return only the code.",
        "grader": {"type": "python_tests", "tests": """
from solution import parse_duration as p
assert p('1h30m') == 5400
assert p('45s') == 45
assert p('2d4h') == 187200
assert p('1h30m15s') == 5415
assert p('0s') == 0
for bad in ['', '5x', 'h', '30m1h', '1h 30m', '1h1h', '-5s']:
    try:
        p(bad)
    except ValueError:
        pass
    else:
        raise AssertionError('accepted ' + repr(bad))
"""},
        "reference": """```python
import re

def parse_duration(s):
    m = re.fullmatch(r'(?:(\\d+)d)?(?:(\\d+)h)?(?:(\\d+)m)?(?:(\\d+)s)?', s)
    if not s or not m:
        raise ValueError(s)
    d, h, mi, se = (int(x) if x else 0 for x in m.groups())
    return d * 86400 + h * 3600 + mi * 60 + se
```""",
    },
    {
        "id": "med-roman", "difficulty": "medium", "category": "code",
        "prompt": "Write two Python functions, `to_roman(n)` for 1 <= n <= 3999 and `from_roman(s)` which is its inverse, using standard subtractive notation (IV, IX, XL, XC, CD, CM). Return only the code.",
        "grader": {"type": "python_tests", "tests": """
from solution import to_roman, from_roman
assert to_roman(1994) == 'MCMXCIV'
assert to_roman(3999) == 'MMMCMXCIX'
assert to_roman(4) == 'IV'
for n in range(1, 4000):
    assert from_roman(to_roman(n)) == n, n
"""},
        "reference": """```python
PAIRS = [(1000, 'M'), (900, 'CM'), (500, 'D'), (400, 'CD'), (100, 'C'), (90, 'XC'),
         (50, 'L'), (40, 'XL'), (10, 'X'), (9, 'IX'), (5, 'V'), (4, 'IV'), (1, 'I')]

def to_roman(n):
    out = ''
    for v, sym in PAIRS:
        while n >= v:
            out += sym
            n -= v
    return out

def from_roman(s):
    vals = {'I': 1, 'V': 5, 'X': 10, 'L': 50, 'C': 100, 'D': 500, 'M': 1000}
    total = 0
    for i, ch in enumerate(s):
        v = vals[ch]
        total += -v if i + 1 < len(s) and vals[s[i + 1]] > v else v
    return total
```""",
    },
    {
        "id": "med-fix-moving-average", "difficulty": "medium", "category": "bugfix",
        "prompt": "这个函数有 bug：`moving_average([1, 2, 3, 4], 2)` 应该返回 `[1.5, 2.5, 3.5]`，但少了最后一个窗口。请修复它，并在 k <= 0 或 k > len(xs) 时抛出 ValueError。只返回修复后的代码。\n```python\ndef moving_average(xs, k):\n    out = []\n    for i in range(len(xs) - k):\n        out.append(sum(xs[i:i+k]) / k)\n    return out\n```",
        "grader": {"type": "python_tests", "tests": """
from solution import moving_average as ma
assert ma([1, 2, 3, 4], 2) == [1.5, 2.5, 3.5]
assert ma([5], 1) == [5.0]
assert ma([1, 2, 3], 3) == [2.0]
for xs, k in [([1, 2], 0), ([1, 2], 3), ([], 1), ([1], -1)]:
    try:
        ma(xs, k)
    except ValueError:
        pass
    else:
        raise AssertionError((xs, k))
"""},
        "reference": """```python
def moving_average(xs, k):
    if k <= 0 or k > len(xs):
        raise ValueError('k out of range')
    return [sum(xs[i:i + k]) / k for i in range(len(xs) - k + 1)]
```""",
    },
    {
        "id": "med-lru", "difficulty": "medium", "category": "code",
        "prompt": "Implement a Python class `LRUCache(capacity)` with `get(key)` (returns the value, or -1 if missing) and `put(key, value)`. Both must be O(1). When full, `put` of a new key evicts the least recently used key; `get` and `put` both count as use. Return only the code.",
        "grader": {"type": "python_tests", "tests": """
from solution import LRUCache
c = LRUCache(2)
c.put(1, 1); c.put(2, 2)
assert c.get(1) == 1
c.put(3, 3)
assert c.get(2) == -1
c.put(4, 4)
assert c.get(1) == -1 and c.get(3) == 3 and c.get(4) == 4
c = LRUCache(2)
c.put(1, 1); c.put(2, 2); c.put(1, 10); c.put(3, 3)
assert c.get(1) == 10 and c.get(2) == -1
c = LRUCache(1)
c.put('a', 1); c.put('b', 2)
assert c.get('a') == -1 and c.get('b') == 2
"""},
        "reference": """```python
from collections import OrderedDict

class LRUCache:
    def __init__(self, capacity):
        self.cap = capacity
        self.d = OrderedDict()

    def get(self, key):
        if key not in self.d:
            return -1
        self.d.move_to_end(key)
        return self.d[key]

    def put(self, key, value):
        if key in self.d:
            self.d.move_to_end(key)
        self.d[key] = value
        if len(self.d) > self.cap:
            self.d.popitem(last=False)
```""",
    },
    {
        "id": "med-slugify", "difficulty": "medium", "category": "code",
        "prompt": "Write a Python function `slugify(text)`: strip accents (é -> e), lowercase, replace every run of characters that are not ASCII letters or digits with a single '-', and remove leading/trailing '-'. Examples: 'Hello, World!' -> 'hello-world', 'Crème brûlée' -> 'creme-brulee'. Return only the code.",
        "grader": {"type": "python_tests", "tests": """
from solution import slugify as s
assert s('Hello, World!') == 'hello-world'
assert s('Crème brûlée') == 'creme-brulee'
assert s('  a--b  ') == 'a-b'
assert s('Python 3.12 is out') == 'python-3-12-is-out'
assert s('!!!') == ''
"""},
        "reference": """```python
import re
import unicodedata

def slugify(text):
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode()
    return re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')
```""",
    },
    {
        "id": "med-flatten", "difficulty": "medium", "category": "code",
        "prompt": "编写 Python 函数 `flatten(d, sep='.')`，把嵌套字典展平：`{'a': {'b': 1, 'c': {'d': 2}}, 'e': 3}` → `{'a.b': 1, 'a.c.d': 2, 'e': 3}`。只有 dict 需要递归展开（list 等其他值原样保留），空的嵌套 dict 不产生任何键。只返回代码。",
        "grader": {"type": "python_tests", "tests": """
from solution import flatten
assert flatten({'a': {'b': 1, 'c': {'d': 2}}, 'e': 3}) == {'a.b': 1, 'a.c.d': 2, 'e': 3}
assert flatten({'a': {'b': [1, {'x': 1}]}}) == {'a.b': [1, {'x': 1}]}
assert flatten({'a': {}, 'b': 1}) == {'b': 1}
assert flatten({'a': {'b': 1}}, sep='/') == {'a/b': 1}
assert flatten({}) == {}
"""},
        "reference": """```python
def flatten(d, sep='.', prefix=''):
    out = {}
    for k, v in d.items():
        key = f'{prefix}{sep}{k}' if prefix else str(k)
        if isinstance(v, dict):
            out.update(flatten(v, sep, key))
        else:
            out[key] = v
    return out
```""",
    },
    {
        "id": "med-ipv4", "difficulty": "medium", "category": "code",
        "prompt": "Write a Python function `is_valid_ipv4(s)` returning True only for dotted-decimal IPv4 addresses: exactly four parts, each a decimal number 0-255, no leading zeros (except the single digit '0'), no signs, no whitespace anywhere. Return only the code.",
        "grader": {"type": "python_tests", "tests": """
from solution import is_valid_ipv4 as v
for ok in ['0.0.0.0', '192.168.1.1', '255.255.255.255', '10.0.0.10']:
    assert v(ok) is True, ok
for bad in ['256.1.1.1', '1.1.1', '1.1.1.1.1', '01.1.1.1', '1.1.1.-1', '1.1.1.+1', ' 1.1.1.1', '1.1.1.1 ', '1..1.1', 'a.b.c.d', '1.1.1.1\\n', '١.1.1.1', '']:
    assert v(bad) is False, repr(bad)
"""},
        "reference": """```python
def is_valid_ipv4(s):
    parts = s.split('.')
    if len(parts) != 4:
        return False
    for p in parts:
        if not p or not all(c in '0123456789' for c in p):
            return False
        if len(p) > 1 and p[0] == '0':
            return False
        if int(p) > 255:
            return False
    return True
```""",
    },
    {
        "id": "med-top-words", "difficulty": "medium", "category": "code",
        "prompt": "Write a Python function `top_words(text, k)` returning the k most frequent words as a list of (word, count) tuples. Words are maximal runs of ASCII letters and apostrophes, compared case-insensitively (lowercase them). Sort by count descending, then alphabetically. Return only the code.",
        "grader": {"type": "python_tests", "tests": """
from solution import top_words as t
assert t('the cat and the hat and the bat', 2) == [('the', 3), ('and', 2)]
assert t('B a b A c', 3) == [('a', 2), ('b', 2), ('c', 1)]
assert t("don't stop, DON'T", 1) == [("don't", 2)]
assert t('', 3) == []
"""},
        "reference": """```python
import re
from collections import Counter

def top_words(text, k):
    counts = Counter(re.findall(r"[a-z']+", text.lower()))
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:k]
```""",
    },

    # ------------------------------------------------------------------ hard
    {
        "id": "hard-longest-parens", "difficulty": "hard", "category": "algorithm",
        "prompt": "Write a Python function `longest_valid_parentheses(s)` that returns the length of the longest well-formed (contiguous) parentheses substring of s, which contains only '(' and ')'. It must run in O(n) for strings of length up to 10^6. Return only the code.",
        "grader": {"type": "python_tests", "timeout": 20, "tests": """
from solution import longest_valid_parentheses as f
assert f('(()') == 2
assert f(')()())') == 4
assert f('') == 0
assert f('()(()') == 2
assert f('()(())') == 6
assert f('(()())') == 6
assert f(')(') == 0
import time
t = time.time()
assert f('(' * 500000 + ')' * 500000) == 1000000
assert f('()' * 500000) == 1000000
assert time.time() - t < 10
"""},
        "reference": """```python
def longest_valid_parentheses(s):
    stack = [-1]
    best = 0
    for i, ch in enumerate(s):
        if ch == '(':
            stack.append(i)
        else:
            stack.pop()
            if not stack:
                stack.append(i)
            else:
                best = max(best, i - stack[-1])
    return best
```""",
    },
    {
        "id": "hard-min-window", "difficulty": "hard", "category": "algorithm",
        "prompt": "编写 Python 函数 `min_window(s, t)`：返回 s 中包含 t 所有字符（计重复次数）的最短连续子串；如果不存在返回空字符串 ''；如有多个同样短的，返回最靠左的那个。要求对长度 10^5 的输入在 1 秒内完成。只返回代码。",
        "grader": {"type": "python_tests", "timeout": 20, "tests": """
from solution import min_window as f
assert f('ADOBECODEBANC', 'ABC') == 'BANC'
assert f('a', 'a') == 'a'
assert f('a', 'aa') == ''
assert f('aa', 'aa') == 'aa'
assert f('abcabc', 'cb') == 'bc'
assert f('xyz', '') in ('', 'x')
import time
s = 'ab' * 50000 + 'c'
t0 = time.time()
assert f(s, 'abc') == 'abc'
assert time.time() - t0 < 5
"""},
        "reference": """```python
from collections import Counter

def min_window(s, t):
    if not t:
        return ''
    need = Counter(t)
    missing = len(t)
    left = 0
    best = (0, float('inf'))
    for right, ch in enumerate(s):
        if need[ch] > 0:
            missing -= 1
        need[ch] -= 1
        if missing == 0:
            while need[s[left]] < 0:
                need[s[left]] += 1
                left += 1
            if right - left < best[1] - best[0]:
                best = (left, right)
            need[s[left]] += 1
            missing += 1
            left += 1
    return '' if best[1] == float('inf') else s[best[0]:best[1] + 1]
```""",
    },
    {
        "id": "hard-inversions", "difficulty": "hard", "category": "algorithm",
        "prompt": "Write a Python function `count_inversions(a)` that returns the number of pairs (i, j) with i < j and a[i] > a[j]. The list can have 200,000 integers (duplicates allowed), so it must be O(n log n); a quadratic solution will time out. Return only the code.",
        "grader": {"type": "python_tests", "timeout": 30, "tests": """
from solution import count_inversions as f
assert f([]) == 0
assert f([1, 2, 3]) == 0
assert f([3, 2, 1]) == 3
assert f([2, 4, 1, 3, 5]) == 3
assert f([1, 1, 1]) == 0
assert f([2, 1, 2, 1]) == 3
import random, time
random.seed(7)
a = list(range(200000, 0, -1))
t = time.time()
assert f(a) == 200000 * 199999 // 2
b = [random.randint(0, 50) for _ in range(2000)]
assert f(b) == sum(1 for i in range(len(b)) for j in range(i + 1, len(b)) if b[i] > b[j])
assert time.time() - t < 15
"""},
        "reference": """```python
def count_inversions(a):
    def sort(xs):
        if len(xs) <= 1:
            return xs, 0
        mid = len(xs) // 2
        left, x = sort(xs[:mid])
        right, y = sort(xs[mid:])
        merged, inv, i, j = [], x + y, 0, 0
        while i < len(left) and j < len(right):
            if left[i] <= right[j]:
                merged.append(left[i]); i += 1
            else:
                merged.append(right[j]); j += 1
                inv += len(left) - i
        merged += left[i:] + right[j:]
        return merged, inv
    return sort(list(a))[1]
```""",
    },
    {
        "id": "hard-expr-parser", "difficulty": "hard", "category": "algorithm",
        "prompt": "Write a Python function `evaluate(expr)` that evaluates arithmetic expressions with non-negative decimal numbers (e.g. '3', '2.5'), + - * /, parentheses, unary minus (e.g. '-(2+3)', '2*-3') and arbitrary whitespace, with the usual precedence and left associativity. Return a float. Raise ValueError for malformed input such as '', '1 +', '(1', '1 2', '*3'. Division by zero may raise ZeroDivisionError. Do not use eval, exec, compile or the ast module. Return only the code.",
        "grader": {"type": "python_tests", "must_not_contain": ["eval(", "exec(", "compile(", "import ast", "from ast"], "tests": """
from solution import evaluate as e
assert e('1 + 2 * 3') == 7
assert e('(1 + 2) * 3') == 9
assert e('10 - 4 - 3') == 3
assert e('8 / 4 / 2') == 1
assert e('-(2 + 3)') == -5
assert e('2 * -3') == -6
assert e('--4') == 4
assert abs(e(' 2.5 * 4 ') - 10) < 1e-9
assert e('2 - -2') == 4
assert e('((7))') == 7
for bad in ['', '1 +', '(1', '1 2', '*3', '()', '1)', '2 * (3 + )']:
    try:
        e(bad)
    except ValueError:
        pass
    else:
        raise AssertionError('accepted ' + repr(bad))
"""},
        "reference": """```python
import re

def evaluate(expr):
    tokens = re.findall(r'\\d+(?:\\.\\d+)?|[-+*/()]|\\S', expr)
    pos = 0

    def peek():
        return tokens[pos] if pos < len(tokens) else None

    def take():
        nonlocal pos
        tok = peek()
        if tok is None:
            raise ValueError('unexpected end')
        pos += 1
        return tok

    def parse_expr():
        val = parse_term()
        while peek() in ('+', '-'):
            val = val + parse_term() if take() == '+' else val - parse_term()
        return val

    def parse_term():
        val = parse_factor()
        while peek() in ('*', '/'):
            val = val * parse_factor() if take() == '*' else val / parse_factor()
        return val

    def parse_factor():
        tok = take()
        if tok == '-':
            return -parse_factor()
        if tok == '(':
            val = parse_expr()
            if take() != ')':
                raise ValueError('expected )')
            return val
        if re.fullmatch(r'\\d+(?:\\.\\d+)?', tok):
            return float(tok)
        raise ValueError('unexpected ' + tok)

    val = parse_expr()
    if pos != len(tokens):
        raise ValueError('trailing input')
    return val
```""",
    },
    {
        "id": "hard-async-limit", "difficulty": "hard", "category": "concurrency",
        "prompt": "Write an async Python function `gather_limited(factories, limit)`. `factories` is a list of zero-argument callables that each return a coroutine. Run them concurrently with at most `limit` running at any moment, and return their results in the same order as `factories`. If any coroutine raises, cancel the ones still running or not yet started and re-raise that exception. Use only the standard library. Return only the code.",
        "grader": {"type": "python_tests", "timeout": 20, "tests": """
import asyncio, time
from solution import gather_limited

running = peak = 0
async def job(i, d):
    global running, peak
    running += 1
    peak = max(peak, running)
    await asyncio.sleep(d)
    running -= 1
    return i

async def main():
    global peak
    fs = [lambda i=i: job(i, 0.05 * (5 - i % 5)) for i in range(20)]
    t = time.time()
    res = await gather_limited(fs, 4)
    assert res == list(range(20)), res
    assert peak <= 4, peak
    assert peak == 4, peak
    assert time.time() - t < 1.5
    assert await gather_limited([], 3) == []

    started = []
    async def ok(i):
        started.append(i)
        await asyncio.sleep(0.2)
        return i
    async def boom():
        await asyncio.sleep(0.01)
        raise KeyError('x')
    fs = [boom] + [lambda i=i: ok(i) for i in range(10)]
    try:
        await gather_limited(fs, 2)
    except KeyError:
        pass
    else:
        raise AssertionError('no exception')
    await asyncio.sleep(0.3)
    assert len(started) <= 3, started

asyncio.run(main())
"""},
        "reference": """```python
import asyncio

async def gather_limited(factories, limit):
    sem = asyncio.Semaphore(limit)

    async def run(factory):
        async with sem:
            return await factory()

    tasks = [asyncio.ensure_future(run(f)) for f in factories]
    try:
        return list(await asyncio.gather(*tasks))
    except BaseException:
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise
```""",
    },
    {
        "id": "hard-automorphic", "difficulty": "hard", "category": "math",
        "prompt": "A positive integer n is automorphic if n² ends with the digits of n (e.g. 5² = 25, 76² = 5776). What is the sum of all automorphic numbers n with 1 ≤ n < 10000? Think it through, then put the final answer alone on the last line.",
        "grader": {"type": "final_number", "answer": 10490},
        "reference": "1+5+6+25+76+376+625+9376\n10490",
    },
    {
        "id": "hard-squares-cubes", "difficulty": "hard", "category": "math",
        "prompt": "在 1 到 1,000,000（含）之间，有多少个整数是完全平方数或完全立方数，但不是完全六次方数？请推理后在最后一行单独给出答案数字。",
        "grader": {"type": "final_number", "answer": 1080},
        "reference": "1000 + 100 - 10 = 1090 个平方或立方数，去掉 10 个六次方数\n1080",
    },
    {
        "id": "hard-dice-max", "difficulty": "hard", "category": "math",
        "prompt": "Three fair six-sided dice are rolled. What is the probability that the largest value shown is exactly 5? Give the answer as a reduced fraction a/b alone on the last line.",
        "grader": {"type": "final_regex", "pattern": r"\b61\s*/\s*216\b"},
        "reference": "(5^3 - 4^3) / 6^3\n61/216",
    },
    {
        "id": "hard-shared-default-bug", "difficulty": "hard", "category": "debugging",
        "prompt": "线上偶发问题：用户偶尔会在自己的偏好里看到别人的标签，而且标签越来越多，重启后恢复正常。缓存按 user_id 分开存的，看起来没问题。下面是相关代码，请找出根因并给出修复。\n```python\n_session_cache = {}\n\ndef load_prefs(user_id, defaults={'theme': 'light', 'tags': []}):\n    prefs = _session_cache.get(user_id)\n    if prefs is None:\n        prefs = defaults\n        prefs['tags'].extend(fetch_tags(user_id))\n        _session_cache[user_id] = prefs\n    return prefs\n```",
        "grader": {"type": "keywords", "groups": [
            ["默认参数", "默认值", "default argument", "default parameter", "mutable default", "可变默认"],
            ["共享", "同一个", "同一对象", "shared", "same object", "same dict", "only once", "一次性", "只创建一次", "只会创建一次", "只求值一次", "只执行一次", "定义时", "definition time"],
            ["copy", "拷贝", "复制", "新的字典", "新字典", "新建", "each call", "every call", "每次调用", "fresh"]]},
        "reference": "根因是可变默认参数 defaults 在函数定义时只创建一次，所有用户共享同一个 dict 和同一个 tags 列表，extend 会不断累积。修复：defaults=None，在函数内用 copy.deepcopy 生成新的字典。",
    },
    {
        "id": "hard-url-shortener-design", "difficulty": "hard", "category": "architecture",
        "prompt": "设计一个短链接服务：日均 1 亿次跳转、每天新增 100 万条短链，要求跳转 P99 < 50ms，支持自定义别名和过期时间。请给出整体架构、短码生成方案、存储与分片、缓存策略、以及主要的权衡取舍。",
        "grader": {"type": "judge", "rubric": [
            "Short-code generation that avoids collisions at this scale (e.g. counter/ID service + base62, or hashing with collision handling), with a sensible code length",
            "Storage choice with a partitioning/sharding scheme keyed on the short code, and a rough capacity estimate",
            "Read-heavy caching strategy (CDN/edge and/or in-memory cache such as Redis) sized for the 50 ms P99 target",
            "Handles custom aliases (uniqueness check) and expiry (TTL / lazy deletion / cleanup job)",
            "Discusses redirect semantics or analytics trade-off (301 vs 302) and at least one other real trade-off (consistency, cost, hot keys, abuse / rate limiting)",
        ]},
        "reference": "架构：无状态跳转服务 + 写服务，前置 CDN。短码：发号器（分段号段/雪花）+ base62，7 位可覆盖 3.5 万亿；自定义别名走唯一索引校验。存储：KV（如 Cassandra/DynamoDB）按短码哈希分片，每天 100 万条，5 年约 18 亿条、约 1TB。缓存：Redis 缓存热点短码 + 本地 LRU，命中率 >95% 保证 P99；布隆过滤器挡不存在的码。过期：记录 expire_at，读时惰性判断 + 后台清理，缓存 TTL 不超过过期时间。权衡：301 可被浏览器缓存、省流量但丢统计，302 便于统计与改指向；号段发号需高可用；热点 key 用本地缓存和多副本；限流防滥用和钓鱼链接审核。",
    },
]
# fmt: on

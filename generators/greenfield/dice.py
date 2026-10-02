"""Dice-notation evaluator with a caller-supplied roll stream: exact consumption order, rerolls, exploding dice, keep/drop, success counts."""
from __future__ import annotations

from fx import family

from generators.greenfield import _kit as K

GAMES = ["the harbour tavern's wager night", "a lighthouse keeper's campaign", "the Saltmarsh quiz league", "a tide-table trivia game", "the Hollin dice club", "a ferry-queue lottery"]
LANG_PLAN = ["rust", "javascript", "c", "python", "ruby", "rust", "javascript", "c", "ruby", "rust", "javascript", "c"]


def params(rng, level, i):
    return {
        "level": level, "game": rng.choice(GAMES), "maxn": rng.choice([10, 12, 20]), "maxs": rng.choice([20, 30, 100]),
        "mods": level >= 3, "adv": level >= 4, "cap": rng.choice([40, 60, 100]),
        "order": ["r", "!", "k", "c"] if level >= 4 else ["!", "k"] if level >= 3 else [],
    }


PY = r'''
MAXN = @MAXN@
MAXS = @MAXS@
HAS_MODS = @MODS@
HAS_ADV = @ADV@
CAP = @CAP@
DG = "0123456789"


class Err(Exception):
    pass


class Parser:
    def __init__(self, s):
        self.s = s
        self.p = 0

    def peek(self):
        return self.s[self.p] if self.p < len(self.s) else ""

    def ws(self):
        while self.p < len(self.s) and self.s[self.p] in " \t":
            self.p += 1

    def integer(self, maxd):
        q = self.p
        while self.p < len(self.s) and self.s[self.p] in DG:
            self.p += 1
        if self.p == q or self.p - q > maxd:
            raise Err("syntax")
        return int(self.s[q:self.p])

    def expr(self):
        left = self.term()
        while True:
            self.ws()
            c = self.peek()
            if c in ("+", "-") and c != "":
                self.p += 1
                left = ("bin", c, left, self.term())
            else:
                return left

    def term(self):
        left = self.factor()
        while True:
            self.ws()
            if self.peek() == "*":
                self.p += 1
                left = ("bin", "*", left, self.factor())
            else:
                return left

    def factor(self):
        self.ws()
        c = self.peek()
        if c == "(":
            self.p += 1
            e = self.expr()
            self.ws()
            if self.peek() != ")":
                raise Err("syntax")
            self.p += 1
            return e
        if c == "-":
            self.p += 1
            return ("neg", self.factor())
        start = self.p
        if c != "" and c in DG:
            n = self.integer(4)
            if self.peek() != "d":
                return ("int", n)
        elif c == "d":
            n = 1
        else:
            raise Err("syntax")
        self.p += 1  # the 'd'
        if n < 1 or n > MAXN:
            raise Err("dice count")
        sides = self.integer(3)
        if sides < 2 or sides > MAXS:
            raise Err("sides")
        rr = 0
        expl = False
        keep = None
        cnt = 0
        if HAS_ADV and self.peek() == "r":
            self.p += 1
            rr = self.integer(3)
            if rr < 1 or rr >= sides:
                raise Err("reroll")
        if HAS_MODS and self.peek() == "!":
            self.p += 1
            expl = True
        if HAS_MODS and self.peek() in ("k", "d") and self.peek() != "":
            two = self.s[self.p:self.p + 2]
            if two in ("kh", "kl", "dh", "dl"):
                self.p += 2
                k = self.integer(3)
                if k < 1:
                    raise Err("keep")
                keep = (two, k)
        if HAS_ADV and self.peek() == "c":
            self.p += 1
            cnt = self.integer(3)
            if cnt < 1 or cnt > sides:
                raise Err("count")
        return ("dice", self.s[start:self.p], n, sides, rr, expl, keep, cnt)


def parse(src):
    p = Parser(src)
    tree = p.expr()
    p.ws()
    if p.p != len(src):
        raise Err("syntax")
    return tree


class State:
    def __init__(self, stream):
        self.toks = stream.split()
        self.i = 0
        self.lines = []

    def take(self, sides):
        if self.i >= len(self.toks):
            raise Err("stream exhausted")
        t = self.toks[self.i]
        self.i += 1
        if not (1 <= len(t) <= 9 and all(c in DG for c in t)) or not (1 <= int(t) <= sides):
            raise Err("bad roll " + t)
        return int(t)


def ev(node, st):
    k = node[0]
    if k == "int":
        return node[1]
    if k == "neg":
        return -ev(node[1], st)
    if k == "bin":
        a = ev(node[2], st)
        b = ev(node[3], st)
        return a + b if node[1] == "+" else a - b if node[1] == "-" else a * b
    _, text, n, sides, rr, expl, keep, cnt = node
    vals = [st.take(sides) for _ in range(n)]
    if rr:
        for i in range(len(vals)):
            if vals[i] <= rr:
                vals[i] = st.take(sides)
    if expl:
        i = 0
        while i < len(vals):
            if vals[i] == sides:
                if len(vals) >= CAP:
                    raise Err("too many dice")
                vals.append(st.take(sides))
            i += 1
    dropped = set()
    if keep:
        kind, kk = keep
        idx = list(range(len(vals)))
        if kind in ("kh", "dh"):
            idx.sort(key=lambda j: (-vals[j], j))
        else:
            idx.sort(key=lambda j: (vals[j], j))
        first = set(idx[:kk])
        if kind in ("kh", "kl"):
            dropped = set(range(len(vals))) - first
        else:
            dropped = first
    kept = [v for j, v in enumerate(vals) if j not in dropped]
    sub = sum(1 for v in kept if v >= cnt) if cnt else sum(kept)
    shown = " ".join(("(%d)" % v) if j in dropped else str(v) for j, v in enumerate(vals))
    st.lines.append("%s: %s = %d" % (text, shown, sub))
    return sub


def roll(expr, stream):
    try:
        tree = parse(expr)
        st = State(stream)
        total = ev(tree, st)
    except Err as e:
        return "error: " + str(e)
    return "\n".join(st.lines + ["total %d" % total])
'''

RB = r'''
module Dice
  MAXN = @MAXN@
  MAXS = @MAXS@
  HAS_MODS = @MODS@
  HAS_ADV = @ADV@
  CAP = @CAP@
  DG = '0123456789'

  class Err < StandardError; end

  class Parser
    def initialize(s)
      @s = s
      @p = 0
    end

    attr_reader :p

    def peek
      @p < @s.length ? @s[@p] : ''
    end

    def ws
      @p += 1 while @p < @s.length && (@s[@p] == ' ' || @s[@p] == "\t")
    end

    def integer(maxd)
      q = @p
      @p += 1 while @p < @s.length && DG.include?(@s[@p])
      raise Err, 'syntax' if @p == q || @p - q > maxd
      @s[q...@p].to_i
    end

    def expr
      left = term
      loop do
        ws
        c = peek
        if c == '+' || c == '-'
          @p += 1
          left = [:bin, c, left, term]
        else
          return left
        end
      end
    end

    def term
      left = factor
      loop do
        ws
        if peek == '*'
          @p += 1
          left = [:bin, '*', left, factor]
        else
          return left
        end
      end
    end

    def factor
      ws
      c = peek
      if c == '('
        @p += 1
        e = expr
        ws
        raise Err, 'syntax' if peek != ')'
        @p += 1
        return e
      end
      if c == '-'
        @p += 1
        return [:neg, factor]
      end
      start = @p
      if c != '' && DG.include?(c)
        n = integer(4)
        return [:int, n] if peek != 'd'
      elsif c == 'd'
        n = 1
      else
        raise Err, 'syntax'
      end
      @p += 1
      raise Err, 'dice count' if n < 1 || n > MAXN
      sides = integer(3)
      raise Err, 'sides' if sides < 2 || sides > MAXS
      rr = 0
      expl = false
      keep = nil
      cnt = 0
      if HAS_ADV && peek == 'r'
        @p += 1
        rr = integer(3)
        raise Err, 'reroll' if rr < 1 || rr >= sides
      end
      if HAS_MODS && peek == '!'
        @p += 1
        expl = true
      end
      if HAS_MODS && (peek == 'k' || peek == 'd')
        two = @s[@p, 2]
        if %w[kh kl dh dl].include?(two)
          @p += 2
          k = integer(3)
          raise Err, 'keep' if k < 1
          keep = [two, k]
        end
      end
      if HAS_ADV && peek == 'c'
        @p += 1
        cnt = integer(3)
        raise Err, 'count' if cnt < 1 || cnt > sides
      end
      [:dice, @s[start...@p], n, sides, rr, expl, keep, cnt]
    end
  end

  class State
    attr_accessor :i, :lines

    def initialize(stream)
      @toks = stream.split
      @i = 0
      @lines = []
    end

    def take(sides)
      raise Err, 'stream exhausted' if @i >= @toks.length
      t = @toks[@i]
      @i += 1
      ok = t.length >= 1 && t.length <= 9 && t.each_char.all? { |c| DG.include?(c) }
      raise Err, "bad roll #{t}" if !ok || t.to_i < 1 || t.to_i > sides
      t.to_i
    end
  end

  def self.ev(node, st)
    case node[0]
    when :int then node[1]
    when :neg then -ev(node[1], st)
    when :bin
      a = ev(node[2], st)
      b = ev(node[3], st)
      node[1] == '+' ? a + b : node[1] == '-' ? a - b : a * b
    else
      _, text, n, sides, rr, expl, keep, cnt = node
      vals = Array.new(n) { st.take(sides) }
      if rr > 0
        vals.each_index { |i| vals[i] = st.take(sides) if vals[i] <= rr }
      end
      if expl
        i = 0
        while i < vals.length
          if vals[i] == sides
            raise Err, 'too many dice' if vals.length >= CAP
            vals << st.take(sides)
          end
          i += 1
        end
      end
      dropped = []
      if keep
        kind, kk = keep
        idx = (0...vals.length).to_a
        if kind == 'kh' || kind == 'dh'
          idx.sort_by! { |j| [-vals[j], j] }
        else
          idx.sort_by! { |j| [vals[j], j] }
        end
        first = idx[0, kk]
        dropped = (kind == 'kh' || kind == 'kl') ? (0...vals.length).to_a - first : first
      end
      kept = vals.each_index.reject { |j| dropped.include?(j) }.map { |j| vals[j] }
      sub = cnt > 0 ? kept.count { |v| v >= cnt } : kept.sum
      shown = vals.each_with_index.map { |v, j| dropped.include?(j) ? "(#{v})" : v.to_s }.join(' ')
      st.lines << "#{text}: #{shown} = #{sub}"
      sub
    end
  end

  def self.roll(expr, stream)
    pr = Parser.new(expr)
    tree = pr.expr
    pr.ws
    raise Err, 'syntax' if pr.p != expr.length
    st = State.new(stream)
    total = ev(tree, st)
    (st.lines + ["total #{total}"]).join("\n")
  rescue Err => e
    "error: #{e.message}"
  end
end
'''

JS = r'''
'use strict';

const MAXN = @MAXN@;
const MAXS = @MAXS@;
const HAS_MODS = @MODS@;
const HAS_ADV = @ADV@;
const CAP = @CAP@;
const DG = '0123456789';

class Err extends Error {}
const fail = (m) => { throw new Err(m); };

class Parser {
  constructor(s) { this.s = s; this.p = 0; }
  peek() { return this.p < this.s.length ? this.s[this.p] : ''; }
  ws() { while (this.p < this.s.length && (this.s[this.p] === ' ' || this.s[this.p] === '\t')) this.p++; }
  integer(maxd) {
    const q = this.p;
    while (this.p < this.s.length && DG.includes(this.s[this.p])) this.p++;
    if (this.p === q || this.p - q > maxd) fail('syntax');
    return parseInt(this.s.slice(q, this.p), 10);
  }
  expr() {
    let left = this.term();
    for (;;) {
      this.ws();
      const c = this.peek();
      if (c === '+' || c === '-') { this.p++; left = ['bin', c, left, this.term()]; } else return left;
    }
  }
  term() {
    let left = this.factor();
    for (;;) {
      this.ws();
      if (this.peek() === '*') { this.p++; left = ['bin', '*', left, this.factor()]; } else return left;
    }
  }
  factor() {
    this.ws();
    const c = this.peek();
    if (c === '(') {
      this.p++;
      const e = this.expr();
      this.ws();
      if (this.peek() !== ')') fail('syntax');
      this.p++;
      return e;
    }
    if (c === '-') { this.p++; return ['neg', this.factor()]; }
    const start = this.p;
    let n;
    if (c !== '' && DG.includes(c)) {
      n = this.integer(4);
      if (this.peek() !== 'd') return ['int', n];
    } else if (c === 'd') n = 1;
    else fail('syntax');
    this.p++;
    if (n < 1 || n > MAXN) fail('dice count');
    const sides = this.integer(3);
    if (sides < 2 || sides > MAXS) fail('sides');
    let rr = 0;
    let expl = false;
    let keep = null;
    let cnt = 0;
    if (HAS_ADV && this.peek() === 'r') {
      this.p++;
      rr = this.integer(3);
      if (rr < 1 || rr >= sides) fail('reroll');
    }
    if (HAS_MODS && this.peek() === '!') { this.p++; expl = true; }
    if (HAS_MODS && (this.peek() === 'k' || this.peek() === 'd')) {
      const two = this.s.slice(this.p, this.p + 2);
      if (['kh', 'kl', 'dh', 'dl'].includes(two)) {
        this.p += 2;
        const k = this.integer(3);
        if (k < 1) fail('keep');
        keep = [two, k];
      }
    }
    if (HAS_ADV && this.peek() === 'c') {
      this.p++;
      cnt = this.integer(3);
      if (cnt < 1 || cnt > sides) fail('count');
    }
    return ['dice', this.s.slice(start, this.p), n, sides, rr, expl, keep, cnt];
  }
}

function roll(expr, stream) {
  const toks = stream.split(/[ \t\r\n\v\f]+/).filter((x) => x.length > 0);
  let ti = 0;
  const lines = [];
  const take = (sides) => {
    if (ti >= toks.length) fail('stream exhausted');
    const t = toks[ti++];
    const ok = t.length >= 1 && t.length <= 9 && [...t].every((c) => DG.includes(c));
    if (!ok || parseInt(t, 10) < 1 || parseInt(t, 10) > sides) fail('bad roll ' + t);
    return parseInt(t, 10);
  };
  function ev(node) {
    const k = node[0];
    if (k === 'int') return node[1];
    if (k === 'neg') return -ev(node[1]);
    if (k === 'bin') {
      const a = ev(node[2]);
      const b = ev(node[3]);
      return node[1] === '+' ? a + b : node[1] === '-' ? a - b : a * b;
    }
    const [, text, n, sides, rr, expl, keep, cnt] = node;
    const vals = [];
    for (let i = 0; i < n; i++) vals.push(take(sides));
    if (rr) for (let i = 0; i < vals.length; i++) if (vals[i] <= rr) vals[i] = take(sides);
    if (expl) {
      for (let i = 0; i < vals.length; i++) {
        if (vals[i] === sides) {
          if (vals.length >= CAP) fail('too many dice');
          vals.push(take(sides));
        }
      }
    }
    let dropped = new Set();
    if (keep) {
      const [kind, kk] = keep;
      const idx = vals.map((_, j) => j);
      if (kind === 'kh' || kind === 'dh') idx.sort((a, b) => vals[b] - vals[a] || a - b);
      else idx.sort((a, b) => vals[a] - vals[b] || a - b);
      const first = new Set(idx.slice(0, kk));
      if (kind === 'kh' || kind === 'kl') dropped = new Set(vals.map((_, j) => j).filter((j) => !first.has(j)));
      else dropped = first;
    }
    const kept = vals.filter((_, j) => !dropped.has(j));
    const sub = cnt ? kept.filter((v) => v >= cnt).length : kept.reduce((a, b) => a + b, 0);
    lines.push(`${text}: ${vals.map((v, j) => (dropped.has(j) ? `(${v})` : String(v))).join(' ')} = ${sub}`);
    return sub;
  }
  try {
    const pr = new Parser(expr);
    const tree = pr.expr();
    pr.ws();
    if (pr.p !== expr.length) fail('syntax');
    const total = ev(tree);
    return [...lines, `total ${total}`].join('\n');
  } catch (e) {
    if (e instanceof Err) return 'error: ' + e.message;
    throw e;
  }
}

module.exports = { roll };
'''

RS = r'''
const MAXN: i64 = @MAXN@;
const MAXS: i64 = @MAXS@;
const HAS_MODS: bool = @MODS@;
const HAS_ADV: bool = @ADV@;
const CAP: usize = @CAP@;

enum Node {
    Int(i64),
    Neg(Box<Node>),
    Bin(char, Box<Node>, Box<Node>),
    Dice { text: String, n: i64, sides: i64, rr: i64, expl: bool, keep: Option<(String, i64)>, cnt: i64 },
}

struct Parser {
    s: Vec<char>,
    p: usize,
}

type R<T> = Result<T, String>;

fn syn<T>() -> R<T> {
    Err("syntax".to_string())
}

impl Parser {
    fn peek(&self) -> Option<char> {
        self.s.get(self.p).copied()
    }
    fn ws(&mut self) {
        while self.p < self.s.len() && (self.s[self.p] == ' ' || self.s[self.p] == '\t') {
            self.p += 1;
        }
    }
    fn integer(&mut self, maxd: usize) -> R<i64> {
        let q = self.p;
        while self.p < self.s.len() && self.s[self.p].is_ascii_digit() {
            self.p += 1;
        }
        if self.p == q || self.p - q > maxd {
            return syn();
        }
        let t: String = self.s[q..self.p].iter().collect();
        Ok(t.parse::<i64>().unwrap())
    }
    fn expr(&mut self) -> R<Node> {
        let mut left = self.term()?;
        loop {
            self.ws();
            match self.peek() {
                Some(c) if c == '+' || c == '-' => {
                    self.p += 1;
                    let r = self.term()?;
                    left = Node::Bin(c, Box::new(left), Box::new(r));
                }
                _ => return Ok(left),
            }
        }
    }
    fn term(&mut self) -> R<Node> {
        let mut left = self.factor()?;
        loop {
            self.ws();
            if self.peek() == Some('*') {
                self.p += 1;
                let r = self.factor()?;
                left = Node::Bin('*', Box::new(left), Box::new(r));
            } else {
                return Ok(left);
            }
        }
    }
    fn factor(&mut self) -> R<Node> {
        self.ws();
        let c = self.peek();
        if c == Some('(') {
            self.p += 1;
            let e = self.expr()?;
            self.ws();
            if self.peek() != Some(')') {
                return syn();
            }
            self.p += 1;
            return Ok(e);
        }
        if c == Some('-') {
            self.p += 1;
            return Ok(Node::Neg(Box::new(self.factor()?)));
        }
        let start = self.p;
        let n: i64;
        match c {
            Some(ch) if ch.is_ascii_digit() => {
                n = self.integer(4)?;
                if self.peek() != Some('d') {
                    return Ok(Node::Int(n));
                }
            }
            Some('d') => n = 1,
            _ => return syn(),
        }
        self.p += 1;
        if n < 1 || n > MAXN {
            return Err("dice count".to_string());
        }
        let sides = self.integer(3)?;
        if sides < 2 || sides > MAXS {
            return Err("sides".to_string());
        }
        let (mut rr, mut expl, mut keep, mut cnt) = (0, false, None, 0);
        if HAS_ADV && self.peek() == Some('r') {
            self.p += 1;
            rr = self.integer(3)?;
            if rr < 1 || rr >= sides {
                return Err("reroll".to_string());
            }
        }
        if HAS_MODS && self.peek() == Some('!') {
            self.p += 1;
            expl = true;
        }
        if HAS_MODS && (self.peek() == Some('k') || self.peek() == Some('d')) {
            let two: String = self.s[self.p..(self.p + 2).min(self.s.len())].iter().collect();
            if two == "kh" || two == "kl" || two == "dh" || two == "dl" {
                self.p += 2;
                let k = self.integer(3)?;
                if k < 1 {
                    return Err("keep".to_string());
                }
                keep = Some((two, k));
            }
        }
        if HAS_ADV && self.peek() == Some('c') {
            self.p += 1;
            cnt = self.integer(3)?;
            if cnt < 1 || cnt > sides {
                return Err("count".to_string());
            }
        }
        let text: String = self.s[start..self.p].iter().collect();
        Ok(Node::Dice { text, n, sides, rr, expl, keep, cnt })
    }
}

struct State {
    toks: Vec<String>,
    i: usize,
    lines: Vec<String>,
}

impl State {
    fn take(&mut self, sides: i64) -> R<i64> {
        if self.i >= self.toks.len() {
            return Err("stream exhausted".to_string());
        }
        let t = self.toks[self.i].clone();
        self.i += 1;
        let ok = !t.is_empty() && t.len() <= 9 && t.bytes().all(|c| c.is_ascii_digit());
        if !ok {
            return Err(format!("bad roll {}", t));
        }
        let v: i64 = t.parse().unwrap();
        if v < 1 || v > sides {
            return Err(format!("bad roll {}", t));
        }
        Ok(v)
    }
}

fn ev(node: &Node, st: &mut State) -> R<i64> {
    match node {
        Node::Int(v) => Ok(*v),
        Node::Neg(x) => Ok(-ev(x, st)?),
        Node::Bin(op, a, b) => {
            let x = ev(a, st)?;
            let y = ev(b, st)?;
            Ok(match *op {
                '+' => x + y,
                '-' => x - y,
                _ => x * y,
            })
        }
        Node::Dice { text, n, sides, rr, expl, keep, cnt } => {
            let mut vals: Vec<i64> = Vec::new();
            for _ in 0..*n {
                vals.push(st.take(*sides)?);
            }
            if *rr > 0 {
                for i in 0..vals.len() {
                    if vals[i] <= *rr {
                        vals[i] = st.take(*sides)?;
                    }
                }
            }
            if *expl {
                let mut i = 0;
                while i < vals.len() {
                    if vals[i] == *sides {
                        if vals.len() >= CAP {
                            return Err("too many dice".to_string());
                        }
                        let v = st.take(*sides)?;
                        vals.push(v);
                    }
                    i += 1;
                }
            }
            let mut dropped = vec![false; vals.len()];
            if let Some((kind, kk)) = keep {
                let mut idx: Vec<usize> = (0..vals.len()).collect();
                let kind = kind.as_str();
                if kind == "kh" || kind == "dh" {
                    idx.sort_by(|a, b| vals[*b].cmp(&vals[*a]).then(a.cmp(b)));
                } else {
                    idx.sort_by(|a, b| vals[*a].cmp(&vals[*b]).then(a.cmp(b)));
                }
                let kk = (*kk as usize).min(vals.len());
                let first: Vec<usize> = idx[..kk].to_vec();
                if kind == "kh" || kind == "kl" {
                    for j in 0..vals.len() {
                        dropped[j] = !first.contains(&j);
                    }
                } else {
                    for j in &first {
                        dropped[*j] = true;
                    }
                }
            }
            let kept: Vec<i64> = vals.iter().enumerate().filter(|(j, _)| !dropped[*j]).map(|(_, v)| *v).collect();
            let sub: i64 = if *cnt > 0 { kept.iter().filter(|v| **v >= *cnt).count() as i64 } else { kept.iter().sum() };
            let shown: Vec<String> = vals.iter().enumerate().map(|(j, v)| if dropped[j] { format!("({})", v) } else { v.to_string() }).collect();
            st.lines.push(format!("{}: {} = {}", text, shown.join(" "), sub));
            Ok(sub)
        }
    }
}

/// Evaluates a dice expression against a stream of die values.
pub fn roll(expr: &str, stream: &str) -> String {
    let mut p = Parser { s: expr.chars().collect(), p: 0 };
    let tree = match p.expr() {
        Ok(t) => t,
        Err(e) => return format!("error: {}", e),
    };
    p.ws();
    if p.p != p.s.len() {
        return "error: syntax".to_string();
    }
    let mut st = State { toks: stream.split_whitespace().map(|x| x.to_string()).collect(), i: 0, lines: Vec::new() };
    match ev(&tree, &mut st) {
        Ok(total) => {
            st.lines.push(format!("total {}", total));
            st.lines.join("\n")
        }
        Err(e) => format!("error: {}", e),
    }
}
'''

CC = r'''
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "dice.h"

#define MAXN @MAXN@
#define MAXS @MAXS@
#define HAS_MODS @MODS@
#define HAS_ADV @ADV@
#define CAP @CAP@

enum { K_INT, K_NEG, K_BIN, K_DICE };

typedef struct {
    int kind;
    long v;
    char op;
    int a, b;
    int tstart, tend;
    long n, sides, rr, cnt, keepk;
    int expl;
    char keep[3];
} Node;

typedef struct {
    const char *s;
    size_t len, p;
    Node *nodes;
    int nn;
    char err[64];
} Parser;

static int fail(Parser *ps, const char *m) {
    if (!ps->err[0]) strcpy(ps->err, m);
    return -1;
}

static char peekc(Parser *ps) { return ps->p < ps->len ? ps->s[ps->p] : 0; }
static void ws(Parser *ps) { while (ps->p < ps->len && (ps->s[ps->p] == ' ' || ps->s[ps->p] == '\t')) ps->p++; }
static int isdig(char c) { return c >= '0' && c <= '9'; }

static int newnode(Parser *ps, int kind) {
    Node *n = &ps->nodes[ps->nn];
    memset(n, 0, sizeof *n);
    n->kind = kind;
    return ps->nn++;
}

static long integer(Parser *ps, int maxd) {
    size_t q = ps->p;
    long v = 0;
    while (ps->p < ps->len && isdig(ps->s[ps->p])) { if (v < 100000000) v = v * 10 + (ps->s[ps->p] - '0'); ps->p++; }
    if (ps->p == q || (int)(ps->p - q) > maxd) { fail(ps, "syntax"); return -1; }
    return v;
}

static int expr(Parser *ps);

static int factor(Parser *ps) {
    ws(ps);
    char c = peekc(ps);
    if (c == '(') {
        ps->p++;
        int e = expr(ps);
        if (e < 0) return -1;
        ws(ps);
        if (peekc(ps) != ')') return fail(ps, "syntax");
        ps->p++;
        return e;
    }
    if (c == '-') {
        ps->p++;
        int x = factor(ps);
        if (x < 0) return -1;
        int n = newnode(ps, K_NEG);
        ps->nodes[n].a = x;
        return n;
    }
    size_t start = ps->p;
    long n;
    if (c && isdig(c)) {
        n = integer(ps, 4);
        if (n < 0) return -1;
        if (peekc(ps) != 'd') {
            int id = newnode(ps, K_INT);
            ps->nodes[id].v = n;
            return id;
        }
    } else if (c == 'd') {
        n = 1;
    } else {
        return fail(ps, "syntax");
    }
    ps->p++;
    if (n < 1 || n > MAXN) return fail(ps, "dice count");
    long sides = integer(ps, 3);
    if (sides < 0) return -1;
    if (sides < 2 || sides > MAXS) return fail(ps, "sides");
    long rr = 0, cnt = 0, keepk = 0;
    int expl = 0;
    char keep[3] = {0, 0, 0};
    if (HAS_ADV && peekc(ps) == 'r') {
        ps->p++;
        rr = integer(ps, 3);
        if (rr < 0) return -1;
        if (rr < 1 || rr >= sides) return fail(ps, "reroll");
    }
    if (HAS_MODS && peekc(ps) == '!') { ps->p++; expl = 1; }
    if (HAS_MODS && (peekc(ps) == 'k' || peekc(ps) == 'd')) {
        char a = peekc(ps), b = ps->p + 1 < ps->len ? ps->s[ps->p + 1] : 0;
        if ((b == 'h' || b == 'l') && (a == 'k' || a == 'd')) {
            ps->p += 2;
            keep[0] = a; keep[1] = b;
            keepk = integer(ps, 3);
            if (keepk < 0) return -1;
            if (keepk < 1) return fail(ps, "keep");
        }
    }
    if (HAS_ADV && peekc(ps) == 'c') {
        ps->p++;
        cnt = integer(ps, 3);
        if (cnt < 0) return -1;
        if (cnt < 1 || cnt > sides) return fail(ps, "count");
    }
    int id = newnode(ps, K_DICE);
    Node *d = &ps->nodes[id];
    d->tstart = (int)start; d->tend = (int)ps->p;
    d->n = n; d->sides = sides; d->rr = rr; d->cnt = cnt; d->expl = expl;
    strcpy(d->keep, keep); d->keepk = keepk;
    return id;
}

static int term(Parser *ps) {
    int left = factor(ps);
    if (left < 0) return -1;
    while (1) {
        ws(ps);
        if (peekc(ps) != '*') return left;
        ps->p++;
        int r = factor(ps);
        if (r < 0) return -1;
        int b = newnode(ps, K_BIN);
        ps->nodes[b].op = '*'; ps->nodes[b].a = left; ps->nodes[b].b = r;
        left = b;
    }
}

static int expr(Parser *ps) {
    int left = term(ps);
    if (left < 0) return -1;
    while (1) {
        ws(ps);
        char c = peekc(ps);
        if (c != '+' && c != '-') return left;
        ps->p++;
        int r = term(ps);
        if (r < 0) return -1;
        int b = newnode(ps, K_BIN);
        ps->nodes[b].op = c; ps->nodes[b].a = left; ps->nodes[b].b = r;
        left = b;
    }
}

typedef struct {
    char **toks;
    int nt, i;
    char *lines;
    size_t llen, lcap;
    char err[96];
    const char *src;
} Eval;

static void addline(Eval *e, const char *s) {
    size_t l = strlen(s);
    if (e->llen + l + 2 > e->lcap) { e->lcap = (e->llen + l + 2) * 2; e->lines = realloc(e->lines, e->lcap); }
    if (e->llen) e->lines[e->llen++] = '\n';
    memcpy(e->lines + e->llen, s, l);
    e->llen += l;
    e->lines[e->llen] = 0;
}

static long take(Eval *e, long sides) {
    if (e->i >= e->nt) { strcpy(e->err, "stream exhausted"); return -1; }
    const char *t = e->toks[e->i++];
    size_t n = strlen(t);
    int ok = n >= 1 && n <= 9;
    for (size_t k = 0; ok && k < n; k++) if (!isdig(t[k])) ok = 0;
    long v = ok ? atol(t) : 0;
    if (!ok || v < 1 || v > sides) { sprintf(e->err, "bad roll %s", t); return -1; }
    return v;
}

static long ev(Parser *ps, Eval *e, int id, int *bad) {
    Node *nd = &ps->nodes[id];
    if (nd->kind == K_INT) return nd->v;
    if (nd->kind == K_NEG) { long x = ev(ps, e, nd->a, bad); return *bad ? 0 : -x; }
    if (nd->kind == K_BIN) {
        long a = ev(ps, e, nd->a, bad);
        if (*bad) return 0;
        long b = ev(ps, e, nd->b, bad);
        if (*bad) return 0;
        return nd->op == '+' ? a + b : nd->op == '-' ? a - b : a * b;
    }
    long vals[200];
    int nv = 0;
    for (long k = 0; k < nd->n; k++) {
        long v = take(e, nd->sides);
        if (v < 0) { *bad = 1; return 0; }
        vals[nv++] = v;
    }
    if (nd->rr) {
        for (int k = 0; k < nv; k++) if (vals[k] <= nd->rr) {
            long v = take(e, nd->sides);
            if (v < 0) { *bad = 1; return 0; }
            vals[k] = v;
        }
    }
    if (nd->expl) {
        for (int k = 0; k < nv; k++) if (vals[k] == nd->sides) {
            if (nv >= CAP) { strcpy(e->err, "too many dice"); *bad = 1; return 0; }
            long v = take(e, nd->sides);
            if (v < 0) { *bad = 1; return 0; }
            vals[nv++] = v;
        }
    }
    int dropped[200];
    memset(dropped, 0, sizeof dropped);
    if (nd->keep[0]) {
        int idx[200];
        for (int k = 0; k < nv; k++) idx[k] = k;
        int desc = (nd->keep[1] == 'h');
        for (int x = 1; x < nv; x++) {
            int cur = idx[x], y = x - 1;
            while (y >= 0) {
                int better = desc ? (vals[cur] > vals[idx[y]]) : (vals[cur] < vals[idx[y]]);
                if (!better) break;
                idx[y + 1] = idx[y];
                y--;
            }
            idx[y + 1] = cur;
        }
        long kk = nd->keepk < nv ? nd->keepk : nv;
        int first[200];
        memset(first, 0, sizeof first);
        for (long k = 0; k < kk; k++) first[idx[k]] = 1;
        for (int k = 0; k < nv; k++) dropped[k] = (nd->keep[0] == 'k') ? !first[k] : first[k];
    }
    long sub = 0;
    for (int k = 0; k < nv; k++) {
        if (dropped[k]) continue;
        if (nd->cnt) { if (vals[k] >= nd->cnt) sub++; } else sub += vals[k];
    }
    char line[2048];
    int pos = sprintf(line, "%.*s:", nd->tend - nd->tstart, e->src + nd->tstart);
    for (int k = 0; k < nv; k++) pos += sprintf(line + pos, dropped[k] ? " (%ld)" : " %ld", vals[k]);
    sprintf(line + pos, " = %ld", sub);
    addline(e, line);
    return sub;
}

static char *dupstr(const char *s) {
    char *r = malloc(strlen(s) + 1);
    strcpy(r, s);
    return r;
}

char *roll(const char *expression, const char *stream) {
    size_t len = strlen(expression);
    Parser ps;
    memset(&ps, 0, sizeof ps);
    ps.s = expression;
    ps.len = len;
    ps.nodes = malloc((len + 4) * sizeof(Node));
    int root = expr(&ps);
    if (root >= 0) {
        ws(&ps);
        if (ps.p != len) { fail(&ps, "syntax"); root = -1; }
    }
    if (root < 0) {
        char buf[96];
        sprintf(buf, "error: %s", ps.err);
        free(ps.nodes);
        return dupstr(buf);
    }
    Eval e;
    memset(&e, 0, sizeof e);
    e.src = expression;
    char *copy = dupstr(stream);
    e.toks = malloc((strlen(stream) + 2) * sizeof(char *));
    char *p = copy;
    while (*p) {
        while (*p == ' ' || *p == '\t' || *p == '\r' || *p == '\n' || *p == '\v' || *p == '\f') *p++ = 0;
        if (!*p) break;
        e.toks[e.nt++] = p;
        while (*p && !(*p == ' ' || *p == '\t' || *p == '\r' || *p == '\n' || *p == '\v' || *p == '\f')) p++;
    }
    e.lines = malloc(64);
    e.lcap = 64;
    e.lines[0] = 0;
    int bad = 0;
    long total = ev(&ps, &e, root, &bad);
    char *res;
    if (bad) {
        char buf[128];
        sprintf(buf, "error: %s", e.err);
        res = dupstr(buf);
    } else {
        char buf[64];
        sprintf(buf, "total %ld", total);
        addline(&e, buf);
        res = dupstr(e.lines);
    }
    free(e.lines);
    free(e.toks);
    free(copy);
    free(ps.nodes);
    return res;
}
'''


def _b(lang, v):
    if lang == "python":
        return "True" if v else "False"
    if lang == "c":
        return "1" if v else "0"
    return "true" if v else "false"


def sol(lang, p):
    src = {"python": PY, "ruby": RB, "javascript": JS, "rust": RS, "c": CC}[lang]
    return K.subst(src, MAXN=p["maxn"], MAXS=p["maxs"], MODS=_b(lang, p["mods"]), ADV=_b(lang, p["adv"]), CAP=p["cap"]).lstrip("\n")


# ---------------------------------------------------------------------------------------------------------------

def readme(p, api, lang, examples):
    L = [f"# Dice roller for {p['game']}", ""]
    L.append("This library evaluates dice expressions written in the club's notation. It does not roll anything itself: the caller passes the *stream* of die values (so results are reproducible), "
             "and the library consumes values from the stream exactly in the order described below. The result is a short report.")
    L.append("")
    L.append("## Expressions")
    L.append("")
    L.append("An expression is built from integers, dice terms, `+`, `-`, `*` and parentheses. Blanks (spaces and tabs) may appear between any two tokens, **except inside a dice term**.")
    L.append("")
    L.append("```")
    L.append("expr    := term { ('+' | '-') term }")
    L.append("term    := factor { '*' factor }")
    L.append("factor  := INT | DICE | '(' expr ')' | '-' factor")
    mods = {"r": "['r' T]", "!": "['!']", "k": "[('kh' | 'kl' | 'dh' | 'dl') K]", "c": "['c' T]"}
    L.append("DICE    := [N] 'd' SIDES " + " ".join(mods[m] for m in p["order"]))
    L.append("```")
    L.append("")
    L.append("`INT`, `N`, `SIDES`, `K` and `T` are unsigned decimal integers of ASCII digits: `INT` and `N` have at most 4 digits, `SIDES`, `K` and `T` at most 3. `N` defaults to 1 (`d20`). "
             "`*` binds tighter than `+` and `-`; operators associate to the left; `-` as a prefix negates the factor after it. An integer directly followed by `d` starts a dice term; there are no blanks inside `4d6kh3`.")
    L.append("")
    L.append("**Limits.** The dice count `N` must be from 1 to " + str(p["maxn"]) + " (otherwise `error: dice count`), `SIDES` from 2 to " + str(p["maxs"]) + " (otherwise `error: sides`)." +
             (" `rT`: `T` from 1 to SIDES-1 (otherwise `error: reroll`); `khK`, `klK`, `dhK`, `dlK`: `K` at least 1 (otherwise `error: keep`); `cT`: `T` from 1 to SIDES (otherwise `error: count`)." if p["adv"] else
              (" `K` of a keep/drop modifier must be at least 1 (otherwise `error: keep`)." if p["mods"] else "")))
    L.append("")
    L.append("The text is scanned from left to right and the **first** problem found is the result, whatever follows it: a grammar violation (a missing operand, an unexpected character, an unclosed parenthesis, an over-long number, "
             "trailing text, an empty expression, ...) is `error: syntax`; the limits above are checked as soon as the number in question has been read.")
    L.append("")
    if p["mods"]:
        L.append("## Modifiers")
        L.append("")
        L.append("The modifiers of a dice term must appear in the order of the grammar (each at most once; leaving some out is fine). They are applied to the dice of that term in this order:")
        L.append("")
        steps = ["**Roll** the `N` dice: take `N` values from the stream, in order."]
        if p["adv"]:
            steps.append("**`rT` reroll**: go through the dice from left to right; every die whose value is `T` or less is replaced by the next value from the stream (once: the new value stays, even if it is `T` or less).")
        steps.append("**`!` exploding**: go through the dice list from left to right, *including dice added during this step*; every die whose value equals `SIDES` causes the next value from the stream to be appended as a new die at the end of the list. "
                     f"If the list already holds {p['cap']} dice when another die would be appended the result is `error: too many dice`.")
        steps.append("**Keep / drop**: `khK` keeps the `K` highest dice, `klK` the `K` lowest, `dhK` drops the `K` highest, `dlK` drops the `K` lowest; ties are broken by position (of equal values the one rolled **earlier** counts as higher *and* as lower, i.e. is picked first); "
                     "`K` larger than the number of dice means all of them.")
        if p["adv"]:
            steps.append("**`cT` count**: the subtotal is the number of kept dice with a value of `T` or more (instead of their sum).")
        for i, s_ in enumerate(steps, 1):
            L.append(f"{i}. {s_}")
        L.append("")
        L.append("Without `cT` the subtotal of a dice term is the sum of its kept dice. Plain `NdS` just rolls and sums.")
        L.append("")
    else:
        L.append("A dice term `NdS` takes `N` values from the stream, in order; its subtotal is their sum.")
        L.append("")
    L.append("## The stream")
    L.append("")
    L.append("`stream` is text; its blank-separated words (spaces, tabs, newlines) are the die values in order. A die needs one word each time the rules above say *take the next value*. "
             "If the stream has no word left: `error: stream exhausted`. If the word is not a number of 1 to 9 ASCII digits, or its value is below 1 or above the die's `SIDES`: `error: bad roll WORD` (with the word as written). "
             "Unused words at the end are ignored.")
    L.append("")
    L.append("## Evaluation order and result")
    L.append("")
    L.append("The whole expression is parsed first (a parse error wins over everything). Then it is evaluated with the dice terms rolled **in the order they appear in the text**, left to right, whatever the operators are "
             "(so in `2*(1d6+1d4)` the d6 takes the first stream value and the d4 the second). The first run-time error stops everything and is the result.")
    L.append("")
    L.append("On success the result has one line for each dice term in text order, then a last line `total N`, joined by `\\n` (no trailing newline). A term line is the term's text exactly as written (no blanks inside it), a colon, "
             "the final dice of the term in list order, each separated by a single blank, with the dice that were dropped by a keep/drop modifier in parentheses, then ` = ` and the subtotal. Example: `4d6kh3: 5 (2) 6 4 = 15`. "
             "`N` in `total N` is the value of the whole arithmetic expression (integers, `+`, `-`, `*`, negation of subtotals); an expression without dice terms has only the `total` line.")
    L.append("")
    L.append(K.interface_section(api, lang))
    L.append("## Examples")
    L.append("")
    L.append("| expression | stream | result |")
    L.append("|---|---|---|")
    for (e, s_), out in examples:
        L.append(f"| `{e}` | `{s_}` | `" + out.replace("\n", " / ") + "` |")
    L.append("")
    L.append("(`/` stands for a line break in multi-line results.)")
    L.append("")
    L.append(K.run_hint(lang, api.mod))
    return "\n".join(L) + "\n"


def make_cases(rng, p, ns):
    cases = []
    maxn, maxs = p["maxn"], p["maxs"]
    roll = ns["roll"]

    def stream_for(expr_dice):
        return " ".join(str(rng.randrange(1, s + 1)) for s in expr_dice)

    def add(e, s=""):
        cases.append((e, s))

    def sidesn():
        return rng.choice([4, 6, 6, 8, 10, 12, 20, 20, 100]) if maxs >= 100 else rng.choice([4, 6, 8, 10, 12, min(20, maxs)])

    def rnd_stream(n, s):
        return " ".join(str(rng.randrange(1, s + 1)) for _ in range(n))

    add("3d6+2", "4 5 1")
    s = sidesn()
    add(f"2d{s}-1d{min(s, 6)}", rnd_stream(2, s) + " " + str(rng.randrange(1, min(s, 6) + 1)))
    if p["mods"]:
        add("4d6kh3", "2 5 6 4")
    else:
        add(f"d{s}*2", rnd_stream(1, s))
    nex = len(cases)
    # plain
    for _ in range(10):
        a, b = rng.randrange(1, 5), sidesn()
        c = rng.randrange(0, 20)
        add(f"{a}d{b}+{c}", rnd_stream(a, b))
    add("d6", "3")
    add("1d6", "3")
    add("d6 + d6", "1 6")
    add("2 + 3", "")
    add("2 + 3 * 4 - 1", "")
    add("(2 + 3) * 4", "1 2 3")
    add("-3", "")
    add("--3", "")
    add("-(2+3)", "")
    add("-d6", "4")
    add("2*-3", "")
    add("2 - -d6", "5")
    add("2*(1d6+1d4)", "6 4")
    add("(d6)*(d4)", "2 3")
    add("d6*d6*d6", "2 3 4")
    add("1d6 + 2d4 * 3", "2 1 4")
    add("0", "")
    add("9999", "")
    add("9999*9999", "")
    add("99999", "")
    add("d6", "")
    add("2d6", "3")
    add("2d6", "3 4 5")
    add("d6", "7")
    add("d6", "0")
    add("d6", "x")
    add("d6", "-1")
    add("d6", "+1")
    add("d6", "1.5")
    add("d6", "1e1")
    add("d6", "0003")
    add("d6", "0007")
    add("d6", "1234567890")
    add("2d6", "3\n4")
    add("2d6", "  3\t 4  ")
    add("d6+d6", "3 x")
    add("d6+d6", "x 3")
    add("d6+d6", "3 7")
    add("d6+d6+d6", "1 2")
    add("d20", "20")
    add("d20", "21")
    add(f"d{maxs}", str(maxs))
    add(f"d{maxs}", str(maxs + 1))
    add("2d6 ", "1 2")
    add(" 2d6", "1 2")
    add(" ( 2d6 ) + ( 1 ) ", "1 2")
    add("2\t+\t3", "")
    # limits and syntax
    add(f"{maxn}d2", " ".join(["1", "2"] * (maxn // 2 + 1))[: 2 * maxn])
    add(f"{maxn + 1}d6", "1 1 1")
    add("0d6", "")
    add("00d6", "")
    add("d1", "1")
    add("d0", "1")
    add(f"d{maxs + 1}", "1")
    add("d1000", "1")
    add("d1000x", "1")
    add("d", "")
    add("2d", "")
    add("2d6d", "1 2")
    add("2 d6", "1 2")
    add("2d 6", "1 2")
    add("d6 d6", "1 2")
    add("d6d6", "1 2")
    add("6", "")
    add("")
    add(" ")
    add("+", "")
    add("2+", "")
    add("+2", "")
    add("2++2", "")
    add("2+-2", "")
    add("2*", "")
    add("*2", "")
    add("(", "")
    add(")", "")
    add("()", "")
    add("(2", "")
    add("2)", "")
    add("((2)", "")
    add("(2))", "")
    add("2 2", "")
    add("2 d6", "1")
    add("a", "")
    add("2d6x", "1 2")
    add("2d6 x", "1 2")
    add("2/3", "")
    add("2%3", "")
    add("1.5", "")
    add("d6.5", "1")
    add("12345", "")
    add("12345d6", "")
    add("d6666", "")
    add("2d6+", "1 2")
    add("2d6+d", "1 2 3")
    add("D6", "1")
    add("2D6", "1 2")
    add("d6 +\n d6", "1 2")
    add("d6\t+d6", "1 2")
    add("+d6", "1")
    add("d-6", "1")
    add("-d-6", "1")
    add("2d-6", "1")
    # error priority: parse before stream
    add("d6+", "")
    add("d6+d1000", "")
    add("d1000+d6", "9")
    add("d6+0d6", "1")
    add("d6 + 99d6", "1")
    add("d6 + (", "1")
    if p["mods"]:
        base = "4d6"
        add("4d6kh3", "2 5 6 4")
        add("4d6kh3", "6 6 6 6")
        add("4d6kh3", "1 1 1 1")
        add("4d6kh2", "3 3 5 3")
        add("4d6kl1", "3 3 5 3")
        add("4d6kl2", "3 3 5 3")
        add("4d6dh1", "3 3 5 5")
        add("4d6dl1", "3 3 5 5")
        add("4d6dl2", "3 3 5 5")
        add("4d6dh2", "6 6 1 1")
        add("4d6kh4", "1 2 3 4")
        add("4d6kh5", "1 2 3 4")
        add("4d6kh99", "1 2 3 4")
        add("4d6dh4", "1 2 3 4")
        add("4d6dh9", "1 2 3 4")
        add("4d6dl4", "1 2 3 4")
        add("3d6kh1", "2 2 2")
        add("3d6kl1", "2 2 2")
        add("3d6dh1", "2 2 2")
        add("3d6dl1", "2 2 2")
        add("5d10kh3", "10 3 10 7 3")
        add("5d10kl3", "10 3 10 7 3")
        add("5d10dh2", "10 3 10 7 3")
        add("5d10dl2", "10 3 10 7 3")
        add("2d20kh1+5", "13 8")
        add("2d20kl1+5", "13 8")
        add("2d20kh1", "9 9")
        add("d20kh1", "9")
        add("d20dh1", "9")
        add("4d6kh0", "1 2 3 4")
        add("4d6dh0", "1 2 3 4")
        add("4d6kh", "1 2 3 4")
        add("4d6k3", "1 2 3 4")
        add("4d6kx3", "1 2 3 4")
        add("4d6kh 3", "1 2 3 4")
        add("4d6kh3kh1", "1 2 3 4")
        add("4d6kh3dl1", "1 2 3 4")
        add("4d6kh1000", "1 2 3 4")
        add("4d6kh03", "1 2 3 4")
        add("4d6KH3", "1 2 3 4")
        add("4d6kh3!", "1 2 3 4")
        add("4d6k", "1 2 3 4")
        add("4d6d", "1 2 3 4")
        add("4d6dh3 + 2d6dl1", "1 2 3 4 5 6")
        add("2*(3d6kh2)", "1 2 3")
        add("(2d6kh1+3d4dl2)*2", "5 2 1 3 4")
        add("-2d6kh1", "4 3")
        # exploding
        add("d6!", "3")
        add("d6!", "6 3")
        add("d6!", "6 6 6 2")
        add("d6!", "6")
        add("d6!", "6 6")
        add("2d6!", "6 2 4")
        add("2d6!", "2 6 3")
        add("2d6!", "6 6 1 5 4")
        add("3d4!", "4 1 4 4 4 2")
        add("3d4!kh2", "4 1 4 4 3")
        add("3d4!dl1", "4 1 4 4 3")
        add("2d6!kh1", "6 3 5")
        add("d6!!", "1")
        add("d6!x", "1")
        add("d6 !", "1")
        add("d6!+d6!", "6 2 3")
        add("d2!", " ".join(["2"] * 5 + ["1"]))
        cap = p["cap"]
        add("d2!", " ".join(["2"] * (cap - 1) + ["1"]))
        add("d2!", " ".join(["2"] * cap + ["1"]))
        add("d2!", " ".join(["2"] * (cap + 1)))
        add("d2!", " ".join(["2"] * (cap + 5)))
        add("3d2!", " ".join(["2"] * 3 + ["2"] * (cap - 3) + ["1"]))
        add("3d2!", " ".join(["2"] * (3 + cap - 3) + ["2", "1"]))
        add("d2!", " ".join(["2"] * 10))
        add("d2!", " ".join(["2"] * 3))
        add(f"d{maxs}!", f"{maxs} 1")
        add(f"d{maxs}!", f"{maxs} {maxs + 1}")
        add("d6!", "6 7")
        add("d6!", "6 x")
        add("d6!kh0", "6 1")
        add("d6!kh1", "6 5")
        add("d6!kl1", "6 5")
    else:
        add("4d6kh3", "1 2 3 4")
        add("d6!", "6 1")
        add("2d6dl1", "1 2")
    if p["adv"]:
        add("2d6r1", "1 5 3")
        add("2d6r1", "1 1 1 1")
        add("2d6r1", "2 3")
        add("2d6r2", "1 2 3 1")
        add("2d6r2", "1 2 3 4")
        add("2d6r5", "6 5 1 2")
        add("2d6r5", "5 6 1")
        add("2d6r5", "5 6 7 8")
        add("3d6r2", "2 5 1 3 4")
        add("3d6r2", "2 5 1 3 4 1")
        add("d6r1!", "1 6 6 3")
        add("d6r1!", "1 1")
        add("d6r1!", "6 3")
        add("2d6r1!", "1 6 6 2 3")
        add("2d6r2!kh2", "1 6 6 4 2 3")
        add("2d6r2!kh1", "1 2 6 4 2 3")
        add("4d6r1kh3", "1 5 1 6 4 2")
        add("4d6r1kh3", "1 5 1 6 4")
        add("4d6r1dl1", "1 5 1 6 4 2")
        add("d6r0", "1")
        add("d6r6", "1")
        add("d6r7", "1")
        add("d6r", "1")
        add("d6rr1", "1")
        add("d6!r1", "1")
        add("d6r1 !", "1")
        add("d6r 1", "1")
        add("d6r01", "1 2")
        add("d6r1000", "1")
        add("d2r1", "1 2")
        add("d2r1", "1 1")
        add("d2r2", "1")
        # counts
        add("5d10c8", "8 9 10 7 1")
        add("5d10c10", "8 9 10 7 1")
        add("5d10c1", "8 9 10 7 1")
        add("5d10c8kh2", "8 9 10 7 1")
        add("5d10kh2c8", "8 9 10 7 1")
        add("5d10kl2c2", "8 9 10 1 1")
        add("5d10dh2c8", "8 9 10 7 1")
        add("5d10dl2c8", "8 9 10 7 1")
        add("5d10!c10", "10 10 3 4 5 1 2")
        add("5d10!c10", "10 1 3 4 5 10")
        add("5d10r2c8", "2 9 10 7 1 8 3")
        add("3d6c4+3d6c4", "1 2 3 4 5 6")
        add("2*3d6c4", "5 5 1")
        add("d6c0", "1")
        add("d6c7", "1")
        add("d6c6", "6")
        add("d6c", "1")
        add("d6c x", "1")
        add("d6cc2", "1")
        add("d6c2c2", "1")
        add("d6c2!", "1")
        add("d6c2r1", "1")
        add("d6c002", "3")
        add("d6c1000", "1")
        add("-5d10c8", "8 9 10 7 1")
        add("10d10c8", " ".join(str(rng.randrange(1, 11)) for _ in range(10)))
    else:
        add("d6r1", "1 2")
        add("5d10c8", "8 9 10 7 1")
    # random expressions
    def rexpr(depth):
        r = rng.random()
        if depth == 0 or r < 0.4:
            if rng.random() < 0.7:
                n = rng.randrange(1, 4)
                s = sidesn()
                t = f"{n if n > 1 or rng.random() < 0.5 else ''}d{s}"
                if p["mods"] and rng.random() < 0.5:
                    mods = ""
                    if p["adv"] and rng.random() < 0.3:
                        mods += f"r{rng.randrange(1, min(3, s))}"
                    if rng.random() < 0.3:
                        mods += "!"
                    if rng.random() < 0.5:
                        mods += rng.choice(["kh", "kl", "dh", "dl"]) + str(rng.randrange(1, 4))
                    if p["adv"] and rng.random() < 0.3:
                        mods += f"c{rng.randrange(1, s + 1)}"
                    t += mods
                return t
            return str(rng.randrange(0, 20))
        op = rng.choice("+-*")
        a, b = rexpr(depth - 1), rexpr(depth - 1)
        if rng.random() < 0.3:
            a = f"({a})"
        return f"{a}{rng.choice(['', ' '])}{op}{rng.choice(['', ' '])}{b}"

    for _ in range(40):
        e = rexpr(rng.randrange(1, 4))
        # generous stream: values 1..100 are valid for most dice only when small; choose per-die random by trying
        st = " ".join(str(rng.randrange(1, 5)) for _ in range(rng.randrange(0, 30)))
        add(e, st)
    out, seen = [], set()
    for c in cases:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out, nex


def prompt(rng, p, api, lang):
    where = api.short(lang)
    fn = api.name(lang)
    ln = K.LANG_NAME[lang]
    feats = ["plain dice sums"] + (["keep/drop and exploding dice"] if p["mods"] else []) + (["rerolls and success counting"] if p["adv"] else [])
    ft = ", ".join(feats)
    opts = [
        f"For {p['game']} we want an evaluator for the club's dice notation in {ln}: `{fn}(expression, stream)` returns a report and takes die values from the stream instead of a random generator. Spec: README.md ({ft}). Put it in {where}. {K.closer(rng)}",
        f"Implement `{fn}` in {ln} ({where}) following README.md. The tricky part is the exact order in which dice values are taken from the stream and which error wins. Features: {ft}.",
        f"dice notation interpreter ({ln}); `{fn}` in {where}; the README describes the grammar, modifiers ({ft}), stream consumption order and the report format. {K.closer(rng)}",
        f"Please write the dice roller of {p['game']}: {ln}, function `{fn}`, file {where}. Deterministic: values come from a stream argument. Read README.md for every rule; hidden checks go through all error cases.",
    ]
    return rng.choice(opts).strip()


@family("greenfield-dice", category="greenfield", lang="mixed", kind="greenfield", n=12,
        summary="dice-notation evaluator over a supplied roll stream: grammar, exact consumption order, reroll/explode/keep-drop/count, parse-vs-runtime error priority")
def gen(rng, n):
    levels = [2, 3, 3, 4, 4, 2, 3, 4, 4, 3, 4, 2]
    diffs = [2, 3, 3, 4, 4, 2, 3, 4, 5, 3, 4, 2]
    for i in range(n):
        lang = LANG_PLAN[i % len(LANG_PLAN)]
        level = levels[i % len(levels)]
        p = params(rng, level, i)
        api = K.Api(mod="dice", fn="roll", args=["expression", "stream"], arg_docs=["the dice expression text", "the die values, separated by blanks"],
                    ret_doc="the report, or an `error: ...` text", doc="dice notation evaluator")
        py_src = sol("python", p)
        ns = K.py_namespace(py_src)
        cases, nex = make_cases(rng, p, ns)
        sols = {lang: sol(lang, p), "python": py_src}
        examples = [(c, ns["roll"](*c)) for c in cases[:nex]]
        rd = readme(p, api, lang, examples)
        yield K.lib_task(
            api=api, lang=lang, readme=rd, solutions=sols, cases=cases, examples=nex, prompt=prompt(rng, p, api, lang),
            difficulty=diffs[i % len(diffs)], slug=f"{i + 1:02d}-{lang}-n{p['maxn']}-s{p['maxs']}-l{level}", oracle=(None if lang == "python" else ns["roll"]),
            tags=["parser", "evaluator"], notes={"level": level, "maxn": p["maxn"], "maxs": p["maxs"], "cap": p["cap"]},
        )

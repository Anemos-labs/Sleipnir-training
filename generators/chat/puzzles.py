"""Puzzles with exactly one answer, checked by a solver at build time: logic grids, ordering puzzles, small probability and
counting problems, rotating rotas. Answers are digit codes or fractions so that they never appear in the prompt."""
from __future__ import annotations

import itertools
import math
from fractions import Fraction

from fx import family

from . import _common as C

# --------------------------------------------------------------------------------------------------------------------
# chat-logic-grid

THEMES = [
    dict(key="potluck", slot="seat", person="guest", layout="Seats are numbered 1 to {n} from left to right along one side of the long table.",
         scene=["We hosted a potluck last weekend and I have forgotten who sat where.", "Our supper club had {n} guests and I want to reconstruct the seating from the things people remember."],
         cats=[("dish", ["lentil stew", "beet salad", "plum tart", "cheese scones", "mushroom pie", "fig chutney", "rice pudding"], "brought the {}"),
               ("drink", ["oolong", "pear cider", "ginger beer", "elderflower cordial", "black coffee", "mint tea", "apple juice"], "is drinking {}")]),
    dict(key="allotment", slot="plot", person="grower", layout="The plots are numbered 1 to {n} in a row from the gate to the pond.",
         scene=["I help run the allotment association and a map got lost in the shed flood.", "We are redrawing the allotment plan from memory, {n} plots in a row."],
         cats=[("crop", ["leeks", "runner beans", "dahlias", "beetroot", "garlic", "sweetcorn", "rhubarb"], "grows {}"),
               ("shed", ["green", "blue", "red", "yellow", "grey", "white", "black"], "has a {} shed")]),
    dict(key="talks", slot="slot", person="speaker", layout="The talks are numbered 1 to {n} in the order they are given during the day.",
         scene=["I am putting together the programme for a small meetup and the speakers keep emailing constraints.", "Our meetup has {n} talks and the organisers' notes are a mess."],
         cats=[("topic", ["compilers", "accessibility", "bees", "observability", "game jams", "typography", "soldering"], "is speaking about {}"),
               ("demo", ["a live stream", "a paper prototype", "a spreadsheet", "a robot arm", "a synth", "a slide deck", "a terminal"], "is demoing {}")]),
    dict(key="pottery", slot="wheel", person="potter", layout="The wheels are numbered 1 to {n} along the studio wall, window end first.",
         scene=["At the pottery studio last night nobody wrote down who used which wheel.", "I teach a pottery evening class and I am trying to work out who had which wheel."],
         cats=[("piece", ["a teapot", "a fruit bowl", "a tall vase", "a set of mugs", "a butter dish", "a lamp base", "a planter"], "is making {}"),
               ("clay", ["white stoneware", "red earthenware", "black clay", "speckled clay", "porcelain", "buff clay", "grey stoneware"], "is using {}")]),
    dict(key="market", slot="stall", person="trader", layout="The stalls are numbered 1 to {n} along the market street, starting at the church.",
         scene=["I run the Saturday market and the stall layout has to be reconstructed after the printer ate the plan.", "Market day puzzle: {n} stalls in a line, and only fragments of the plan survive."],
         cats=[("product", ["honey", "cheese", "ceramics", "sourdough", "candles", "knitwear", "pickles"], "sells {}"),
               ("awning", ["striped", "orange", "green", "navy", "plain", "yellow", "red"], "has a {} awning")]),
    dict(key="benches", slot="bench", person="technician", layout="The benches are numbered 1 to {n} down the lab, starting at the door.",
         scene=["Lab reshuffle: I need to confirm which technician is at which bench before the safety inspection.", "We moved benches again in the lab and the booking sheet only gives hints."],
         cats=[("assay", ["ELISA", "PCR", "gel", "titration", "culture", "microscopy", "spectroscopy"], "is running the {} work"),
               ("instrument", ["centrifuge", "balance", "incubator", "pH meter", "fume hood", "plate reader", "autoclave"], "is using the {}")]),
    dict(key="choir", slot="position", person="singer", layout="The singers stand in a single row, positions numbered 1 to {n} from the conductor's left.",
         scene=["Before the concert the conductor wants the exact standing order and I only have what people told me.", "Choir risers puzzle: {n} singers in one row, no photo of who stood where."],
         cats=[("part", ["soprano", "alto", "tenor", "bass", "descant", "baritone", "mezzo"], "sings {}"),
               ("scarf", ["green", "purple", "orange", "cream", "teal", "maroon", "silver"], "wears a {} scarf")]),
    dict(key="racks", slot="rack", person="cyclist", layout="The bike racks are numbered 1 to {n} along the wall of the office garage, starting by the lift.",
         scene=["Office bike garage mystery: who parked where this morning?", "The facilities team asked me to reconstruct the bike rack layout from what colleagues said."],
         cats=[("bike", ["red", "blue", "black", "silver", "orange", "mint", "white"], "rides a {} bike"),
               ("lock", ["chain", "D-lock", "cable", "folding", "combination", "no", "padlock"], "uses a {} lock")]),
]
EXTRA_CATS = {
    "potluck": ("dessert", ["tiramisu", "flapjack", "lemon tart", "meringues", "brownies", "baklava", "trifle"], "brought {} for dessert"),
    "allotment": ("tool", ["spade", "hoe", "trowel", "fork", "rake", "shears", "dibber"], "keeps a {} by the gate"),
    "talks": ("laptop", ["a silver laptop", "a black laptop", "a borrowed laptop", "a tablet", "a retro netbook", "a gaming laptop", "a chromebook"], "is presenting from {}"),
    "pottery": ("glaze", ["celadon", "tenmoku", "ash", "cobalt", "shino", "honey", "copper"], "is glazing in {}"),
    "market": ("payment", ["cash only", "card only", "tokens", "cash and card", "phone payments", "barter", "invoices"], "takes {}"),
    "benches": ("shift", ["early shift", "late shift", "night shift", "split shift", "weekend shift", "flex shift", "bank-holiday shift"], "is on the {}"),
    "choir": ("solo", ["the hymn", "the lullaby", "the sea shanty", "the carol", "the madrigal", "the spiritual", "the folk song"], "has the solo in {}"),
    "racks": ("helmet", ["a white helmet", "a green helmet", "a yellow helmet", "a black helmet", "a pink helmet", "a blue helmet", "no helmet"], "wears {}"),
}


def _holds(cl, s, n):
    t = cl[0]
    if t == "same":
        return s[cl[1]] == s[cl[2]]
    if t == "diff":
        return s[cl[1]] != s[cl[2]]
    if t == "before":
        return s[cl[1]] < s[cl[2]]
    if t == "adj":
        return abs(s[cl[1]] - s[cl[2]]) == 1
    if t == "next":
        return s[cl[2]] == s[cl[1]] + 1
    if t == "gap2":
        return abs(s[cl[1]] - s[cl[2]]) == 2
    if t == "at":
        return s[cl[1]] == cl[2]
    if t == "notat":
        return s[cl[1]] != cl[2]
    if t == "end":
        return s[cl[1]] in (1, n)
    if t == "notend":
        return s[cl[1]] not in (1, n)
    if t == "oneof":
        return s[cl[1]] in (s[cl[2]], s[cl[3]])
    if t == "between":
        lo, hi = sorted((s[cl[2]], s[cl[3]]))
        return lo < s[cl[1]] < hi
    raise ValueError(t)


def _vars(cl):
    t = cl[0]
    if t in ("at", "notat"):
        return (cl[1],)
    if t in ("end", "notend"):
        return (cl[1],)
    if t in ("oneof", "between"):
        return (cl[1], cl[2], cl[3])
    return (cl[1], cl[2])


def count_solutions(vars_, cats, clues, n, limit=2):
    """vars_: list of variable ids (cat, idx). Backtracking with per-category all-different; stops after `limit`."""
    deg = {v: 0 for v in vars_}
    for cl in clues:
        for v in _vars(cl):
            deg[v] += 1
    order = sorted(vars_, key=lambda v: (-deg[v], v))
    by_last = {v: [] for v in order}
    pos = {v: i for i, v in enumerate(order)}
    for cl in clues:
        last = max(_vars(cl), key=lambda v: pos[v])
        by_last[last].append(cl)
    assign: dict = {}
    used = {c: set() for c in cats}
    found = 0

    def rec(k):
        nonlocal found
        if found >= limit:
            return
        if k == len(order):
            found += 1
            return
        v = order[k]
        for val in range(1, n + 1):
            if val in used[v[0]]:
                continue
            assign[v] = val
            if all(_holds(cl, assign, n) for cl in by_last[v]):
                used[v[0]].add(val)
                rec(k + 1)
                used[v[0]].discard(val)
            del assign[v]

    rec(0)
    return found


def _sample_clue(rng, truth, vars_, n, kinds, k_cats):
    t = rng.choice(kinds)
    for _ in range(40):
        a, b, c = rng.sample(vars_, 3)
        if t in ("same", "diff") and a[0] == b[0]:
            continue
        if t == "oneof" and not (b[0] == c[0] and a[0] != b[0]):
            continue
        if t == "between" and not (a not in (b, c)):
            continue
        cl = {"same": ("same", a, b), "diff": ("diff", a, b), "before": ("before", a, b), "adj": ("adj", a, b), "next": ("next", a, b),
              "gap2": ("gap2", a, b), "at": ("at", a, rng.randint(1, n)), "notat": ("notat", a, rng.randint(1, n)), "end": ("end", a),
              "notend": ("notend", a), "oneof": ("oneof", a, b, c), "between": ("between", a, b, c)}[t]
        if _holds(cl, truth, n):
            return cl
    return None


CATNOUN = {"shed": "shed colours", "awning": "awning colours", "scarf": "scarf colours", "bike": "bike colours", "lock": "lock types", "clay": "clays",
           "piece": "pieces", "topic": "topics", "demo": "demos", "part": "voice parts", "dessert": "desserts", "tool": "tools", "laptop": "laptops",
           "glaze": "glazes", "payment": "payment methods", "shift": "shifts", "solo": "solos", "helmet": "helmets", "assay": "assays", "instrument": "instruments",
           "product": "products", "crop": "crops", "dish": "dishes", "drink": "drinks"}


@family("chat-logic-grid", category="chat", lang="text", kind="puzzle", n=14, mode="answer",
        summary="who-sat-where logic grids with a unique solution (verified by a solver); the answer is a pair of digit strings")
def gen_grid(rng, n_inst):
    plan = [(3, 2, 1), (3, 3, 2), (4, 2, 2), (4, 3, 3), (4, 3, 3), (5, 2, 3), (5, 3, 4), (5, 3, 5), (3, 3, 2), (4, 3, 3), (5, 3, 4), (4, 2, 2), (5, 3, 5), (4, 3, 3)]
    for i in range(n_inst):
        n, n_attr, d = plan[i % len(plan)]
        theme = rng.choice(THEMES)
        cats_def = list(theme["cats"]) + [EXTRA_CATS[theme["key"]]]
        cats_def = cats_def[:n_attr]
        names = C.pick_names(rng, n)
        cat_items = [names] + [rng.sample(c[1], n) for c in cats_def]
        k = len(cat_items)
        vars_ = [(c, j) for c in range(k) for j in range(n)]
        truth = {}
        for c in range(k):
            perm = list(range(1, n + 1))
            rng.shuffle(perm)
            for j in range(n):
                truth[(c, j)] = perm[j]
        kinds = ["same", "diff", "before", "adj", "next", "at", "notat", "end", "notend", "oneof"]
        if d >= 4:
            kinds += ["between", "gap2", "before", "adj", "diff", "oneof"]
        if d == 5:
            kinds = [x for x in kinds if x != "same"] + ["diff", "between", "gap2"]
        clues = []
        tries = 0
        while True:
            cl = _sample_clue(rng, truth, vars_, n, kinds, k)
            tries += 1
            if cl and cl not in clues:
                clues.append(cl)
            if len(clues) >= 5 * n * k // 2 and count_solutions(vars_, range(k), clues, n) == 1:
                break
            if tries > 600:
                raise RuntimeError("logic grid: could not reach uniqueness")
        order = list(range(len(clues)))
        rng.shuffle(order)
        keep = list(clues)
        for idx in order:
            trial = [c for c in keep if c != clues[idx]]
            if count_solutions(vars_, range(k), trial, n) == 1:
                keep = trial
        rng.shuffle(keep)
        assert count_solutions(vars_, range(k), keep, n, limit=3) == 1
        slot, person = theme["slot"], theme["person"]

        def vp(c, j):
            if c == 0:
                return f"is {cat_items[0][j]}"
            return cats_def[c - 1][2].format(cat_items[c][j])

        def desc(c, j):
            if c == 0:
                return cat_items[0][j]
            return f"the {person} who {vp(c, j)}"

        def cap(x):
            return x[0].upper() + x[1:]

        def text(cl):
            t = cl[0]
            if t == "same":
                return f"{cap(desc(*cl[1]))} {vp(*cl[2])}."
            if t == "diff":
                b2 = cl[2]
                if b2[0] == 0:
                    return f"{cap(desc(*cl[1]))} is not {cat_items[0][b2[1]]}."
                return f"{cap(desc(*cl[1]))} is not the {person} who {vp(*b2)}."
            if t == "before":
                return f"{cap(desc(*cl[1]))} is in a lower-numbered {slot} than {desc(*cl[2])}."
            if t == "adj":
                return f"{cap(desc(*cl[1]))} and {desc(*cl[2])} are in neighbouring {slot}s."
            if t == "next":
                return f"{cap(desc(*cl[1]))} is in a {slot} numbered exactly one lower than the {slot} of {desc(*cl[2])}."
            if t == "gap2":
                return f"{cap(desc(*cl[1]))} and {desc(*cl[2])} are exactly two {slot}s apart."
            if t == "at":
                return f"{cap(desc(*cl[1]))} is in {slot} {cl[2]}."
            if t == "notat":
                return f"{cap(desc(*cl[1]))} is not in {slot} {cl[2]}."
            if t == "end":
                return f"{cap(desc(*cl[1]))} is in one of the two end {slot}s."
            if t == "notend":
                return f"{cap(desc(*cl[1]))} is not in either end {slot}."
            if t == "oneof":
                return f"{cap(desc(*cl[1]))} is either {desc(*cl[2])} or {desc(*cl[3])}."
            return f"{cap(desc(*cl[1]))} is in a {slot} somewhere between those of {desc(*cl[2])} and {desc(*cl[3])} (in either order)."

        data = "\n".join(f"{j + 1}. {C.fix_articles(text(cl))}" for j, cl in enumerate(keep))
        listing = f"The {person}s are {', '.join(names[:-1])} and {names[-1]}."
        items2 = list(cat_items[1])
        code1 = "".join(str(truth[(0, j)]) for j in range(n))
        code2 = "".join(str(truth[(1, j)]) for j in range(n))
        cat1 = cats_def[0][0]
        scene = rng.choice(theme["scene"]).format(n=n)
        ask = (f"Work out the full arrangement, then give me two strings of digits. First: the {slot} numbers of {', '.join(names)}, in that order. "
               f"Second: the {slot} numbers belonging to these {CATNOUN.get(cat1, cat1 + 's')}, in the order I list them: {', '.join(items2)}.")
        what = [c[0] for c in cats_def]
        owns = ", ".join(f"one {w}" for w in what[:-1]) + f" and one {what[-1]}" if len(what) > 1 else f"one {what[0]}"
        intro = f"{scene} {theme['layout'].format(n=n)} {listing} Everyone has exactly {owns}, and no two people share any of these. Here is everything I know:"
        prompt = C.chat(rng, intro, ask, data, C.register_for(rng))
        contains = [code1] if code1 == code2 else [code1, code2]
        keepc = C.unseen(prompt, contains, True, min_keep=len(contains))
        if keepc is None:
            continue_flag = True
            raise RuntimeError("code in prompt")
        gold = f"{code1} and {code2}"
        yield C.answer_task(f"{i + 1:02d}-{theme['key']}-{n}x{n_attr}", prompt, d, contains, gold, fold=True,
                            tags=["logic", "puzzle"], notes={"n": n, "attrs": n_attr, "clues": len(keep), "theme": theme["key"]})


# --------------------------------------------------------------------------------------------------------------------
# chat-ordering-puzzle

ORDER_SCENES = [
    ("Our shop is staging a pretend bakery queue for a photo shoot: {n} people, spot 1 at the front and spot {n} at the back.", "person", "spot in the queue"),
    ("We are setting the running order for a {n}-leg relay (leg 1 starts the race).", "runner", "leg"),
    ("I am putting {n} books back on a shelf and spot 1 is the leftmost.", "book", "spot on the shelf"),
    ("We are lining {n} people up for a team photo, spot 1 at the left end.", "person", "spot in the row"),
    ("I am building the running order for a school showcase: {n} acts, act 1 goes first.", "act", "place in the running order"),
    ("A car ferry loads {n} vehicles into one lane and number 1 boards first.", "vehicle", "place in the loading order"),
]
THINGS_ORDER = {
    "person": ["Ines", "Tobias", "Mina", "Culver", "Dalia", "Rufus", "Petra", "Osei", "Noor", "Lev"],
    "runner": ["Ines", "Tobias", "Mina", "Culver", "Dalia", "Rufus", "Petra", "Osei", "Noor", "Lev"],
    "book": ["the atlas", "the cookbook", "the thriller", "the almanac", "the poetry volume", "the field guide", "the dictionary", "the biography", "the manual", "the diary"],
    "act": ["the jugglers", "the string trio", "the poet", "the magician", "the choir", "the mime", "the drummer", "the comedian", "the dancers", "the ukulele band"],
    "vehicle": ["the red van", "the tractor", "the caravan", "the minibus", "the bicycle group", "the horsebox", "the delivery truck", "the hearse", "the camper", "the estate car"],
}


@family("chat-ordering-puzzle", category="chat", lang="text", kind="puzzle", n=12, mode="answer",
        summary="work out one linear order from before/next/end/gap clues (unique by brute force); answer is a digit string")
def gen_order(rng, n_inst):
    plan = [5, 5, 6, 6, 6, 7, 7, 8, 5, 6, 7, 8]
    for i in range(n_inst):
        n = plan[i % len(plan)]
        d = {5: 2, 6: 3, 7: 4, 8: 5}[n]
        scene_t, noun, place = rng.choice(ORDER_SCENES)
        items = rng.sample(THINGS_ORDER[noun], n)
        order = list(range(n))
        rng.shuffle(order)
        pos = {item: p + 1 for p, item in enumerate(order)}  # item index -> position
        truth = {(0, j): pos[j] for j in range(n)}
        vars_ = [(0, j) for j in range(n)]
        kinds = ["before", "adj", "next", "gap2", "at", "notat", "end", "notend", "between", "before"]
        clues = []
        for _ in range(3000):
            if len(clues) >= 3 * n and count_solutions(vars_, [0], clues, n) == 1:
                break
            cl = _sample_clue(rng, truth, vars_, n, kinds, 1)
            if cl and cl not in clues:
                clues.append(cl)
        else:
            raise RuntimeError("order puzzle: not unique")
        keep = list(clues)
        idxs = list(range(len(clues)))
        rng.shuffle(idxs)
        for idx in idxs:
            trial = [c for c in keep if c != clues[idx]]
            if count_solutions(vars_, [0], trial, n) == 1:
                keep = trial
        rng.shuffle(keep)

        def nm(j):
            return items[j]

        lines = []
        for cl in keep:
            t = cl[0]
            A = nm(cl[1][1])
            if t == "before":
                s = f"{A} comes somewhere before {nm(cl[2][1])}."
            elif t == "adj":
                s = f"{A} and {nm(cl[2][1])} are right next to each other (in either order)."
            elif t == "next":
                s = f"{A} comes immediately before {nm(cl[2][1])}."
            elif t == "gap2":
                s = f"There is exactly one other {noun} between {A} and {nm(cl[2][1])}."
            elif t == "at":
                s = f"{A} is number {cl[2]}."
            elif t == "notat":
                s = f"{A} is not number {cl[2]}."
            elif t == "end":
                s = f"{A} is either first or last."
            elif t == "notend":
                s = f"{A} is neither first nor last."
            else:
                s = f"{A} is somewhere between {nm(cl[2][1])} and {nm(cl[3][1])} (in either order)."
            lines.append(s[0].upper() + s[1:])
        data = "\n".join(f"{j + 1}. {s}" for j, s in enumerate(lines))
        alpha = sorted(range(n), key=lambda j: items[j])
        code = "".join(str(pos[j]) for j in alpha)
        item_list = ", ".join(items[j] for j in alpha)
        intro = rng.choice([scene_t.format(n=n) + " I lost the sheet but I remember these things:",
                            "Quick logic puzzle for the group chat. " + scene_t.format(n=n) + " Clues:",
                            scene_t.format(n=n) + " People gave me a few facts that should pin it down:"])
        ask = f"Which {place} does each one get? Give me one string of {n} digits: the numbers for {item_list}, in exactly that (alphabetical) order."
        prompt = C.chat(rng, intro, ask, data, C.register_for(rng))
        if not C.uniq_in_prompt_ok(prompt, [code]):
            continue
        yield C.answer_task(f"{i + 1:02d}-{n}items", prompt, d, [code], f"{code}", fold=True, tags=["logic", "puzzle"], notes={"n": n, "clues": len(keep)})


# --------------------------------------------------------------------------------------------------------------------
# chat-probability-small


def _frac(f: Fraction) -> str:
    return f"{f.numerator}/{f.denominator}" if f.denominator != 1 else f"{f.numerator}"


@family("chat-probability-small", category="chat", lang="text", kind="lookup", n=14, mode="answer",
        summary="exact small-number probabilities by enumeration: draws, custom dice, shuffles, committees, conditional on a pasted table, expected payout")
def gen_prob(rng, n_inst):
    plan = [2, 2, 3, 3, 3, 4, 4, 4, 5, 2, 3, 4, 3, 5]
    for i in range(n_inst):
        d = plan[i % len(plan)]
        for _attempt in range(100):
            kind = rng.choice({2: ["draw", "dice"], 3: ["draw2", "shuffle", "dice"], 4: ["committee", "table", "shuffle", "replace"], 5: ["table2", "shuffle2", "game"]}[d])
            data = None
            if kind == "draw":
                a, b = rng.randint(3, 6), rng.randint(4, 8)
                k = 3
                total = list(itertools.combinations(range(a + b), k))
                p = 1 - Fraction(sum(1 for c in total if all(x >= a for x in c)), len(total))
                what = rng.choice([("fuses", "blown", "good"), ("batteries", "flat", "fine"), ("eggs", "cracked", "intact"), ("pens", "dried-out", "working")])
                intro = f"A box holds {a + b} {what[0]}, and {a} of them are {what[1]} (the rest {what[2]}). I grab {k} at random without looking, and I do not put any back."
                ask = f"What is the probability that at least one of the {k} I grab is {what[1]}? Give it as a reduced fraction like 7/20."
            elif kind == "draw2":
                red, blue, green = rng.randint(2, 4), rng.randint(2, 4), rng.randint(2, 3)
                items = ["R"] * red + ["B"] * blue + ["G"] * green
                combos = list(itertools.permutations(range(len(items)), 2))
                p = Fraction(sum(1 for x, y in combos if items[x] != items[y]), len(combos))
                intro = f"A bag has {red} red, {blue} blue and {green} green wooden tiles. I draw one tile, keep it out, then draw a second."
                ask = "What is the probability that the two tiles are different colours? Please give a reduced fraction like 11/30."
            elif kind == "dice":
                f1 = sorted(rng.choices([1, 2, 3, 4, 5, 6, 8], k=6))
                f2 = sorted(rng.choices([0, 1, 2, 3, 4, 5, 7], k=6))
                thr = rng.randint(5, 9)
                cnt = sum(1 for x in f1 for y in f2 if x + y >= thr)
                p = Fraction(cnt, 36)
                if p == 0 or p == 1:
                    continue
                intro = (f"For our board game I made two custom dice. Die A has the faces {', '.join(map(str, f1))} and die B has {', '.join(map(str, f2))}. "
                         f"We roll both and add the numbers.")
                ask = f"What is the probability that the total is at least {thr}? Reduced fraction please."
            elif kind == "shuffle":
                m = rng.randint(5, 7)
                perms = list(itertools.permutations(range(m)))
                p = Fraction(sum(1 for q in perms if abs(q.index(0) - q.index(1)) == 1), len(perms))
                intro = f"My playlist has {m} songs and I put it on shuffle (every ordering equally likely, each song played once). Two of the songs are my absolute favourites."
                ask = "What is the probability that my two favourites play back to back, in either order? Reduced fraction, e.g. 2/7."
            elif kind == "shuffle2":
                m = rng.randint(6, 7)
                perms = list(itertools.permutations(range(m)))
                p = Fraction(sum(1 for q in perms if q.index(0) < q.index(1) < q.index(2) < q.index(3)), len(perms)) if rng.random() < 0.0 else \
                    Fraction(sum(1 for q in perms if q.index(0) < q.index(1) < q.index(2) and q.index(3) > q.index(2)), len(perms))
                intro = f"A band has {m} songs on the set list and the order is drawn at random from a hat (all orders equally likely). Call the songs 1 to {m}."
                ask = "What is the probability that song 1 is played before song 2, song 2 before song 3, and song 4 is played after song 3? Reduced fraction."
            elif kind == "committee":
                w, m = rng.randint(4, 6), rng.randint(3, 5)
                k = 3
                combos = list(itertools.combinations(range(w + m), k))
                p = Fraction(sum(1 for c in combos if any(x < w for x in c) and 0 not in c), len(combos))
                intro = f"A club of {w + m} members ({w} women and {m} men) draws a {k}-person committee at random. Priya is one of the {w} women."
                ask = "What is the probability that the committee has at least one woman and does not include Priya? Reduced fraction."
            elif kind == "replace":
                tick = rng.randint(8, 20)
                k = rng.randint(3, 5)
                wins = rng.randint(1, 3)
                p = 1 - (1 - Fraction(wins, tick)) ** k
                intro = f"A raffle drum holds {tick} tickets and {wins} of them win a prize. After each draw the ticket goes back in the drum and it is shaken again. I draw {k} times."
                ask = "What is the probability that I win at least once? Please give an exact reduced fraction."
            elif kind in ("table", "table2"):
                groups = rng.sample(["cyclists", "walkers", "bus riders", "drivers"], 3)
                cnts = [[rng.randint(5, 40), rng.randint(2, 25)] for _ in groups]
                rows = [[g, c[0], c[1]] for g, c in zip(groups, cnts)]
                data = C.block(C.table(rows, ["commute", "on time", "late"]))
                intro = "A survey of one office's commutes gave the table below. I pick one respondent at random from everyone."
                g = rng.randrange(3)
                if kind == "table":
                    p = Fraction(cnts[g][1], sum(cnts[g]))
                    ask = f"Given that the person I pick is one of the {groups[g]}, what is the probability they were late? Reduced fraction."
                else:
                    late = sum(c[1] for c in cnts)
                    p = Fraction(cnts[g][1], late)
                    ask = f"Given that the person I pick was late, what is the probability that they were one of the {groups[g]}? Reduced fraction."
            else:  # game
                nf = rng.randint(2, 4)
                faces = rng.sample(range(1, 7), nf)
                pay = {f: rng.choice([-3, -2, -1, 1, 2, 4, 5, 8, 10]) for f in faces}
                p = Fraction(sum(pay.values()), 6)
                lines = ", ".join(f"a {f} pays {'+' if v > 0 else ''}{v} coins" for f, v in sorted(pay.items()))
                intro = f"At the school fair there is a game with one fair six-sided die. {lines[0].upper() + lines[1:]}, and any other number pays nothing."
                ask = "What is the expected payout per roll, as an exact reduced fraction (or a whole number)? Write a negative one with a minus sign."
                if p == 0 or (p.denominator == 1 and abs(p) < 4):
                    continue
            contains = [_frac(p)]
            prompt = C.chat(rng, intro, ask, data, C.register_for(rng))
            if not C.uniq_in_prompt_ok(prompt, contains):
                continue
            yield C.answer_task(f"{i + 1:02d}-{kind}", prompt, d, contains, _frac(p), tags=["probability"], notes={"kind": kind})
            break
        else:
            raise RuntimeError("prob: no instance")


# --------------------------------------------------------------------------------------------------------------------
# chat-counting-small


def _count_codes(alphabet, L, rule):
    cnt = 0
    for tup in itertools.product(alphabet, repeat=L):
        if rule(tup):
            cnt += 1
    return cnt


@family("chat-counting-small", category="chat", lang="text", kind="lookup", n=12, mode="answer",
        summary="count codes, seatings, grid routes and handouts under constraints; the number comes from brute force")
def gen_counting(rng, n_inst):
    plan = [2, 3, 3, 4, 4, 5, 2, 3, 4, 5, 3, 4]
    for i in range(n_inst):
        d = plan[i % len(plan)]
        for _attempt in range(100):
            kind = rng.choice({2: ["codes_simple", "handout"], 3: ["codes_adj", "routes"], 4: ["seating", "codes_vowel", "routes2"], 5: ["seating2", "codes_combo"]}[d])
            data = None
            if kind == "codes_simple":
                L = rng.randint(3, 4)
                alpha = rng.choice(["ABCDEF", "1234567", "XYZWQ"])
                cnt = _count_codes(alpha, L, lambda t: len(set(t)) == L)
                intro = f"The bike-shed padlock takes a {L}-character code. Each character is one of {', '.join(alpha)}, and the manufacturer says the characters in one code must all be different."
                ask = "How many different codes are possible?"
            elif kind == "handout":
                k = rng.randint(3, 4)
                total = rng.randint(8, 12)
                cap = rng.randint(4, 6)
                cnt = sum(1 for xs in itertools.product(range(cap + 1), repeat=k) if sum(xs) == total)
                if cnt == 0:
                    continue
                intro = f"I have {total} identical raffle prizes to hand out to {k} named winners. Everyone must get a whole number of prizes (zero is allowed), but nobody may get more than {cap}."
                ask = "In how many different ways can I hand them out? Two ways differ if some winner gets a different number."
            elif kind == "codes_adj":
                L = rng.randint(4, 5)
                alpha = rng.choice(["ABC", "ABCD", "12345", "RGBY"])
                cnt = _count_codes(alpha, L, lambda t: all(t[j] != t[j + 1] for j in range(L - 1)))
                intro = f"A door keypad has the buttons {', '.join(alpha)}. The code is {L} presses long, and the lock refuses a code where the same button is pressed twice in a row."
                ask = "How many valid codes are there?"
            elif kind == "codes_vowel":
                L = rng.randint(4, 5)
                alpha = rng.choice(["AEBCD", "AEKLMN", "IOPQRS"])
                vow = set("AEIOU")
                cnt = _count_codes(alpha, L, lambda t: any(c in vow for c in t) and all(t[j] != t[j + 1] for j in range(L - 1)))
                intro = f"A locker code is {L} characters from this set: {', '.join(alpha)}. Rules: no character may repeat in two adjacent places, and at least one of the characters must be a vowel (A, E, I, O, U)."
                ask = "How many codes satisfy both rules?"
            elif kind == "codes_combo":
                L = 5
                alpha = rng.choice(["ABCDE", "12345X"])
                cnt = _count_codes(alpha, L, lambda t: t[0] != t[-1] and all(t[j] != t[j + 1] for j in range(L - 1)) and len(set(t)) >= 3)
                intro = (f"A safe uses a {L}-symbol code over the symbols {', '.join(alpha)}. The rules from the manual: no symbol directly next to itself, the first and last "
                         f"symbols must differ, and at least 3 different symbols must appear in the code.")
                ask = "How many codes does that allow?"
            elif kind in ("routes", "routes2"):
                R, Cc = rng.randint(4, 6), rng.randint(4, 6)
                nb = rng.randint(1, 3) if kind == "routes" else rng.randint(3, 5)
                blocked = set()
                while len(blocked) < nb:
                    b2 = (rng.randrange(R), rng.randrange(Cc))
                    if b2 not in ((0, 0), (R - 1, Cc - 1)):
                        blocked.add(b2)
                dp = [[0] * Cc for _ in range(R)]
                dp[0][0] = 1
                for r in range(R):
                    for c in range(Cc):
                        if (r, c) in blocked or (r, c) == (0, 0):
                            continue
                        dp[r][c] = (dp[r - 1][c] if r else 0) + (dp[r][c - 1] if c else 0)
                cnt = dp[R - 1][Cc - 1]
                if cnt < 5:
                    continue
                grid = "\n".join("".join("#" if (r, c) in blocked else ("S" if (r, c) == (0, 0) else "E" if (r, c) == (R - 1, Cc - 1) else ".") for c in range(Cc)) for r in range(R))
                data = C.block(grid)
                intro = ("My delivery robot moves on a grid of streets. It starts at S (top left) and must reach E (bottom right), and it can only move one cell right or "
                         "one cell down at a time. Cells marked # are closed for roadworks.")
                ask = "How many different routes can it take?"
            else:  # seating
                m = rng.randint(5, 6) if kind == "seating" else rng.randint(6, 7)
                people = C.pick_names(rng, m)
                npairs = rng.randint(2, 3) if kind == "seating" else rng.randint(3, 4)
                pairs = rng.sample(list(itertools.combinations(range(m), 2)), npairs)
                cnt = sum(1 for q in itertools.permutations(range(m)) if all(abs(q.index(a) - q.index(b2)) != 1 for a, b2 in pairs))
                txt = "; ".join(f"{people[a]} and {people[b2]}" for a, b2 in pairs)
                intro = f"We are seating {m} people in a single row of {m} chairs: {', '.join(people)}. Some of them have fallen out, so these pairs must not sit next to each other: {txt}."
                ask = "In how many different ways can the row be filled? Every distinct left-to-right order counts as one way."
            contains = [str(cnt)]
            prompt = C.chat(rng, intro, ask + C.nosep(contains), data, C.register_for(rng))
            if not C.uniq_in_prompt_ok(prompt, contains):
                continue
            yield C.answer_task(f"{i + 1:02d}-{kind}", prompt, d, contains, str(cnt), tags=["counting"], notes={"kind": kind})
            break
        else:
            raise RuntimeError("counting: no instance")


# --------------------------------------------------------------------------------------------------------------------
# chat-rota-simulation

OPS = ["rot", "swap", "rev", "tofront"]


def _apply(ops, arr):
    a = list(arr)
    for op in ops:
        if op[0] == "rot":
            k = op[1] % len(a)
            a = a[k:] + a[:k]
        elif op[0] == "swap":
            a[op[1]], a[op[2]] = a[op[2]], a[op[1]]
        elif op[0] == "rev":
            a[op[1]:op[2] + 1] = reversed(a[op[1]:op[2] + 1])
        elif op[0] == "tofront":
            a = [a[op[1]]] + a[:op[1]] + a[op[1] + 1:]
    return a


def _op_text(op, nm="person"):
    if op[0] == "rot":
        return f"the first {op[1]} {nm}{'s' if op[1] > 1 else ''} in the list move to the back, keeping their order"
    if op[0] == "swap":
        return f"the people in positions {op[1] + 1} and {op[2] + 1} swap places"
    if op[0] == "rev":
        return f"positions {op[1] + 1} to {op[2] + 1} are reversed"
    return f"the person in position {op[1] + 1} jumps to the front of the list"


@family("chat-rota-simulation", category="chat", lang="text", kind="lookup", n=10, mode="answer",
        summary="a rota that is reshuffled by a fixed rule every week: who is where after many weeks (cycle structure matters)")
def gen_rota(rng, n_inst):
    plan = [2, 3, 3, 4, 4, 5, 3, 4, 5, 2]
    for i in range(n_inst):
        d = plan[i % len(plan)]
        for _attempt in range(100):
            m = {2: 5, 3: 6, 4: 7, 5: 8}[d]
            nops = {2: 1, 3: 2, 4: 3, 5: 4}[d]
            ops = []
            for _ in range(nops):
                t = rng.choice(OPS)
                if t == "rot":
                    ops.append(("rot", rng.randint(1, m - 1)))
                elif t == "swap":
                    a, b = rng.sample(range(m), 2)
                    ops.append(("swap", a, b))
                elif t == "rev":
                    a = rng.randrange(m - 2)
                    b = rng.randint(a + 2, m - 1)
                    ops.append(("rev", a, b))
                else:
                    ops.append(("tofront", rng.randint(2, m - 1)))
            people = []
            pool = C.pick_names(rng, 20)
            seen = set()
            for nm in pool:
                if nm[0] not in seen:
                    seen.add(nm[0])
                    people.append(nm)
                if len(people) == m:
                    break
            if len(people) < m:
                continue
            arr = list(range(m))
            # cycle length of the permutation
            cur = list(range(m))
            period = 0
            state = cur
            while True:
                state = _apply(ops, state)
                period += 1
                if state == cur or period > 5000:
                    break
            N = rng.choice([40, 97, 150, 365, 1000, 2500, 10000, 123456]) if d >= 3 else rng.choice([20, 50, 100])
            if period > 3000 or period == 1:
                continue
            final = list(range(m))
            Neff = N % period
            for _ in range(Neff):
                final = _apply(ops, final)
            code = "".join(people[j][0] for j in final)
            start_code = "".join(p[0] for p in people)
            if code == start_code:
                continue
            what = rng.choice(["washing-up", "bin duty", "morning shift", "cleaning", "lunch-order"])
            steps = "; then ".join(_op_text(o) for o in ops)
            intro = (f"Our flat has a {what} rota. The list is: {', '.join(people)} (position 1 is first, and the person in position 1 has the duty that week). "
                     f"Every Sunday night the list is reshuffled by the same rule, applied in this order: {steps}.")
            ask = (f"Week 1 uses the list exactly as written above. Who is in each position in week {N + 1}? Give me the first letters of the names, left to right, as one string, e.g. {start_code}.")
            prompt = C.chat(rng, intro, ask, None, C.register_for(rng))
            if not C.uniq_in_prompt_ok(prompt, [code]):
                continue
            yield C.answer_task(f"{i + 1:02d}-{m}p-{N}w", prompt, d, [code], code, tags=["simulation", "cycles"], notes={"period": period, "weeks": N, "ops": [list(o) for o in ops]})
            break
        else:
            raise RuntimeError("rota: no instance")

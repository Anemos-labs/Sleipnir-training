"""Recipe scaling and pantry questions, phrased the way a cook would ask them. Answers are computed with exact fractions."""
from __future__ import annotations

import math
from fractions import Fraction

from fx import family

from . import _common as C

# (name, servings choices, [(ingredient, unit, lo, hi, step)])
RECIPES = [
    ("walnut-date loaf", (6, 8, 12), [("plain flour", "g", 200, 350, 25), ("chopped dates", "g", 100, 180, 20), ("walnuts", "g", 50, 100, 10),
                                      ("brown sugar", "g", 60, 120, 10), ("eggs", "egg", 2, 4, 1), ("milk", "ml", 100, 250, 25),
                                      ("melted butter", "g", 60, 120, 10), ("baking powder", "tsp", 2, 3, 1)]),
    ("smoky lentil stew", (4, 6, 8), [("brown lentils", "g", 200, 400, 25), ("tinned tomatoes", "g", 300, 500, 50), ("onions", "g", 150, 300, 25),
                                      ("vegetable stock", "ml", 600, 1000, 100), ("olive oil", "tbsp", 1, 3, 1), ("smoked paprika", "tsp", 1, 3, 1),
                                      ("carrots", "g", 150, 300, 25)]),
    ("lemon polenta cake", (8, 10, 12), [("ground almonds", "g", 150, 250, 25), ("fine polenta", "g", 100, 150, 10), ("caster sugar", "g", 150, 220, 10),
                                         ("eggs", "egg", 3, 5, 1), ("olive oil", "ml", 100, 150, 10), ("lemon juice", "ml", 50, 100, 10),
                                         ("baking powder", "tsp", 2, 3, 1)]),
    ("harvest barley soup", (4, 6, 10), [("pearl barley", "g", 120, 200, 20), ("leeks", "g", 200, 400, 50), ("celeriac", "g", 200, 300, 25),
                                         ("chicken stock", "ml", 900, 1500, 100), ("butter", "g", 30, 60, 10), ("dried thyme", "tsp", 1, 2, 1),
                                         ("white beans", "g", 200, 400, 50)]),
    ("miso aubergine bake", (4, 6), [("aubergines", "g", 500, 900, 50), ("white miso", "tbsp", 2, 4, 1), ("rice vinegar", "ml", 30, 60, 10),
                                     ("sesame oil", "tsp", 2, 4, 1), ("cooked rice", "g", 300, 600, 50), ("spring onions", "g", 60, 120, 20),
                                     ("maple syrup", "tbsp", 1, 3, 1)]),
    ("cardamom oat cookies", (12, 18, 24), [("rolled oats", "g", 180, 300, 20), ("plain flour", "g", 100, 160, 20), ("butter", "g", 120, 200, 20),
                                            ("light brown sugar", "g", 100, 170, 10), ("eggs", "egg", 1, 2, 1), ("ground cardamom", "tsp", 1, 2, 1),
                                            ("raisins", "g", 60, 120, 20)]),
    ("tomato and fennel risotto", (4, 6), [("arborio rice", "g", 250, 400, 25), ("fennel bulbs", "g", 250, 450, 50), ("passata", "ml", 250, 400, 50),
                                           ("vegetable stock", "ml", 900, 1200, 100), ("white wine", "ml", 100, 200, 25), ("parmesan", "g", 40, 80, 10),
                                           ("butter", "g", 25, 50, 5)]),
    ("beetroot brownies", (9, 12, 16), [("cooked beetroot", "g", 200, 300, 25), ("dark chocolate", "g", 150, 200, 10), ("butter", "g", 100, 150, 10),
                                        ("caster sugar", "g", 120, 200, 10), ("eggs", "egg", 3, 4, 1), ("plain flour", "g", 90, 140, 10),
                                        ("cocoa powder", "tbsp", 2, 4, 1)]),
    ("chickpea shakshuka", (2, 4, 6), [("tinned tomatoes", "g", 400, 800, 50), ("chickpeas", "g", 240, 480, 40), ("red peppers", "g", 150, 300, 50),
                                       ("eggs", "egg", 4, 6, 1), ("olive oil", "tbsp", 1, 3, 1), ("ground cumin", "tsp", 1, 2, 1), ("feta", "g", 80, 160, 20)]),
    ("rye and caraway bread", (8, 12, 16), [("rye flour", "g", 250, 400, 50), ("strong white flour", "g", 250, 400, 50), ("water", "ml", 350, 550, 50),
                                            ("salt", "tsp", 2, 3, 1), ("caraway seeds", "tsp", 2, 4, 1), ("fresh yeast", "g", 15, 30, 5),
                                            ("treacle", "tbsp", 1, 2, 1)]),
    ("plum and ginger crumble", (6, 8), [("plums", "g", 600, 1000, 100), ("stem ginger", "g", 40, 80, 10), ("rolled oats", "g", 80, 120, 20),
                                         ("plain flour", "g", 120, 180, 20), ("butter", "g", 100, 140, 10), ("demerara sugar", "g", 80, 130, 10),
                                         ("orange juice", "ml", 50, 100, 25)]),
    ("coconut dal", (4, 6, 8), [("red lentils", "g", 240, 400, 40), ("coconut milk", "ml", 400, 800, 100), ("onions", "g", 150, 250, 25),
                                ("grated ginger", "tbsp", 1, 2, 1), ("turmeric", "tsp", 1, 2, 1), ("water", "ml", 600, 1000, 100), ("spinach", "g", 100, 200, 50)]),
]
CONV_TEXT = {"tsp": "1 tsp = 5 ml", "tbsp": "1 tbsp = 15 ml", "cup": "1 cup = 240 ml"}
CONV = {"tsp": 5, "tbsp": 15}
UNIT_WORD = {"g": "g", "ml": "ml", "egg": "", "tsp": "tsp", "tbsp": "tbsp"}


def _line(name, unit, q) -> str:
    if unit == "egg":
        return f"- {q} {name}" if q != 1 else "- 1 egg"
    return f"- {q} {UNIT_WORD[unit]} {name}"


def _recipe(rng, idx=None):
    name, servs, ings = RECIPES[idx if idx is not None else rng.randrange(len(RECIPES))]
    S = rng.choice(servs)
    chosen = ings[:]
    rng.shuffle(chosen)
    chosen = chosen[:rng.randint(5, len(chosen))]
    rows = []
    for nm, unit, lo, hi, step in chosen:
        q = rng.randrange(lo, hi + 1, step)
        rows.append((nm, unit, q))
    return name, S, rows


def _recipe_block(name, S, rows):
    return C.block(f"{name} (serves {S})\n" + "\n".join(_line(n, u, q) for n, u, q in rows))


def _integral_targets(S, qs, lo, hi):
    """Targets T in [lo, hi] for which every quantity in qs scales to an integer."""
    return [T for T in range(lo, hi + 1) if T != S and all((Fraction(q) * T / S).denominator == 1 for q in qs)]


INTROS_SCALE = [
    "I am cooking for a bigger crowd than usual and the recipe I use only makes {S}.",
    "my in-laws are coming round so i need to scale up my {rname} recipe",
    "We are doing a potluck at work and I promised to bring my {rname}. The recipe below is the one I always make.",
    "Cooking club tomorrow! I normally make this {rname} for {S} but there will be {T} of us.",
    "I scribbled my {rname} recipe down years ago and now I need it for a different number of people.",
    "Cooking for the {T} of us this weekend and I do not trust myself to multiply while the onions are frying.",
]
INTROS_PANTRY = [
    "I want to make {rname} tonight but the shops are shut and I only have what is in the cupboard.",
    "Pantry check before I commit to {rname}: I do not want to start and then discover I am short.",
    "Fridge and cupboard are nearly empty, so how many servings of this {rname} can I actually manage?",
    "Quick one, I am about to start the {rname} and I think I will run out of something half way through.",
]


@family("chat-recipe-scale", category="chat", lang="text", kind="lookup", n=12, mode="answer",
        summary="scale an invented recipe, convert spoons to millilitres, find what a half-empty cupboard allows, plan pack purchases")
def gen(rng, n):
    plan = [1, 2, 2, 3, 3, 3, 4, 4, 5, 2, 3, 4]
    for i in range(n):
        d = plan[i % len(plan)]
        for _attempt in range(400):
            rname, S, rows = _recipe(rng)
            kind = {1: "scale1", 2: rng.choice(["scale2", "spoon"]), 3: rng.choice(["spoon", "pantry"]), 4: "pantry", 5: "packs"}[d]
            reg = C.register_for(rng)
            if kind in ("scale1", "scale2"):
                k = 1 if kind == "scale1" else 2
                asked = rng.sample([r for r in rows if r[1] in ("g", "ml")], k=min(k, len([r for r in rows if r[1] in ("g", "ml")])))
                Ts = _integral_targets(S, [a[2] for a in asked], max(2, S // 2), S * 4)
                if not Ts:
                    continue
                T = rng.choice(Ts)
                res = [(a[0], a[1], int(Fraction(a[2]) * T / S)) for a in asked]
                contains = [str(r[2]) for r in res]
                names = " and ".join(r[0] for r in res)
                ask = rng.choice([f"How much {names} do I need for {T}?", f"What are the amounts of {names} for {T}?", f"For {T}, what quantity of {names} should I weigh out?"]) + f" Just the number{'s' if len(res) > 1 else ''}, in {'/'.join(sorted({r[1] for r in res}))}."
                intro = rng.choice(INTROS_SCALE).format(S=S, T=T, rname=rname)
                gold = "; ".join(f"{r[0]}: {r[2]} {r[1]}" for r in res) + f" (that is {T}/{S} of the original)."
                prompt = C.chat(rng, intro, ask, _recipe_block(rname, S, rows), reg)
            elif kind == "spoon":
                spoons = [r for r in rows if r[1] in CONV]
                if not spoons:
                    continue
                a = rng.choice(spoons)
                Ts = [T for T in range(max(2, S // 2), S * 4 + 1) if T != S and (Fraction(a[2]) * CONV[a[1]] * T / S).denominator == 1]
                if not Ts:
                    continue
                T = rng.choice(Ts)
                ml = int(Fraction(a[2]) * CONV[a[1]] * T / S)
                contains = [str(ml)]
                intro = rng.choice(INTROS_SCALE).format(S=S, T=T, rname=rname) + " My measuring jug only has millilitres."
                ask = (f"For {T} servings, how many millilitres is the {a[0]} in the recipe? Use {CONV_TEXT[a[1]]}. "
                       f"(The recipe is in {a[1]}, I need the number in ml.)")
                gold = f"{a[0]} for {T}: {a[2]} {a[1]} x {T}/{S} = {ml} ml."
                prompt = C.chat(rng, intro, ask, _recipe_block(rname, S, rows), reg)
            elif kind == "pantry":
                cand = [r for r in rows if r[1] in ("g", "ml", "egg")]
                if len(cand) < 3:
                    continue
                k = 3 if d == 3 else min(len(cand), 4)
                pant = rng.sample(cand, k)
                stock = {}
                for nm, unit, q in pant:
                    per = Fraction(q, S)
                    f = rng.uniform(2.2, 1.8 * S + 3)
                    stock[nm] = max(1, int(float(per) * f)) if unit == "egg" else max(10, int(round(float(per) * f / 10.0)) * 10)
                ratios = {nm: Fraction(stock[nm]) / (Fraction(q) / S) for nm, unit, q in pant}
                lo = min(ratios.values())
                if sum(1 for v in ratios.values() if v == lo) != 1 or math.floor(lo) < 2:
                    continue
                servings = math.floor(lo)
                limiter = [nm for nm, v in ratios.items() if v == lo][0]
                others = [p for p in pant if p[0] != limiter and p[1] != "egg"]
                if not others:
                    continue
                other = rng.choice(others)
                left = Fraction(stock[other[0]]) - Fraction(other[2]) * servings / S
                left_r = int(C.round_half_up(left))
                contains = [str(servings), str(left_r)]
                inv = "\n".join(f"- {stock[nm]} {UNIT_WORD[unit]} {nm}".replace("  ", " ") if unit != "egg" else f"- {stock[nm]} {nm}" for nm, unit, q in pant)
                intro = rng.choice(INTROS_PANTRY).format(rname=rname) + f" Here is the recipe and what I have of the relevant things (the other ingredients I have plenty of):"
                ask = (f"What is the largest whole number of servings I can make, which ingredient runs out first, and how much {other[0]} "
                       f"is left over after cooking that many (nearest whole {UNIT_WORD[other[1]]})?")
                gold = (f"{servings} servings; {limiter} runs out first; {other[0]} left over: {left_r}.")
                prompt = C.chat(rng, intro, ask, _recipe_block(rname, S, rows) + "\n\nI have:\n" + inv, reg, data_after_ask=False)
                # recipe + stock in one pasted block
            else:  # packs
                n2 = rng.randrange(len(RECIPES))
                rname2, S2, rows2 = _recipe(rng, n2)
                shared = [r for r in rows if r[1] in ("g",) and r[0] in [x[0] for x in rows2 if x[1] == "g"]]
                if rname2 == rname or not shared:
                    continue
                ing = shared[0][0]
                q1 = shared[0][2]
                q2 = [x[2] for x in rows2 if x[0] == ing][0]
                T1, T2 = rng.choice([S, S * 2, S + S // 2]), 0
                T2 = rng.choice([S2, S2 * 2, S2 + 2, S2 + S2 // 2])
                total = Fraction(q1) * T1 / S + Fraction(q2) * T2 / S2
                pack = rng.choice([250, 500, 1000])
                packs = math.ceil(total / pack)
                tot_r = int(C.round_half_up(total))
                if total.denominator != 1 or total % pack == 0 or packs < 2:
                    continue
                contains = [str(tot_r), f"{packs} pack"]
                intro = (f"I am cooking two things for a street party and both use {ing}. Recipe one is the {rname}, recipe two is the {rname2}. "
                         f"I need {T1} servings of the first and {T2} of the second.")
                ask = f"How many grams of {ing} do I need in total, and how many {pack} g packs must I buy (whole packs only)? Please write the pack count as a number followed by the word packs."
                gold = f"Total {ing}: {tot_r} g, so {packs} packs of {pack} g."
                data = _recipe_block(rname, S, rows) + "\n\n" + _recipe_block(rname2, S2, rows2)
                prompt = C.chat(rng, intro, ask, data, reg)
            if not C.uniq_in_prompt_ok(prompt, contains, True):
                continue
            yield C.answer_task(f"{i + 1:02d}-{kind}-{rname.split()[0]}", prompt, d, contains, gold, fold=True,
                                tags=["recipe", "units"], notes={"kind": kind, "recipe": rname})
            break
        else:
            raise RuntimeError("recipe family: could not build an instance")

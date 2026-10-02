"""A few open-ended conversational tasks graded by rubric (no verifier command)."""
from fx import Task, family

CASES = [
    ("I have a standup in five minutes and I haven't prepared anything. Give me a way to sound organised in thirty seconds.", 1,
     [("Gives a concrete, usable structure (for example yesterday / today / blockers) rather than generic advice", 3),
      ("Fits the five-minute constraint: short, no long preamble", 2),
      ("Does not invent facts about the user's work", 2)],
     {"max_words": 140}),
    ("My friend keeps cancelling plans at the last minute. How do I bring it up without starting a fight?", 2,
     [("Suggests a calm, specific opening line the user could actually say", 3),
      ("Acknowledges that the friend's side might have reasons, without excusing the pattern", 2),
      ("Avoids moralising and avoids a long lecture", 1)],
     {"max_words": 220}),
    ("Explain what a mutex is to someone who has only ever written single-threaded scripts.", 2,
     [("Uses an everyday analogy and then connects it back to code", 3),
      ("States what goes wrong without a mutex (a race), with a small concrete example", 3),
      ("Mentions deadlock or lock scope as a caveat, briefly", 1)],
     {"max_words": 300, "must_include_any": ["race", "lock"]}),
]


@family("chat-everyday-advice", category="chat", lang="text", kind="advice", n=3, mode="rubric",
        summary="short advice and explanation requests graded by rubric")
def gen(rng, n):
    for i, (prompt, d, rub, checks) in enumerate(CASES[:n]):
        yield Task(slug=f"{i + 1:02d}", prompt=prompt, difficulty=d,
                   rubric=[{"criterion": c, "weight": w} for c, w in rub], checks=checks, tags=["advice", "no-tools"])

"""SQL tasks on an invented genealogy society's family-tree records (recursive ancestry and descent, siblings, cousins, impossible data, overlapping marriages)."""
import random
from datetime import date, timedelta

from fx import dd, family
from generators.data import _sqlkit as K

SCHEMA = dd('''
    CREATE TABLE persons (
      person_id  INTEGER PRIMARY KEY,
      name       TEXT NOT NULL,
      born       INTEGER NOT NULL,          -- year
      died       INTEGER,                   -- year, NULL if alive or unknown
      sex        TEXT NOT NULL CHECK (sex IN ('F', 'M'))
    );
    CREATE TABLE parent_links (
      child_id   INTEGER NOT NULL REFERENCES persons(person_id),
      parent_id  INTEGER NOT NULL REFERENCES persons(person_id),
      kind       TEXT NOT NULL CHECK (kind IN ('birth', 'adoptive')),
      PRIMARY KEY (child_id, parent_id)
    );
    CREATE TABLE marriages (
      marriage_id  INTEGER PRIMARY KEY,
      spouse_a     INTEGER NOT NULL REFERENCES persons(person_id),
      spouse_b     INTEGER NOT NULL REFERENCES persons(person_id),
      married_on   TEXT NOT NULL,           -- YYYY-MM-DD
      ended_on     TEXT                     -- NULL while the marriage lasted until the end of the records
    );
''')

DOC = dd('''
    The Wicker Lane Genealogy Society keeps a database of family-tree research.

    * `parent_links` connects a child to a parent. `kind` is `birth` or `adoptive`. A person has at most two birth parents on record, sometimes only one or none (unknown).
    * **Siblings** share at least one *birth* parent (adoptive links do not make siblings). **Full** siblings share two birth parents, **half** siblings exactly one.
    * **Descendants** and **ancestors** follow links of any kind unless a task says otherwise.
    * `born` and `died` are years. `died` is NULL for living people and when the death is unknown. A *lifespan* is `died - born`.
    * A `marriages` row joins two persons from `married_on` until `ended_on` (inclusive); NULL means it was never ended in the records.
    * The records are research notes, so they contain mistakes: that is what some reports look for.
''')

FIRST_F = ["Agnes", "Beatrix", "Clara", "Dagny", "Edith", "Frida", "Greta", "Hilda", "Ingrid", "Johanna", "Karin", "Lotte", "Marta", "Nora", "Olga", "Petra", "Rosa", "Sigrid", "Thea", "Ulla", "Vera", "Wilma", "Yrsa", "Zelda"]
FIRST_M = ["Anton", "Bertil", "Carl", "Dirk", "Emil", "Fritz", "Gustav", "Hugo", "Ivar", "Jonas", "Karl", "Lars", "Magnus", "Nils", "Otto", "Pieter", "Rolf", "Sven", "Tobias", "Ulrich", "Viggo", "Willem", "Yngve", "Zeno"]
SURN = ["Ashdown", "Bramley", "Colthorpe", "Dunmore", "Elmsworth", "Fairlight", "Garrowby"]


def gen(rng, big):
    persons, links, marriages = [], [], []
    ff, fm = [b + v for v in ('', 'ke', 'lyn', 'ton', 'sa', 'ne', 'da', 'ra') for b in FIRST_F], [b + v for v in ('', 'ke', 'son', 'ton', 'os', 'er', 'an', 'ic') for b in FIRST_M]
    rng.shuffle(ff)
    rng.shuffle(fm)
    pid = 0

    def person(born, sex, surname):
        nonlocal pid
        pid += 1
        first = (ff if sex == "F" else fm).pop()
        died = None
        if born < 1935 and rng.random() < 0.85:
            died = born + rng.randint(28, 96)
            if died > 2030:
                died = None
        persons.append([pid, f"{first} {surname}", born, died, sex])
        return pid

    mid = 0
    nfam = 4 if big else 2
    byid = lambda i: persons[i - 1]
    for fam in range(nfam):
        sn = SURN[fam]
        b = rng.randint(1835, 1855)
        mother, father = person(b, "F", sn), person(b + rng.randint(-2, 6), "M", sn)
        couples = [(mother, father)]
        depth = 3
        for g in range(depth):
            nxt = []
            for m, f in couples:
                mid += 1
                wed = date(byid(m)[2] + rng.randint(19, 28), rng.randint(1, 12), rng.randint(1, 28))
                marriages.append([mid, m, f, wed.isoformat(), None])
                kids = []
                born_y = wed.year + 1
                for k in range(3 if g == 0 else rng.randint(1, 3)):
                    sex = rng.choice("FM")
                    c = person(born_y + 2 * k, sex, sn)
                    kids.append(c)
                    links.append((c, m, "birth"))
                    if rng.random() > 0.15:
                        links.append((c, f, "birth"))
                # father remarries: half siblings
                if rng.random() < 0.35 and g < depth:
                    marriages[-1][4] = date(born_y + 8, 6, 1).isoformat()
                    sp = person(byid(f)[2] + rng.randint(2, 10), "F", rng.choice(SURN))
                    mid += 1
                    marriages.append([mid, sp, f, date(born_y + 9, 5, 5).isoformat(), None])
                    for k in range(rng.randint(1, 2)):
                        c = person(born_y + 10 + 2 * k, rng.choice("FM"), sn)
                        kids.append(c)
                        links.append((c, sp, "birth"))
                        links.append((c, f, "birth"))
                for c in kids:
                    if byid(c)[2] + 20 > 2020 or g == depth - 1:
                        continue
                    if (g == 0 and kids.index(c) < 2) or rng.random() < 0.55:
                        spouse = person(byid(c)[2] + rng.randint(-4, 6), "M" if byid(c)[4] == "F" else "F", rng.choice(SURN))
                        nxt.append((c, spouse) if byid(c)[4] == "F" else (spouse, c))
            couples = nxt
    # adoptive links: a few children also get an adoptive parent, and one child has only an adoptive link
    kids = sorted({l[0] for l in links})
    adopt = rng.sample(kids, 3 if big else 2)
    for c in adopt[:-1]:
        cand = [p[0] for p in persons if p[2] < byid(c)[2] - 22 and (c, p[0], "birth") not in links and (c, p[0], "adoptive") not in links]
        if cand:
            links.append((c, rng.choice(cand), "adoptive"))
    only = adopt[-1]
    links = [l for l in links if l[0] != only]
    cand = [p[0] for p in persons if p[2] < byid(only)[2] - 22] or [p[0] for p in persons if p[2] < byid(only)[2] - 12] or [persons[0][0]]
    links.append((only, rng.choice(cand), "adoptive"))
    # plant mistakes: a parent younger than the child; a bigamist; a marriage that overlaps by one day only
    yc = rng.choice([c for c in kids if c != only])
    links = [l for l in links if not (l[0] == yc and l[2] == "birth")][:]
    young = person(byid(yc)[2] + 6, "M", "Ashdown")
    links.append((yc, young, "birth"))
    first = marriages[0]
    mid += 1
    spouse = person(byid(first[1])[2] + 3, "M", "Bramley")
    marriages.append([mid, first[1], spouse, (date.fromisoformat(first[3]) + timedelta(days=400)).isoformat(), None])
    mid += 1
    s2 = person(byid(first[1])[2] + 4, "M", "Colthorpe")
    marriages.append([mid, spouse, s2, "1999-01-01", "1999-12-31"])
    mid += 1
    marriages.append([mid, s2, persons[0][0], "1999-12-31", None])
    return {"persons": [tuple(p) for p in persons], "parent_links": links, "marriages": [tuple(m) for m in marriages]}


DOMAIN = K.Domain("kinship", "Wicker Lane Genealogy Society: family-tree research", SCHEMA, DOC, gen)
S = K.Spec

SPECS = [
    S("no-known-parents", 1,
      "List the persons with no recorded parent at all (neither birth nor adoptive): name and birth year, oldest first, ties by name.",
      "SELECT name, born FROM persons p WHERE NOT EXISTS (SELECT 1 FROM parent_links l WHERE l.child_id = p.person_id) ORDER BY born, name;",
      ["name", "born"], ordered=True),
    S("children-counts", 2,
      "For every person who has at least one child on record: name, the number of distinct children (any kind of link) and how many of those are birth children. Most children first, ties by name.",
      """SELECT p.name, COUNT(*) AS children, SUM(l.kind = 'birth') AS birth_children
FROM parent_links l JOIN persons p ON p.person_id = l.parent_id GROUP BY p.person_id ORDER BY children DESC, p.name;""",
      ["name", "children", "birth_children"], ordered=True),
    S("lifespan-by-sex", 2,
      "Lifespan statistics by sex over the persons whose death year is known: sex, how many persons, the average lifespan (1 decimal), the shortest and the longest lifespan. Order by sex.",
      "SELECT sex, COUNT(*) AS n, ROUND(AVG(died - born), 1) AS avg_years, MIN(died - born) AS shortest, MAX(died - born) AS longest FROM persons WHERE died IS NOT NULL GROUP BY sex ORDER BY sex;",
      ["sex", "n", "avg_years", "shortest", "longest"], ordered=True),
    S("adopted-only", 2,
      "Which people have only adoptive parents on record (at least one adoptive link and no birth link)? Show name and birth year, ordered by birth year then name.",
      """SELECT p.name, p.born FROM persons p WHERE EXISTS (SELECT 1 FROM parent_links l WHERE l.child_id = p.person_id AND l.kind = 'adoptive')
AND NOT EXISTS (SELECT 1 FROM parent_links l WHERE l.child_id = p.person_id AND l.kind = 'birth') ORDER BY p.born, p.name;""",
      ["name", "born"], ordered=True),
    S("generations-above", 3,
      "How many generations of recorded ancestors does each person have above them? Count the longest chain of parent links (any kind) from the person upwards: a person with no parents has 0, a person whose parents have none has 1, and so on. "
      "List the persons with 3 or more generations: name and the count, deepest first, ties by name.",
      """WITH RECURSIVE up(person_id, anc, depth) AS (
  SELECT child_id, parent_id, 1 FROM parent_links
  UNION ALL SELECT up.person_id, l.parent_id, up.depth + 1 FROM up JOIN parent_links l ON l.child_id = up.anc
)
SELECT p.name, MAX(up.depth) AS generations FROM up JOIN persons p ON p.person_id = up.person_id GROUP BY p.person_id HAVING MAX(up.depth) >= 3 ORDER BY generations DESC, p.name;""",
      ["name", "generations"], ordered=True,
      wrong=("""WITH RECURSIVE up(person_id, anc, depth) AS (SELECT child_id, parent_id, 1 FROM parent_links UNION ALL SELECT up.person_id, l.parent_id, up.depth + 1 FROM up JOIN parent_links l ON l.child_id = up.anc AND l.kind = 'birth')
SELECT p.name, MAX(up.depth) FROM up JOIN persons p ON p.person_id = up.person_id GROUP BY p.person_id HAVING MAX(up.depth) >= 3 ORDER BY 2 DESC, p.name;""",)),
    S("sibling-pairs", 3,
      "List every pair of siblings (shared birth parent) once, with the lower person id first: both names and whether they are `full` (two shared birth parents) or `half` (one). "
      "Order by the first id, then the second.",
      """SELECT a.name AS name_a, b.name AS name_b, CASE WHEN COUNT(*) = 2 THEN 'full' ELSE 'half' END AS kind
FROM parent_links x JOIN parent_links y ON y.parent_id = x.parent_id AND y.child_id > x.child_id AND y.kind = 'birth'
JOIN persons a ON a.person_id = x.child_id JOIN persons b ON b.person_id = y.child_id WHERE x.kind = 'birth'
GROUP BY x.child_id, y.child_id ORDER BY x.child_id, y.child_id;""",
      ["name_a", "name_b", "kind"], ordered=True,
      wrong=("""SELECT a.name, b.name, 'full' FROM parent_links x JOIN parent_links y ON y.parent_id = x.parent_id AND y.child_id > x.child_id JOIN persons a ON a.person_id = x.child_id JOIN persons b ON b.person_id = y.child_id GROUP BY x.child_id, y.child_id ORDER BY x.child_id, y.child_id;""",)),
    S("descendant-counts", 3,
      "For everybody who has at least one descendant (children, grandchildren, ... through links of any kind), count the distinct descendants. Columns: name, descendants. Most first, ties by name.",
      """WITH RECURSIVE d(anc, person) AS (
  SELECT parent_id, child_id FROM parent_links
  UNION SELECT d.anc, l.child_id FROM d JOIN parent_links l ON l.parent_id = d.person
)
SELECT p.name, COUNT(*) AS descendants FROM d JOIN persons p ON p.person_id = d.anc GROUP BY d.anc ORDER BY descendants DESC, p.name;""",
      ["name", "descendants"], ordered=True,
      wrong=("""SELECT p.name, COUNT(*) AS c FROM parent_links l JOIN persons p ON p.person_id = l.parent_id GROUP BY l.parent_id ORDER BY c DESC, p.name;""",)),
    S("impossible-parents", 3,
      "Find parent links that cannot be right: the parent is less than 15 years older than the child (a negative gap counts). Report the child's name, the parent's name, and the age gap in years (parent born minus... "
      "the child's birth year minus the parent's birth year). Smallest gap first, ties by child name then parent name.",
      """SELECT c.name AS child, p.name AS parent, c.born - p.born AS gap FROM parent_links l JOIN persons c ON c.person_id = l.child_id JOIN persons p ON p.person_id = l.parent_id
WHERE c.born - p.born < 15 ORDER BY gap, c.name, p.name;""",
      ["child", "parent", "gap"], ordered=True, allow_empty=True),
    S("overlapping-marriages", 4,
      "Persons in two marriages at the same time: report every pair of marriages of one person whose periods share at least one day (a NULL end means the marriage never ended; both end dates are included). "
      "Columns: person name, the two marriage ids (lower first). Order by person name, then the first id, then the second.",
      """WITH m AS (SELECT marriage_id, spouse_a AS person_id, married_on, COALESCE(ended_on, '9999-12-31') AS ended FROM marriages UNION ALL SELECT marriage_id, spouse_b, married_on, COALESCE(ended_on, '9999-12-31') FROM marriages)
SELECT p.name AS person, a.marriage_id AS marriage_a, b.marriage_id AS marriage_b
FROM m a JOIN m b ON b.person_id = a.person_id AND b.marriage_id > a.marriage_id AND b.married_on <= a.ended AND a.married_on <= b.ended
JOIN persons p ON p.person_id = a.person_id ORDER BY p.name, a.marriage_id, b.marriage_id;""",
      ["person", "marriage_a", "marriage_b"], ordered=True, allow_empty=True,
      wrong=("""WITH m AS (SELECT marriage_id, spouse_a AS person_id, married_on, COALESCE(ended_on, '9999-12-31') AS ended FROM marriages UNION ALL SELECT marriage_id, spouse_b, married_on, COALESCE(ended_on, '9999-12-31') FROM marriages)
SELECT p.name, a.marriage_id, b.marriage_id FROM m a JOIN m b ON b.person_id = a.person_id AND b.marriage_id > a.marriage_id AND b.married_on < a.ended AND a.married_on < b.ended JOIN persons p ON p.person_id = a.person_id ORDER BY p.name, a.marriage_id, b.marriage_id;""",)),
    S("first-cousins", 4,
      "First cousins: pairs of persons who share a grandparent through *birth* links (grandparent of both via a birth parent of each) but are not siblings themselves (they have no birth parent in common). "
      "List each pair once, lower person id first: both names and the number of grandparents they share. Order by the first id, then the second.",
      """WITH gp AS (
  SELECT c.child_id AS person, g.parent_id AS grand, c.parent_id AS parent FROM parent_links c JOIN parent_links g ON g.child_id = c.parent_id AND g.kind = 'birth' WHERE c.kind = 'birth'
)
SELECT a.name AS name_a, b.name AS name_b, COUNT(DISTINCT x.grand) AS shared_grandparents
FROM gp x JOIN gp y ON y.grand = x.grand AND y.person > x.person AND y.parent <> x.parent
JOIN persons a ON a.person_id = x.person JOIN persons b ON b.person_id = y.person
WHERE NOT EXISTS (SELECT 1 FROM parent_links p1 JOIN parent_links p2 ON p2.parent_id = p1.parent_id AND p2.kind = 'birth' WHERE p1.kind = 'birth' AND p1.child_id = x.person AND p2.child_id = y.person)
GROUP BY x.person, y.person ORDER BY x.person, y.person;""",
      ["name_a", "name_b", "shared_grandparents"], ordered=True,
      wrong=("""WITH gp AS (SELECT c.child_id AS person, g.parent_id AS grand FROM parent_links c JOIN parent_links g ON g.child_id = c.parent_id)
SELECT a.name, b.name, COUNT(DISTINCT x.grand) FROM gp x JOIN gp y ON y.grand = x.grand AND y.person > x.person JOIN persons a ON a.person_id = x.person JOIN persons b ON b.person_id = y.person GROUP BY x.person, y.person ORDER BY x.person, y.person;""",)),
    S("parent-age-at-birth", 3,
      "Average age of mothers and of fathers at the birth of their birth children: by the parent's sex, the number of birth links and the average of (child born minus parent born), 1 decimal. Order by sex.",
      "SELECT p.sex, COUNT(*) AS links, ROUND(AVG(c.born - p.born), 1) AS avg_age FROM parent_links l JOIN persons p ON p.person_id = l.parent_id JOIN persons c ON c.person_id = l.child_id WHERE l.kind = 'birth' GROUP BY p.sex ORDER BY p.sex;",
      ["sex", "links", "avg_age"], ordered=True),
    S("longest-lived-per-decade", 3,
      "For each birth decade (1840, 1850, ...: the year rounded down to a multiple of 10) among the persons with a known death year, the person with the longest lifespan; ties go to the one born earlier, then the lower id. "
      "Columns: decade, name, lifespan. Order by decade.",
      """WITH x AS (SELECT person_id, name, born / 10 * 10 AS decade, died - born AS life, ROW_NUMBER() OVER (PARTITION BY born / 10 ORDER BY died - born DESC, born, person_id) AS rn FROM persons WHERE died IS NOT NULL)
SELECT decade, name, life FROM x WHERE rn = 1 ORDER BY decade;""",
      ["decade", "name", "lifespan"], ordered=True,
      wrong=("""SELECT born / 10 * 10, name, MAX(died - born) FROM persons WHERE died IS NOT NULL GROUP BY born / 10 ORDER BY 1;""",)),
    S("pedigree-depth-roots", 4,
      "For every person without any recorded parent who has at least one descendant, how many generations of descendants are there below them in the longest line? (children = 1, grandchildren = 2, ...; links of any kind.) "
      "Show the person's name and that depth for the roots whose depth is 2 or more. Deepest first, ties by name.",
      """WITH RECURSIVE d(root, person, depth) AS (
  SELECT p.person_id, l.child_id, 1 FROM persons p JOIN parent_links l ON l.parent_id = p.person_id WHERE NOT EXISTS (SELECT 1 FROM parent_links x WHERE x.child_id = p.person_id)
  UNION ALL SELECT d.root, l.child_id, d.depth + 1 FROM d JOIN parent_links l ON l.parent_id = d.person
)
SELECT p.name, MAX(d.depth) AS depth FROM d JOIN persons p ON p.person_id = d.root GROUP BY d.root HAVING MAX(d.depth) >= 2 ORDER BY depth DESC, p.name;""",
      ["name", "depth"], ordered=True,
      wrong=("""SELECT p.name, 2 FROM persons p WHERE NOT EXISTS (SELECT 1 FROM parent_links x WHERE x.child_id = p.person_id) AND EXISTS (SELECT 1 FROM parent_links l JOIN parent_links l2 ON l2.parent_id = l.child_id WHERE l.parent_id = p.person_id) ORDER BY p.name;""",)),
    S("fix-sibling-pairs", 3,
      "`query.sql` should list every pair of full or half siblings once, but it pairs people with themselves, lists each pair twice and treats adoptive links as sibling links. "
      "Fix it: output the two names (lower person id first) once per pair, where the two share at least one *birth* parent. Order by the first id, then the second.",
      ref="""SELECT DISTINCT a.name AS name_a, b.name AS name_b FROM parent_links x JOIN parent_links y ON y.parent_id = x.parent_id AND y.child_id > x.child_id AND y.kind = 'birth' AND x.kind = 'birth'
JOIN persons a ON a.person_id = x.child_id JOIN persons b ON b.person_id = y.child_id ORDER BY x.child_id, y.child_id;""",
      cols=["name_a", "name_b"], ordered=True, show=False,
      buggy="""SELECT a.name, b.name FROM parent_links x JOIN parent_links y ON y.parent_id = x.parent_id
JOIN persons a ON a.person_id = x.child_id JOIN persons b ON b.person_id = y.child_id ORDER BY x.child_id, y.child_id;"""),
]


@family("data-family-tree", category="data", lang="sql", kind="feature", n=len(SPECS),
        summary="SQL on genealogy records: recursive ancestry and descent, full/half siblings, first cousins, impossible parents, overlapping marriages")
def family_tree(rng, n):
    return K.query_tasks(DOMAIN, SPECS, rng, n)

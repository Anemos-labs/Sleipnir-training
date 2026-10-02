"""SQL tasks on an invented document vault's access model (nested groups by recursion, deny-overrides, expiring grants, path inheritance)."""
from datetime import date, timedelta

from fx import dd, family
from generators.data import _sqlkit as K

SCHEMA = dd('''
    CREATE TABLE users (
      user_id     INTEGER PRIMARY KEY,
      name        TEXT NOT NULL UNIQUE,
      active      INTEGER NOT NULL DEFAULT 1,
      created_on  TEXT NOT NULL
    );
    CREATE TABLE groups (
      group_id  INTEGER PRIMARY KEY,
      name      TEXT NOT NULL UNIQUE
    );
    CREATE TABLE memberships (
      member_kind  TEXT NOT NULL CHECK (member_kind IN ('user', 'group')),
      member_id    INTEGER NOT NULL,          -- a user_id or a group_id, depending on member_kind
      group_id     INTEGER NOT NULL REFERENCES groups(group_id),
      PRIMARY KEY (member_kind, member_id, group_id)
    );
    CREATE TABLE resources (
      resource_id  INTEGER PRIMARY KEY,
      path         TEXT NOT NULL UNIQUE,      -- like /finance/q1/raw
      owner_group  INTEGER REFERENCES groups(group_id)
    );
    CREATE TABLE grants (
      grant_id     INTEGER PRIMARY KEY,
      group_id     INTEGER NOT NULL REFERENCES groups(group_id),
      resource_id  INTEGER NOT NULL REFERENCES resources(resource_id),
      perm         TEXT NOT NULL CHECK (perm IN ('read', 'write', 'admin')),
      effect       TEXT NOT NULL CHECK (effect IN ('allow', 'deny')),
      expires_on   TEXT                       -- NULL = never
    );
''')

DOC = dd('''
    The Quillmark vault stores documents under paths and controls who may touch them.

    * A group can contain users and other groups (`memberships`). A user is a member of a group **directly or through any chain of nested groups**. The nesting never loops.
    * Grants are given to groups, never to users. `perm` is one of `read`, `write`, `admin`; the three are independent (admin does not imply write).
    * A grant is **in force** unless `expires_on` is before today. Today is **2036-05-01**: a grant that expires today is still in force.
    * A user has **effective access** with a permission on a resource when some in-force `allow` grant for that permission on that very resource reaches the user through one of their groups, and **no** in-force `deny` grant for the same permission on that resource reaches them (deny wins).
      Unless a task says otherwise, grants apply to the exact resource only.
    * A grant on a path **covers descendant paths**: `/finance` covers `/finance/q1` and `/finance/q1/raw` (a path covers another when the other starts with the path followed by `/`) only in the tasks that talk about inheritance.
    * Inactive users (`active = 0`) are accounts that were switched off but not deleted.
''')

USERS = ["amara", "bjorn", "cleo", "dmitri", "elif", "farid", "greta", "hugo", "isla", "jonas", "kamila", "leo", "mina", "nils", "oona", "pavel", "quinn", "rhea", "stellan", "tove", "ugo", "vera", "wren", "xavi", "yara", "zane", "alma", "boris", "cyra", "dante", "ezra", "fia"]
GROUPS = ["everyone", "staff", "finance", "finance-leads", "hr", "engineering", "platform", "oncall", "contractors", "auditors", "board", "interns"]
PATHS = ["/finance", "/finance/q1", "/finance/q1/raw", "/finance/q2", "/hr", "/hr/policies", "/hr/cases", "/eng", "/eng/design", "/eng/design/drafts", "/eng/runbooks", "/board", "/shared"]
TODAY = date(2036, 5, 1)


def gen(rng, big):
    nu = 28 if big else 10
    users = [(i + 1, USERS[i], 0 if rng.random() < 0.12 else 1, (date(2033, 1, 1) + timedelta(days=rng.randint(0, 1200))).isoformat()) for i in range(nu)]
    ng = 12 if big else 7
    groups = [(i + 1, GROUPS[i]) for i in range(ng)]
    mem = set()
    for gi in range(1, ng):  # group gi may contain groups with a higher id only: no loops
        for gj in rng.sample(range(gi + 1, ng + 1), min(ng - gi, rng.choice([0, 1, 1, 2]))):
            mem.add(("group", gj, gi))
    # plant a chain of depth 3: group 1 contains 2 contains 3 contains 4
    for a, b in ((1, 2), (2, 3), (3, 4)):
        mem.add(("group", b, a))
    for u in users:
        for g in rng.sample(range(1, ng + 1), rng.choice([1, 1, 2, 3])):
            mem.add(("user", u[0], g))
    empties = set(rng.sample(range(5, ng + 1), 2 if big else 1))  # some groups stay empty and are contained nowhere
    mem = {m for m in mem if m[2] not in empties and not (m[0] == "group" and m[1] in empties)}
    npaths = len(PATHS) if big else 8
    res = [(i + 1, PATHS[i], rng.choice([None, None, rng.randint(1, ng - 1)])) for i in range(npaths)]
    grants, gid = [], 0
    for _ in range(46 if big else 16):
        gid += 1
        exp = rng.choice([None, None, None, (TODAY + timedelta(days=rng.choice([-40, -1, 0, 3, 20, 29, 30, 31, 90]))).isoformat()])
        grants.append((gid, rng.randint(1, ng - 1), rng.randint(1, npaths), rng.choice(["read", "read", "write", "admin"]), "deny" if rng.random() < 0.15 else "allow", exp))
    # plant: an allow/deny conflict through nested groups, a grant that expires today and one that expired yesterday, an admin grant on a parent path only
    for g, r, p, e, x in ((1, 1, "read", "allow", None), (4, 1, "read", "deny", None), (2, 2, "read", "allow", TODAY.isoformat()), (3, 2, "write", "allow", (TODAY - timedelta(days=1)).isoformat()), (2, 1, "admin", "allow", None)):
        gid += 1
        grants.append((gid, g, r, p, e, x))
    return {"users": users, "groups": groups, "memberships": sorted(mem), "resources": res, "grants": grants}


DOMAIN = K.Domain("accessgraph", "Quillmark vault: groups, grants and paths", SCHEMA, DOC, gen)
S = K.Spec

CLOSURE = """WITH RECURSIVE gm(user_id, group_id) AS (
  SELECT member_id, group_id FROM memberships WHERE member_kind = 'user'
  UNION SELECT gm.user_id, m.group_id FROM gm JOIN memberships m ON m.member_kind = 'group' AND m.member_id = gm.group_id
)"""
LIVE = "(g.expires_on IS NULL OR g.expires_on >= '2036-05-01')"
EFFECTIVE = f"""{CLOSURE}
, allowed AS (SELECT DISTINCT gm.user_id, g.resource_id, g.perm FROM grants g JOIN gm ON gm.group_id = g.group_id WHERE g.effect = 'allow' AND {LIVE}),
denied AS (SELECT DISTINCT gm.user_id, g.resource_id, g.perm FROM grants g JOIN gm ON gm.group_id = g.group_id WHERE g.effect = 'deny' AND {LIVE}),
eff AS (SELECT a.* FROM allowed a WHERE NOT EXISTS (SELECT 1 FROM denied d WHERE d.user_id = a.user_id AND d.resource_id = a.resource_id AND d.perm = a.perm))"""

SPECS = [
    S("users-by-year", 1, "How many users were created in each year, and how many of them are still active? Columns: year (as text like 2034), users, active. Order by year.",
      "SELECT substr(created_on, 1, 4) AS year, COUNT(*) AS users, SUM(active) AS active FROM users GROUP BY year ORDER BY year;", ["year", "users", "active"], ordered=True),
    S("direct-members", 2,
      "For every group: its name, the number of users that are direct members and the number of groups that are direct members. Groups with no direct member show zeros. Order by name.",
      """SELECT g.name, COALESCE(SUM(m.member_kind = 'user'), 0) AS users, COALESCE(SUM(m.member_kind = 'group'), 0) AS groups
FROM groups g LEFT JOIN memberships m ON m.group_id = g.group_id GROUP BY g.group_id ORDER BY g.name;""",
      ["name", "users", "groups"], ordered=True),
    S("group-reach", 4,
      "How many active users does each group really contain, counting members of nested groups at any depth (each user once)? Show every group, 0 when nobody. Columns: group name, active users. Order by users descending, then name.",
      f"""{CLOSURE}
SELECT g.name, COUNT(DISTINCT u.user_id) AS active_users FROM groups g LEFT JOIN gm ON gm.group_id = g.group_id LEFT JOIN users u ON u.user_id = gm.user_id AND u.active = 1 GROUP BY g.group_id ORDER BY active_users DESC, g.name;""",
      ["name", "active_users"], ordered=True,
      wrong=("""SELECT g.name, COUNT(DISTINCT u.user_id) AS c FROM groups g LEFT JOIN memberships m ON m.group_id = g.group_id AND m.member_kind = 'user' LEFT JOIN users u ON u.user_id = m.member_id AND u.active = 1 GROUP BY g.group_id ORDER BY c DESC, g.name;""",)),
    S("empty-groups", 2,
      "Groups that contain nobody at all: no direct member of any kind. Show the group name, ordered by name.",
      "SELECT name FROM groups g WHERE NOT EXISTS (SELECT 1 FROM memberships m WHERE m.group_id = g.group_id) ORDER BY name;", ["name"], ordered=True),
    S("nesting-depth", 3,
      "How deeply is each group nested? For every group that contains at least one group, the length of the longest chain of group-in-group links below it (a group directly containing another group has depth 1, containing a group that contains a group depth 2, and so on). "
      "Columns: group name, depth. Deepest first, ties by name.",
      """WITH RECURSIVE d(top, grp, depth) AS (
  SELECT group_id, member_id, 1 FROM memberships WHERE member_kind = 'group'
  UNION ALL SELECT d.top, m.member_id, d.depth + 1 FROM d JOIN memberships m ON m.member_kind = 'group' AND m.group_id = d.grp
)
SELECT g.name, MAX(d.depth) AS depth FROM d JOIN groups g ON g.group_id = d.top GROUP BY d.top ORDER BY depth DESC, g.name;""",
      ["name", "depth"], ordered=True),
    S("busy-users", 3,
      "Active users who belong to four or more groups when nesting is taken into account (a user is in a group directly or through any chain of groups). Columns: user name, number of groups. Most first, ties by name.",
      f"""{CLOSURE}
SELECT u.name, COUNT(DISTINCT gm.group_id) AS groups FROM users u JOIN gm ON gm.user_id = u.user_id WHERE u.active = 1 GROUP BY u.user_id HAVING COUNT(DISTINCT gm.group_id) >= 4 ORDER BY groups DESC, u.name;""",
      ["name", "groups"], ordered=True,
      wrong=("""SELECT u.name, COUNT(*) AS c FROM users u JOIN memberships m ON m.member_kind = 'user' AND m.member_id = u.user_id WHERE u.active = 1 GROUP BY u.user_id HAVING COUNT(*) >= 4 ORDER BY c DESC, u.name;""",)),
    S("expiring-soon", 2,
      "Grants that are still in force today (2036-05-01) but expire within the next 30 days (an expiry date from today up to 2036-05-31 counts). Columns: group name, resource path, permission, effect, days left (0 for today). Order by days left, then group, then path, then permission.",
      """SELECT gr.name AS grp, r.path, g.perm, g.effect, CAST(julianday(g.expires_on) - julianday('2036-05-01') AS INTEGER) AS days_left
FROM grants g JOIN groups gr ON gr.group_id = g.group_id JOIN resources r ON r.resource_id = g.resource_id
WHERE g.expires_on >= '2036-05-01' AND g.expires_on <= '2036-05-31' ORDER BY days_left, gr.name, r.path, g.perm;""",
      ["group", "path", "perm", "effect", "days_left"], ordered=True),
    S("who-can-read", 4,
      "Effective read access: list every (user, resource) pair where an active or inactive user has effective `read` access (exact resource only; allow through any group, no in-force deny for read through any group, expired grants ignored). "
      "Columns: user name, resource path. Order by path, then user name.",
      f"""{EFFECTIVE}
SELECT u.name AS user, r.path FROM eff e JOIN users u ON u.user_id = e.user_id JOIN resources r ON r.resource_id = e.resource_id WHERE e.perm = 'read' ORDER BY r.path, u.name;""",
      ["user", "path"], ordered=True,
      wrong=(f"""{CLOSURE}
SELECT u.name, r.path FROM grants g JOIN gm ON gm.group_id = g.group_id JOIN users u ON u.user_id = gm.user_id JOIN resources r ON r.resource_id = g.resource_id WHERE g.perm = 'read' AND g.effect = 'allow' AND {LIVE} GROUP BY u.user_id, r.resource_id ORDER BY r.path, u.name;""",)),
    S("deny-conflicts", 4,
      "Where deny beats allow: list every (user, resource, permission) for which at least one in-force allow grant and at least one in-force deny grant reach the user (so the user ends up without access). "
      "Columns: user name, resource path, permission. Order by path, permission, user name.",
      f"""{CLOSURE}
, a AS (SELECT DISTINCT gm.user_id, g.resource_id, g.perm FROM grants g JOIN gm ON gm.group_id = g.group_id WHERE g.effect = 'allow' AND {LIVE}),
d AS (SELECT DISTINCT gm.user_id, g.resource_id, g.perm FROM grants g JOIN gm ON gm.group_id = g.group_id WHERE g.effect = 'deny' AND {LIVE})
SELECT u.name AS user, r.path, a.perm FROM a JOIN d ON d.user_id = a.user_id AND d.resource_id = a.resource_id AND d.perm = a.perm JOIN users u ON u.user_id = a.user_id JOIN resources r ON r.resource_id = a.resource_id ORDER BY r.path, a.perm, u.name;""",
      ["user", "path", "perm"], ordered=True, allow_empty=True,
      wrong=(f"""{CLOSURE}
SELECT u.name, r.path, g.perm FROM grants g JOIN gm ON gm.group_id = g.group_id JOIN users u ON u.user_id = gm.user_id JOIN resources r ON r.resource_id = g.resource_id WHERE g.effect = 'deny' GROUP BY u.user_id, r.resource_id, g.perm ORDER BY r.path, g.perm, u.name;""",)),
    S("inherited-admin", 5,
      "Admin by inheritance only: with inheritance a grant on a path covers all descendant paths. Find the (user, resource) pairs where the user has effective `admin` through inheritance (in-force allow on a strict ancestor path reaches them, and no in-force admin deny reaches them "
      "for the resource itself or any of its ancestors) but has no in-force admin allow on the resource itself. Columns: user name, resource path. Order by path, then user name.",
      f"""{CLOSURE}
, allow_adm AS (SELECT DISTINCT gm.user_id, g.resource_id FROM grants g JOIN gm ON gm.group_id = g.group_id WHERE g.perm = 'admin' AND g.effect = 'allow' AND {LIVE}),
deny_adm AS (SELECT DISTINCT gm.user_id, g.resource_id FROM grants g JOIN gm ON gm.group_id = g.group_id WHERE g.perm = 'admin' AND g.effect = 'deny' AND {LIVE})
SELECT DISTINCT u.name AS user, c.path FROM allow_adm a JOIN resources p ON p.resource_id = a.resource_id JOIN resources c ON c.path LIKE p.path || '/%' JOIN users u ON u.user_id = a.user_id
WHERE NOT EXISTS (SELECT 1 FROM allow_adm x WHERE x.user_id = a.user_id AND x.resource_id = c.resource_id)
  AND NOT EXISTS (SELECT 1 FROM deny_adm d JOIN resources dr ON dr.resource_id = d.resource_id WHERE d.user_id = a.user_id AND (dr.path = c.path OR c.path LIKE dr.path || '/%'))
ORDER BY c.path, u.name;""",
      ["user", "path"], ordered=True, allow_empty=True,
      wrong=(f"""{CLOSURE}
SELECT DISTINCT u.name, c.path FROM grants g JOIN gm ON gm.group_id = g.group_id JOIN resources p ON p.resource_id = g.resource_id JOIN resources c ON c.path LIKE p.path || '%' AND c.path <> p.path JOIN users u ON u.user_id = gm.user_id WHERE g.perm = 'admin' AND g.effect = 'allow' AND {LIVE} ORDER BY c.path, u.name;""",)),
    S("risky-open-resources", 3,
      "Resources that nobody owns (`owner_group` is NULL) but that have at least one in-force `allow` grant for `write` or `admin`. Show the path and how many such grants it has. Order by that count descending, then path.",
      f"""SELECT r.path, COUNT(*) AS risky_grants FROM resources r JOIN grants g ON g.resource_id = r.resource_id WHERE r.owner_group IS NULL AND g.effect = 'allow' AND g.perm IN ('write', 'admin') AND {LIVE} GROUP BY r.resource_id ORDER BY risky_grants DESC, r.path;""",
      ["path", "risky_grants"], ordered=True, allow_empty=True),
    S("switched-off-but-powerful", 3,
      "Inactive users who still have effective access: for each such user the number of (resource, permission) pairs they can use, with the usual rules (exact resources, deny wins, expired grants ignored). Columns: user name, pairs. Most first, ties by name.",
      f"""{EFFECTIVE}
SELECT u.name, COUNT(*) AS pairs FROM eff e JOIN users u ON u.user_id = e.user_id WHERE u.active = 0 GROUP BY e.user_id ORDER BY pairs DESC, u.name;""",
      ["name", "pairs"], ordered=True, allow_empty=True,
      wrong=(f"""{CLOSURE}
SELECT u.name, COUNT(DISTINCT g.resource_id || g.perm) AS c FROM grants g JOIN gm ON gm.group_id = g.group_id JOIN users u ON u.user_id = gm.user_id WHERE u.active = 0 AND g.effect = 'allow' GROUP BY u.user_id ORDER BY c DESC, u.name;""",)),
    S("fix-group-members", 3,
      "The headcount report in `query.sql` only counts direct user members and counts inactive accounts. Fix it so that, for every group, it shows the number of active users that belong to it directly or through nested groups (each user once, 0 when none). "
      "Columns: group name, active users. Order by name.",
      ref=f"""{CLOSURE}
SELECT g.name, COUNT(DISTINCT u.user_id) AS active_users FROM groups g LEFT JOIN gm ON gm.group_id = g.group_id LEFT JOIN users u ON u.user_id = gm.user_id AND u.active = 1 GROUP BY g.group_id ORDER BY g.name;""",
      cols=["name", "active_users"], ordered=True, show=False,
      buggy="""SELECT g.name, COUNT(*) AS active_users FROM groups g JOIN memberships m ON m.group_id = g.group_id AND m.member_kind = 'user' GROUP BY g.group_id ORDER BY g.name;"""),
]


@family("data-access-graph", category="data", lang="sql", kind="feature", n=len(SPECS),
        summary="SQL on a vault's access model: nested groups by recursion, deny-overrides-allow, grants that expire today, path inheritance")
def access_graph(rng, n):
    return K.query_tasks(DOMAIN, SPECS, rng, n)

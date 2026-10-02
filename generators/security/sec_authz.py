"""Security families: broken access control (IDOR, missing function-level checks, tenant isolation, stale permissions) and mass assignment."""
from fx import dd, family

from . import _sec
from ._sec import patched, readme

P = _sec.PY_PRELUDE

# =================================================================================================================================
#  access control
# =================================================================================================================================
AZ = []

BILL = dd(r'''
    """Invoices of the billing portal."""


    class Billing:
        def __init__(self, invoices):
            """`invoices` is a list of dicts with `id`, `owner` (user name) and `total`."""
            self.invoices = {inv["id"]: inv for inv in invoices}

        def get_invoice(self, user, invoice_id):
            """The invoice with that id. `user` is a dict with `name` and `role`. Users may read their own invoices only; users with role `admin` may read all of them.
            PermissionError for somebody else's invoice, KeyError for an unknown id."""
            return self.invoices[invoice_id]

        def list_invoices(self, user):
            """The invoices the user may read (all for admins), sorted by id."""
            return sorted(self.invoices.values(), key=lambda inv: inv["id"])
''')

AZ.append(dict(
    slug="invoice-owner", d=1, product="the billing portal", func="Billing.get_invoice", cwe="CWE-639",
    finding="`get_invoice` and `list_invoices` never look at who is asking: changing the id in `/invoices/17` to `/invoices/18` shows another customer's invoice, and the list page shows everybody's invoices (insecure direct object reference).",
    start={"billing.py": BILL, "README.md": readme("billing", "`get_invoice(user, invoice_id)` and `list_invoices(user)` enforce ownership as the docstrings say: customers see only invoices whose `owner` is their `name`, admins (`role == \"admin\"`) see everything. Foreign invoices raise `PermissionError` and are never part of any result.")},
    solution={"billing.py": patched(BILL, (
        '            return self.invoices[invoice_id]\n',
        '            invoice = self.invoices[invoice_id]\n            if user.get("role") != "admin" and invoice["owner"] != user.get("name"):\n                raise PermissionError("not your invoice")\n            return invoice\n'), (
        '            return sorted(self.invoices.values(), key=lambda inv: inv["id"])\n',
        '            allowed = [inv for inv in self.invoices.values() if user.get("role") == "admin" or inv["owner"] == user.get("name")]\n            return sorted(allowed, key=lambda inv: inv["id"])\n'))},
    hidden={"tests/test_billing_security.py": P + dd(r'''
        import billing as m

        INVOICES = [{"id": 1, "owner": "ann", "total": 120}, {"id": 2, "owner": "bob", "total": 80}, {"id": 3, "owner": "ann", "total": 15}, {"id": 4, "owner": "carol", "total": 999}]
        ANN, BOB, ADMIN = {"name": "ann", "role": "user"}, {"name": "bob", "role": "user"}, {"name": "root", "role": "admin"}


        class BillingTest(unittest.TestCase):
            def setUp(self):
                self.b = m.Billing([dict(i) for i in INVOICES])

            def test_own_and_admin(self):
                self.assertEqual(self.b.get_invoice(ANN, 1)["total"], 120)
                self.assertEqual(self.b.get_invoice(ANN, 3)["total"], 15)
                self.assertEqual([i["id"] for i in self.b.list_invoices(ANN)], [1, 3])
                self.assertEqual([i["id"] for i in self.b.list_invoices(BOB)], [2])
                self.assertEqual([i["id"] for i in self.b.list_invoices(ADMIN)], [1, 2, 3, 4])
                self.assertEqual(self.b.get_invoice(ADMIN, 4)["owner"], "carol")
                self.assertEqual(self.b.list_invoices({"name": "nobody", "role": "user"}), [])

            def test_foreign_and_unknown(self):
                for uid in (2, 4):
                    with self.assertRaises(PermissionError):
                        self.b.get_invoice(ANN, uid)
                with self.assertRaises(PermissionError):
                    self.b.get_invoice(BOB, 1)
                with self.assertRaises(KeyError):
                    self.b.get_invoice(ANN, 99)
                self.assertIsNone(attempt(self.b.get_invoice, {"name": "ann", "role": "admin-ish"}, 2))
                self.assertIsNone(attempt(self.b.get_invoice, {"name": "", "role": ""}, 2))
                self.assertNotIn(2, [i["id"] for i in self.b.list_invoices(ANN)])


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

DOCS = dd(r'''
    """Shared documents of the team wiki."""


    class Docs:
        def __init__(self):
            self.docs = {}

        def create(self, user, doc_id, text):
            if doc_id in self.docs:
                raise ValueError("exists")
            self.docs[doc_id] = {"owner": user["name"], "text": text, "shared": set()}

        def read(self, user, doc_id):
            """The text. Allowed for the owner, for users the document is shared with, and for admins (`role == "admin"`); otherwise PermissionError."""
            doc = self.docs[doc_id]
            if user["name"] == doc["owner"] or user["name"] in doc["shared"] or user.get("role") == "admin":
                return doc["text"]
            raise PermissionError("no access")

        def update(self, user, doc_id, text):
            """Replace the text. Allowed for the owner and admins only (readers the document is shared with cannot edit)."""
            self.docs[doc_id]["text"] = text

        def share(self, user, doc_id, other):
            """Give the user named `other` read access. Allowed for the owner and admins only."""
            self.docs[doc_id]["shared"].add(other)

        def delete(self, user, doc_id):
            """Delete the document. Allowed for the owner and admins only."""
            del self.docs[doc_id]
''')

AZ.append(dict(
    slug="document-share", d=2, product="the team wiki", func="Docs.update", cwe="CWE-863",
    finding="Only `read` checks permissions: `update`, `share` and `delete` accept any logged-in user, so a reader can overwrite or delete a document they were only meant to view, and any user can grant themselves (or others) access to somebody else's document by calling `share`.",
    start={"docs.py": DOCS, "README.md": readme("wiki documents", "Access rules: `read` - owner, shared users, admins. `update`, `share`, `delete` - owner and admins only. Everybody else gets `PermissionError` and the document stays untouched. Unknown documents raise `KeyError`, as before.")},
    solution={"docs.py": patched(DOCS, (
        '''        def read(self, user, doc_id):''', '''        def _owner_or_admin(self, user, doc_id):
            doc = self.docs[doc_id]
            if user["name"] != doc["owner"] and user.get("role") != "admin":
                raise PermissionError("owner only")

        def read(self, user, doc_id):'''), (
        '            self.docs[doc_id]["text"] = text\n', '            self._owner_or_admin(user, doc_id)\n            self.docs[doc_id]["text"] = text\n'), (
        '            self.docs[doc_id]["shared"].add(other)\n', '            self._owner_or_admin(user, doc_id)\n            self.docs[doc_id]["shared"].add(other)\n'), (
        '            del self.docs[doc_id]\n', '            self._owner_or_admin(user, doc_id)\n            del self.docs[doc_id]\n'))},
    hidden={"tests/test_docs_security.py": P + dd(r'''
        import docs as m


        def user(name, role="user"):
            return {"name": name, "role": role}


        class DocsTest(unittest.TestCase):
            def setUp(self):
                self.d = m.Docs()
                self.d.create(user("ann"), "plan", "v1")
                self.d.share(user("ann"), "plan", "bob")

            def test_allowed(self):
                d = self.d
                self.assertEqual(d.read(user("ann"), "plan"), "v1")
                self.assertEqual(d.read(user("bob"), "plan"), "v1")
                self.assertEqual(d.read(user("root", "admin"), "plan"), "v1")
                d.update(user("ann"), "plan", "v2")
                self.assertEqual(d.read(user("bob"), "plan"), "v2")
                d.update(user("root", "admin"), "plan", "v3")
                d.share(user("ann"), "plan", "carol")
                self.assertEqual(d.read(user("carol"), "plan"), "v3")
                d.share(user("root", "admin"), "plan", "dave")
                self.assertEqual(d.read(user("dave"), "plan"), "v3")
                d.delete(user("ann"), "plan")
                self.assertNotIn("plan", d.docs)
                with self.assertRaises(KeyError):
                    d.read(user("ann"), "plan")

            def test_denied(self):
                d = self.d
                for who in (user("bob"), user("eve"), user("eve", "editor")):
                    self.assertIsNone(attempt(d.update, who, "plan", "pwned"))
                    self.assertIsNone(attempt(d.share, who, "plan", who["name"]))
                    self.assertIsNone(attempt(d.delete, who, "plan"))
                self.assertEqual(d.docs["plan"]["text"], "v1")
                self.assertEqual(d.docs["plan"]["shared"], {"bob"})
                self.assertIsNone(attempt(d.read, user("eve"), "plan"))
                with self.assertRaises(PermissionError):
                    d.update(user("bob"), "plan", "x")
                with self.assertRaises(PermissionError):
                    d.delete(user("eve"), "plan")


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

HELP = dd(r'''
    """Multi-tenant help desk."""


    class Helpdesk:
        def __init__(self, tickets):
            """`tickets`: list of dicts with `id`, `tenant`, `title`, `body` and `comments` (a list of strings)."""
            self.tickets = {t["id"]: t for t in tickets}

        def get(self, user, ticket_id):
            """The ticket. `user` has `name` and `tenant`; users only see tickets of their own tenant (others: PermissionError; unknown id: KeyError)."""
            ticket = self.tickets[ticket_id]
            if ticket["tenant"] != user["tenant"]:
                raise PermissionError("other tenant")
            return ticket

        def search(self, user, text):
            """Tickets of the user's tenant whose title or body contains `text` (case-insensitive), sorted by id."""
            hits = [t for t in self.tickets.values() if text.lower() in (t["title"] + " " + t["body"]).lower()]
            return sorted(hits, key=lambda t: t["id"])

        def comment(self, user, ticket_id, text):
            """Add a comment to a ticket of the user's tenant; returns the number of comments."""
            ticket = self.tickets[ticket_id]
            ticket["comments"].append(user["name"] + ": " + text)
            return len(ticket["comments"])
''')

AZ.append(dict(
    slug="tenant-isolation", d=3, product="the multi-tenant help desk", func="Helpdesk.search", cwe="CWE-639",
    finding="Only `get` checks the tenant: `search` returns matching tickets of *all* tenants (titles, bodies and comments of other customers), and `comment` lets a user write into another tenant's ticket just by knowing or guessing its id.",
    start={"helpdesk.py": HELP, "README.md": readme("help desk", "Every operation is confined to the caller's tenant: `get` and `comment` raise `PermissionError` for tickets of other tenants (and change nothing), `search` only ever returns tickets of the caller's tenant. Unknown ids still raise `KeyError`.")},
    solution={"helpdesk.py": patched(HELP, (
        '            hits = [t for t in self.tickets.values() if text.lower() in (t["title"] + " " + t["body"]).lower()]\n',
        '            hits = [t for t in self.tickets.values() if t["tenant"] == user["tenant"] and text.lower() in (t["title"] + " " + t["body"]).lower()]\n'), (
        '            ticket = self.tickets[ticket_id]\n            ticket["comments"].append',
        '            ticket = self.tickets[ticket_id]\n            if ticket["tenant"] != user["tenant"]:\n                raise PermissionError("other tenant")\n            ticket["comments"].append'))},
    hidden={"tests/test_helpdesk_security.py": P + dd(r'''
        import copy

        import helpdesk as m

        TICKETS = [
            {"id": 1, "tenant": "acme", "title": "Printer on fire", "body": "smoke everywhere", "comments": []},
            {"id": 2, "tenant": "globex", "title": "Password reset", "body": "the CEO password is secret", "comments": ["support: done"]},
            {"id": 3, "tenant": "acme", "title": "Password policy", "body": "please explain", "comments": []},
            {"id": 4, "tenant": "globex", "title": "Printer jam", "body": "paper", "comments": []},
        ]
        ANN, GUY = {"name": "ann", "tenant": "acme"}, {"name": "guy", "tenant": "globex"}


        class HelpdeskTest(unittest.TestCase):
            def setUp(self):
                self.h = m.Helpdesk(copy.deepcopy(TICKETS))

            def test_own_tenant(self):
                self.assertEqual(self.h.get(ANN, 1)["title"], "Printer on fire")
                self.assertEqual([t["id"] for t in self.h.search(ANN, "printer")], [1])
                self.assertEqual([t["id"] for t in self.h.search(GUY, "PRINTER")], [4])
                self.assertEqual([t["id"] for t in self.h.search(ANN, "password")], [3])
                self.assertEqual([t["id"] for t in self.h.search(GUY, "password")], [2])
                self.assertEqual([t["id"] for t in self.h.search(ANN, "")], [1, 3])
                self.assertEqual(self.h.comment(GUY, 2, "thanks"), 2)
                self.assertEqual(self.h.tickets[2]["comments"][-1], "guy: thanks")
                self.assertEqual(self.h.search(ANN, "nothing matches"), [])

            def test_cross_tenant(self):
                with self.assertRaises(PermissionError):
                    self.h.get(ANN, 2)
                with self.assertRaises(PermissionError):
                    self.h.comment(ANN, 2, "gotcha")
                with self.assertRaises(PermissionError):
                    self.h.comment(GUY, 1, "gotcha")
                self.assertEqual(self.h.tickets[2]["comments"], ["support: done"])
                self.assertEqual(self.h.tickets[1]["comments"], [])
                for hit in self.h.search(ANN, "secret") + self.h.search(ANN, "paper") + self.h.search(ANN, "i"):
                    self.assertEqual(hit["tenant"], "acme")
                with self.assertRaises(KeyError):
                    self.h.get(ANN, 99)


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

DIRS = dd(r'''
    """User administration of the intranet."""


    class Directory:
        def __init__(self, users):
            """`users` maps a name to its role, `"user"` or `"admin"`."""
            self.users = dict(users)

        def list_users(self, actor):
            """The sorted names of all users (any logged-in user may call this)."""
            return sorted(self.users)

        def set_role(self, actor, name, role):
            """Give `name` the role `"user"` or `"admin"` (ValueError for other roles, KeyError for unknown users). Admins only. The last remaining admin cannot be demoted (ValueError)."""
            self.users[name] = role

        def delete_user(self, actor, name):
            """Remove a user. Admins only; nobody can delete themselves, and the last admin cannot be deleted (ValueError); KeyError for unknown users."""
            del self.users[name]
''')

AZ.append(dict(
    slug="admin-functions", d=2, product="the intranet user administration", func="Directory.set_role", cwe="CWE-285",
    finding="`set_role` and `delete_user` can be called by any logged-in user: a normal user promotes themselves with `set_role(me, me, \"admin\")` or deletes the administrators (missing function-level authorization).",
    start={"directory.py": DIRS, "README.md": readme("user directory", "`actor` is a dict with `name` and `role`. `list_users` is open to everybody. `set_role` and `delete_user` require `actor[\"role\"] == \"admin\"` (`PermissionError` otherwise, nothing changes) and then follow their docstrings, including the last-admin and self-delete rules. The role is whatever is stored in `actor` (callers authenticate it elsewhere), but only the exact value `admin` counts.")},
    solution={"directory.py": patched(DIRS, (
        '            self.users[name] = role\n', '''            if actor.get("role") != "admin":
                raise PermissionError("admins only")
            if role not in ("user", "admin"):
                raise ValueError("bad role")
            if name not in self.users:
                raise KeyError(name)
            if role != "admin" and self.users[name] == "admin" and sum(1 for r in self.users.values() if r == "admin") == 1:
                raise ValueError("last admin")
            self.users[name] = role
'''), (
        '            del self.users[name]\n', '''            if actor.get("role") != "admin":
                raise PermissionError("admins only")
            if name not in self.users:
                raise KeyError(name)
            if name == actor.get("name"):
                raise ValueError("cannot delete yourself")
            if self.users[name] == "admin" and sum(1 for r in self.users.values() if r == "admin") == 1:
                raise ValueError("last admin")
            del self.users[name]
'''))},
    hidden={"tests/test_directory_security.py": P + dd(r'''
        import directory as m

        ROOT, ROOT2, ANN = {"name": "root", "role": "admin"}, {"name": "root2", "role": "admin"}, {"name": "ann", "role": "user"}


        class DirectoryTest(unittest.TestCase):
            def make(self):
                return m.Directory({"root": "admin", "root2": "admin", "ann": "user", "bob": "user"})

            def test_admin_actions(self):
                d = self.make()
                self.assertEqual(d.list_users(ANN), ["ann", "bob", "root", "root2"])
                d.set_role(ROOT, "bob", "admin")
                self.assertEqual(d.users["bob"], "admin")
                d.set_role(ROOT, "bob", "user")
                d.delete_user(ROOT, "bob")
                self.assertNotIn("bob", d.users)
                d.set_role(ROOT, "root2", "user")
                self.assertEqual(d.users["root2"], "user")
                self.assertIsNone(attempt(d.set_role, ROOT, "root", "user"))
                self.assertIsNone(attempt(d.set_role, ROOT, "ann", "superuser"))
                self.assertIsNone(attempt(d.set_role, ROOT, "ghost", "user"))
                self.assertEqual(d.users["root"], "admin")
                self.assertIsNone(attempt(d.delete_user, ROOT, "root"))
                self.assertIsNone(attempt(d.delete_user, ROOT, "ghost"))
                self.assertIsNone(attempt(d.delete_user, ROOT2, "root"))
                self.assertIn("root", d.users)

            def test_everybody_else(self):
                for actor in (ANN, {"name": "ann", "role": "Admin"}, {"name": "ann", "role": "administrator"}, {"name": "ann"}, {"name": "ann", "role": None}):
                    d = self.make()
                    self.assertIsNone(attempt(d.set_role, actor, "ann", "admin"), actor)
                    self.assertIsNone(attempt(d.delete_user, actor, "root"), actor)
                    self.assertIsNone(attempt(d.delete_user, actor, "bob"), actor)
                    self.assertEqual(d.users, {"root": "admin", "root2": "admin", "ann": "user", "bob": "user"}, actor)
                with self.assertRaises(PermissionError):
                    self.make().set_role(ANN, "ann", "admin")


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

NOTES = dd(r'''
    """Personal notes (in-process model)."""


    class Notes:
        def __init__(self, notes):
            """`notes` is a list of dicts with `id`, `owner` and `text`."""
            self.notes = {n["id"]: n for n in notes}

        def delete_many(self, user, ids):
            """Delete the notes with these ids, all or nothing: a user may only delete their own notes (admins, `role == "admin"`, any); if one of the ids is unknown (KeyError) or
            belongs to somebody else (PermissionError), nothing is deleted at all. Returns how many notes were deleted (an id listed twice counts once)."""
            if not any(self.notes[i]["owner"] == user["name"] for i in ids):
                raise PermissionError("not your notes")
            count = 0
            for i in ids:
                if i in self.notes:
                    del self.notes[i]
                    count += 1
            return count
''')

AZ.append(dict(
    slug="bulk-delete", d=3, product="the notes app", func="Notes.delete_many", cwe="CWE-639",
    finding="`delete_many` only requires that *some* id in the list belongs to the caller (`any`): a request listing one of your own notes plus fifty ids of other users deletes all of them; unknown ids are skipped silently.",
    start={"notes.py": NOTES, "README.md": readme("notes", "`delete_many(user, ids)` is atomic and checks every id: unknown ids raise `KeyError`, ids of other users raise `PermissionError` (admins may delete any note), and in both cases no note is deleted. Otherwise all listed notes are deleted and the number of distinct notes is returned. An empty list deletes nothing and returns 0.")},
    solution={"notes.py": patched(NOTES, (
        '''            if not any(self.notes[i]["owner"] == user["name"] for i in ids):
                raise PermissionError("not your notes")
            count = 0
            for i in ids:
                if i in self.notes:
                    del self.notes[i]
                    count += 1
            return count
''', '''            wanted = list(dict.fromkeys(ids))
            for i in wanted:
                if i not in self.notes:
                    raise KeyError(i)
            if user.get("role") != "admin" and not all(self.notes[i]["owner"] == user["name"] for i in wanted):
                raise PermissionError("not your notes")
            for i in wanted:
                del self.notes[i]
            return len(wanted)
'''))},
    hidden={"tests/test_notes_security.py": P + dd(r'''
        import notes as m

        DATA = [{"id": i, "owner": o, "text": "n%d" % i} for i, o in enumerate(["ann", "bob", "ann", "carol", "bob", "ann"], start=1)]
        ANN, ADMIN = {"name": "ann", "role": "user"}, {"name": "root", "role": "admin"}


        class NotesTest(unittest.TestCase):
            def make(self):
                return m.Notes([dict(d) for d in DATA])

            def test_own_notes(self):
                n = self.make()
                self.assertEqual(n.delete_many(ANN, [1, 3]), 2)
                self.assertEqual(sorted(n.notes), [2, 4, 5, 6])
                self.assertEqual(n.delete_many(ANN, [6, 6]), 1)
                self.assertEqual(n.delete_many(ANN, []), 0)
                self.assertEqual(sorted(n.notes), [2, 4, 5])
                self.assertEqual(n.delete_many(ADMIN, [2, 4, 5]), 3)
                self.assertEqual(n.notes, {})

            def test_all_or_nothing(self):
                for ids in ([1, 2], [2, 1], [1, 3, 4], [2], [1, 99], [99], [3, 5, 1]):
                    n = self.make()
                    self.assertIsNone(attempt(n.delete_many, ANN, ids), ids)
                    self.assertEqual(sorted(n.notes), [1, 2, 3, 4, 5, 6], ids)
                with self.assertRaises(PermissionError):
                    self.make().delete_many(ANN, [1, 2])
                with self.assertRaises(KeyError):
                    self.make().delete_many(ANN, [1, 99])
                n = self.make()
                self.assertIsNone(attempt(n.delete_many, ADMIN, [1, 99]))
                self.assertEqual(len(n.notes), 6)


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

PROJ = dd(r'''
    """Organisations and projects (in-process model)."""


    class Projects:
        def __init__(self, members, projects):
            """`members[org][user]` is the role (`"member"` or `"admin"`) of a user in an organisation; `projects[pid]` is a dict with `org` and `name`."""
            self.members = members
            self.projects = projects

        def _role(self, org_id, user):
            role = self.members.get(org_id, {}).get(user)
            if role is None:
                raise PermissionError("not a member of %s" % org_id)
            return role

        def get_project(self, user, org_id, project_id):
            """The project dict, looked up as `/orgs/<org_id>/projects/<project_id>`: the user must belong to the organisation *and* the project must belong to that organisation
            (PermissionError otherwise, KeyError for unknown project ids)."""
            self._role(org_id, user)
            return self.projects[project_id]

        def delete_project(self, user, org_id, project_id):
            """Delete a project. Organisation admins only, and only projects of that organisation (PermissionError)."""
            if self._role(org_id, user) != "admin":
                raise PermissionError("admins only")
            del self.projects[project_id]
''')

AZ.append(dict(
    slug="nested-resources", d=3, product="the project tracker API", func="Projects.get_project", cwe="CWE-639",
    finding="`/orgs/<org>/projects/<id>` checks that the caller belongs to `<org>`, but then loads the project by id alone: a member of any organisation can read (or, as admin of their own org, delete) projects of other organisations by pairing their own org id with a foreign project id.",
    start={"projects.py": PROJ, "README.md": readme("project tracker", "`get_project` and `delete_project` verify the whole path: membership of the organisation in the URL, and that the project's `org` equals that organisation. A mismatch raises `PermissionError` (the same error as for non-members, so ids cannot be probed) and nothing is deleted; unknown project ids raise `KeyError`.")},
    solution={"projects.py": patched(PROJ, (
        '            self._role(org_id, user)\n            return self.projects[project_id]\n',
        '            self._role(org_id, user)\n            project = self.projects[project_id]\n            if project["org"] != org_id:\n                raise PermissionError("project belongs to another organisation")\n            return project\n'), (
        '            del self.projects[project_id]\n',
        '            if self.projects[project_id]["org"] != org_id:\n                raise PermissionError("project belongs to another organisation")\n            del self.projects[project_id]\n'))},
    hidden={"tests/test_projects_security.py": P + dd(r'''
        import copy

        import projects as m

        MEMBERS = {"acme": {"ann": "admin", "bob": "member"}, "globex": {"guy": "admin", "gina": "member"}}
        PROJECTS = {1: {"org": "acme", "name": "rocket"}, 2: {"org": "acme", "name": "anvil"}, 3: {"org": "globex", "name": "secret-merger"}}


        class ProjectsTest(unittest.TestCase):
            def make(self):
                return m.Projects(copy.deepcopy(MEMBERS), copy.deepcopy(PROJECTS))

            def test_own_org(self):
                p = self.make()
                self.assertEqual(p.get_project("ann", "acme", 1)["name"], "rocket")
                self.assertEqual(p.get_project("bob", "acme", 2)["name"], "anvil")
                self.assertEqual(p.get_project("gina", "globex", 3)["name"], "secret-merger")
                p.delete_project("ann", "acme", 2)
                self.assertNotIn(2, p.projects)
                self.assertIsNone(attempt(p.delete_project, "bob", "acme", 1))
                self.assertIn(1, p.projects)
                with self.assertRaises(KeyError):
                    p.get_project("ann", "acme", 99)

            def test_wrong_pairs(self):
                p = self.make()
                for who, org, pid in [("ann", "acme", 3), ("bob", "acme", 3), ("guy", "globex", 1), ("gina", "globex", 2), ("ann", "globex", 3), ("ann", "nope", 1), ("mallory", "acme", 1)]:
                    self.assertIsNone(attempt(p.get_project, who, org, pid), (who, org, pid))
                    self.assertIsNone(attempt(p.delete_project, who, org, pid), (who, org, pid))
                self.assertEqual(p.projects, PROJECTS)
                with self.assertRaises(PermissionError):
                    p.get_project("ann", "acme", 3)
                with self.assertRaises(PermissionError):
                    p.delete_project("ann", "acme", 3)


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

INVITE = dd(r'''
    """Workspace invitations (in-process model)."""

    RANKS = {"viewer": 0, "member": 1, "admin": 2, "owner": 3}


    class Workspace:
        def __init__(self, members):
            """`members` maps a user name to a role in RANKS."""
            self.members = dict(members)
            self.invites = []

        def invite(self, inviter, email, role):
            """Invite `email` with `role`; returns the invitation `{"email", "role", "by"}` (also appended to `self.invites`). Viewers cannot invite anybody; everybody else may invite up to
            their own role (a member can invite viewers and members, an admin up to admin). The `owner` role cannot be handed out by invitation, there is exactly one owner. Unknown roles: ValueError.
            Not-allowed invitations raise PermissionError. Strangers (not a member) cannot invite."""
            if role not in RANKS:
                raise ValueError("unknown role")
            invitation = {"email": email, "role": role, "by": inviter}
            self.invites.append(invitation)
            return invitation
''')

AZ.append(dict(
    slug="invite-escalation", d=2, product="the workspace invitations", func="Workspace.invite", cwe="CWE-269",
    finding="`invite` accepts any role from any caller: a viewer (or a stranger) can invite their own second account as `admin` or `owner`, which is a privilege escalation path through a feature that was meant to be harmless.",
    start={"workspace.py": INVITE, "README.md": readme("workspace", "`invite(inviter, email, role)` follows the docstring: strangers and viewers cannot invite; nobody can grant a role above their own; the `owner` role is never granted by invitation; unknown roles raise `ValueError` (checked first), forbidden invitations `PermissionError` and are not recorded.")},
    solution={"workspace.py": patched(INVITE, (
        '            invitation = {"email": email, "role": role, "by": inviter}\n',
        '''            inviter_role = self.members.get(inviter)
            if inviter_role is None or RANKS[inviter_role] < RANKS["member"]:
                raise PermissionError("not allowed to invite")
            if role == "owner" or RANKS[role] > RANKS[inviter_role]:
                raise PermissionError("cannot grant that role")
            invitation = {"email": email, "role": role, "by": inviter}
'''))},
    hidden={"tests/test_workspace_security.py": P + dd(r'''
        import workspace as m

        MEMBERS = {"olga": "owner", "adam": "admin", "mia": "member", "vic": "viewer"}


        class WorkspaceTest(unittest.TestCase):
            def test_allowed(self):
                w = m.Workspace(MEMBERS)
                for who, role in [("olga", "admin"), ("olga", "viewer"), ("adam", "admin"), ("adam", "member"), ("mia", "member"), ("mia", "viewer")]:
                    inv = w.invite(who, "x@example.com", role)
                    self.assertEqual(inv, {"email": "x@example.com", "role": role, "by": who})
                self.assertEqual(len(w.invites), 6)

            def test_escalation(self):
                for who, role in [("vic", "viewer"), ("vic", "admin"), ("vic", "owner"), ("mia", "admin"), ("mia", "owner"), ("adam", "owner"), ("olga", "owner"), ("stranger", "viewer"), ("stranger", "owner"), ("", "member")]:
                    w = m.Workspace(MEMBERS)
                    self.assertIsNone(attempt(w.invite, who, "evil@example.com", role), (who, role))
                    self.assertEqual(w.invites, [], (who, role))
                w = m.Workspace(MEMBERS)
                with self.assertRaises(ValueError):
                    w.invite("olga", "x@example.com", "superadmin")
                with self.assertRaises(ValueError):
                    w.invite("stranger", "x@example.com", "root")
                with self.assertRaises(PermissionError):
                    w.invite("mia", "x@example.com", "admin")
                self.assertEqual(w.invites, [])


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

ACL = dd(r'''
    """Team-based access to documents, with a cache of decisions."""


    class Acl:
        def __init__(self):
            self.teams = {}        # team -> set of user names
            self.doc_team = {}     # document -> team
            self._cache = {}

        def add_member(self, team, user):
            self.teams.setdefault(team, set()).add(user)

        def remove_member(self, team, user):
            self.teams[team].discard(user)

        def move_doc(self, doc, team):
            self.doc_team[doc] = team

        def delete_team(self, team):
            self.teams.pop(team, None)

        def can_read(self, user, doc):
            """True when `user` belongs to the team that owns `doc`. Decisions are cached for speed, but a change of membership or ownership takes effect immediately."""
            key = (user, doc)
            if key not in self._cache:
                team = self.doc_team.get(doc)
                self._cache[key] = team is not None and user in self.teams.get(team, ())
            return self._cache[key]
''')

AZ.append(dict(
    slug="stale-permissions", d=3, product="the document access layer", func="Acl.can_read", cwe="CWE-613",
    finding="`can_read` caches every decision in `_cache`, and none of the functions that change memberships or document ownership clears it: a user removed from a team (or whose team was deleted, or whose document moved to another team) can keep reading for as long as the process lives, and new members are denied until restart.",
    start={"acl.py": ACL, "README.md": readme("access layer", "`can_read(user, doc)` always reflects the current teams: after `add_member`, `remove_member`, `move_doc` or `delete_team` the very next answer is correct. Keep the cache if you like (it must be invalidated, or key the cache by something that changes), but never answer from stale data.")},
    solution={"acl.py": patched(ACL, (
        '            self.teams.setdefault(team, set()).add(user)\n', '            self.teams.setdefault(team, set()).add(user)\n            self._cache.clear()\n'), (
        '            self.teams[team].discard(user)\n', '            self.teams[team].discard(user)\n            self._cache.clear()\n'), (
        '            self.doc_team[doc] = team\n', '            self.doc_team[doc] = team\n            self._cache.clear()\n'), (
        '            self.teams.pop(team, None)\n', '            self.teams.pop(team, None)\n            self._cache.clear()\n'))},
    hidden={"tests/test_acl_security.py": P + dd(r'''
        import acl as m


        class AclTest(unittest.TestCase):
            def make(self):
                a = m.Acl()
                a.add_member("eng", "ann")
                a.add_member("eng", "bob")
                a.add_member("ops", "cat")
                a.move_doc("design", "eng")
                a.move_doc("runbook", "ops")
                return a

            def test_basic(self):
                a = self.make()
                self.assertTrue(a.can_read("ann", "design"))
                self.assertTrue(a.can_read("bob", "design"))
                self.assertFalse(a.can_read("cat", "design"))
                self.assertFalse(a.can_read("ann", "runbook"))
                self.assertFalse(a.can_read("ann", "nonexistent"))
                self.assertTrue(a.can_read("ann", "design"))

            def test_changes_take_effect_immediately(self):
                a = self.make()
                self.assertTrue(a.can_read("ann", "design"))
                a.remove_member("eng", "ann")
                self.assertFalse(a.can_read("ann", "design"))
                self.assertTrue(a.can_read("bob", "design"))
                self.assertFalse(a.can_read("cat", "design"))
                a.add_member("eng", "cat")
                self.assertTrue(a.can_read("cat", "design"))
                a.add_member("eng", "ann")
                self.assertTrue(a.can_read("ann", "design"))
                a.move_doc("design", "ops")
                self.assertFalse(a.can_read("ann", "design"))
                self.assertFalse(a.can_read("bob", "design"))
                self.assertTrue(a.can_read("cat", "design"))
                self.assertTrue(a.can_read("cat", "runbook"))
                a.delete_team("ops")
                self.assertFalse(a.can_read("cat", "design"))
                self.assertFalse(a.can_read("cat", "runbook"))
                a.add_member("ops", "dan")
                self.assertTrue(a.can_read("dan", "runbook"))


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

AZ_ORDER = ["invoice-owner", "document-share", "admin-functions", "invite-escalation", "tenant-isolation", "bulk-delete", "nested-resources", "stale-permissions"]
AZ.sort(key=lambda s: (s["d"], AZ_ORDER.index(s["slug"])))


@family("security-access-control", category="security", lang="python", kind="fix", n=8,
        summary="broken access control: IDOR, missing function-level checks, tenant isolation, nested ids, privilege escalation, stale permissions")
def gen_authz(rng, n):
    return list(_sec.emit(rng, AZ[:n], tags=["authz"]))


# =================================================================================================================================
#  mass assignment
# =================================================================================================================================
MA = []

PROF = dd(r'''
    """Profile updates of the community site."""


    def update_profile(user, fields):
        """Apply the form `fields` (a dict) to the profile dict `user`, in place, and return it. Members may edit `display_name`, `email`, `bio` and `website` - nothing else. If `fields` contains any
        other key (`is_admin`, `id`, `balance`, `verified`...), the update is refused with ValueError and nothing changes at all (the profile stays exactly as it was)."""
        user.update(fields)
        return user
''')

MA.append(dict(
    slug="profile-form", d=1, product="the community site", func="update_profile", cwe="CWE-915",
    finding="`update_profile` copies every submitted form field into the profile, so a request with an extra `is_admin=true`, `verified=true` or `id=1` field (the edit form has no such inputs, but nothing stops a client from sending them) escalates privileges: mass assignment.",
    start={"profiles.py": PROF, "README.md": readme("profile updates", "`update_profile(user, fields)` accepts only `display_name`, `email`, `bio`, `website`; the profile is updated in place and returned. Any other key makes it raise `ValueError` before anything is changed. Empty `fields` is fine.")},
    solution={"profiles.py": patched(PROF, (
        '        user.update(fields)\n', '        extra = set(fields) - ALLOWED\n        if extra:\n            raise ValueError("fields not editable: %s" % ", ".join(sorted(map(str, extra))))\n        user.update(fields)\n'), (
        '"""Profile updates of the community site."""\n', '"""Profile updates of the community site."""\n\nALLOWED = {"display_name", "email", "bio", "website"}\n'))},
    hidden={"tests/test_profiles_security.py": P + dd(r'''
        import copy

        import profiles as m

        BASE = {"id": 7, "display_name": "Ann", "email": "ann@example.com", "bio": "", "website": "", "is_admin": False, "verified": False, "balance": 0}


        class ProfileTest(unittest.TestCase):
            def test_allowed(self):
                u = copy.deepcopy(BASE)
                out = m.update_profile(u, {"display_name": "Ann O.", "bio": "hello", "website": "https://ann.example", "email": "a@x.example"})
                self.assertIs(out, u)
                self.assertEqual(u["display_name"], "Ann O.")
                self.assertEqual(u["bio"], "hello")
                self.assertEqual(u["email"], "a@x.example")
                self.assertEqual(u["id"], 7)
                self.assertIs(u["is_admin"], False)
                self.assertEqual(m.update_profile(copy.deepcopy(BASE), {}), BASE)

            def test_extra_fields(self):
                for extra in [{"is_admin": True}, {"verified": True}, {"id": 1}, {"balance": 10 ** 6}, {"password_hash": "x"}, {"__class__": "x"}, {"Email": "x"}, {"display_name ": "x"}, {"": "x"}, {"role": "admin"}]:
                    u = copy.deepcopy(BASE)
                    fields = dict(extra, display_name="Mallory", bio="b")
                    self.assertIsNone(attempt(m.update_profile, u, fields), extra)
                    self.assertEqual(u, BASE, extra)
                with self.assertRaises(ValueError):
                    m.update_profile(copy.deepcopy(BASE), {"is_admin": True})


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

ORDERS = dd(r'''
    """Order creation of the web shop."""

    CATALOG = {"pen": 150, "notebook": 450, "backpack": 4900}      # prices in cents


    def create_order(items):
        """Build an order from the cart `items`: a list of dicts with `sku` and `qty` (the browser may also send a `price`, which is ignored: prices come from CATALOG).
        Returns `{"lines": [{"sku", "qty", "unit", "total"}...], "total": cents}`. ValueError for unknown skus, quantities that are not integers from 1 to 100 (bools included), an empty cart,
        or items that are not dicts."""
        lines = []
        for item in items:
            unit = item.get("price", CATALOG[item["sku"]])
            lines.append({"sku": item["sku"], "qty": item["qty"], "unit": unit, "total": unit * item["qty"]})
        return {"lines": lines, "total": sum(line["total"] for line in lines)}
''')

MA.append(dict(
    slug="order-price", d=2, product="the web shop", func="create_order", cwe="CWE-915",
    finding="`create_order` takes the unit price from the cart item when the client supplies one, so `{\"sku\": \"backpack\", \"qty\": 1, \"price\": 1}` buys a backpack for one cent (the price is a server-side fact, not user input), and quantities are not validated (negative quantities give refunds).",
    start={"orders.py": ORDERS, "README.md": readme("orders", "`create_order(items)` prices every line from `CATALOG` and ignores client-supplied prices (the extra key is harmless, not an error). Unknown skus, an empty cart, items that are not dicts, and quantities that are not ints between 1 and 100 raise `ValueError` (bools, floats, strings and `None` are not quantities).")},
    solution={"orders.py": patched(ORDERS, (
        '''        lines = []
        for item in items:
            unit = item.get("price", CATALOG[item["sku"]])
            lines.append({"sku": item["sku"], "qty": item["qty"], "unit": unit, "total": unit * item["qty"]})
''', '''        lines = []
        if not items:
            raise ValueError("empty cart")
        for item in items:
            if not isinstance(item, dict) or item.get("sku") not in CATALOG:
                raise ValueError("bad item")
            qty = item.get("qty")
            if isinstance(qty, bool) or not isinstance(qty, int) or not 1 <= qty <= 100:
                raise ValueError("bad quantity")
            unit = CATALOG[item["sku"]]
            lines.append({"sku": item["sku"], "qty": qty, "unit": unit, "total": unit * qty})
'''))},
    hidden={"tests/test_orders_security.py": P + dd(r'''
        import orders as m


        class OrderTest(unittest.TestCase):
            def test_pricing(self):
                o = m.create_order([{"sku": "pen", "qty": 3}, {"sku": "backpack", "qty": 1, "price": 1}, {"sku": "notebook", "qty": 2, "price": 0}])
                self.assertEqual(o["lines"], [{"sku": "pen", "qty": 3, "unit": 150, "total": 450}, {"sku": "backpack", "qty": 1, "unit": 4900, "total": 4900}, {"sku": "notebook", "qty": 2, "unit": 450, "total": 900}])
                self.assertEqual(o["total"], 6250)
                self.assertEqual(m.create_order([{"sku": "pen", "qty": 100}])["total"], 15000)
                self.assertEqual(m.create_order([{"sku": "pen", "qty": 1}, {"sku": "pen", "qty": 1}])["total"], 300)

            def test_bad_input(self):
                for cart in [[], [{"sku": "ghost", "qty": 1}], [{"sku": "pen", "qty": 0}], [{"sku": "pen", "qty": -5}], [{"sku": "pen", "qty": 101}], [{"sku": "pen", "qty": 1.5}],
                             [{"sku": "pen", "qty": "2"}], [{"sku": "pen", "qty": True}], [{"sku": "pen", "qty": None}], [{"sku": "pen"}], [{"qty": 1}], ["pen"], [None], [{"sku": "pen", "qty": 1}, {"sku": "ghost", "qty": 1}],
                             [{"sku": "pen", "qty": 1}, {"sku": "pen", "qty": -1}]]:
                    self.assertIsNone(attempt(m.create_order, cart), cart)


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

MODEL = dd(r'''
    """A small active-record style model."""


    class Account:
        def __init__(self, **fields):
            """Create an account from keyword fields. Only `name`, `email` and `plan` can be given (`plan` defaults to "free"); anything else raises ValueError. `is_admin` is always False
            and `credits` always 0 for new accounts. A `name` is required."""
            self.is_admin = False
            self.credits = 0
            self.plan = "free"
            for key, value in fields.items():
                setattr(self, key, value)
            if not hasattr(self, "name"):
                raise ValueError("name required")

        def save(self):
            return {"name": self.name, "email": getattr(self, "email", None), "plan": self.plan, "is_admin": self.is_admin, "credits": self.credits}

        def update(self, **fields):
            """Change `name`, `email` or `plan`; other keys raise ValueError and nothing changes."""
            for key, value in fields.items():
                setattr(self, key, value)
''')

MA.append(dict(
    slug="setattr-model", d=2, product="the account service", func="Account.__init__", cwe="CWE-915",
    finding="`Account.__init__` and `update` run `setattr` for every key the caller passes, and the keys come straight from the request body: `{\"is_admin\": true, \"credits\": 100000}` creates a privileged account, and keys such as `save` or `__class__` replace methods or break the object.",
    start={"account.py": MODEL, "README.md": readme("accounts", "Only `name`, `email`, `plan` are assignable, on creation and in `update`; any other key (including privileged fields, method names and dunder names) raises `ValueError`, and a failed `update` changes nothing (check all keys before applying any). `is_admin`/`credits` are never set from outside.")},
    solution={"account.py": patched(MODEL, (
        '"""A small active-record style model."""\n', '"""A small active-record style model."""\n\nASSIGNABLE = ("name", "email", "plan")\n'), (
        '''            self.is_admin = False
            self.credits = 0
            self.plan = "free"
            for key, value in fields.items():
''', '''            bad = [k for k in fields if k not in ASSIGNABLE]
            if bad:
                raise ValueError("cannot set: %s" % ", ".join(map(str, bad)))
            self.is_admin = False
            self.credits = 0
            self.plan = "free"
            for key, value in fields.items():
'''), (
        '''            """Change `name`, `email` or `plan`; other keys raise ValueError and nothing changes."""
            for key, value in fields.items():
''', '''            """Change `name`, `email` or `plan`; other keys raise ValueError and nothing changes."""
            bad = [k for k in fields if k not in ASSIGNABLE]
            if bad:
                raise ValueError("cannot set: %s" % ", ".join(map(str, bad)))
            for key, value in fields.items():
'''))},
    hidden={"tests/test_account_security.py": P + dd(r'''
        import account as m


        class AccountTest(unittest.TestCase):
            def test_normal(self):
                a = m.Account(name="Ann", email="ann@example.com", plan="pro")
                self.assertEqual(a.save(), {"name": "Ann", "email": "ann@example.com", "plan": "pro", "is_admin": False, "credits": 0})
                b = m.Account(name="Bob")
                self.assertEqual(b.save(), {"name": "Bob", "email": None, "plan": "free", "is_admin": False, "credits": 0})
                b.update(email="b@example.com", plan="team")
                self.assertEqual(b.save()["plan"], "team")
                self.assertIsNone(attempt(m.Account))
                self.assertIsNone(attempt(m.Account, email="x@example.com"))

            def test_privileged_and_odd_keys(self):
                for extra in [{"is_admin": True}, {"credits": 100000}, {"save": lambda: {"is_admin": True}}, {"__class__": dict}, {"update": None}, {"__dict__": {}}, {"_secret": 1}, {"Name": "x"}]:
                    self.assertIsNone(attempt(m.Account, name="Mallory", **extra), list(extra))
                a = m.Account(name="Ann")
                before = a.save()
                for extra in [{"is_admin": True}, {"credits": 5}, {"save": None}, {"__class__": dict}, {"name": "Changed", "is_admin": True}, {"plan": "pro", "credits": 1}]:
                    self.assertIsNone(attempt(a.update, **extra), list(extra))
                    self.assertEqual(a.save(), before, list(extra))
                self.assertTrue(callable(a.save))
                self.assertIs(type(a), m.Account)


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

IMP = dd(r'''
    """CSV import of users."""


    def import_users(actor, rows):
        """Create users from `rows`, a list of dicts with `name` and optionally `email`, `role` and `disabled` (strings as read from a CSV file). Returns the list of created users as dicts
        `{"name", "email", "role", "disabled"}` with defaults `email` "", `role` "member", `disabled` False. Roles: "member", "admin". Only an `actor` with role "admin" may set `role` or
        `disabled` in the file; for other actors those columns are not allowed: a row that has them (non-empty) makes the whole import fail with PermissionError and nothing is created.
        Unknown roles: ValueError. `disabled` is "true"/"false" (any case), anything else is ValueError. A missing or empty name: ValueError."""
        users = []
        for row in rows:
            users.append({"name": row["name"], "email": row.get("email", ""), "role": row.get("role") or "member", "disabled": row.get("disabled", "").lower() == "true"})
        return users
''')

MA.append(dict(
    slug="csv-import", d=3, product="the user import", func="import_users", cwe="CWE-915",
    finding="`import_users` applies the `role` and `disabled` columns of an uploaded file no matter who uploads it, so any user allowed to import a roster of colleagues can add themselves as an admin (and re-enable disabled accounts) through two extra columns.",
    start={"importer.py": IMP, "README.md": readme("user import", "`import_users(actor, rows)` is all-or-nothing and validates every row first. Non-admin actors may only provide `name` and `email`: a non-empty `role` or `disabled` cell raises `PermissionError`. Admins may use all columns, with validated values (`role` in member/admin, `disabled` true/false, any letter case; otherwise `ValueError`). Names must be non-empty strings; duplicates within one file are `ValueError`.")},
    solution={"importer.py": patched(IMP, (
        '''        users = []
        for row in rows:
            users.append({"name": row["name"], "email": row.get("email", ""), "role": row.get("role") or "member", "disabled": row.get("disabled", "").lower() == "true"})
        return users
''', '''        is_admin = actor.get("role") == "admin"
        users, seen = [], set()
        for row in rows:
            name = row.get("name")
            if not isinstance(name, str) or not name.strip() or name in seen:
                raise ValueError("bad or duplicate name")
            seen.add(name)
            role, disabled = (row.get("role") or "").strip(), (row.get("disabled") or "").strip()
            if (role or disabled) and not is_admin:
                raise PermissionError("only admins may set role or disabled")
            if role and role not in ("member", "admin"):
                raise ValueError("unknown role")
            if disabled and disabled.lower() not in ("true", "false"):
                raise ValueError("bad disabled flag")
            users.append({"name": name, "email": row.get("email", ""), "role": role or "member", "disabled": disabled.lower() == "true"})
        return users
'''))},
    hidden={"tests/test_importer_security.py": P + dd(r'''
        import importer as m

        ROOT, ANN = {"name": "root", "role": "admin"}, {"name": "ann", "role": "member"}


        class ImportTest(unittest.TestCase):
            def test_plain_rows(self):
                rows = [{"name": "bob", "email": "bob@example.com"}, {"name": "cat"}, {"name": "dan", "email": "", "role": "", "disabled": ""}]
                expected = [{"name": "bob", "email": "bob@example.com", "role": "member", "disabled": False}, {"name": "cat", "email": "", "role": "member", "disabled": False},
                            {"name": "dan", "email": "", "role": "member", "disabled": False}]
                self.assertEqual(m.import_users(ANN, rows), expected)
                self.assertEqual(m.import_users(ROOT, rows), expected)
                self.assertEqual(m.import_users(ANN, []), [])

            def test_admin_columns(self):
                rows = [{"name": "bob", "role": "admin"}, {"name": "cat", "disabled": "TRUE"}, {"name": "dan", "role": "member", "disabled": "False"}]
                got = m.import_users(ROOT, rows)
                self.assertEqual([(u["role"], u["disabled"]) for u in got], [("admin", False), ("member", True), ("member", False)])
                for bad in [{"name": "x", "role": "root"}, {"name": "x", "disabled": "yes"}, {"name": ""}, {"name": None}, {}, {"name": "a"}, {"name": "A", "role": "Admin"}]:
                    rows = [bad, {"name": "a"}] if bad.get("name") != "a" else [bad, bad]
                    self.assertIsNone(attempt(m.import_users, ROOT, rows), bad)

            def test_non_admins_cannot_set_privileged_columns(self):
                for extra in [{"role": "admin"}, {"role": "member"}, {"disabled": "false"}, {"disabled": "true"}, {"role": "admin", "disabled": "false"}, {"role": "root"}]:
                    rows = [{"name": "ok1"}, dict({"name": "me"}, **extra), {"name": "ok2"}]
                    self.assertIsNone(attempt(m.import_users, ANN, rows), extra)
                with self.assertRaises(PermissionError):
                    m.import_users(ANN, [{"name": "me", "role": "admin"}])
                self.assertIsNone(attempt(m.import_users, {"name": "x", "role": "Admin"}, [{"name": "me", "role": "admin"}]))
                self.assertIsNone(attempt(m.import_users, {"name": "x"}, [{"name": "me", "role": "admin"}]))


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

NESTED = dd(r'''
    """Per-user settings with partial updates."""

    DEFAULTS = {"theme": "light", "language": "en", "notifications": {"email": True, "sms": False}, "limits": {"max_items": 50}, "billing": {"plan": "free", "seats": 1}}


    def merge(settings, patch):
        """Recursively merge the dict `patch` into `settings` (in place) and return `settings`."""
        for key, value in patch.items():
            if isinstance(value, dict) and isinstance(settings.get(key), dict):
                merge(settings[key], value)
            else:
                settings[key] = value
        return settings


    def apply_patch(settings, patch):
        """Apply a user-submitted partial update. The user may change `theme` ("light"/"dark"), `language` (2 lowercase letters), `notifications.email` and `notifications.sms` (bools) and
        `limits.max_items` (an int from 1 to 500). Everything else - `billing.*`, unknown keys, other types - is rejected with ValueError, and then the settings are left completely unchanged."""
        return merge(settings, patch)
''')

MA.append(dict(
    slug="nested-settings", d=3, product="the settings API", func="apply_patch", cwe="CWE-915",
    finding="`apply_patch` deep-merges whatever JSON the client sends: a patch like `{\"billing\": {\"plan\": \"enterprise\", \"seats\": 9999}}` upgrades the account for free, `{\"limits\": {\"max_items\": 10**9}}` removes the quota, and wrongly typed values end up in the settings.",
    start={"settings.py": NESTED, "README.md": readme("settings", "`apply_patch(settings, patch)` is validated and atomic: exactly the five paths listed in its docstring are editable, with the stated types and ranges (bools are not ints, ints are not bools); every other path, unknown key, or a dict where a scalar belongs raises `ValueError` and `settings` stays unchanged. `merge` itself remains a plain deep merge.")},
    solution={"settings.py": patched(NESTED, (
        '        return merge(settings, patch)\n', '''        def check(node, path, spec):
            if not isinstance(node, dict):
                raise ValueError("object expected at " + (path or "root"))
            for key, value in node.items():
                full = path + "." + key if path else key
                rule = spec.get(key) if isinstance(key, str) else None
                if rule is None:
                    raise ValueError("not editable: " + full)
                if isinstance(rule, dict):
                    check(value, full, rule)
                elif not rule(value):
                    raise ValueError("bad value for " + full)

        spec = {
            "theme": lambda v: v in ("light", "dark"),
            "language": lambda v: isinstance(v, str) and len(v) == 2 and v.isascii() and v.islower() and v.isalpha(),
            "notifications": {"email": lambda v: isinstance(v, bool), "sms": lambda v: isinstance(v, bool)},
            "limits": {"max_items": lambda v: isinstance(v, int) and not isinstance(v, bool) and 1 <= v <= 500},
        }
        check(patch, "", spec)
        return merge(settings, patch)
'''))},
    hidden={"tests/test_settings_security.py": P + dd(r'''
        import copy

        import settings as m


        class SettingsTest(unittest.TestCase):
            def test_allowed_changes(self):
                s = copy.deepcopy(m.DEFAULTS)
                m.apply_patch(s, {"theme": "dark", "notifications": {"sms": True}, "limits": {"max_items": 500}, "language": "de"})
                self.assertEqual(s["theme"], "dark")
                self.assertEqual(s["language"], "de")
                self.assertEqual(s["notifications"], {"email": True, "sms": True})
                self.assertEqual(s["limits"]["max_items"], 500)
                self.assertEqual(s["billing"], {"plan": "free", "seats": 1})
                self.assertIs(m.apply_patch(s, {}), s)
                m.apply_patch(s, {"limits": {"max_items": 1}})
                self.assertEqual(s["limits"]["max_items"], 1)

            def test_everything_else_is_refused_atomically(self):
                bad = [{"billing": {"plan": "enterprise"}}, {"billing": {"seats": 9999}}, {"billing": "gold"}, {"limits": {"max_items": 10 ** 9}}, {"limits": {"max_items": 0}}, {"limits": {"max_items": True}},
                       {"limits": {"max_items": "50"}}, {"limits": {"max_items": 5.5}}, {"limits": 7}, {"theme": "neon"}, {"theme": None}, {"theme": {"x": 1}}, {"language": "english"}, {"language": "EN"},
                       {"language": "e1"}, {"notifications": {"email": "yes"}}, {"notifications": {"push": True}}, {"notifications": True}, {"admin": True}, {"__class__": {}}, {"theme": {}}, {"limits": {"max_items": 5, "extra": 1}},
                       {1: "x"}, {"": 1}]
                for patch in bad:
                    s = copy.deepcopy(m.DEFAULTS)
                    self.assertIsNone(attempt(m.apply_patch, s, dict(patch, theme="dark") if "theme" not in patch else patch), patch)
                    self.assertEqual(s, m.DEFAULTS, patch)
                s = copy.deepcopy(m.DEFAULTS)
                self.assertIsNone(attempt(m.apply_patch, s, {"theme": "dark", "billing": {"plan": "x"}}))
                self.assertEqual(s["theme"], "light")


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

MA_ORDER = ["profile-form", "order-price", "setattr-model", "csv-import", "nested-settings"]
MA.sort(key=lambda s: (s["d"], MA_ORDER.index(s["slug"])))


@family("security-mass-assignment", category="security", lang="python", kind="fix", n=5,
        summary="mass assignment: allow-lists for profile fields, prices, model attributes, CSV columns and nested settings")
def gen_mass(rng, n):
    return list(_sec.emit(rng, MA[:n], tags=["mass-assignment"]))

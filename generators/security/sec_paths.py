"""Security families: path traversal (file access confined to a directory)."""
from fx import dd, family

from . import _sec

P = _sec.PY_PRELUDE


def readme(title, body):
    return f"# {title}\n\n{body.strip()}\n"


def common_setup(extra=""):
    return dd(f'''
        def setUp(self):
            self.root = tmpdir()
            write(os.path.join(self.root, "secret.txt"), b"TOP-SECRET")
            {extra}

        def tearDown(self):
            shutil.rmtree(self.root, ignore_errors=True)
    ''')


SC = []

# ---------------------------------------------------------------------------------------------------------------
# 1. avatars: open(join(base, name)) with no check
SC.append(dict(
    slug="avatar-names", d=1, product="the profile service", func="load_avatar", cwe="CWE-22",
    finding="`load_avatar` opens `os.path.join(AVATAR_DIR, name)` for whatever `name` the request supplies, so a name like `../secret.txt` (or an absolute path) reads files outside the avatar directory.",
    start={
        "avatars.py": dd('''
            """Avatar storage for the profile service."""
            import os

            AVATAR_DIR = os.environ.get("AVATAR_DIR", "avatars")


            def load_avatar(name):
                """Return the bytes of the avatar stored under `name` (it may contain one sub-directory, e.g. "teams/blue.png")."""
                with open(os.path.join(AVATAR_DIR, name), "rb") as fh:
                    return fh.read()
        '''),
        "README.md": readme("avatars", "`load_avatar(name)` returns the bytes of `AVATAR_DIR/<name>`. Names may name a file in a sub-directory (`teams/blue.png`) and may contain dots (`a..b.png`). A missing avatar raises `FileNotFoundError`."),
    },
    visible={"tests/test_avatars.py": P + dd('''
        import avatars as m


        class Basic(unittest.TestCase):
            def test_load(self):
                root = tmpdir()
                write(os.path.join(root, "me.png"), b"PNG-me")
                m.AVATAR_DIR = root
                self.assertEqual(m.load_avatar("me.png"), b"PNG-me")


        if __name__ == "__main__":
            unittest.main()
    ''')},
    solution={"avatars.py": dd('''
        """Avatar storage for the profile service."""
        import os

        AVATAR_DIR = os.environ.get("AVATAR_DIR", "avatars")


        def _resolve(name):
            base = os.path.realpath(AVATAR_DIR)
            full = os.path.realpath(os.path.join(base, name))
            if os.path.commonpath([base, full]) != base:
                raise PermissionError("avatar path escapes the avatar directory")
            return full


        def load_avatar(name):
            """Return the bytes of the avatar stored under `name` (it may contain one sub-directory, e.g. "teams/blue.png")."""
            with open(_resolve(name), "rb") as fh:
                return fh.read()
    ''')},
    hidden={"tests/test_avatar_security.py": P + dd('''
        import avatars as m


        class AvatarTest(unittest.TestCase):
            def setUp(self):
                self.root = tmpdir()
                self.base = os.path.join(self.root, "avatars")
                write(os.path.join(self.base, "me.png"), b"PNG-me")
                write(os.path.join(self.base, "teams", "blue.png"), b"PNG-blue")
                write(os.path.join(self.base, "a..b.png"), b"PNG-dots")
                write(os.path.join(self.root, "secret.txt"), b"TOP-SECRET")
                m.AVATAR_DIR = self.base

            def tearDown(self):
                shutil.rmtree(self.root, ignore_errors=True)

            def test_normal(self):
                self.assertEqual(m.load_avatar("me.png"), b"PNG-me")
                self.assertEqual(m.load_avatar("teams/blue.png"), b"PNG-blue")
                self.assertEqual(m.load_avatar("a..b.png"), b"PNG-dots")
                self.assertEqual(m.load_avatar("teams/../me.png"), b"PNG-me")

            def test_missing(self):
                with self.assertRaises(FileNotFoundError):
                    m.load_avatar("nope.png")

            def test_escape(self):
                payloads = ["../secret.txt", "teams/../../secret.txt", "./../secret.txt", os.path.join(self.root, "secret.txt"), "teams/./../../secret.txt", "..//secret.txt"]
                for name in payloads:
                    self.assertNotIn(b"TOP-SECRET", attempt(m.load_avatar, name) or b"", name)


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

# ---------------------------------------------------------------------------------------------------------------
# 2. replace("../", "") blacklist
SC.append(dict(
    slug="note-blacklist", d=2, product="the notes app", func="read_note", cwe="CWE-22",
    finding="`read_note` strips `../` from the note name before opening it, but `....//secret` turns into `../secret` after the replacement, and the sanitising does not stop absolute paths either.",
    start={
        "notes.py": dd('''
            """Plain-text notes stored as files."""
            import os

            NOTES_DIR = os.environ.get("NOTES_DIR", "notes")


            def read_note(name):
                """Return the text of the note called `name` (stored as NOTES_DIR/<name>.txt; names may use sub-folders)."""
                name = name.replace("../", "")
                with open(os.path.join(NOTES_DIR, name + ".txt"), encoding="utf-8") as fh:
                    return fh.read()


            def list_notes():
                """Names of all notes, sorted, without the .txt suffix (sub-folders are written with '/')."""
                out = []
                for dirpath, _, files in os.walk(NOTES_DIR):
                    for f in files:
                        if f.endswith(".txt"):
                            rel = os.path.relpath(os.path.join(dirpath, f), NOTES_DIR)
                            out.append(rel[:-4].replace(os.sep, "/"))
                return sorted(out)
        '''),
        "README.md": readme("notes", "`read_note(name)` returns the text of `NOTES_DIR/<name>.txt`; names may contain `/` for sub-folders and dots inside names are fine (`v1..2`). A missing note raises `FileNotFoundError`. `list_notes()` lists every note."),
    },
    solution={"notes.py": dd('''
        """Plain-text notes stored as files."""
        import os

        NOTES_DIR = os.environ.get("NOTES_DIR", "notes")


        def _path(name):
            base = os.path.realpath(NOTES_DIR)
            full = os.path.realpath(os.path.join(base, name + ".txt"))
            if os.path.commonpath([base, full]) != base:
                raise ValueError("note name escapes the notes directory")
            return full


        def read_note(name):
            """Return the text of the note called `name` (stored as NOTES_DIR/<name>.txt; names may use sub-folders)."""
            with open(_path(name), encoding="utf-8") as fh:
                return fh.read()


        def list_notes():
            """Names of all notes, sorted, without the .txt suffix (sub-folders are written with '/')."""
            out = []
            for dirpath, _, files in os.walk(NOTES_DIR):
                for f in files:
                    if f.endswith(".txt"):
                        rel = os.path.relpath(os.path.join(dirpath, f), NOTES_DIR)
                        out.append(rel[:-4].replace(os.sep, "/"))
            return sorted(out)
    ''')},
    hidden={"tests/test_notes_security.py": P + dd('''
        import notes as m


        class NotesTest(unittest.TestCase):
            def setUp(self):
                self.root = tmpdir()
                self.base = os.path.join(self.root, "notes")
                write(os.path.join(self.base, "todo.txt"), "buy milk")
                write(os.path.join(self.base, "ideas", "2024.txt"), "build a boat")
                write(os.path.join(self.base, "v1..2.txt"), "dots")
                write(os.path.join(self.root, "secret.txt"), "TOP-SECRET")
                m.NOTES_DIR = self.base

            def tearDown(self):
                shutil.rmtree(self.root, ignore_errors=True)

            def test_normal(self):
                self.assertEqual(m.read_note("todo"), "buy milk")
                self.assertEqual(m.read_note("ideas/2024"), "build a boat")
                self.assertEqual(m.read_note("v1..2"), "dots")
                self.assertEqual(m.read_note("ideas/../todo"), "buy milk")
                self.assertEqual(m.list_notes(), ["ideas/2024", "todo", "v1..2"])

            def test_missing(self):
                with self.assertRaises(FileNotFoundError):
                    m.read_note("nothing")

            def test_escape(self):
                payloads = ["../secret", "....//secret", "ideas/....//....//secret", "..././secret", ".../...//secret", os.path.join(self.root, "secret"), "ideas/../../secret", "..%2fsecret"]
                for name in payloads:
                    self.assertNotIn("TOP-SECRET", attempt(m.read_note, name) or "", name)


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

# ---------------------------------------------------------------------------------------------------------------
# 3. startswith prefix collision
SC.append(dict(
    slug="report-prefix", d=2, product="the reporting service", func="open_report", cwe="CWE-22",
    finding="`open_report` checks that the resolved path starts with the reports directory, but a sibling directory such as `reports_private` shares that prefix, so `../reports_private/q3.csv` passes the check.",
    start={
        "reports.py": dd('''
            """Download of generated reports."""
            import os

            BASE = os.environ.get("REPORTS_DIR", "reports")


            def open_report(name):
                """Return the text of the report file `name` inside the reports directory (sub-folders are allowed)."""
                base = os.path.abspath(BASE)
                path = os.path.abspath(os.path.join(base, name))
                if not path.startswith(base):
                    raise ValueError("report is outside the reports directory")
                with open(path, encoding="utf-8") as fh:
                    return fh.read()
        '''),
        "README.md": readme("reports", "`open_report(name)` returns the text of `BASE/<name>`. Sub-folders (`2024/q1.csv`) are allowed, a missing file raises `FileNotFoundError`, and anything outside `BASE` is refused."),
    },
    solution={"reports.py": dd('''
        """Download of generated reports."""
        import os

        BASE = os.environ.get("REPORTS_DIR", "reports")


        def open_report(name):
            """Return the text of the report file `name` inside the reports directory (sub-folders are allowed)."""
            base = os.path.realpath(BASE)
            path = os.path.realpath(os.path.join(base, name))
            if os.path.commonpath([base, path]) != base:
                raise ValueError("report is outside the reports directory")
            with open(path, encoding="utf-8") as fh:
                return fh.read()
    ''')},
    hidden={"tests/test_reports_security.py": P + dd('''
        import reports as m


        class ReportsTest(unittest.TestCase):
            def setUp(self):
                self.root = tmpdir()
                self.base = os.path.join(self.root, "reports")
                write(os.path.join(self.base, "2024", "q1.csv"), "a,b")
                write(os.path.join(self.base, "summary.txt"), "ok")
                write(os.path.join(self.root, "reports_private", "q3.csv"), "TOP-SECRET")
                write(os.path.join(self.root, "reports2.txt"), "TOP-SECRET")
                m.BASE = self.base

            def tearDown(self):
                shutil.rmtree(self.root, ignore_errors=True)

            def test_normal(self):
                self.assertEqual(m.open_report("2024/q1.csv"), "a,b")
                self.assertEqual(m.open_report("summary.txt"), "ok")
                self.assertEqual(m.open_report("2024/../summary.txt"), "ok")

            def test_missing(self):
                with self.assertRaises(FileNotFoundError):
                    m.open_report("none.txt")

            def test_escape(self):
                for name in ["../reports_private/q3.csv", "../reports2.txt", "2024/../../reports_private/q3.csv", os.path.join(self.root, "reports_private", "q3.csv")]:
                    self.assertNotIn("TOP-SECRET", attempt(m.open_report, name) or "", name)


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

# ---------------------------------------------------------------------------------------------------------------
# 4. percent-decoding after the check
SC.append(dict(
    slug="static-decode", d=3, product="the embedded web server", func="serve_static", cwe="CWE-22",
    finding="`serve_static` rejects paths with a `..` segment but only looks at the raw request path and percent-decodes it afterwards, so `/%2e%2e/secret.txt`, `/..%2fsecret.txt` and an encoded absolute path all get through.",
    start={
        "staticfiles.py": dd('''
            """Static file handler of the embedded web server."""
            import os
            from urllib.parse import unquote

            WEBROOT = os.environ.get("WEBROOT", "www")


            def serve_static(url_path):
                """Map a request path to (status, body): (200, bytes) for a file, (404, b"not found"), (403, b"forbidden") for forbidden paths.
                The request path is percent-encoded; a directory serves its index.html; "/" serves the root index.html."""
                if ".." in url_path.split("/"):
                    return 403, b"forbidden"
                rel = unquote(url_path.lstrip("/"))
                full = os.path.join(WEBROOT, rel)
                if os.path.isdir(full):
                    full = os.path.join(full, "index.html")
                if not os.path.isfile(full):
                    return 404, b"not found"
                with open(full, "rb") as fh:
                    return 200, fh.read()
        '''),
        "README.md": readme("staticfiles", "`serve_static(url_path)` serves files below `WEBROOT`. The path is percent-encoded UTF-8 (`/caf%C3%A9.txt`, `/a%20b.txt`); `/` and directories serve their `index.html`; unknown files give `(404, b\"not found\")`; paths that try to leave the web root give `(403, b\"forbidden\")` or a 404, never the file's content."),
    },
    solution={"staticfiles.py": dd('''
        """Static file handler of the embedded web server."""
        import os
        from urllib.parse import unquote

        WEBROOT = os.environ.get("WEBROOT", "www")


        def serve_static(url_path):
            """Map a request path to (status, body): (200, bytes) for a file, (404, b"not found"), (403, b"forbidden") for forbidden paths.
            The request path is percent-encoded; a directory serves its index.html; "/" serves the root index.html."""
            rel = unquote(url_path).lstrip("/")
            if "\\x00" in rel:
                return 403, b"forbidden"
            base = os.path.realpath(WEBROOT)
            full = os.path.realpath(os.path.join(base, rel))
            if os.path.commonpath([base, full]) != base:
                return 403, b"forbidden"
            if os.path.isdir(full):
                full = os.path.join(full, "index.html")
            if not os.path.isfile(full):
                return 404, b"not found"
            with open(full, "rb") as fh:
                return 200, fh.read()
    ''')},
    hidden={"tests/test_static_security.py": P + dd('''
        import staticfiles as m


        class StaticTest(unittest.TestCase):
            def setUp(self):
                self.root = tmpdir()
                self.web = os.path.join(self.root, "www")
                write(os.path.join(self.web, "index.html"), b"<h1>home</h1>")
                write(os.path.join(self.web, "css", "site.css"), b"body{}")
                write(os.path.join(self.web, "docs", "index.html"), b"docs home")
                write(os.path.join(self.web, "a b.txt"), b"spaced")
                write(os.path.join(self.web, "caf\\u00e9.txt"), b"unicode")
                write(os.path.join(self.web, "v1..2.txt"), b"dots")
                write(os.path.join(self.root, "secret.txt"), b"TOP-SECRET")
                m.WEBROOT = self.web

            def tearDown(self):
                shutil.rmtree(self.root, ignore_errors=True)

            def test_normal(self):
                self.assertEqual(m.serve_static("/"), (200, b"<h1>home</h1>"))
                self.assertEqual(m.serve_static("/index.html"), (200, b"<h1>home</h1>"))
                self.assertEqual(m.serve_static("/css/site.css"), (200, b"body{}"))
                self.assertEqual(m.serve_static("/docs/"), (200, b"docs home"))
                self.assertEqual(m.serve_static("/docs"), (200, b"docs home"))
                self.assertEqual(m.serve_static("/a%20b.txt"), (200, b"spaced"))
                self.assertEqual(m.serve_static("/caf%C3%A9.txt"), (200, b"unicode"))
                self.assertEqual(m.serve_static("/v1..2.txt"), (200, b"dots"))
                self.assertEqual(m.serve_static("/css/%2e%2e/index.html"), (200, b"<h1>home</h1>"))

            def test_missing(self):
                self.assertEqual(m.serve_static("/nope.txt")[0], 404)

            def test_escape(self):
                abs_enc = "/%2f" + self.root.lstrip("/").replace("/", "%2f") + "%2fsecret.txt"
                payloads = ["/%2e%2e/secret.txt", "/..%2fsecret.txt", "/%2E%2E%2Fsecret.txt", "/css/%2e%2e/%2e%2e/secret.txt", "/../secret.txt", "/css/../../secret.txt", abs_enc,
                            "/" + self.root + "/secret.txt", "//" + self.root + "/secret.txt", "/%2e%2e%2fsecret.txt"]
                for p in payloads:
                    res = attempt(m.serve_static, p)
                    body = res[1] if res else b""
                    self.assertNotIn(b"TOP-SECRET", body, p)


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

# ---------------------------------------------------------------------------------------------------------------
# 5. template include
SC.append(dict(
    slug="template-include", d=3, product="the mail template engine", func="render", cwe="CWE-22",
    finding="template names, including the names in `{% include ... %}` tags that anyone with template-edit rights can write, are joined to the template directory without checking, so `{% include ../../secret %}` pulls in files from elsewhere.",
    start={
        "tpl.py": dd('''
            """A tiny include-only template engine for transactional mails."""
            import os
            import re

            TPL_DIR = os.environ.get("TPL_DIR", "templates")
            INCLUDE = re.compile(r"\\{%\\s*include\\s+([^\\s%]+)\\s*%\\}")


            class TemplateError(Exception):
                pass


            def _load(name):
                path = os.path.join(TPL_DIR, name + ".tpl")
                try:
                    with open(path, encoding="utf-8") as fh:
                        return fh.read()
                except FileNotFoundError:
                    raise TemplateError("no such template: " + name)


            def render(name, depth=0):
                """Text of template `name` with every `{% include other %}` replaced by the rendered template `other`."""
                if depth > 5:
                    raise TemplateError("includes nested too deeply")
                text = _load(name)
                return INCLUDE.sub(lambda m: render(m.group(1), depth + 1), text)
        '''),
        "README.md": readme("tpl", "Templates live in `TPL_DIR` as `<name>.tpl`; names may contain `/` for sub-folders (`partials/footer`). `{% include name %}` is replaced by the rendered template `name`; includes may nest up to 5 levels. Unknown templates and too deep nesting raise `TemplateError`."),
    },
    solution={"tpl.py": dd('''
        """A tiny include-only template engine for transactional mails."""
        import os
        import re

        TPL_DIR = os.environ.get("TPL_DIR", "templates")
        INCLUDE = re.compile(r"\\{%\\s*include\\s+([^\\s%]+)\\s*%\\}")


        class TemplateError(Exception):
            pass


        def _load(name):
            base = os.path.realpath(TPL_DIR)
            path = os.path.realpath(os.path.join(base, name + ".tpl"))
            if os.path.commonpath([base, path]) != base:
                raise TemplateError("template outside the template directory: " + name)
            try:
                with open(path, encoding="utf-8") as fh:
                    return fh.read()
            except FileNotFoundError:
                raise TemplateError("no such template: " + name)


        def render(name, depth=0):
            """Text of template `name` with every `{% include other %}` replaced by the rendered template `other`."""
            if depth > 5:
                raise TemplateError("includes nested too deeply")
            text = _load(name)
            return INCLUDE.sub(lambda m: render(m.group(1), depth + 1), text)
    ''')},
    hidden={"tests/test_tpl_security.py": P + dd('''
        import tpl as m


        class TplTest(unittest.TestCase):
            def setUp(self):
                self.root = tmpdir()
                self.dir = os.path.join(self.root, "templates")
                write(os.path.join(self.dir, "welcome.tpl"), "Hello!\\n{% include partials/footer %}")
                write(os.path.join(self.dir, "partials", "footer.tpl"), "-- team {% include partials/sig %}")
                write(os.path.join(self.dir, "partials", "sig.tpl"), "ACME")
                write(os.path.join(self.dir, "loop.tpl"), "{% include loop %}")
                write(os.path.join(self.dir, "evil1.tpl"), "x {% include ../secret %} y")
                write(os.path.join(self.dir, "evil2.tpl"), "x {% include partials/../../secret %} y")
                write(os.path.join(self.dir, "evil3.tpl"), "x {% include " + os.path.join(self.root, "secret") + " %} y")
                write(os.path.join(self.root, "secret.tpl"), "TOP-SECRET")
                m.TPL_DIR = self.dir

            def tearDown(self):
                shutil.rmtree(self.root, ignore_errors=True)

            def test_normal(self):
                self.assertEqual(m.render("welcome"), "Hello!\\n-- team ACME")
                self.assertEqual(m.render("partials/sig"), "ACME")

            def test_errors(self):
                with self.assertRaises(m.TemplateError):
                    m.render("missing")
                with self.assertRaises(m.TemplateError):
                    m.render("loop")

            def test_escape(self):
                for name in ["evil1", "evil2", "evil3", "../secret", os.path.join(self.root, "secret")]:
                    self.assertNotIn("TOP-SECRET", attempt(m.render, name) or "", name)


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

# ---------------------------------------------------------------------------------------------------------------
# 6. symlink inside the attachments directory
SC.append(dict(
    slug="attachment-symlink", d=3, product="the ticket system", func="read_attachment", cwe="CWE-59",
    finding="`read_attachment` compares absolute paths lexically, but attachments are unpacked from customer archives and can contain symbolic links, so a link inside a ticket folder that points to `../../secret.txt` is followed when the file is opened.",
    start={
        "attachments.py": dd('''
            """Attachment download for the ticket system."""
            import os

            ATTACH_DIR = os.environ.get("ATTACH_DIR", "attachments")


            def read_attachment(ticket_id, filename):
                """Bytes of ATTACH_DIR/<ticket id>/<filename>. `filename` may name a file in a sub-folder; symlinks that stay inside the ticket's folder are fine."""
                base = os.path.abspath(os.path.join(ATTACH_DIR, str(int(ticket_id))))
                path = os.path.abspath(os.path.join(base, filename))
                if os.path.commonpath([base, path]) != base:
                    raise PermissionError("outside the ticket folder")
                with open(path, "rb") as fh:
                    return fh.read()
        '''),
        "README.md": readme("attachments", "`read_attachment(ticket_id, filename)` returns the bytes of `ATTACH_DIR/<ticket_id>/<filename>`. `ticket_id` must be an integer. Sub-folders are allowed. Customer archives may contain symlinks: links that stay inside the same ticket folder keep working, links that lead anywhere else must not be followed."),
    },
    solution={"attachments.py": dd('''
        """Attachment download for the ticket system."""
        import os

        ATTACH_DIR = os.environ.get("ATTACH_DIR", "attachments")


        def read_attachment(ticket_id, filename):
            """Bytes of ATTACH_DIR/<ticket id>/<filename>. `filename` may name a file in a sub-folder; symlinks that stay inside the ticket's folder are fine."""
            base = os.path.realpath(os.path.join(ATTACH_DIR, str(int(ticket_id))))
            path = os.path.realpath(os.path.join(base, filename))
            if os.path.commonpath([base, path]) != base:
                raise PermissionError("outside the ticket folder")
            with open(path, "rb") as fh:
                return fh.read()
    ''')},
    hidden={"tests/test_attachments_security.py": P + dd('''
        import attachments as m


        class AttachmentTest(unittest.TestCase):
            def setUp(self):
                self.root = tmpdir()
                self.base = os.path.join(self.root, "attachments")
                t7 = os.path.join(self.base, "7")
                write(os.path.join(t7, "log.txt"), b"log7")
                write(os.path.join(t7, "sub", "shot.png"), b"png7")
                write(os.path.join(self.base, "8", "private.txt"), b"TOP-SECRET")
                write(os.path.join(self.root, "secret.txt"), b"TOP-SECRET")
                os.symlink("log.txt", os.path.join(t7, "latest"))
                os.symlink(os.path.join("..", "..", "..", "secret.txt"), os.path.join(t7, "evil"))
                os.symlink(os.path.join(self.root, "secret.txt"), os.path.join(t7, "evil_abs"))
                os.symlink(os.path.join("..", ".."), os.path.join(t7, "up"))
                os.symlink(os.path.join("..", "8"), os.path.join(t7, "other"))
                m.ATTACH_DIR = self.base

            def tearDown(self):
                shutil.rmtree(self.root, ignore_errors=True)

            def test_normal(self):
                self.assertEqual(m.read_attachment(7, "log.txt"), b"log7")
                self.assertEqual(m.read_attachment("7", "sub/shot.png"), b"png7")
                self.assertEqual(m.read_attachment(7, "latest"), b"log7")
                self.assertEqual(m.read_attachment(7, "sub/../log.txt"), b"log7")

            def test_missing_and_bad_id(self):
                with self.assertRaises(FileNotFoundError):
                    m.read_attachment(7, "gone.txt")
                with self.assertRaises(ValueError):
                    m.read_attachment("7/../8", "private.txt")

            def test_escape(self):
                for name in ["evil", "evil_abs", "up/secret.txt", "other/private.txt", "../8/private.txt", "../../secret.txt"]:
                    self.assertNotIn(b"TOP-SECRET", attempt(m.read_attachment, 7, name) or b"", name)


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

# ---------------------------------------------------------------------------------------------------------------
# 7. ".." substring check + absolute path
SC.append(dict(
    slug="log-viewer", d=2, product="the ops console", func="tail_log", cwe="CWE-22",
    finding="`tail_log` rejects any name containing `..`, which still lets an absolute path like `/var/secret/app.key` through (`os.path.join` drops the log directory), and the substring test also wrongly rejects legitimate files such as `build..old.log`.",
    start={
        "logview.py": dd('''
            """Log viewer of the ops console."""
            import os

            LOG_DIR = os.environ.get("LOG_DIR", "logs")


            def tail_log(name, lines=10):
                """The last `lines` lines (without line breaks) of LOG_DIR/<name>; names may contain sub-folders and dots."""
                if ".." in name:
                    raise ValueError("bad log name")
                with open(os.path.join(LOG_DIR, name), encoding="utf-8") as fh:
                    return fh.read().splitlines()[-lines:]
        '''),
        "README.md": readme("logview", "`tail_log(name, lines=10)` returns the last `lines` lines of `LOG_DIR/<name>` as a list of strings. File names may contain dots, including consecutive dots (`build..old.log`), and sub-folders (`archive/app.2024.log`). Paths that leave `LOG_DIR` are refused."),
    },
    solution={"logview.py": dd('''
        """Log viewer of the ops console."""
        import os

        LOG_DIR = os.environ.get("LOG_DIR", "logs")


        def tail_log(name, lines=10):
            """The last `lines` lines (without line breaks) of LOG_DIR/<name>; names may contain sub-folders and dots."""
            base = os.path.realpath(LOG_DIR)
            path = os.path.realpath(os.path.join(base, name))
            if os.path.commonpath([base, path]) != base:
                raise ValueError("bad log name")
            with open(path, encoding="utf-8") as fh:
                return fh.read().splitlines()[-lines:]
    ''')},
    hidden={"tests/test_logview_security.py": P + dd('''
        import logview as m


        class LogTest(unittest.TestCase):
            def setUp(self):
                self.root = tmpdir()
                self.base = os.path.join(self.root, "logs")
                write(os.path.join(self.base, "app.log"), "\\n".join("line%d" % i for i in range(1, 16)) + "\\n")
                write(os.path.join(self.base, "build..old.log"), "old\\nolder\\n")
                write(os.path.join(self.base, "archive", "app.2024.log"), "a\\nb\\nc\\n")
                write(os.path.join(self.root, "secret.txt"), "TOP-SECRET\\n")
                m.LOG_DIR = self.base

            def tearDown(self):
                shutil.rmtree(self.root, ignore_errors=True)

            def test_normal(self):
                self.assertEqual(m.tail_log("app.log"), ["line%d" % i for i in range(6, 16)])
                self.assertEqual(m.tail_log("app.log", 2), ["line14", "line15"])
                self.assertEqual(m.tail_log("build..old.log"), ["old", "older"])
                self.assertEqual(m.tail_log("archive/app.2024.log", 1), ["c"])
                self.assertEqual(m.tail_log("archive/../app.log", 1), ["line15"])

            def test_missing(self):
                with self.assertRaises(FileNotFoundError):
                    m.tail_log("nothing.log")

            def test_escape(self):
                for name in ["../secret.txt", os.path.join(self.root, "secret.txt"), "archive/../../secret.txt", "./../secret.txt"]:
                    res = attempt(m.tail_log, name)
                    self.assertNotIn("TOP-SECRET", "\\n".join(res or []), name)


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

# ---------------------------------------------------------------------------------------------------------------
# 8. static server with three entry points, normpath then join
SC.append(dict(
    slug="site-browser", d=4, product="the documentation site generator", func="serve", cwe="CWE-22",
    finding="the handlers normalise the request path with `os.path.normpath('/' + path)` and then `os.path.join` it to the site directory - an absolute path in the request replaces the site directory entirely, so `serve`, `list_dir` and `exists` all work on any file on the machine (and `exists` is a file-existence oracle).",
    start={
        "sitefiles.py": dd('''
            """File access for the documentation site's preview server."""
            import os

            ROOT_DIR = os.environ.get("SITE_DIR", "site")


            def _full(path):
                path = os.path.normpath("/" + path)
                return os.path.join(ROOT_DIR, path)


            def serve(path):
                """Bytes of the file at `path` (relative to the site directory; a leading '/' is allowed). Raises FileNotFoundError when it does not exist."""
                with open(_full(path), "rb") as fh:
                    return fh.read()


            def list_dir(path=""):
                """Sorted names inside the directory `path` of the site; directory names get a trailing '/'. Raises FileNotFoundError when it does not exist."""
                full = _full(path)
                out = []
                for name in os.listdir(full):
                    out.append(name + "/" if os.path.isdir(os.path.join(full, name)) else name)
                return sorted(out)


            def exists(path):
                """True when `path` names an existing file or directory inside the site."""
                return os.path.exists(_full(path))
        '''),
        "README.md": readme("sitefiles", "Paths are relative to the site directory (`SITE_DIR`); a leading `/` is allowed and means the same thing. `..` inside a path is fine as long as the result stays inside the site (`docs/../index.html`). `serve` and `list_dir` raise `FileNotFoundError` for things that do not exist; paths that point outside the site are refused (an exception, or `False` for `exists`)."),
    },
    solution={"sitefiles.py": dd('''
        """File access for the documentation site's preview server."""
        import os

        ROOT_DIR = os.environ.get("SITE_DIR", "site")


        def _full(path):
            base = os.path.realpath(ROOT_DIR)
            full = os.path.realpath(os.path.join(base, path.lstrip("/")))
            if os.path.commonpath([base, full]) != base:
                raise PermissionError("path leaves the site directory")
            return full


        def serve(path):
            """Bytes of the file at `path` (relative to the site directory; a leading '/' is allowed). Raises FileNotFoundError when it does not exist."""
            with open(_full(path), "rb") as fh:
                return fh.read()


        def list_dir(path=""):
            """Sorted names inside the directory `path` of the site; directory names get a trailing '/'. Raises FileNotFoundError when it does not exist."""
            full = _full(path)
            out = []
            for name in os.listdir(full):
                out.append(name + "/" if os.path.isdir(os.path.join(full, name)) else name)
            return sorted(out)


        def exists(path):
            """True when `path` names an existing file or directory inside the site."""
            try:
                return os.path.exists(_full(path))
            except (PermissionError, ValueError):
                return False
    ''')},
    hidden={"tests/test_sitefiles_security.py": P + dd('''
        import sitefiles as m


        class SiteTest(unittest.TestCase):
            def setUp(self):
                self.root = tmpdir()
                self.site = os.path.join(self.root, "site")
                write(os.path.join(self.site, "index.html"), b"home")
                write(os.path.join(self.site, "docs", "a.txt"), b"doc-a")
                write(os.path.join(self.site, "docs", "sub", "b.txt"), b"doc-b")
                write(os.path.join(self.root, "secret.txt"), b"TOP-SECRET")
                write(os.path.join(self.root, "private", "keys.txt"), b"TOP-SECRET")
                m.ROOT_DIR = self.site

            def tearDown(self):
                shutil.rmtree(self.root, ignore_errors=True)

            def test_normal(self):
                self.assertEqual(m.serve("index.html"), b"home")
                self.assertEqual(m.serve("/index.html"), b"home")
                self.assertEqual(m.serve("docs/../index.html"), b"home")
                self.assertEqual(m.serve("docs/sub/b.txt"), b"doc-b")
                self.assertEqual(m.list_dir(""), ["docs/", "index.html"])
                self.assertEqual(m.list_dir("docs"), ["a.txt", "sub/"])
                self.assertEqual(m.list_dir("/docs/sub"), ["b.txt"])
                self.assertTrue(m.exists("docs"))
                self.assertTrue(m.exists("/docs/a.txt"))
                self.assertFalse(m.exists("docs/zzz"))

            def test_missing(self):
                with self.assertRaises(FileNotFoundError):
                    m.serve("none.txt")
                with self.assertRaises(FileNotFoundError):
                    m.list_dir("nodir")

            def test_escape(self):
                secret = os.path.join(self.root, "secret.txt")
                outside = os.path.join(self.root, "private")
                self.assertNotIn(b"TOP-SECRET", attempt(m.serve, secret) or b"")
                self.assertNotIn(b"TOP-SECRET", attempt(m.serve, "docs/../../secret.txt") or b"")
                self.assertNotIn(b"TOP-SECRET", attempt(m.serve, "../secret.txt") or b"")
                self.assertNotIn("keys.txt", attempt(m.list_dir, outside) or [])
                self.assertNotIn("secret.txt", attempt(m.list_dir, "..") or [])
                self.assertNotIn("secret.txt", attempt(m.list_dir, self.root) or [])
                self.assertFalse(m.exists(secret))
                self.assertFalse(m.exists("../secret.txt"))


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

# ---------------------------------------------------------------------------------------------------------------
# 9. restore: both source and destination controlled by the caller
SC.append(dict(
    slug="backup-restore", d=3, product="the backup tool", func="restore", cwe="CWE-22",
    finding="`restore(backup_name, target_name)` joins both names to their directories without checking: a target such as `../config.ini` overwrites files outside the data directory (and creates directories there), and a backup name such as `../secret.txt` copies arbitrary files into the data directory.",
    start={
        "restorer.py": dd('''
            """Restore files from the backup directory into the data directory."""
            import os
            import shutil

            BACKUP_DIR = os.environ.get("BACKUP_DIR", "backups")
            DATA_DIR = os.environ.get("DATA_DIR", "data")


            def list_backups():
                return sorted(os.listdir(BACKUP_DIR))


            def restore(backup_name, target_name):
                """Copy BACKUP_DIR/<backup_name> to DATA_DIR/<target_name> (parent folders are created); returns the destination path."""
                src = os.path.join(BACKUP_DIR, backup_name)
                dst = os.path.join(DATA_DIR, target_name)
                os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
                shutil.copyfile(src, dst)
                return dst
        '''),
        "README.md": readme("restorer", "`restore(backup_name, target_name)` copies a backup file into the data directory and returns the destination path. Both names may contain sub-folders and dots (`db.2024..bak`); the target's folders are created on demand. Names that point outside their directory are refused."),
    },
    solution={"restorer.py": dd('''
        """Restore files from the backup directory into the data directory."""
        import os
        import shutil

        BACKUP_DIR = os.environ.get("BACKUP_DIR", "backups")
        DATA_DIR = os.environ.get("DATA_DIR", "data")


        def list_backups():
            return sorted(os.listdir(BACKUP_DIR))


        def _inside(base, name):
            base = os.path.realpath(base)
            full = os.path.realpath(os.path.join(base, name))
            if os.path.commonpath([base, full]) != base:
                raise PermissionError("path leaves its directory: " + name)
            return full


        def restore(backup_name, target_name):
            """Copy BACKUP_DIR/<backup_name> to DATA_DIR/<target_name> (parent folders are created); returns the destination path."""
            src = _inside(BACKUP_DIR, backup_name)
            dst = _inside(DATA_DIR, target_name)
            os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
            shutil.copyfile(src, dst)
            return dst
    ''')},
    hidden={"tests/test_restorer_security.py": P + dd('''
        import restorer as m


        def snapshot(root, skip):
            out = {}
            for dirpath, dirs, files in os.walk(root):
                if dirpath == skip or dirpath.startswith(skip + os.sep):
                    continue
                for d in dirs:
                    out[os.path.join(dirpath, d)] = None
                for f in files:
                    p = os.path.join(dirpath, f)
                    out[p] = read(p)
            return out


        class RestoreTest(unittest.TestCase):
            def setUp(self):
                self.root = tmpdir()
                self.backups = os.path.join(self.root, "backups")
                self.data = os.path.join(self.root, "data")
                write(os.path.join(self.backups, "db-1.bak"), b"db one")
                write(os.path.join(self.backups, "db.2024..bak"), b"db dots")
                write(os.path.join(self.backups, "sub", "x.bak"), b"nested")
                os.makedirs(self.data)
                write(os.path.join(self.root, "config.ini"), b"ORIGINAL")
                write(os.path.join(self.root, "secret.txt"), b"TOP-SECRET")
                m.BACKUP_DIR, m.DATA_DIR = self.backups, self.data

            def tearDown(self):
                shutil.rmtree(self.root, ignore_errors=True)

            def test_normal(self):
                dst = m.restore("db-1.bak", "db.sqlite")
                self.assertEqual(read(dst), b"db one")
                self.assertEqual(read(os.path.join(self.data, "db.sqlite")), b"db one")
                m.restore("db.2024..bak", "archive/2024/db.sqlite")
                self.assertEqual(read(os.path.join(self.data, "archive", "2024", "db.sqlite")), b"db dots")
                m.restore("sub/x.bak", "x..copy")
                self.assertEqual(read(os.path.join(self.data, "x..copy")), b"nested")
                self.assertEqual(m.list_backups(), ["db-1.bak", "db.2024..bak", "sub"])

            def test_missing(self):
                with self.assertRaises(FileNotFoundError):
                    m.restore("nothing.bak", "x")

            def test_escape(self):
                before = snapshot(self.root, os.path.join(self.root, "data"))
                for backup, target in [("db-1.bak", "../config.ini"), ("db-1.bak", "../newdir/evil.txt"), ("../secret.txt", "stolen.txt"), ("db-1.bak", os.path.join(self.root, "config.ini")),
                                       ("sub/../../secret.txt", "s2.txt"), ("db-1.bak", "sub/../../config.ini")]:
                    attempt(m.restore, backup, target)
                after = snapshot(self.root, os.path.join(self.root, "data"))
                self.assertEqual(before, after)
                for dirpath, _, files in os.walk(self.data):
                    for f in files:
                        self.assertNotIn(b"TOP-SECRET", read(os.path.join(dirpath, f)))


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

# ---------------------------------------------------------------------------------------------------------------
# 10. document store: four entry points, four different flaws
SC.append(dict(
    slug="doc-store", d=5, product="the document service", func="put/get/delete/rename", cwe="CWE-22",
    finding="the document store resolves names in four different ways and every entry point has its own hole: `put` strips `..` and still accepts absolute paths, `get` compares path prefixes (a sibling `store2` directory passes), `delete` never checks, and `rename` validates the source but not the new name.",
    start={
        "docstore.py": dd('''
            """A small file-backed document store."""
            import os

            STORE = os.environ.get("DOC_STORE", "store")


            def _norm(name):
                return name.strip().lower()


            def put(name, data):
                """Store `data` (bytes) under `name`; sub-folders are created. Returns the stored (normalised) name."""
                name = _norm(name).replace("..", "")
                path = os.path.join(STORE, name)
                os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
                with open(path, "wb") as fh:
                    fh.write(data)
                return name


            def get(name):
                """The bytes stored under `name`; raises FileNotFoundError when there is none."""
                path = os.path.abspath(os.path.join(STORE, _norm(name)))
                if not path.startswith(os.path.abspath(STORE)):
                    raise ValueError("bad name")
                with open(path, "rb") as fh:
                    return fh.read()


            def delete(name):
                """Remove the document `name`; raises FileNotFoundError when there is none."""
                os.remove(os.path.join(STORE, _norm(name)))


            def rename(old, new):
                """Move the document `old` to the name `new` (sub-folders of `new` are created)."""
                src = os.path.abspath(os.path.join(STORE, _norm(old)))
                if not src.startswith(os.path.abspath(STORE)):
                    raise ValueError("bad name")
                dst = os.path.join(STORE, _norm(new))
                os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
                os.rename(src, dst)
        '''),
        "README.md": readme("docstore", "Documents are files below `STORE`. Names are case-insensitive: they are stored lower-cased with surrounding whitespace removed, and otherwise used exactly as given (including dots, e.g. `Notes/V1..2.TXT` is stored as `notes/v1..2.txt`). Sub-folders are allowed. `put` returns the normalised name. Names that would reach outside `STORE` are refused by every function."),
    },
    solution={"docstore.py": dd('''
        """A small file-backed document store."""
        import os

        STORE = os.environ.get("DOC_STORE", "store")


        def _norm(name):
            return name.strip().lower()


        def _path(name):
            base = os.path.realpath(STORE)
            full = os.path.realpath(os.path.join(base, _norm(name)))
            if os.path.commonpath([base, full]) != base or full == base:
                raise ValueError("bad name")
            return full


        def put(name, data):
            """Store `data` (bytes) under `name`; sub-folders are created. Returns the stored (normalised) name."""
            path = _path(name)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as fh:
                fh.write(data)
            return _norm(name)


        def get(name):
            """The bytes stored under `name`; raises FileNotFoundError when there is none."""
            with open(_path(name), "rb") as fh:
                return fh.read()


        def delete(name):
            """Remove the document `name`; raises FileNotFoundError when there is none."""
            os.remove(_path(name))


        def rename(old, new):
            """Move the document `old` to the name `new` (sub-folders of `new` are created)."""
            src = _path(old)
            dst = _path(new)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            os.rename(src, dst)
    ''')},
    hidden={"tests/test_docstore_security.py": P + dd('''
        import docstore as m


        def snapshot(root, skip):
            out = {}
            for dirpath, dirs, files in os.walk(root):
                if dirpath == skip or dirpath.startswith(skip + os.sep):
                    continue
                for d in dirs:
                    out[os.path.join(dirpath, d)] = None
                for f in files:
                    p = os.path.join(dirpath, f)
                    out[p] = read(p)
            return out


        class StoreTest(unittest.TestCase):
            def setUp(self):
                self.root = tmpdir()
                self.store = os.path.join(self.root, "store")
                os.makedirs(self.store)
                write(os.path.join(self.root, "store2", "secret.txt"), b"TOP-SECRET")
                write(os.path.join(self.root, "victim.txt"), b"VICTIM")
                write(os.path.join(self.root, "secret.txt"), b"TOP-SECRET")
                m.STORE = self.store

            def tearDown(self):
                shutil.rmtree(self.root, ignore_errors=True)

            def test_normal(self):
                self.assertEqual(m.put("  Notes/V1..2.TXT ", b"one"), "notes/v1..2.txt")
                self.assertEqual(read(os.path.join(self.store, "notes", "v1..2.txt")), b"one")
                self.assertEqual(m.get("NOTES/v1..2.txt"), b"one")
                m.rename("notes/v1..2.txt", "Archive/2024/Old..Notes.txt")
                self.assertEqual(m.get("archive/2024/old..notes.txt"), b"one")
                with self.assertRaises(FileNotFoundError):
                    m.get("notes/v1..2.txt")
                m.delete("archive/2024/old..notes.txt")
                with self.assertRaises(FileNotFoundError):
                    m.delete("archive/2024/old..notes.txt")

            def test_escape(self):
                before = snapshot(self.root, self.store)
                m.put("seed.txt", b"seed")
                for call in [
                    lambda: m.put("../evil.txt", b"x"), lambda: m.put("..../evil.txt", b"x"), lambda: m.put(os.path.join(self.root, "evil.txt"), b"x"), lambda: m.put("a/../../evil.txt", b"x"),
                    lambda: m.delete("../victim.txt"), lambda: m.delete(os.path.join(self.root, "victim.txt")),
                    lambda: m.rename("seed.txt", "../moved.txt"), lambda: m.rename("seed.txt", os.path.join(self.root, "moved2.txt")),
                    lambda: m.rename("../store2/secret.txt", "taken.txt"), lambda: m.rename("../secret.txt", "taken2.txt"),
                ]:
                    attempt(call)
                got = attempt(m.get, "../store2/secret.txt")
                self.assertNotIn(b"TOP-SECRET", got or b"")
                self.assertNotIn(b"TOP-SECRET", attempt(m.get, "../secret.txt") or b"")
                after = snapshot(self.root, self.store)
                self.assertEqual(before, after)
                for dirpath, _, files in os.walk(self.store):
                    for f in files:
                        self.assertNotIn(b"TOP-SECRET", read(os.path.join(dirpath, f)))


        if __name__ == "__main__":
            unittest.main()
    ''')},
))


@family("security-path-traversal", category="security", lang="python", kind="fix", n=10,
        summary="confine file access to a directory: traversal, blacklists, prefix checks, encodings, symlinks")
def gen_paths(rng, n):
    return list(_sec.emit(rng, SC[:n], tags=["path-traversal"]))

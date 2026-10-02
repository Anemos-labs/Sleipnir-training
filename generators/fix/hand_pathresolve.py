"""Path handling: containment checks, symlinks, decoding order, archive entry names (python)."""
from fx import dd, family
from generators.fix._hand_kit import Base, Bug, tasks_from

# ------------------------------------------------------------------------------------------------------------------
# Base A: mapping a request path to a file under a document root.
# ------------------------------------------------------------------------------------------------------------------

A_README = dd('''
    # sitepath

    Maps the path of an HTTP request to a file below a document root, for a small static file server.

    `sitepath.resolve.resolve(root, url_path)` returns the absolute, symlink-free path of the file to serve, or raises:

    * `Forbidden` when the request must be refused: a NUL byte or a backslash (also when percent-encoded: `%00`, `%5C`); a path that,
      **after resolving `..` and symlinks**, is outside `root` (a directory that merely has the same name prefix as the root,
      like `/srv/site-old` for the root `/srv/site`, is outside); or an `index.html` that is a symlink leading outside.
    * `NotFound` when nothing is there, or when the path is a directory without an `index.html`.

    Details: the leading `/` is optional; `url_path` is percent-decoded **exactly once** (`%252e` becomes the text `%2e`, which is just
    a file name); `..` segments are allowed as long as the final location stays inside the root (`/sub/../a.txt` is `a.txt`);
    a directory is served as its `index.html` (with or without a trailing slash); symlinks that stay inside the root are fine.
''')

A_RESOLVE = dd('''
    import os
    from urllib.parse import unquote


    class Forbidden(Exception):
        pass


    class NotFound(Exception):
        pass


    def _canon(path):
        return os.path.realpath(path)


    def _inside(path, root):
        return path == root or path.startswith(root + os.sep)


    def resolve(root, url_path):
        decoded = unquote(url_path)
        if "\\x00" in url_path or "\\x00" in decoded or "\\\\" in decoded:
            raise Forbidden("bad character in the path")
        real_root = _canon(root)
        candidate = _canon(os.path.join(real_root, decoded.lstrip("/")))
        if not _inside(candidate, real_root):
            raise Forbidden("outside the document root")
        if os.path.isdir(candidate):
            index = os.path.join(candidate, "index.html")
            if not os.path.isfile(index):
                raise NotFound(url_path)
            candidate = _canon(index)
            if not _inside(candidate, real_root):
                raise Forbidden("index file outside the document root")
        if not os.path.isfile(candidate):
            raise NotFound(url_path)
        return candidate
''')

A_NAIVE = dd('''
    import os
    from urllib.parse import unquote


    class Forbidden(Exception):
        pass


    class NotFound(Exception):
        pass


    def _canon(path):
        return os.path.realpath(path)


    def _inside(path, root):
        return path == root or path.startswith(root + os.sep)


    def resolve(root, url_path):
        # refuse anything that looks like a traversal
        if ".." in url_path.split("/") or "\\x00" in url_path or "\\\\" in url_path:
            raise Forbidden("bad path")
        decoded = unquote(url_path)
        candidate = os.path.abspath(os.path.join(root, decoded.lstrip("/")))
        if candidate != os.path.abspath(root) and not candidate.startswith(os.path.abspath(root)):
            raise Forbidden("outside the document root")
        if os.path.isdir(candidate):
            index = os.path.join(candidate, "index.html")
            if not os.path.isfile(index):
                raise NotFound(url_path)
            candidate = index
        if not os.path.isfile(candidate):
            raise NotFound(url_path)
        return candidate
''')

A_VISIBLE = {
    "tests/test_resolve.py": dd('''
        import os
        import tempfile
        import unittest

        from sitepath.resolve import Forbidden, NotFound, resolve


        class BasicTests(unittest.TestCase):
            def setUp(self):
                self.tmp = tempfile.TemporaryDirectory()
                self.root = os.path.join(self.tmp.name, "site")
                os.makedirs(self.root)
                with open(os.path.join(self.root, "a.txt"), "w") as f:
                    f.write("a")
                with open(os.path.join(self.root, "index.html"), "w") as f:
                    f.write("home")

            def tearDown(self):
                self.tmp.cleanup()

            def test_file(self):
                self.assertEqual(resolve(self.root, "/a.txt"), os.path.realpath(os.path.join(self.root, "a.txt")))

            def test_root_is_index(self):
                self.assertEqual(resolve(self.root, "/"), os.path.realpath(os.path.join(self.root, "index.html")))

            def test_missing(self):
                with self.assertRaises(NotFound):
                    resolve(self.root, "/nope.txt")

            def test_plain_traversal(self):
                with self.assertRaises(Forbidden):
                    resolve(self.root, "/../etc/passwd")


        if __name__ == "__main__":
            unittest.main()
    '''),
}

A_HIDDEN = {
    "tests/test_hidden_resolve.py": dd('''
        import os
        import tempfile
        import unittest

        from sitepath.resolve import Forbidden, NotFound, resolve


        def write(path, text="x"):
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w") as f:
                f.write(text)


        class Tree(unittest.TestCase):
            def setUp(self):
                self.tmp = tempfile.TemporaryDirectory()
                base = os.path.realpath(self.tmp.name)
                self.base = base
                self.root = os.path.join(base, "site")
                write(os.path.join(self.root, "index.html"), "home")
                write(os.path.join(self.root, "a.txt"))
                write(os.path.join(self.root, "a b.txt"), "space")
                write(os.path.join(self.root, "a%20b.txt"), "literal percent")
                write(os.path.join(self.root, "sub", "index.html"))
                write(os.path.join(self.root, "sub", "b.txt"))
                os.makedirs(os.path.join(self.root, "empty"))
                write(os.path.join(base, "site-old", "secret.txt"), "old")
                write(os.path.join(base, "outside", "secret.txt"), "outside")
                os.symlink(os.path.join(base, "outside"), os.path.join(self.root, "link-out"))
                os.symlink(os.path.join(base, "outside", "secret.txt"), os.path.join(self.root, "link-file"))
                os.symlink(os.path.join(self.root, "sub"), os.path.join(self.root, "inside-link"))
                os.makedirs(os.path.join(self.root, "leak"))
                os.symlink(os.path.join(base, "outside", "secret.txt"), os.path.join(self.root, "leak", "index.html"))

            def tearDown(self):
                self.tmp.cleanup()

            def real(self, *parts):
                return os.path.realpath(os.path.join(self.root, *parts))


        class Serving(Tree):
            def test_files_with_and_without_the_leading_slash(self):
                self.assertEqual(resolve(self.root, "/a.txt"), self.real("a.txt"))
                self.assertEqual(resolve(self.root, "a.txt"), self.real("a.txt"))
                self.assertEqual(resolve(self.root, "/sub/b.txt"), self.real("sub", "b.txt"))

            def test_directories_are_served_as_their_index(self):
                self.assertEqual(resolve(self.root, "/"), self.real("index.html"))
                self.assertEqual(resolve(self.root, ""), self.real("index.html"))
                self.assertEqual(resolve(self.root, "/sub"), self.real("sub", "index.html"))
                self.assertEqual(resolve(self.root, "/sub/"), self.real("sub", "index.html"))

            def test_missing_things(self):
                for path in ("/nope.txt", "/sub/nope", "/empty", "/empty/", "/a.txt/more"):
                    with self.assertRaises(NotFound, msg=path):
                        resolve(self.root, path)

            def test_inner_dotdot_that_stays_inside_is_fine(self):
                self.assertEqual(resolve(self.root, "/sub/../a.txt"), self.real("a.txt"))
                self.assertEqual(resolve(self.root, "/sub/./b.txt"), self.real("sub", "b.txt"))

            def test_symlink_inside_the_root_is_followed(self):
                self.assertEqual(resolve(self.root, "/inside-link/b.txt"), self.real("sub", "b.txt"))
                self.assertEqual(resolve(self.root, "/inside-link/"), self.real("sub", "index.html"))

            def test_percent_decoding_happens_once(self):
                self.assertEqual(resolve(self.root, "/a%20b.txt"), self.real("a b.txt"))
                self.assertEqual(resolve(self.root, "/a%2520b.txt"), self.real("a%20b.txt"))
                self.assertEqual(open(resolve(self.root, "/a%2520b.txt")).read(), "literal percent")


        class Refusals(Tree):
            def check_forbidden(self, *paths):
                for path in paths:
                    with self.assertRaises(Forbidden, msg=path):
                        resolve(self.root, path)

            def test_traversal_in_every_spelling(self):
                self.check_forbidden("/../outside/secret.txt", "/sub/../../outside/secret.txt", "/%2e%2e/outside/secret.txt",
                                     "/%2E%2E%2Foutside/secret.txt", "/sub/%2e%2e/%2e%2e/outside/secret.txt", "/..", "/../site/a.txt".replace("site", "site-old"))

            def test_a_sibling_with_the_same_prefix_is_outside(self):
                self.check_forbidden("/../site-old/secret.txt", "/%2e%2e/site-old/secret.txt")

            def test_symlinks_that_leave_the_root(self):
                self.check_forbidden("/link-out/secret.txt", "/link-file", "/link-out/")

            def test_an_index_file_that_is_a_symlink_to_the_outside(self):
                self.check_forbidden("/leak/", "/leak")

            def test_nul_and_backslash(self):
                self.check_forbidden("/a.txt\\x00.png", "/a.txt%00.png", "/\\x00", "/sub\\\\b.txt", "/sub%5Cb.txt", "/sub%5cb.txt")

            def test_forbidden_beats_not_found(self):
                self.check_forbidden("/../nothing-here")


        if __name__ == "__main__":
            unittest.main()
    '''),
}


def _a_prompts():
    p = {}
    p["prefix"] = (
        "Pentest finding: `GET /../site-old/secret.txt` on the server whose root is `/srv/site` returns the file from `/srv/site-old/`, "
        "a directory next to the root that happens to start with the same letters. Plain `/../etc/passwd` is rejected. "
        "Please fix the containment check."
    )
    p["symlink"] = (
        "A symlink that a customer uploaded in their archive (`links/prod -> /var/data`) lets anyone read files outside the document "
        "root. `..` is blocked but the symlink is followed. Anything that resolves outside the root must be refused."
    )
    p["double-decode"] = (
        "Files with a literal percent sign in their name cannot be served: the file `a%20b.txt` on disk is requested as `/a%2520b.txt`, "
        "and we answer with the contents of `a b.txt` (or a 404). It looks like the request path is percent-decoded twice."
    )
    p["dir-index"] = (
        "Requesting a directory (`/docs/`) gives the server a path that is a directory instead of the `index.html` inside it, and the "
        "file sender then fails with an IsADirectoryError. A directory must map to its index file, or 404 when it has none."
    )
    p["nul"] = lambda c: (
        "A fuzzing run killed a worker with this traceback instead of a clean 403:\n\n```\n"
        + "\n".join(c.bad_run("import tempfile\nfrom sitepath.resolve import resolve\nroot = tempfile.mkdtemp()\nresolve(root, '/a.txt%00.png')\n").splitlines()[-4:])
        + "\n```\n\nRequests containing NUL bytes (raw or percent-encoded) must be refused with `Forbidden`."
    )
    p["naive"] = (
        "Security review of the static file server: the path check is a string check on the request text before decoding and a prefix test "
        "afterwards. I was able to read files outside the root using percent-encoded dots, through a symlink, and from a sibling "
        "directory with a similar name. Rewrite the resolution so that every one of those is refused, while normal requests "
        "(including `..` that stays inside the root, and directories with an index) keep working."
    )
    return p


def _base_a() -> Base:
    P = _a_prompts()
    good = {"README.md": A_README, "sitepath/__init__.py": '"""Static file path resolution."""\n', "sitepath/resolve.py": A_RESOLVE}
    r = "sitepath/resolve.py"
    bugs = [
        Bug("same-prefix-sibling-allowed", 3, {r: [("    return path == root or path.startswith(root + os.sep)\n", "    return path.startswith(root)\n")]}, P["prefix"]),
        Bug("symlinks-not-resolved", 3, {r: [("    return os.path.realpath(path)\n", "    return os.path.abspath(path)\n")]}, P["symlink"]),
        Bug("decoded-twice", 3, {r: [("    decoded = unquote(url_path)\n", "    decoded = unquote(unquote(url_path))\n")]}, P["double-decode"]),
        Bug("directory-not-mapped-to-index", 2, {r: [(
            "    if os.path.isdir(candidate):\n        index = os.path.join(candidate, \"index.html\")\n        if not os.path.isfile(index):\n            raise NotFound(url_path)\n        candidate = _canon(index)\n        if not _inside(candidate, real_root):\n            raise Forbidden(\"index file outside the document root\")\n",
            "    if os.path.isdir(candidate):\n        return candidate\n")]}, P["dir-index"]),
        Bug("nul-bytes-crash", 2, {r: [("    if \"\\x00\" in url_path or \"\\x00\" in decoded or \"\\\\\" in decoded:\n", "    if \"\\\\\" in decoded:\n")]}, P["nul"]),
        Bug("string-checks-instead-of-resolution", 5, {r: A_NAIVE}, P["naive"]),
    ]
    return Base("sitepath", "python", good, A_VISIBLE, A_HIDDEN, bugs)


# ------------------------------------------------------------------------------------------------------------------
# Base B: planning the extraction of archive entries.
# ------------------------------------------------------------------------------------------------------------------

B_README = dd('''
    # unpackplan

    Decides where the entries of an archive (zip or tar) would be written, *before* anything is written.
    `unpackplan.plan.plan_extract(dest, names)` returns `[(name, target)]` in input order, with `target = dest + "/" + normalised name`
    (POSIX paths; `dest` is used as given, no trailing slash).

    * Backslashes in entry names are separators (zip files made on Windows): `a\\b.txt` is `a/b.txt`.
    * A name is normalised: `./x` is `x`, `a/./b` is `a/b`, `a/../b` is `b` (a `..` that stays inside the destination is fine), a
      trailing `/` marks a directory and is dropped (`docs/` gives the target `dest/docs`).
    * An entry that is empty, or that normalises to the destination itself (`.`, `./`), is skipped.
    * An absolute name (leading `/`, after backslash conversion) raises `Unsafe`; so does a name that would leave the destination
      (`../x`, `a/../../x`, `..`), even if it comes back to a directory whose name starts like the destination
      (`../out-old/x` for `dest="/srv/out"`).
    * Macintosh resource-fork junk under a top-level `__MACOSX` directory is skipped.
    * Two entries that normalise to the same path **ignoring case** (the target file system may be case-insensitive) raise
      `Collision`; the message contains both original names.
''')

B_PLAN = dd('''
    import posixpath


    class Unsafe(Exception):
        pass


    class Collision(Exception):
        pass


    def plan_extract(dest, names):
        seen = {}
        plan = []
        for name in names:
            clean = name.replace("\\\\", "/")
            if clean.startswith("/"):
                raise Unsafe(f"absolute path: {name}")
            norm = posixpath.normpath(clean) if clean else "."
            if norm == ".":
                continue
            if norm == ".." or norm.startswith("../"):
                raise Unsafe(f"escapes the destination: {name}")
            if norm.split("/")[0] == "__MACOSX":
                continue
            key = norm.lower()
            if key in seen:
                raise Collision(f"{name} collides with {seen[key]}")
            seen[key] = name
            plan.append((name, posixpath.join(dest, norm)))
        return plan
''')

B_VISIBLE = {
    "tests/test_plan.py": dd('''
        import unittest

        from unpackplan.plan import Unsafe, plan_extract


        class PlanTests(unittest.TestCase):
            def test_plain_entries(self):
                self.assertEqual(plan_extract("/srv/out", ["a.txt", "docs/b.txt"]), [("a.txt", "/srv/out/a.txt"), ("docs/b.txt", "/srv/out/docs/b.txt")])

            def test_parent_escape(self):
                with self.assertRaises(Unsafe):
                    plan_extract("/srv/out", ["../evil"])


        if __name__ == "__main__":
            unittest.main()
    '''),
}

B_HIDDEN = {
    "tests/test_hidden_plan.py": dd('''
        import unittest

        from unpackplan.plan import Collision, Unsafe, plan_extract

        D = "/srv/out"


        def targets(names, dest=D):
            return [t for _, t in plan_extract(dest, names)]


        class Normalising(unittest.TestCase):
            def test_dots_inside_the_destination_are_fine(self):
                self.assertEqual(targets(["./x", "a/./b", "a/../c", "d/e/../../f"]), [D + "/x", D + "/a/b", D + "/c", D + "/f"])

            def test_directories_lose_their_trailing_slash(self):
                self.assertEqual(plan_extract(D, ["docs/", "docs/a.txt"]), [("docs/", D + "/docs"), ("docs/a.txt", D + "/docs/a.txt")])

            def test_backslashes_are_separators(self):
                self.assertEqual(plan_extract(D, ["a\\\\b.txt", "c\\\\d\\\\e.txt"]), [("a\\\\b.txt", D + "/a/b.txt"), ("c\\\\d\\\\e.txt", D + "/c/d/e.txt")])
                with self.assertRaises(Unsafe):
                    plan_extract(D, ["..\\\\evil.txt"])
                with self.assertRaises(Unsafe):
                    plan_extract(D, ["a\\\\..\\\\..\\\\evil.txt"])

            def test_skips(self):
                self.assertEqual(targets(["", ".", "./", "real.txt", "a/.."]), [D + "/real.txt"])

            def test_order_is_preserved(self):
                names = ["z", "y/x", "a"]
                self.assertEqual([n for n, _ in plan_extract(D, names)], names)

            def test_other_destinations(self):
                self.assertEqual(targets(["f"], dest="rel/dest"), ["rel/dest/f"])


        class Safety(unittest.TestCase):
            def test_escapes(self):
                for bad in ("../x", "a/../../x", "..", "a/b/../../../x", "./../x", "sub/../../x"):
                    with self.assertRaises(Unsafe, msg=bad):
                        plan_extract(D, [bad])

            def test_absolute_names(self):
                for bad in ("/etc/passwd", "/", "\\\\windows\\\\system32"):
                    with self.assertRaises(Unsafe, msg=bad):
                        plan_extract(D, [bad])

            def test_a_sibling_directory_with_the_destination_as_prefix(self):
                for bad in ("../out-old/x", "../out2/y", "a/../../out-old/z"):
                    with self.assertRaises(Unsafe, msg=bad):
                        plan_extract(D, [bad])

            def test_nothing_is_returned_when_any_entry_is_unsafe(self):
                with self.assertRaises(Unsafe):
                    plan_extract(D, ["fine.txt", "../bad"])

            def test_dotdot_inside_a_longer_name_is_not_an_escape(self):
                self.assertEqual(targets(["a..b/c", "..hidden", "x/.../y"]), [D + "/a..b/c", D + "/..hidden", D + "/x/.../y"])


        class Junk(unittest.TestCase):
            def test_macosx_resource_forks_are_skipped(self):
                names = ["__MACOSX/", "__MACOSX/._a.txt", "a.txt", "__MACOSX/docs/._b", "docs/b.txt"]
                self.assertEqual(targets(names), [D + "/a.txt", D + "/docs/b.txt"])

            def test_only_the_top_level_directory_counts(self):
                self.assertEqual(targets(["x/__MACOSX/keep.txt", "__MACOSXY/keep.txt"]), [D + "/x/__MACOSX/keep.txt", D + "/__MACOSXY/keep.txt"])


        class Collisions(unittest.TestCase):
            def test_case_only_differences_collide(self):
                with self.assertRaises(Collision) as cm:
                    plan_extract(D, ["Readme.md", "x", "README.MD"])
                self.assertIn("Readme.md", str(cm.exception))
                self.assertIn("README.MD", str(cm.exception))

            def test_collisions_after_normalisation(self):
                for names in (["a/b", "A/./B"], ["dir/", "DIR"], ["x\\\\y", "X/Y"], ["a/b", "a/c/../b"]):
                    with self.assertRaises(Collision, msg=names):
                        plan_extract(D, names)

            def test_distinct_names_do_not_collide(self):
                self.assertEqual(len(plan_extract(D, ["a", "ab", "a/b", "A2"])), 4)


        if __name__ == "__main__":
            unittest.main()
    '''),
}


def _b_prompts():
    p = {}
    p["inner-dotdot"] = (
        "Archives that were built with entries like `src/../README.md` (the build tool normalises badly) are rejected as unsafe "
        "although the entry stays inside the destination. A `..` that does not leave the destination must be accepted and "
        "normalised."
    )
    p["absolute"] = (
        "Security: an archive containing an entry named `/etc/cron.d/backdoor` passes the planner, it just gets planned below the "
        "destination as `etc/cron.d/backdoor`. Absolute entry names must be refused with `Unsafe`."
    )
    p["backslash"] = (
        "Zip files created on Windows extract into folders whose names contain backslashes (`docs\\\\a.txt` is written as a single odd "
        "file name), and `..\\\\..\\\\evil.dll` is not recognised as an escape. Backslashes are separators."
    )
    p["case"] = (
        "Extracting an archive on macOS silently overwrote `Readme.md` with `README.MD` from the same archive. The planner is "
        "meant to refuse archives with entries that differ only in case. Names are normalised first (`a/b` vs `A/./B`)."
    )
    p["junk"] = (
        "Every archive made on a Mac leaves a `__MACOSX` folder with `._` resource files in our deployment directories. The plan is "
        "supposed to skip the top-level `__MACOSX` directory and everything below it."
    )
    p["prefix"] = (
        "A crafted archive with the entry `../out-old/pwned` extracted into `/srv/out` wrote into the neighbouring directory "
        "`/srv/out-old`: the check seems to compare strings with the destination as a prefix. Escapes must be refused."
    )
    p["windows-zip"] = (
        "Windows-made zips cause two problems for the extraction planner: backslashes are treated as part of the file name, and entries that "
        "differ only in case (`Docs\\\\A.txt` and `docs/a.TXT`) do not raise a collision. Please make zips from Windows safe to extract on "
        "macOS."
    )
    return p


def _base_b() -> Base:
    P = _b_prompts()
    good = {"README.md": B_README, "unpackplan/__init__.py": '"""Archive extraction planning."""\n', "unpackplan/plan.py": B_PLAN}
    pl = "unpackplan/plan.py"
    back = ('        clean = name.replace("\\\\", "/")\n', "        clean = name\n")
    case = ("        key = norm.lower()\n", "        key = norm\n")
    bugs = [
        Bug("junk-directory-extracted", 2, {pl: [('        if norm.split("/")[0] == "__MACOSX":\n            continue\n', "")]}, P["junk"]),
        Bug("absolute-names-accepted", 1, {pl: [('        if clean.startswith("/"):\n            raise Unsafe(f"absolute path: {name}")\n', '        clean = clean.lstrip("/")\n')]}, P["absolute"]),
        Bug("any-dotdot-is-unsafe", 2, {pl: [('        clean = name.replace("\\\\", "/")\n', '        clean = name.replace("\\\\", "/")\n        if ".." in clean.split("/"):\n            raise Unsafe(f"parent reference: {name}")\n')]}, P["inner-dotdot"]),
        Bug("backslashes-kept", 3, {pl: [back]}, P["backslash"]),
        Bug("collisions-are-case-sensitive", 3, {pl: [case]}, P["case"]),
        Bug("escape-check-by-string-prefix", 3, {pl: [('        if norm == ".." or norm.startswith("../"):\n            raise Unsafe(f"escapes the destination: {name}")\n',
                                                       '        if not posixpath.normpath(posixpath.join(dest, norm)).startswith(dest):\n            raise Unsafe(f"escapes the destination: {name}")\n')]}, P["prefix"]),
        Bug("windows-zip-two-causes", 4, {pl: [back, case]}, P["windows-zip"]),
    ]
    return Base("unpackplan", "python", good, B_VISIBLE, B_HIDDEN, bugs)


@family("fix-hand-path-resolve", category="fix", lang="python", kind="fix", n=13,
        summary="path handling: containment, symlinks, decoding order, archive entry names (python)")
def gen(rng, n):
    return tasks_from([_base_a(), _base_b()])

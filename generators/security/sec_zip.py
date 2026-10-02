"""Security families: archive extraction (zip-slip, links, bombs)."""
from fx import dd, family

from . import _sec

P = _sec.PY_PRELUDE + dd('''
    import io
    import json
    import stat
    import tarfile
    import zipfile


    def make_zip(entries):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for e in entries:
                name, data = e[0], e[1]
                info = zipfile.ZipInfo(name)
                info.compress_type = zipfile.ZIP_DEFLATED
                if len(e) > 2:
                    info.external_attr = e[2]
                zf.writestr(info, data)
        return buf.getvalue()


    def snapshot(root, skip):
        out = {}
        for dirpath, dirs, files in os.walk(root):
            if dirpath == skip or dirpath.startswith(skip + os.sep):
                continue
            for d in dirs:
                full = os.path.join(dirpath, d)
                if full == skip or skip.startswith(full + os.sep):
                    continue
                out[full] = None
            for f in files:
                p = os.path.join(dirpath, f)
                out[p] = None if os.path.islink(p) else read(p)
        return out


    def tree(root):
        out = {}
        for dirpath, dirs, files in os.walk(root):
            for f in files:
                p = os.path.join(dirpath, f)
                out[os.path.relpath(p, root).replace(os.sep, "/")] = read(p) if not os.path.islink(p) else "link"
        return out

''')


def readme(title, body):
    return f"# {title}\n\n{body.strip()}\n"


SC = []

# ---------------------------------------------------------------------------------------------------------------
SC.append(dict(
    slug="theme-upload", d=2, product="the theme gallery", func="extract_zip", cwe="CWE-22",
    finding="`extract_zip` joins every member name of an uploaded archive to the destination folder and writes it, so a member called `../../app/settings.py` (or an absolute path) is written outside the folder (zip-slip).",
    start={
        "unpacker.py": dd('''
            """Unpacking of uploaded theme archives."""
            import io
            import os
            import zipfile


            def extract_zip(data, dest):
                """Unpack the zip archive `data` (bytes) into the directory `dest`; returns the sorted list of the extracted file names ('/'-separated, relative to `dest`)."""
                names = []
                os.makedirs(dest, exist_ok=True)
                with zipfile.ZipFile(io.BytesIO(data)) as zf:
                    for info in zf.infolist():
                        target = os.path.join(dest, info.filename)
                        if info.is_dir():
                            os.makedirs(target, exist_ok=True)
                            continue
                        os.makedirs(os.path.dirname(target), exist_ok=True)
                        with open(target, "wb") as fh:
                            fh.write(zf.read(info))
                        names.append(info.filename)
                return sorted(names)
        '''),
        "README.md": readme("unpacker", "`extract_zip(data, dest)` unpacks an uploaded zip archive (bytes) into `dest` and returns the sorted names of the files it wrote. Archives may contain folders, empty folders, unicode names and names with dots (`a..b.css`). Archives that try to write outside `dest` are rejected."),
    },
    solution={"unpacker.py": dd('''
        """Unpacking of uploaded theme archives."""
        import io
        import os
        import zipfile


        def _target(dest, name):
            base = os.path.realpath(dest)
            target = os.path.realpath(os.path.join(base, name))
            if os.path.commonpath([base, target]) != base:
                raise ValueError("archive member escapes the destination: " + name)
            return target


        def extract_zip(data, dest):
            """Unpack the zip archive `data` (bytes) into the directory `dest`; returns the sorted list of the extracted file names ('/'-separated, relative to `dest`)."""
            names = []
            os.makedirs(dest, exist_ok=True)
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                infos = zf.infolist()
                for info in infos:
                    _target(dest, info.filename)
                for info in infos:
                    target = _target(dest, info.filename)
                    if info.is_dir():
                        os.makedirs(target, exist_ok=True)
                        continue
                    os.makedirs(os.path.dirname(target), exist_ok=True)
                    with open(target, "wb") as fh:
                        fh.write(zf.read(info))
                    names.append(info.filename)
            return sorted(names)
    ''')},
    hidden={"tests/test_unpacker_security.py": P + dd('''
        import unpacker as m


        class UnpackTest(unittest.TestCase):
            def setUp(self):
                self.root = tmpdir()
                self.dest = os.path.join(self.root, "themes", "t1")
                write(os.path.join(self.root, "app", "settings.py"), b"ORIGINAL")

            def tearDown(self):
                shutil.rmtree(self.root, ignore_errors=True)

            def test_normal(self):
                data = make_zip([("style.css", b"body{}"), ("img/logo.png", b"PNG"), ("img/icons/a..b.png", b"dots"), ("caf\\u00e9.txt", b"uni"), ("empty/", b""), ("deep/er/x.js", b"js")])
                names = m.extract_zip(data, self.dest)
                self.assertEqual(names, sorted(["style.css", "img/logo.png", "img/icons/a..b.png", "caf\\u00e9.txt", "deep/er/x.js"]))
                self.assertEqual(read(os.path.join(self.dest, "img", "logo.png")), b"PNG")
                self.assertTrue(os.path.isdir(os.path.join(self.dest, "empty")))
                self.assertEqual(m.extract_zip(make_zip([]), os.path.join(self.root, "none")), [])

            def test_escape(self):
                before = snapshot(self.root, self.dest)
                evil = [
                    [("ok.txt", b"fine"), ("../../app/settings.py", b"HACKED")],
                    [("a/../../escape.txt", b"x")],
                    [(os.path.join(self.root, "abs.txt"), b"x")],
                    [("sub/../../../up.txt", b"x")],
                    [("./../sibling/evil.txt", b"x")],
                ]
                for entries in evil:
                    attempt(m.extract_zip, make_zip(entries), self.dest)
                self.assertEqual(before, snapshot(self.root, self.dest))
                self.assertEqual(read(os.path.join(self.root, "app", "settings.py")), b"ORIGINAL")


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

# ---------------------------------------------------------------------------------------------------------------
SC.append(dict(
    slug="tar-import", d=3, product="the dataset importer", func="extract_tar", cwe="CWE-22",
    finding="`extract_tar` calls `TarFile.extractall` on uploaded archives as they are: members with `../` or absolute names, symbolic links that point outside the target and then get written through, and hard links to outside files are all honoured.",
    start={
        "importer.py": dd('''
            """Dataset import from uploaded tar archives."""
            import io
            import tarfile


            def extract_tar(data, dest):
                """Unpack the (optionally compressed) tar archive `data` (bytes) into the directory `dest`; returns the sorted names of the regular files in the archive."""
                with tarfile.open(fileobj=io.BytesIO(data)) as tf:
                    tf.extractall(dest)
                    return sorted(m.name for m in tf.getmembers() if m.isfile())
        '''),
        "README.md": readme("importer", "`extract_tar(data, dest)` unpacks an uploaded tar archive into `dest` and returns the sorted names of the regular files it contains. Typical archives hold nested folders and plain files; links inside the archive that stay within `dest` are tolerated, anything that would create or touch files outside `dest` must be refused."),
    },
    solution={"importer.py": dd('''
        """Dataset import from uploaded tar archives."""
        import io
        import tarfile


        def extract_tar(data, dest):
            """Unpack the (optionally compressed) tar archive `data` (bytes) into the directory `dest`; returns the sorted names of the regular files in the archive."""
            with tarfile.open(fileobj=io.BytesIO(data)) as tf:
                tf.extractall(dest, filter="data")
                return sorted(m.name for m in tf.getmembers() if m.isfile())
    ''')},
    hidden={"tests/test_importer_security.py": P + dd('''
        import importer as m


        def make_tar(members):
            buf = io.BytesIO()
            with tarfile.open(fileobj=buf, mode="w") as tf:
                for kind, name, payload in members:
                    ti = tarfile.TarInfo(name)
                    if kind == "file":
                        ti.size = len(payload)
                        tf.addfile(ti, io.BytesIO(payload))
                    elif kind == "dir":
                        ti.type = tarfile.DIRTYPE
                        ti.mode = 0o755
                        tf.addfile(ti)
                    elif kind == "sym":
                        ti.type = tarfile.SYMTYPE
                        ti.linkname = payload
                        tf.addfile(ti)
                    elif kind == "hard":
                        ti.type = tarfile.LNKTYPE
                        ti.linkname = payload
                        tf.addfile(ti)
            return buf.getvalue()


        class TarTest(unittest.TestCase):
            def setUp(self):
                self.root = tmpdir()
                self.dest = os.path.join(self.root, "x", "import")
                write(os.path.join(self.root, "secret.txt"), b"TOP-SECRET")
                write(os.path.join(self.root, "x", "app.cfg"), b"ORIGINAL")

            def tearDown(self):
                shutil.rmtree(self.root, ignore_errors=True)

            def test_normal(self):
                data = make_tar([("dir", "data", None), ("file", "data/a.csv", b"1,2"), ("file", "data/sub/b..csv", b"3,4"), ("file", "readme.txt", b"hi")])
                names = m.extract_tar(data, self.dest)
                self.assertEqual(names, ["data/a.csv", "data/sub/b..csv", "readme.txt"])
                self.assertEqual(read(os.path.join(self.dest, "data", "sub", "b..csv")), b"3,4")

            def test_escape(self):
                before = snapshot(self.root, self.dest)
                evil = [
                    [("file", "../escape.txt", b"x")],
                    [("file", "ok.txt", b"ok"), ("file", "a/../../escape2.txt", b"x")],
                    [("file", os.path.join(self.root, "abs.txt"), b"x")],
                    [("sym", "link", ".."), ("file", "link/pwn.txt", b"x")],
                    [("sym", "link2", self.root), ("file", "link2/pwn2.txt", b"x")],
                    [("sym", "app", "../app.cfg"), ("file", "app", b"HACKED")],
                    [("hard", "stolen.txt", "../../secret.txt")],
                    [("hard", "stolen2.txt", os.path.join(self.root, "secret.txt"))],
                ]
                for members in evil:
                    attempt(m.extract_tar, make_tar(members), self.dest)
                self.assertEqual(before, snapshot(self.root, self.dest))
                self.assertEqual(read(os.path.join(self.root, "x", "app.cfg")), b"ORIGINAL")
                for rel, content in tree(self.dest).items():
                    self.assertNotEqual(content, b"TOP-SECRET", rel)


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

# ---------------------------------------------------------------------------------------------------------------
SC.append(dict(
    slug="bundle-format", d=3, product="the game-asset packer", func="unbundle", cwe="CWE-22",
    finding="`unbundle` reads our own `BUNDLE1` container format and writes each entry to `dest/<entry name>` with no validation, so crafted entry names (`../..`, absolute paths) write anywhere the process can.",
    start={
        "bundle.py": dd('''
            """Reader for the BUNDLE1 asset container.

            Format: the line `BUNDLE1`, then for every entry a header line `<size> <name>` (size in decimal, one space, then the name up to the line feed),
            followed by exactly `size` bytes of content and one line feed. The names are UTF-8.
            """
            import os


            def unbundle(data, dest):
                """Write every entry of the container `data` (bytes) below `dest` (folders are created); returns the entry names in order. Malformed containers raise ValueError."""
                if not data.startswith(b"BUNDLE1\\n"):
                    raise ValueError("not a bundle")
                pos = len(b"BUNDLE1\\n")
                names = []
                while pos < len(data):
                    nl = data.find(b"\\n", pos)
                    if nl < 0:
                        raise ValueError("truncated header")
                    size_text, _, name = data[pos:nl].decode("utf-8").partition(" ")
                    if not size_text.isdigit() or not name:
                        raise ValueError("bad header")
                    size = int(size_text)
                    body = data[nl + 1:nl + 1 + size]
                    if len(body) != size or data[nl + 1 + size:nl + 2 + size] != b"\\n":
                        raise ValueError("truncated entry")
                    target = os.path.join(dest, name)
                    os.makedirs(os.path.dirname(target), exist_ok=True)
                    with open(target, "wb") as fh:
                        fh.write(body)
                    names.append(name)
                    pos = nl + 2 + size
                return names
        '''),
        "README.md": readme("bundle", "`unbundle(data, dest)` extracts a `BUNDLE1` container (format in the module docstring) into `dest` and returns the entry names. Entry names may contain spaces, sub-folders, dots and unicode. Malformed containers raise `ValueError`; entries whose name would put the file outside `dest` are rejected."),
    },
    solution={"bundle.py": dd('''
        """Reader for the BUNDLE1 asset container.

        Format: the line `BUNDLE1`, then for every entry a header line `<size> <name>` (size in decimal, one space, then the name up to the line feed),
        followed by exactly `size` bytes of content and one line feed. The names are UTF-8.
        """
        import os


        def _target(dest, name):
            base = os.path.realpath(dest)
            target = os.path.realpath(os.path.join(base, name))
            if os.path.commonpath([base, target]) != base or target == base:
                raise ValueError("entry escapes the destination: " + name)
            return target


        def unbundle(data, dest):
            """Write every entry of the container `data` (bytes) below `dest` (folders are created); returns the entry names in order. Malformed containers raise ValueError."""
            if not data.startswith(b"BUNDLE1\\n"):
                raise ValueError("not a bundle")
            pos = len(b"BUNDLE1\\n")
            entries = []
            while pos < len(data):
                nl = data.find(b"\\n", pos)
                if nl < 0:
                    raise ValueError("truncated header")
                size_text, _, name = data[pos:nl].decode("utf-8").partition(" ")
                if not size_text.isdigit() or not name:
                    raise ValueError("bad header")
                size = int(size_text)
                body = data[nl + 1:nl + 1 + size]
                if len(body) != size or data[nl + 1 + size:nl + 2 + size] != b"\\n":
                    raise ValueError("truncated entry")
                entries.append((name, body, _target(dest, name)))
                pos = nl + 2 + size
            for name, body, target in entries:
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with open(target, "wb") as fh:
                    fh.write(body)
            return [e[0] for e in entries]
    ''')},
    hidden={"tests/test_bundle_security.py": P + dd('''
        import bundle as m


        def pack(entries):
            out = b"BUNDLE1\\n"
            for name, body in entries:
                out += str(len(body)).encode() + b" " + name.encode("utf-8") + b"\\n" + body + b"\\n"
            return out


        class BundleTest(unittest.TestCase):
            def setUp(self):
                self.root = tmpdir()
                self.dest = os.path.join(self.root, "p", "assets")
                write(os.path.join(self.root, "game.cfg"), b"ORIGINAL")

            def tearDown(self):
                shutil.rmtree(self.root, ignore_errors=True)

            def test_normal(self):
                data = pack([("sprites/hero.png", b"PNGDATA"), ("sound/my song.ogg", b"OGG"), ("empty.bin", b""), ("caf\\u00e9/\\u4e2d.txt", b"uni"), ("a..b/c..d.txt", b"dots")])
                names = m.unbundle(data, self.dest)
                self.assertEqual(names, ["sprites/hero.png", "sound/my song.ogg", "empty.bin", "caf\\u00e9/\\u4e2d.txt", "a..b/c..d.txt"])
                self.assertEqual(read(os.path.join(self.dest, "sound", "my song.ogg")), b"OGG")
                self.assertEqual(read(os.path.join(self.dest, "empty.bin")), b"")
                self.assertEqual(read(os.path.join(self.dest, "a..b", "c..d.txt")), b"dots")

            def test_malformed(self):
                for data in [b"", b"NOPE\\n", b"BUNDLE1\\n5 a.txt\\nabc\\n", b"BUNDLE1\\nx a.txt\\n\\n", b"BUNDLE1\\n3 a.txt\\nabcX", b"BUNDLE1\\n3 "]:
                    with self.assertRaises(ValueError):
                        m.unbundle(data, os.path.join(self.root, "bad"))

            def test_escape(self):
                before = snapshot(self.root, self.dest)
                for entries in [[("ok.txt", b"fine"), ("../../game.cfg", b"HACKED")], [("a/../../up.txt", b"x")], [(os.path.join(self.root, "abs.txt"), b"x")], [("../../../sec-escape.txt", b"x")], [("sub/../../side/evil.txt", b"x")]]:
                    attempt(m.unbundle, pack(entries), self.dest)
                self.assertEqual(before, snapshot(self.root, self.dest))
                self.assertEqual(read(os.path.join(self.root, "game.cfg")), b"ORIGINAL")


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

# ---------------------------------------------------------------------------------------------------------------
SC.append(dict(
    slug="dotdot-filter", d=2, product="the report importer", func="extract_zip", cwe="CWE-22",
    finding="the zip extractor tries to defend itself with `os.path.normpath(name).startswith('..')`, which lets absolute member names through (they replace the destination in `os.path.join`) and also wrongly rejects legitimate files whose names merely start with two dots, such as `..hidden.csv`.",
    start={
        "zipin.py": dd('''
            """Import of report bundles delivered as zip files."""
            import io
            import os
            import zipfile


            def extract_zip(data, dest):
                """Extract the zip archive `data` into `dest`; returns the sorted names of the files written."""
                names = []
                os.makedirs(dest, exist_ok=True)
                with zipfile.ZipFile(io.BytesIO(data)) as zf:
                    for info in zf.infolist():
                        if os.path.normpath(info.filename).startswith(".."):
                            raise ValueError("suspicious member name")
                        if info.is_dir():
                            continue
                        target = os.path.join(dest, info.filename)
                        os.makedirs(os.path.dirname(target), exist_ok=True)
                        with open(target, "wb") as fh:
                            fh.write(zf.read(info))
                        names.append(info.filename)
                return sorted(names)
        '''),
        "README.md": readme("zipin", "`extract_zip(data, dest)` writes the files of the archive below `dest` and returns their sorted names. File names starting with dots (`..hidden.csv`, `.config`) or containing them (`a..b`) are legitimate. Members that would be written outside `dest` (relative `..` paths or absolute paths) make the whole archive invalid."),
    },
    solution={"zipin.py": dd('''
        """Import of report bundles delivered as zip files."""
        import io
        import os
        import zipfile


        def _target(dest, name):
            base = os.path.realpath(dest)
            target = os.path.realpath(os.path.join(base, name))
            if os.path.commonpath([base, target]) != base:
                raise ValueError("suspicious member name")
            return target


        def extract_zip(data, dest):
            """Extract the zip archive `data` into `dest`; returns the sorted names of the files written."""
            names = []
            os.makedirs(dest, exist_ok=True)
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                for info in zf.infolist():
                    _target(dest, info.filename)
                for info in zf.infolist():
                    if info.is_dir():
                        continue
                    target = _target(dest, info.filename)
                    os.makedirs(os.path.dirname(target), exist_ok=True)
                    with open(target, "wb") as fh:
                        fh.write(zf.read(info))
                    names.append(info.filename)
            return sorted(names)
    ''')},
    hidden={"tests/test_zipin_security.py": P + dd('''
        import zipin as m


        class ZipinTest(unittest.TestCase):
            def setUp(self):
                self.root = tmpdir()
                self.dest = os.path.join(self.root, "x", "in")

            def tearDown(self):
                shutil.rmtree(self.root, ignore_errors=True)

            def test_normal(self):
                data = make_zip([("..hidden.csv", b"h"), (".config", b"c"), ("a..b/x..y.csv", b"d"), ("reports/2024/q1.csv", b"q"), ("reports/", b"")])
                names = m.extract_zip(data, self.dest)
                self.assertEqual(names, sorted(["..hidden.csv", ".config", "a..b/x..y.csv", "reports/2024/q1.csv"]))
                self.assertEqual(read(os.path.join(self.dest, "..hidden.csv")), b"h")
                self.assertEqual(read(os.path.join(self.dest, "reports", "2024", "q1.csv")), b"q")

            def test_escape(self):
                before = snapshot(self.root, self.dest)
                abs_name = os.path.join(self.root, "abs.txt")
                for entries in [[(abs_name, b"x")], [("ok.txt", b"1"), (abs_name + "2", b"x")], [("../up.txt", b"x")], [("a/../../up2.txt", b"x")], [("//" + abs_name, b"x")]]:
                    attempt(m.extract_zip, make_zip(entries), self.dest)
                self.assertEqual(before, snapshot(self.root, self.dest))


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

# ---------------------------------------------------------------------------------------------------------------
SC.append(dict(
    slug="zip-symlinks", d=4, product="the firmware update tool", func="extract_zip", cwe="CWE-59",
    finding="`extract_zip` faithfully recreates symbolic links stored in an archive (unix mode in the zip entry) and its lexical `..` check passes for a later member like `evil/pwn.txt`; an archive can first plant `evil -> ..` (or an absolute link) and then write through it to anywhere.",
    start={
        "fwunzip.py": dd('''
            """Unpacking of firmware update archives (they may contain symlinks)."""
            import io
            import os
            import stat
            import zipfile


            def extract_zip(data, dest):
                """Extract the zip archive `data` into `dest`; unix symlink entries are recreated as symlinks. Returns the sorted names of all entries that are not directories."""
                names = []
                os.makedirs(dest, exist_ok=True)
                base = os.path.abspath(dest)
                with zipfile.ZipFile(io.BytesIO(data)) as zf:
                    for info in zf.infolist():
                        target = os.path.abspath(os.path.join(base, info.filename))
                        if os.path.commonpath([base, target]) != base:
                            raise ValueError("member outside the destination")
                        if info.is_dir():
                            os.makedirs(target, exist_ok=True)
                            continue
                        os.makedirs(os.path.dirname(target), exist_ok=True)
                        mode = info.external_attr >> 16
                        if stat.S_ISLNK(mode):
                            os.symlink(zf.read(info).decode("utf-8"), target)
                        else:
                            with open(target, "wb") as fh:
                                fh.write(zf.read(info))
                        names.append(info.filename)
                return sorted(names)
        '''),
        "README.md": readme("fwunzip", "`extract_zip(data, dest)` unpacks a firmware archive into `dest`. Symlink entries are recreated as symlinks **only if** the link (resolved relative to the folder it lives in) points to a place inside `dest`; an archive with a link that leads outside, or that tries to write through such a link, is rejected. Regular files, folders and internal symlinks work as usual."),
    },
    solution={"fwunzip.py": dd('''
        """Unpacking of firmware update archives (they may contain symlinks)."""
        import io
        import os
        import stat
        import zipfile


        def _inside(base, path):
            return os.path.commonpath([base, path]) == base


        def extract_zip(data, dest):
            """Extract the zip archive `data` into `dest`; unix symlink entries are recreated as symlinks. Returns the sorted names of all entries that are not directories."""
            names = []
            os.makedirs(dest, exist_ok=True)
            base = os.path.realpath(dest)
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                for info in zf.infolist():
                    parent = os.path.realpath(os.path.dirname(os.path.join(base, info.filename)))
                    target = os.path.join(parent, os.path.basename(info.filename.rstrip("/")))
                    if not _inside(base, parent) or not _inside(base, os.path.realpath(target)) and not stat.S_ISLNK(info.external_attr >> 16):
                        raise ValueError("member outside the destination")
                    if info.is_dir():
                        os.makedirs(os.path.join(base, info.filename), exist_ok=True)
                        continue
                    os.makedirs(parent, exist_ok=True)
                    mode = info.external_attr >> 16
                    if stat.S_ISLNK(mode):
                        link_to = zf.read(info).decode("utf-8")
                        resolved = os.path.realpath(os.path.join(os.path.dirname(target), link_to))
                        if not _inside(base, resolved):
                            raise ValueError("symlink leads outside the destination")
                        os.symlink(link_to, target)
                    else:
                        with open(target, "wb") as fh:
                            fh.write(zf.read(info))
                    names.append(info.filename)
            return sorted(names)
    ''')},
    hidden={"tests/test_fwunzip_security.py": P + dd('''
        import fwunzip as m

        LNK = 0o120777 << 16


        class FwTest(unittest.TestCase):
            def setUp(self):
                self.root = tmpdir()
                self.dest = os.path.join(self.root, "x", "fw")
                write(os.path.join(self.root, "x", "victim.txt"), b"ORIGINAL")

            def tearDown(self):
                shutil.rmtree(self.root, ignore_errors=True)

            def test_normal(self):
                data = make_zip([("bin/tool", b"ELF"), ("bin/tool-latest", "tool", LNK), ("etc/conf", b"c"), ("lib/", b""), ("lib/libx.so.1", b"so"), ("lib/libx.so", "libx.so.1", LNK), ("top", "bin", LNK)])
                names = m.extract_zip(data, self.dest)
                self.assertEqual(names, sorted(["bin/tool", "bin/tool-latest", "etc/conf", "lib/libx.so.1", "lib/libx.so", "top"]))
                self.assertEqual(read(os.path.join(self.dest, "bin", "tool-latest")), b"ELF")
                self.assertEqual(read(os.path.join(self.dest, "lib", "libx.so")), b"so")
                self.assertTrue(os.path.islink(os.path.join(self.dest, "lib", "libx.so")))
                self.assertEqual(read(os.path.join(self.dest, "top", "tool")), b"ELF")

            def test_escape(self):
                before = snapshot(self.root, self.dest)
                for entries in [
                    [("evil", "..", LNK), ("evil/pwn.txt", b"x")],
                    [("evil", self.root, LNK), ("evil/pwn2.txt", b"x")],
                    [("a/evil", "../..", LNK), ("a/evil/pwn3.txt", b"x")],
                    [("victim.txt", "../victim.txt", LNK), ("victim.txt", b"HACKED")],
                    [("hop1", "..", LNK), ("hop2", "hop1", LNK), ("hop2/pwn4.txt", b"x")],
                    [("../up.txt", b"x")],
                ]:
                    attempt(m.extract_zip, make_zip(entries), self.dest)
                    shutil.rmtree(self.dest, ignore_errors=True)
                self.assertEqual(before, snapshot(self.root, self.dest))
                self.assertEqual(read(os.path.join(self.root, "x", "victim.txt")), b"ORIGINAL")


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

# ---------------------------------------------------------------------------------------------------------------
SC.append(dict(
    slug="zip-bomb", d=3, product="the photo import service", func="extract_zip", cwe="CWE-409",
    finding="`extract_zip` reads every member completely into memory and writes it out, with no limit on the number of entries or on the uncompressed size, so a few kilobytes of zip can fill the disk and memory (zip bomb).",
    start={
        "photozip.py": dd('''
            """Import of photo archives uploaded by users."""
            import io
            import os
            import zipfile


            def extract_zip(data, dest):
                """Extract the archive `data` into `dest`; returns the sorted names of the extracted files."""
                names = []
                os.makedirs(dest, exist_ok=True)
                with zipfile.ZipFile(io.BytesIO(data)) as zf:
                    for info in zf.infolist():
                        if info.is_dir():
                            continue
                        target = os.path.join(dest, os.path.basename(info.filename))
                        with open(target, "wb") as fh:
                            fh.write(zf.read(info))
                        names.append(os.path.basename(info.filename))
                return sorted(names)
        '''),
        "README.md": readme("photozip", "`extract_zip(data, dest)` extracts the files of an uploaded archive into `dest` (flat: only the base name of each entry is used) and returns their sorted names. Limits: at most **100 entries**, at most **2 MiB** per file and at most **5 MiB** in total after decompression. An archive that exceeds a limit raises `ValueError` and leaves (at most a negligible amount of) data on disk."),
    },
    solution={"photozip.py": dd('''
        """Import of photo archives uploaded by users."""
        import io
        import os
        import zipfile

        MAX_ENTRIES = 100
        MAX_FILE = 2 * 1024 * 1024
        MAX_TOTAL = 5 * 1024 * 1024


        def extract_zip(data, dest):
            """Extract the archive `data` into `dest`; returns the sorted names of the extracted files."""
            names = []
            os.makedirs(dest, exist_ok=True)
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                infos = zf.infolist()
                if len(infos) > MAX_ENTRIES:
                    raise ValueError("too many entries")
                if any(i.file_size > MAX_FILE for i in infos) or sum(i.file_size for i in infos) > MAX_TOTAL:
                    raise ValueError("archive too large")
                total = 0
                for info in infos:
                    if info.is_dir():
                        continue
                    name = os.path.basename(info.filename)
                    with zf.open(info) as src:
                        chunk = src.read(MAX_FILE + 1)
                    total += len(chunk)
                    if len(chunk) > MAX_FILE or total > MAX_TOTAL:
                        raise ValueError("archive too large")
                    with open(os.path.join(dest, name), "wb") as fh:
                        fh.write(chunk)
                    names.append(name)
            return sorted(names)
    ''')},
    hidden={"tests/test_photozip_security.py": P + dd('''
        import photozip as m


        def dir_size(path):
            total = 0
            for dirpath, _, files in os.walk(path):
                for f in files:
                    total += os.path.getsize(os.path.join(dirpath, f))
            return total


        class PhotoTest(unittest.TestCase):
            def setUp(self):
                self.root = tmpdir()
                self.dest = os.path.join(self.root, "photos")

            def tearDown(self):
                shutil.rmtree(self.root, ignore_errors=True)

            def test_normal(self):
                data = make_zip([("a.jpg", b"J" * 1000), ("trip/b.jpg", b"K" * 5000), ("c.png", b"")] + [("many/f%d.txt" % i, b"x" * 100) for i in range(40)])
                names = m.extract_zip(data, self.dest)
                self.assertEqual(len(names), 43)
                self.assertIn("a.jpg", names)
                self.assertEqual(read(os.path.join(self.dest, "b.jpg")), b"K" * 5000)

            def test_limits(self):
                bombs = [
                    make_zip([("big.bin", b"\\0" * (6 * 1024 * 1024))]),
                    make_zip([("a.bin", b"\\0" * (3 * 1024 * 1024))]),
                    make_zip([("p%d.bin" % i, b"\\0" * (1024 * 1024)) for i in range(7)]),
                    make_zip([("f%d.txt" % i, b"x") for i in range(150)]),
                ]
                for z in bombs:
                    shutil.rmtree(self.dest, ignore_errors=True)
                    with self.assertRaises(ValueError):
                        m.extract_zip(z, self.dest)
                    self.assertLess(dir_size(self.dest) if os.path.exists(self.dest) else 0, 3 * 1024 * 1024)

            def test_at_the_limit(self):
                shutil.rmtree(self.dest, ignore_errors=True)
                data = make_zip([("p%d.bin" % i, os.urandom(1024 * 1024)) for i in range(5)])
                self.assertEqual(len(m.extract_zip(data, self.dest)), 5)


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

# ---------------------------------------------------------------------------------------------------------------
SC.append(dict(
    slug="plugin-manifest", d=4, product="the plugin manager", func="install_plugin", cwe="CWE-22",
    finding="`install_plugin` trusts the `manifest.json` inside the uploaded package: the plugin `name` becomes a directory name (so `../../bin` escapes), and every path listed under `files` is joined to that directory unchecked.",
    start={
        "plugins.py": dd('''
            """Installer for zipped plugin packages."""
            import io
            import json
            import os
            import zipfile


            def install_plugin(package, plugins_dir):
                """Install the plugin package (zip bytes) below PLUGINS_DIR/<plugin name>; returns the plugin name.

                The package holds `manifest.json` with {"name": ..., "files": [...]}; every listed file is copied from the archive (same relative path)."""
                with zipfile.ZipFile(io.BytesIO(package)) as zf:
                    manifest = json.loads(zf.read("manifest.json"))
                    name = manifest["name"]
                    target_dir = os.path.join(plugins_dir, name)
                    os.makedirs(target_dir, exist_ok=True)
                    for rel in manifest["files"]:
                        out = os.path.join(target_dir, rel)
                        os.makedirs(os.path.dirname(out), exist_ok=True)
                        with open(out, "wb") as fh:
                            fh.write(zf.read(rel))
                return name
        '''),
        "README.md": readme("plugins", "`install_plugin(package, plugins_dir)` installs a plugin package and returns its name. Plugin names consist of lower-case letters, digits, `-` and `_` (1 to 40 characters). Listed files keep their relative paths (sub-folders allowed, dots allowed in file names). Any invalid package raises `ValueError`: no manifest, bad JSON, missing `name` or `files`, a bad name, a listed file that is not in the archive, or a file path that would leave the plugin's folder. An invalid package installs nothing."),
    },
    solution={"plugins.py": dd('''
        """Installer for zipped plugin packages."""
        import io
        import json
        import os
        import re
        import zipfile

        NAME = re.compile(r"[a-z0-9_-]{1,40}")


        def install_plugin(package, plugins_dir):
            """Install the plugin package (zip bytes) below PLUGINS_DIR/<plugin name>; returns the plugin name.

            The package holds `manifest.json` with {"name": ..., "files": [...]}; every listed file is copied from the archive (same relative path)."""
            try:
                zf = zipfile.ZipFile(io.BytesIO(package))
            except zipfile.BadZipFile:
                raise ValueError("not a zip package")
            with zf:
                try:
                    manifest = json.loads(zf.read("manifest.json"))
                    name = manifest["name"]
                    files = manifest["files"]
                except (KeyError, ValueError, TypeError):
                    raise ValueError("invalid manifest")
                if not isinstance(name, str) or not NAME.fullmatch(name) or not isinstance(files, list):
                    raise ValueError("invalid manifest")
                base = os.path.realpath(os.path.join(plugins_dir, name))
                if os.path.dirname(base) != os.path.realpath(plugins_dir):
                    raise ValueError("bad plugin name")
                writes = []
                for rel in files:
                    if not isinstance(rel, str):
                        raise ValueError("bad file entry")
                    out = os.path.realpath(os.path.join(base, rel))
                    if os.path.commonpath([base, out]) != base or out == base:
                        raise ValueError("file path leaves the plugin folder")
                    try:
                        writes.append((out, zf.read(rel)))
                    except KeyError:
                        raise ValueError("listed file missing from the archive")
                os.makedirs(base, exist_ok=True)
                for out, data in writes:
                    os.makedirs(os.path.dirname(out), exist_ok=True)
                    with open(out, "wb") as fh:
                        fh.write(data)
            return name
    ''')},
    hidden={"tests/test_plugins_security.py": P + dd('''
        import plugins as m


        def package(manifest, members):
            entries = [("manifest.json", manifest if isinstance(manifest, bytes) else json.dumps(manifest).encode())] if manifest is not None else []
            return make_zip(entries + members)


        class PluginTest(unittest.TestCase):
            def setUp(self):
                self.root = tmpdir()
                self.plugins = os.path.join(self.root, "x", "plugins")
                os.makedirs(self.plugins)

            def tearDown(self):
                shutil.rmtree(self.root, ignore_errors=True)

            def test_normal(self):
                pkg = package({"name": "weather-2_x", "files": ["main.py", "lib/util.py", "assets/a..b.png"]}, [("main.py", b"print(1)"), ("lib/util.py", b"u"), ("assets/a..b.png", b"png"), ("unlisted.txt", b"nope")])
                self.assertEqual(m.install_plugin(pkg, self.plugins), "weather-2_x")
                self.assertEqual(read(os.path.join(self.plugins, "weather-2_x", "lib", "util.py")), b"u")
                self.assertEqual(read(os.path.join(self.plugins, "weather-2_x", "assets", "a..b.png")), b"png")
                self.assertFalse(os.path.exists(os.path.join(self.plugins, "weather-2_x", "unlisted.txt")))

            def test_invalid_packages(self):
                bad = [
                    package(None, [("a.py", b"x")]), package(b"{not json", []), package({"files": []}, []), package({"name": "x"}, []), package({"name": "UPPER", "files": []}, []), package({"name": "", "files": []}, []),
                    package({"name": "a" * 41, "files": []}, []), package({"name": "ok", "files": ["missing.py"]}, []), package({"name": "ok", "files": [3]}, []), package({"name": 5, "files": []}, []), b"not a zip at all",
                ]
                for pkg in bad:
                    with self.assertRaises(ValueError):
                        m.install_plugin(pkg, self.plugins)
                self.assertEqual(os.listdir(self.plugins), [])

            def test_escape(self):
                before = snapshot(self.root, self.plugins)
                evil = [
                    package({"name": "../../evil", "files": []}, []), package({"name": "../outside", "files": ["x.py"]}, [("x.py", b"x")]), package({"name": "ok", "files": ["../../up.py"]}, [("../../up.py", b"x")]),
                    package({"name": os.path.join(self.root, "abs"), "files": ["x.py"]}, [("x.py", b"x")]), package({"name": "ok", "files": [os.path.join(self.root, "abs.py")]}, [(os.path.join(self.root, "abs.py"), b"x")]),
                    package({"name": "..", "files": ["x.py"]}, [("x.py", b"x")]), package({"name": ".", "files": ["x.py"]}, [("x.py", b"x")]),
                ]
                for pkg in evil:
                    attempt(m.install_plugin, pkg, self.plugins)
                self.assertEqual(before, snapshot(self.root, self.plugins))
                self.assertEqual(os.listdir(self.plugins), [])


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

# ---------------------------------------------------------------------------------------------------------------
SC.append(dict(
    slug="nested-archives", d=4, product="the document intake pipeline", func="unpack_all", cwe="CWE-409",
    finding="`unpack_all` recursively unpacks zip files found inside zip files without any limits, and joins member names to the destination unchecked: a deeply nested or wide archive exhausts the machine, and a nested archive can still write outside the destination.",
    start={
        "intake.py": dd('''
            """Recursive unpacking of document bundles."""
            import io
            import os
            import zipfile


            def unpack_all(data, dest):
                """Extract the zip archive `data` below `dest`. A member whose name ends in `.zip` is itself unpacked into a folder of the same name (without the extension).
                Returns the sorted '/'-separated relative names of all plain files that were written."""
                written = []
                _unpack(data, dest, "", written)
                return sorted(written)


            def _unpack(data, dest, prefix, written):
                os.makedirs(dest, exist_ok=True)
                with zipfile.ZipFile(io.BytesIO(data)) as zf:
                    for info in zf.infolist():
                        if info.is_dir():
                            continue
                        content = zf.read(info)
                        rel = prefix + info.filename
                        if info.filename.lower().endswith(".zip"):
                            _unpack(content, os.path.join(dest, info.filename[:-4]), rel[:-4] + "/", written)
                        else:
                            target = os.path.join(dest, info.filename)
                            os.makedirs(os.path.dirname(target), exist_ok=True)
                            with open(target, "wb") as fh:
                                fh.write(content)
                            written.append(rel)
        '''),
        "README.md": readme("intake", "`unpack_all(data, dest)` unpacks a zip bundle and, recursively, the zip files inside it (`inner.zip` becomes the folder `inner/`). It returns the sorted relative names of the plain files written. Limits: nesting depth at most **3** (the bundle itself is depth 0), at most **200** files in total and at most **4 MiB** written in total; exceeding a limit raises `ValueError`. Member names that would write outside the destination of their archive raise `ValueError` as well."),
    },
    solution={"intake.py": dd('''
        """Recursive unpacking of document bundles."""
        import io
        import os
        import zipfile

        MAX_DEPTH = 3
        MAX_FILES = 200
        MAX_BYTES = 4 * 1024 * 1024


        def unpack_all(data, dest):
            """Extract the zip archive `data` below `dest`. A member whose name ends in `.zip` is itself unpacked into a folder of the same name (without the extension).
            Returns the sorted '/'-separated relative names of all plain files that were written."""
            state = {"files": 0, "bytes": 0}
            written = []
            _unpack(data, dest, "", written, 0, state)
            return sorted(written)


        def _unpack(data, dest, prefix, written, depth, state):
            if depth > MAX_DEPTH:
                raise ValueError("archives nested too deeply")
            os.makedirs(dest, exist_ok=True)
            base = os.path.realpath(dest)
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                for info in zf.infolist():
                    if info.is_dir():
                        continue
                    if info.file_size > MAX_BYTES:
                        raise ValueError("archive too large")
                    with zf.open(info) as src:
                        content = src.read(MAX_BYTES + 1)
                    if len(content) > MAX_BYTES:
                        raise ValueError("archive too large")
                    rel = prefix + info.filename
                    if info.filename.lower().endswith(".zip"):
                        sub = os.path.realpath(os.path.join(base, info.filename[:-4]))
                        if os.path.commonpath([base, sub]) != base or sub == base:
                            raise ValueError("member escapes the destination")
                        _unpack(content, sub, rel[:-4] + "/", written, depth + 1, state)
                    else:
                        target = os.path.realpath(os.path.join(base, info.filename))
                        if os.path.commonpath([base, target]) != base:
                            raise ValueError("member escapes the destination")
                        state["files"] += 1
                        state["bytes"] += len(content)
                        if state["files"] > MAX_FILES or state["bytes"] > MAX_BYTES:
                            raise ValueError("too many files or bytes")
                        os.makedirs(os.path.dirname(target), exist_ok=True)
                        with open(target, "wb") as fh:
                            fh.write(content)
                        written.append(rel)
    ''')},
    hidden={"tests/test_intake_security.py": P + dd('''
        import intake as m


        def nest(levels, leaf=b"leaf"):
            data = make_zip([("deep.txt", leaf)])
            for i in range(levels):
                data = make_zip([("inner%d.zip" % i, data), ("note%d.txt" % i, b"n")])
            return data


        class IntakeTest(unittest.TestCase):
            def setUp(self):
                self.root = tmpdir()
                self.dest = os.path.join(self.root, "out")
                write(os.path.join(self.root, "victim.txt"), b"ORIGINAL")

            def tearDown(self):
                shutil.rmtree(self.root, ignore_errors=True)

            def test_normal(self):
                inner = make_zip([("b.txt", b"bee"), ("sub/c..d.txt", b"c")])
                data = make_zip([("a.txt", b"ay"), ("pack.zip", inner), ("docs/e.txt", b"e")])
                names = m.unpack_all(data, self.dest)
                self.assertEqual(names, sorted(["a.txt", "pack/b.txt", "pack/sub/c..d.txt", "docs/e.txt"]))
                self.assertEqual(read(os.path.join(self.dest, "pack", "sub", "c..d.txt")), b"c")
                names = m.unpack_all(nest(3), os.path.join(self.root, "n3"))
                self.assertIn("inner2/inner1/inner0/deep.txt", names)

            def test_limits(self):
                for data in [nest(4), nest(8), make_zip([("f%d.txt" % i, b"x") for i in range(250)]), make_zip([("big%d.bin" % i, b"\\0" * (1024 * 1024)) for i in range(6)]),
                             make_zip([("n%d.zip" % i, make_zip([("g%d.txt" % j, b"x") for j in range(30)])) for i in range(8)])]:
                    shutil.rmtree(self.dest, ignore_errors=True)
                    with self.assertRaises(ValueError):
                        m.unpack_all(data, self.dest)

            def test_escape(self):
                before = snapshot(self.root, self.dest)
                inner_evil = make_zip([("../../victim.txt", b"HACKED")])
                inner_evil2 = make_zip([("ok.txt", b"1"), ("../side/x.txt", b"x")])
                for data in [make_zip([("../victim.txt", b"HACKED")]), make_zip([("pack.zip", inner_evil)]), make_zip([("a/pack.zip", inner_evil2)]), make_zip([("../evil.zip", make_zip([("x.txt", b"x")]))]),
                             make_zip([(os.path.join(self.root, "abs.txt"), b"x")])]:
                    attempt(m.unpack_all, data, self.dest)
                self.assertEqual(before, snapshot(self.root, self.dest))
                self.assertEqual(read(os.path.join(self.root, "victim.txt")), b"ORIGINAL")


        if __name__ == "__main__":
            unittest.main()
    ''')},
))


@family("security-zip-slip", category="security", lang="python", kind="fix", n=8,
        summary="safe archive extraction: traversal, absolute names, symlinks and hard links, bombs, manifests, nesting")
def gen_zip(rng, n):
    return list(_sec.emit(rng, SC[:n], tags=["archives"]))

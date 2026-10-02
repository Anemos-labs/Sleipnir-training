"""Security families: time-of-check/time-of-use races (modelled deterministically by firing the "other party" at the worst moment), upload validation,
and log / output injection. Nothing leaves the temporary directories created by the tests."""
from fx import dd, family

from . import _sec
from ._sec import patched, readme

P = _sec.PY_PRELUDE

RACE = P + dd(r'''
    import builtins
    import contextlib
    import io
    import signal


    @contextlib.contextmanager
    def before_open(name, action):
        """Runs `action()` once, right before the first open() / io.open() / os.open() of a path whose last component is `name`: the worst possible moment for a check-then-use race."""
        real = (builtins.open, io.open, os.open)
        fired = []

        def trigger(path):
            try:
                last = os.path.basename(os.fsdecode(path))
            except TypeError:        # a file descriptor
                return
            if last == name and not fired:
                fired.append(1)
                action()

        def wrap(fn):
            def inner(path, *args, **kwargs):
                trigger(path)
                return fn(path, *args, **kwargs)
            return inner

        builtins.open, io.open, os.open = (wrap(f) for f in real)
        try:
            yield fired
        finally:
            builtins.open, io.open, os.open = real


    @contextlib.contextmanager
    def time_limit(seconds=8):
        """Fails the test instead of hanging when the code under test deadlocks."""
        def boom(signum, frame):
            raise TimeoutError("test timed out (deadlock?)")
        old = signal.signal(signal.SIGALRM, boom)
        signal.alarm(seconds)
        try:
            yield
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old)


    def symlink(target, path):
        if os.path.lexists(path):
            os.remove(path)
        os.symlink(target, path)


''')

# =================================================================================================================================
#  TOCTOU
# =================================================================================================================================
TO = []

REPORTS = dd(r'''
    """Report files of the nightly job."""
    import os


    def save_report(directory, name, text):
        """Write `text` to the file `name` inside `directory` (a plain file name, no separators) and return its path. An existing regular file is replaced; a symbolic link is never followed
        (OSError or ValueError instead): nothing outside `directory` may be written, whatever happens to the path while this function runs - another user can create or swap names in the directory."""
        path = os.path.join(directory, name)
        if os.path.islink(path):
            raise ValueError("refusing to write through a symbolic link")
        with open(path, "w") as fh:
            fh.write(text)
        return path
''')

TO.append(dict(
    slug="symlink-swap", d=3, product="the nightly report job", func="save_report", cwe="CWE-367",
    finding="`save_report` checks `os.path.islink(path)` and opens the path afterwards; in the gap another user who can write to the shared directory replaces the file with a symlink to a file of the job's user (a credentials file, the crontab...) and the job overwrites that file: a classic time-of-check/time-of-use race.",
    start={"reports.py": REPORTS, "README.md": readme("reports", "`save_report(directory, name, text)` returns the path and writes the text (replacing a regular file at that path, creating it otherwise). Symbolic links at the target path are refused with `OSError` or `ValueError`, also when they appear *between* any check and the open: open the file in a way that cannot follow a link (`O_NOFOLLOW`) instead of checking first. Files are created with mode 0644 (before umask).")},
    solution={"reports.py": patched(REPORTS, (
        '''    path = os.path.join(directory, name)
    if os.path.islink(path):
        raise ValueError("refusing to write through a symbolic link")
    with open(path, "w") as fh:
        fh.write(text)
    return path
''', '''    path = os.path.join(directory, name)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o644)
    with os.fdopen(fd, "w") as fh:
        fh.write(text)
    return path
'''))},
    hidden={"tests/test_reports_security.py": RACE + dd(r'''
        import reports as m


        class ReportTest(unittest.TestCase):
            def setUp(self):
                self.root = tmpdir()
                self.addCleanup(shutil.rmtree, self.root, True)
                self.dir = os.path.join(self.root, "reports")
                os.makedirs(self.dir)
                self.secret = os.path.join(self.root, "secret.txt")
                write(self.secret, "original secret")

            def test_normal(self):
                path = m.save_report(self.dir, "a.txt", "hello\n")
                self.assertEqual(path, os.path.join(self.dir, "a.txt"))
                self.assertEqual(read(path), b"hello\n")
                self.assertEqual(m.save_report(self.dir, "a.txt", "second"), path)
                self.assertEqual(read(path), b"second")
                self.assertFalse(os.path.islink(path))

            def test_existing_symlink(self):
                link = os.path.join(self.dir, "link.txt")
                os.symlink(self.secret, link)
                self.assertIsNone(attempt(m.save_report, self.dir, "link.txt", "pwned"))
                self.assertEqual(read(self.secret), b"original secret")

            def test_symlink_swapped_in_during_the_call(self):
                path = os.path.join(self.dir, "report.txt")
                write(path, "old report")
                with before_open("report.txt", lambda: symlink(self.secret, path)) as fired:
                    attempt(m.save_report, self.dir, "report.txt", "pwned")
                self.assertTrue(fired)
                self.assertEqual(read(self.secret), b"original secret")
                fresh = os.path.join(self.dir, "fresh.txt")
                with before_open("fresh.txt", lambda: symlink(self.secret, fresh)):
                    attempt(m.save_report, self.dir, "fresh.txt", "pwned")
                self.assertEqual(read(self.secret), b"original secret")


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

TEMPFILE = dd(r'''
    """Temporary files of the upload handler."""
    import os


    def write_temp(tmp_dir, data):
        """Create a new private temporary file inside `tmp_dir` holding the bytes `data`, and return its path. `tmp_dir` is shared: other users can create names in it, so the file name must be
        unpredictable, an existing file or link must never be reused, opened or followed, and the new file is readable by its owner only (mode 0600)."""
        path = os.path.join(tmp_dir, "upload-%d.tmp" % os.getpid())
        if os.path.exists(path):
            raise FileExistsError(path)
        with open(path, "wb") as fh:
            fh.write(data)
        return path
''')

TO.append(dict(
    slug="predictable-temp", d=3, product="the upload handler", func="write_temp", cwe="CWE-377",
    finding="`write_temp` names its file after the process id and checks `os.path.exists` before opening it: an attacker who can create names in the shared directory plants a dangling symlink at the predictable name (`exists` follows links, so the check passes) and the handler creates or overwrites a file of the attacker's choosing with upload data.",
    start={"tempfiles.py": TEMPFILE, "README.md": readme("temporary files", "`write_temp(tmp_dir, data)` creates a fresh file with an unpredictable name inside `tmp_dir` (the standard library's `tempfile.mkstemp` does everything required), mode 0600, content exactly `data`, and returns its path. It never writes through pre-existing names, however they were planted before or during the call.")},
    solution={"tempfiles.py": patched(TEMPFILE, ('"""Temporary files of the upload handler."""\nimport os\n', '"""Temporary files of the upload handler."""\nimport os\nimport tempfile\n'), (
        '''    path = os.path.join(tmp_dir, "upload-%d.tmp" % os.getpid())
    if os.path.exists(path):
        raise FileExistsError(path)
    with open(path, "wb") as fh:
        fh.write(data)
    return path
''', '''    fd, path = tempfile.mkstemp(dir=tmp_dir, prefix="upload-", suffix=".tmp")
    with os.fdopen(fd, "wb") as fh:
        fh.write(data)
    return path
'''))},
    hidden={"tests/test_tempfiles_security.py": RACE + dd(r'''
        import tempfiles as m


        class TempTest(unittest.TestCase):
            def setUp(self):
                self.root = tmpdir()
                self.addCleanup(shutil.rmtree, self.root, True)
                self.tmp = os.path.join(self.root, "shared-tmp")
                os.makedirs(self.tmp)
                self.victim = os.path.join(self.root, "victim", "target.txt")
                os.makedirs(os.path.dirname(self.victim))
                self.secret = os.path.join(self.root, "secret.txt")
                write(self.secret, "original secret")
                self.predictable = os.path.join(self.tmp, "upload-%d.tmp" % os.getpid())

            def test_normal(self):
                a, b = m.write_temp(self.tmp, b"first"), m.write_temp(self.tmp, b"second \x00 \xff")
                self.assertNotEqual(a, b)
                self.assertEqual(os.path.dirname(a), self.tmp)
                self.assertEqual(read(a), b"first")
                self.assertEqual(read(b), b"second \x00 \xff")
                self.assertEqual(os.stat(a).st_mode & 0o777, 0o600)
                self.assertNotEqual(a, self.predictable)
                self.assertNotEqual(b, self.predictable)

            def test_planted_dangling_symlink(self):
                os.symlink(self.victim, self.predictable)
                attempt(m.write_temp, self.tmp, b"upload data")
                self.assertFalse(os.path.exists(self.victim))

            def test_planted_symlink_to_existing_file(self):
                os.symlink(self.secret, self.predictable)
                attempt(m.write_temp, self.tmp, b"upload data")
                self.assertEqual(read(self.secret), b"original secret")

            def test_symlink_appearing_during_the_call(self):
                with before_open("upload-%d.tmp" % os.getpid(), lambda: symlink(self.secret, self.predictable)):
                    attempt(m.write_temp, self.tmp, b"upload data")
                self.assertEqual(read(self.secret), b"original secret")
                with before_open("upload-%d.tmp" % os.getpid(), lambda: symlink(self.victim, self.predictable)):
                    attempt(m.write_temp, self.tmp, b"upload data")
                self.assertFalse(os.path.exists(self.victim))


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

SECRETSTORE = dd(r'''
    """Storage of private key material."""
    import os


    def save_secret(path, data):
        """Create the file `path` holding the bytes `data`, readable and writable by its owner only (mode 0600) from the moment it exists - the content must never be visible to other users, even for an
        instant, whatever the process umask is. The file must be new: if `path` exists (a file, a symbolic link, even a dangling one) raise FileExistsError and leave it alone."""
        with open(path, "wb") as fh:
            fh.write(data)
        os.chmod(path, 0o600)
''')

TO.append(dict(
    slug="chmod-after-write", d=3, product="the key storage", func="save_secret", cwe="CWE-276",
    finding="`save_secret` creates the file with the default permissions (0666 minus umask, typically world-readable), writes the key, and only then calls `chmod 600`: between the write and the chmod any local user can open the file and keep the descriptor, and an existing file or symlink at the path is happily truncated or followed.",
    start={"secretstore.py": SECRETSTORE, "README.md": readme("key storage", "`save_secret(path, data)` creates the file atomically with mode 0600 (permissions set at creation, not afterwards: `os.open` with `O_CREAT | O_EXCL | O_WRONLY` and mode `0o600`), writes the data, and raises `FileExistsError` - touching nothing - when the path already exists in any form. The result is mode 0600 whatever the umask is.")},
    solution={"secretstore.py": patched(SECRETSTORE, (
        '''    with open(path, "wb") as fh:
        fh.write(data)
    os.chmod(path, 0o600)
''', '''    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as fh:
        fh.write(data)
'''))},
    hidden={"tests/test_secretstore_security.py": RACE + dd(r'''
        import secretstore as m


        class SecretStoreTest(unittest.TestCase):
            def setUp(self):
                self.root = tmpdir()
                self.addCleanup(shutil.rmtree, self.root, True)
                self.old_umask = os.umask(0)
                self.addCleanup(os.umask, self.old_umask)

            def test_new_file(self):
                path = os.path.join(self.root, "key.pem")
                m.save_secret(path, b"-----key material-----\n")
                self.assertEqual(read(path), b"-----key material-----\n")
                self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)
                path2 = os.path.join(self.root, "empty.key")
                m.save_secret(path2, b"")
                self.assertEqual(os.stat(path2).st_mode & 0o777, 0o600)

            def test_never_world_readable_with_content(self):
                seen = []
                real_chmod, real_fchmod = os.chmod, os.fchmod

                def chmod(p, mode, *a, **k):
                    st = os.stat(p)
                    seen.append((st.st_mode & 0o077, st.st_size))
                    return real_chmod(p, mode, *a, **k)

                def fchmod(fd, mode):
                    st = os.fstat(fd)
                    seen.append((st.st_mode & 0o077, st.st_size))
                    return real_fchmod(fd, mode)

                os.chmod, os.fchmod = chmod, fchmod
                try:
                    m.save_secret(os.path.join(self.root, "k2.pem"), b"top secret")
                finally:
                    os.chmod, os.fchmod = real_chmod, real_fchmod
                self.assertEqual([entry for entry in seen if entry[0] and entry[1]], [])
                self.assertEqual(os.stat(os.path.join(self.root, "k2.pem")).st_mode & 0o777, 0o600)

            def test_existing_paths_are_left_alone(self):
                existing = os.path.join(self.root, "old.pem")
                write(existing, "old content")
                os.chmod(existing, 0o644)
                with self.assertRaises(FileExistsError):
                    m.save_secret(existing, b"new")
                self.assertEqual(read(existing), b"old content")
                self.assertEqual(os.stat(existing).st_mode & 0o777, 0o644)
                target = os.path.join(self.root, "target.txt")
                write(target, "target")
                link = os.path.join(self.root, "link.pem")
                os.symlink(target, link)
                self.assertIsNone(attempt(m.save_secret, link, b"pwned"))
                self.assertEqual(read(target), b"target")
                dangling = os.path.join(self.root, "dangling.pem")
                os.symlink(os.path.join(self.root, "nowhere.txt"), dangling)
                with self.assertRaises(FileExistsError):
                    m.save_secret(dangling, b"pwned")
                self.assertFalse(os.path.exists(os.path.join(self.root, "nowhere.txt")))


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

LOCK = dd(r'''
    """Single-instance lock of the batch job."""
    import os


    def acquire_lock(path):
        """Try to take the lock file at `path`. True when this caller created it and now holds the lock, False when somebody else holds it. Of any number of callers racing for the same path
        exactly one gets True - the others must not be able to slip in between a check and the creation."""
        if os.path.exists(path):
            return False
        with open(path, "w") as fh:
            fh.write(str(os.getpid()))
        return True


    def release_lock(path):
        """Give the lock back (no error when it is not held)."""
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
''')

TO.append(dict(
    slug="lock-file-race", d=3, product="the batch job", func="acquire_lock", cwe="CWE-367",
    finding="`acquire_lock` tests whether the lock file exists and creates it in a second step: two job instances started in the same instant both see no file, both create it and both run, which is exactly what the lock exists to prevent (the nightly run corrupted the ledger twice).",
    start={"locking.py": LOCK, "README.md": readme("single-instance lock", "`acquire_lock(path)` must be atomic: create the file with `O_CREAT | O_EXCL` and treat `FileExistsError` as \"somebody else has the lock\" (False). `release_lock` is unchanged. When another caller creates the lock after any check, it still wins and this caller gets False.")},
    solution={"locking.py": patched(LOCK, (
        '''    if os.path.exists(path):
        return False
    with open(path, "w") as fh:
        fh.write(str(os.getpid()))
    return True
''', '''    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    except FileExistsError:
        return False
    with os.fdopen(fd, "w") as fh:
        fh.write(str(os.getpid()))
    return True
'''))},
    hidden={"tests/test_locking_security.py": RACE + dd(r'''
        import locking as m


        class LockTest(unittest.TestCase):
            def setUp(self):
                self.root = tmpdir()
                self.addCleanup(shutil.rmtree, self.root, True)
                self.path = os.path.join(self.root, "job.lock")

            def test_basic(self):
                self.assertTrue(m.acquire_lock(self.path))
                self.assertEqual(read(self.path), str(os.getpid()).encode())
                self.assertFalse(m.acquire_lock(self.path))
                m.release_lock(self.path)
                m.release_lock(self.path)
                self.assertTrue(m.acquire_lock(self.path))

            def test_only_one_of_two_racing_callers_wins(self):
                results = []
                with time_limit(), before_open("job.lock", lambda: results.append(m.acquire_lock(self.path))) as fired:
                    results.append(m.acquire_lock(self.path))
                self.assertEqual(results.count(True), 1, results)
                self.assertEqual(len(results), 2)
                self.assertTrue(os.path.exists(self.path))

            def test_existing_lock_even_if_link_or_directory(self):
                os.symlink(os.path.join(self.root, "nowhere"), self.path)
                self.assertFalse(m.acquire_lock(self.path))
                self.assertFalse(os.path.exists(os.path.join(self.root, "nowhere")))


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

WALLET = dd(r'''
    """Wallet balances kept in a shared key-value store."""


    class InsufficientFunds(Exception):
        pass


    class MemoryStore:
        """The store of the tests. Every call is atomic on its own, but a `get` followed by a `set` is not: other requests are served in between. `add` is the atomic read-modify-write:
        it applies `delta` and returns the new value, or raises ValueError (changing nothing) when the result would be below `minimum`."""

        def __init__(self, data=None):
            self.data = dict(data or {})

        def get(self, key):
            return self.data[key]

        def set(self, key, value):
            self.data[key] = value

        def add(self, key, delta, minimum=None):
            value = self.data[key] + delta
            if minimum is not None and value < minimum:
                raise ValueError("below minimum")
            self.data[key] = value
            return value


    class Wallet:
        def __init__(self, store):
            self.store = store

        def withdraw(self, account, amount):
            """Take `amount` (a positive int, otherwise ValueError) out of the account and return the new balance. InsufficientFunds when the balance is too small, nothing changes then; KeyError for
            unknown accounts. Many requests run concurrently against the same store: balances must never go negative and no withdrawal may be lost or counted twice."""
            if isinstance(amount, bool) or not isinstance(amount, int) or amount <= 0:
                raise ValueError("amount must be a positive integer")
            balance = self.store.get(account)
            if balance < amount:
                raise InsufficientFunds(account)
            self.store.set(account, balance - amount)
            return balance - amount
''')

TO.append(dict(
    slug="double-spend", d=4, product="the wallet service", func="Wallet.withdraw", cwe="CWE-362",
    finding="`withdraw` reads the balance, checks it, and writes the new value back as three separate store calls; two requests that interleave between the read and the write both see 100, both withdraw 80, and the account ends with 20 after 160 left it (double spend). The store has an atomic `add` for exactly this.",
    start={"wallet.py": WALLET, "README.md": readme("wallet", "`Wallet.withdraw` keeps its contract (see docstring) but performs the balance check and the update as one atomic store operation (`store.add(account, -amount, minimum=0)`, translating its `ValueError` into `InsufficientFunds`). `MemoryStore` and `InsufficientFunds` stay as they are; a process-local lock is not a fix because the store is shared by many processes.")},
    solution={"wallet.py": patched(WALLET, (
        '''            balance = self.store.get(account)
            if balance < amount:
                raise InsufficientFunds(account)
            self.store.set(account, balance - amount)
            return balance - amount
''', '''            try:
                return self.store.add(account, -amount, minimum=0)
            except ValueError:
                raise InsufficientFunds(account)
'''))},
    hidden={"tests/test_wallet_security.py": RACE + dd(r'''
        import wallet as m


        class RacyStore(m.MemoryStore):
            """A store whose first modifying call is preceded by another client's complete request - the interleaving that breaks read-modify-write code."""

            def __init__(self, data):
                super().__init__(data)
                self.rival = None
                self.fired = False

            def _race(self):
                if self.rival and not self.fired:
                    self.fired = True
                    self.rival()

            def set(self, key, value):
                self._race()
                super().set(key, value)

            def add(self, key, delta, minimum=None):
                self._race()
                return super().add(key, delta, minimum)


        class WalletTest(unittest.TestCase):
            def test_plain_operations(self):
                w = m.Wallet(m.MemoryStore({"ann": 100, "bob": 5}))
                self.assertEqual(w.withdraw("ann", 30), 70)
                self.assertEqual(w.withdraw("ann", 70), 0)
                with self.assertRaises(m.InsufficientFunds):
                    w.withdraw("ann", 1)
                with self.assertRaises(m.InsufficientFunds):
                    w.withdraw("bob", 6)
                self.assertEqual(w.store.data, {"ann": 0, "bob": 5})
                for bad in (0, -5, 1.5, "3", None, True):
                    self.assertRaises(ValueError, w.withdraw, "bob", bad)
                with self.assertRaises(KeyError):
                    w.withdraw("nobody", 1)
                self.assertEqual(w.store.data, {"ann": 0, "bob": 5})

            def run_race(self, balance, first, second):
                store = RacyStore({"acct": balance})
                w = m.Wallet(store)
                outcomes = []

                def request(label, amount):
                    try:
                        outcomes.append((label, w.withdraw("acct", amount)))
                    except m.InsufficientFunds:
                        outcomes.append((label, "refused"))

                store.rival = lambda: request("rival", second)
                with time_limit():
                    request("main", first)
                return store, outcomes

            def test_interleaved_requests(self):
                for balance, first, second in [(100, 80, 80), (100, 60, 60), (100, 100, 1), (50, 30, 30)]:
                    store, outcomes = self.run_race(balance, first, second)
                    paid = {"main": first, "rival": second}
                    taken = sum(paid[label] for label, result in outcomes if result != "refused")
                    self.assertEqual(len(outcomes), 2)
                    self.assertGreaterEqual(store.data["acct"], 0, (balance, first, second))
                    self.assertEqual(store.data["acct"], balance - taken, (balance, first, second, outcomes))
                    self.assertLessEqual(taken, balance)
                    if first + second > balance:
                        self.assertEqual(sum(1 for _, r in outcomes if r == "refused"), 1, outcomes)


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

REGISTRY = dd(r'''
    """User registration on top of a shared key-value store."""


    class MemoryStore:
        """The store of the tests. Every call is atomic on its own, but `exists` followed by `put` is not: other requests are served in between. `put_if_absent(key, value)` is the atomic
        check-and-insert: it stores the value and returns True, or returns False when the key is already there."""

        def __init__(self):
            self.data = {}

        def exists(self, key):
            return key in self.data

        def put(self, key, value):
            self.data[key] = value

        def put_if_absent(self, key, value):
            if key in self.data:
                return False
            self.data[key] = value
            return True

        def get(self, key):
            return self.data[key]


    class Registry:
        def __init__(self, store):
            self.store = store

        def register(self, name, email):
            """Create the account `name` (case-insensitive: `Ann` and `ann` are the same name) with the given e-mail. ValueError("name taken") when it exists. Concurrent registrations of the same
            name must produce exactly one account: the loser gets the ValueError and the winner's data stays untouched."""
            key = "user:" + name.lower()
            if self.store.exists(key):
                raise ValueError("name taken")
            self.store.put(key, {"name": name, "email": email})
''')

TO.append(dict(
    slug="duplicate-accounts", d=3, product="the sign-up service", func="Registry.register", cwe="CWE-362",
    finding="`register` asks the store whether the name exists and then inserts it, as two separate calls: two sign-ups for the same name that interleave both pass the check, both insert, and the second silently overwrites the first account's e-mail address, which hands the account (and its password resets) to the second requester.",
    start={"registry.py": REGISTRY, "README.md": readme("sign-up", "`Registry.register` keeps its behaviour (case-insensitive names, `ValueError(\"name taken\")`) but uses the store's atomic `put_if_absent` instead of `exists` + `put`. Of two interleaved registrations of the same name exactly one succeeds and its record is what remains in the store.")},
    solution={"registry.py": patched(REGISTRY, (
        '''            if self.store.exists(key):
                raise ValueError("name taken")
            self.store.put(key, {"name": name, "email": email})
''', '''            if not self.store.put_if_absent(key, {"name": name, "email": email}):
                raise ValueError("name taken")
'''))},
    hidden={"tests/test_registry_security.py": RACE + dd(r'''
        import registry as m


        class RacyStore(m.MemoryStore):
            def __init__(self):
                super().__init__()
                self.rival = None
                self.fired = False

            def _race(self):
                if self.rival and not self.fired:
                    self.fired = True
                    self.rival()

            def put(self, key, value):
                self._race()
                super().put(key, value)

            def put_if_absent(self, key, value):
                self._race()
                return super().put_if_absent(key, value)


        class RegistryTest(unittest.TestCase):
            def test_plain(self):
                r = m.Registry(m.MemoryStore())
                r.register("Ann", "ann@example.com")
                r.register("bob", "bob@example.com")
                for name in ("Ann", "ann", "ANN"):
                    with self.assertRaises(ValueError):
                        r.register(name, "other@example.com")
                self.assertEqual(r.store.get("user:ann"), {"name": "Ann", "email": "ann@example.com"})

            def test_interleaved_registrations(self):
                for first, second in [("ann", "ann"), ("Ann", "ann"), ("ann", "ANN")]:
                    store = RacyStore()
                    r = m.Registry(store)
                    results = []

                    def attempt_register(label, name):
                        try:
                            r.register(name, label + "@example.com")
                            results.append((label, True))
                        except ValueError:
                            results.append((label, False))

                    store.rival = lambda: attempt_register("rival", second)
                    with time_limit():
                        attempt_register("main", first)
                    self.assertEqual(sorted(ok for _, ok in results), [False, True], results)
                    winner = [label for label, ok in results if ok][0]
                    self.assertEqual(store.get("user:ann")["email"], winner + "@example.com")


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

TO_ORDER = ["symlink-swap", "predictable-temp", "chmod-after-write", "lock-file-race", "duplicate-accounts", "double-spend"]
TO.sort(key=lambda s: (s["d"], TO_ORDER.index(s["slug"])))


@family("security-toctou", category="security", lang="python", kind="fix", n=6,
        summary="check-then-use races: symlink swaps, predictable temp files, chmod after write, lock files, read-modify-write on shared stores")
def gen_toctou(rng, n):
    return list(_sec.emit(rng, TO[:n], tags=["race"]))


# =================================================================================================================================
#  uploads
# =================================================================================================================================
UP = []

EXT = dd(r'''
    """Upload filter of the profile page."""

    ALLOWED = {"png", "jpg", "jpeg", "gif", "pdf"}
    EXECUTABLE = {"php", "phtml", "pl", "py", "sh", "exe", "js", "html", "htm", "svg", "cgi", "jsp", "asp", "aspx"}


    def is_allowed_upload(filename):
        """True when an uploaded file name is acceptable: a plain name (no `/` or `\\`, no NUL or other control characters, at most 100 characters) that has a base name and an extension, whose last
        extension (any letter case) is in ALLOWED, with no other extension in EXECUTABLE (`shell.php.png` is refused: some servers run it as PHP), and that does not end in a dot or a space
        (Windows drops those). `.png` alone (no base name) is refused."""
        return filename.lower().split(".")[-1] in ALLOWED
''')

UP.append(dict(
    slug="extension-filter", d=2, product="the profile page upload", func="is_allowed_upload", cwe="CWE-434",
    finding="`is_allowed_upload` only looks at the text after the last dot: `shell.php.png` (executed as PHP by servers that honour any extension), `../../x.png`, `evil.png ` (trailing space dropped on Windows), names with NUL bytes (`x.php\\x00.png`) and absurdly long names all pass the filter.",
    start={"filters.py": EXT, "README.md": readme("upload filter", "`is_allowed_upload(filename)` follows its docstring exactly: `a.png`, `Photo.JPG`, `my.cv.pdf`, `x.tar.png` are accepted; `shell.php.png`, `a.PHP`, `.png`, `a.png.`, `a.png `, `dir/a.png`, `dir\\\\a.png`, `a\\x00.png`, `a.exe`, `a`, `` and names over 100 characters are refused.")},
    solution={"filters.py": patched(EXT, (
        '    return filename.lower().split(".")[-1] in ALLOWED\n', '''    if not isinstance(filename, str) or not filename or len(filename) > 100:
        return False
    if "/" in filename or "\\\\" in filename or any(ord(c) < 32 or ord(c) == 127 for c in filename):
        return False
    if filename.endswith((".", " ")):
        return False
    parts = filename.lower().split(".")
    if len(parts) < 2 or not parts[0]:
        return False
    return parts[-1] in ALLOWED and not (set(parts[1:-1]) & EXECUTABLE)
'''))},
    hidden={"tests/test_filters_security.py": P + dd(r'''
        import filters as m


        class FilterTest(unittest.TestCase):
            def test_accepted(self):
                for name in ["a.png", "Photo.JPG", "my.cv.pdf", "x.tar.png", "scan 01.jpeg", "a.gif", "UPPER.PNG", "x" * 96 + ".png", "php.png", "a.b.c.d.png", "py.pdf"]:
                    self.assertIs(m.is_allowed_upload(name), True, name)

            def test_refused(self):
                for name in ["shell.php.png", "a.PHP", ".png", "a.png.", "a.png ", "dir/a.png", "dir\\a.png", "a\x00.png", "a.exe", "a", "", "x" * 97 + ".png", "a.html.pdf", "a.SVG.png", "x.js.gif",
                             "a.png\n", "a\tb.png", "../../x.png", "a.php5", "a.phtml.jpg", "a.sh.png", "a..", ".", "..", "a.png\x00", "/a.png", "a.jpg/"]:
                    self.assertIs(m.is_allowed_upload(name), False, repr(name))
                for bad in (None, 5, b"a.png"):
                    self.assertIs(m.is_allowed_upload(bad), False, repr(bad))


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

MAGIC = dd(r'''
    """Content checks of the attachment upload."""

    MAX_SIZE = 5 * 1024 * 1024
    TYPES = {"image/png": "png", "image/jpeg": "jpeg", "image/gif": "gif", "application/pdf": "pdf"}
    EXTENSIONS = {"png": "png", "jpg": "jpeg", "jpeg": "jpeg", "gif": "gif", "pdf": "pdf"}


    def accept_upload(filename, content_type, data):
        """Decide whether an upload may be stored; returns its kind (`png`, `jpeg`, `gif` or `pdf`) or raises ValueError. The kind is what the *bytes* say: PNG starts with `\\x89PNG\\r\\n\\x1a\\n`,
        JPEG with `\\xff\\xd8\\xff`, GIF with `GIF87a` or `GIF89a`, PDF with `%PDF-`. The file name's extension (png, jpg, jpeg, gif, pdf, any letter case) and the client-declared content type
        (`image/png`, `image/jpeg`, `image/gif`, `application/pdf`; parameters such as `; charset=...` are ignored, letter case too) must agree with it. Data of 0 bytes or more than MAX_SIZE
        bytes is refused."""
        kind = TYPES.get(content_type)
        if kind is None:
            raise ValueError("unsupported content type")
        return kind
''')

UP.append(dict(
    slug="magic-bytes", d=3, product="the attachment upload", func="accept_upload", cwe="CWE-434",
    finding="`accept_upload` believes the `Content-Type` header the client sent and never looks at the bytes: an HTML page with `Content-Type: image/png` and the name `avatar.png` is stored as an image, and served back to other users where browsers sniff it as HTML (stored XSS).",
    start={"magic.py": MAGIC, "README.md": readme("attachment upload", "`accept_upload(filename, content_type, data)` implements its docstring: the kind comes from the signature of the bytes, and the extension and the declared content type have to agree with it. Examples: PNG bytes + `a.PNG` + `image/png` give `\"png\"`; `a.jpg` and `a.jpeg` both mean JPEG; HTML in a file called `x.png` with type `image/png` is refused, as is a PNG named `x.gif`.")},
    solution={"magic.py": patched(MAGIC, (
        '''    kind = TYPES.get(content_type)
    if kind is None:
        raise ValueError("unsupported content type")
    return kind
''', '''    if not isinstance(data, (bytes, bytearray)) or not 0 < len(data) <= MAX_SIZE:
        raise ValueError("bad size")
    data = bytes(data)
    if data.startswith(b"\\x89PNG\\r\\n\\x1a\\n"):
        kind = "png"
    elif data.startswith(b"\\xff\\xd8\\xff"):
        kind = "jpeg"
    elif data.startswith((b"GIF87a", b"GIF89a")):
        kind = "gif"
    elif data.startswith(b"%PDF-"):
        kind = "pdf"
    else:
        raise ValueError("unrecognised file content")
    declared = TYPES.get(str(content_type).split(";")[0].strip().lower())
    extension = EXTENSIONS.get(str(filename).rsplit(".", 1)[-1].lower()) if "." in str(filename) else None
    if declared != kind or extension != kind:
        raise ValueError("content type or extension do not match the content")
    return kind
'''))},
    hidden={"tests/test_magic_security.py": P + dd(r'''
        import magic as m

        PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 20
        JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 20
        GIF = b"GIF89a" + b"\x00" * 20
        PDF = b"%PDF-1.7\n" + b"x" * 20


        class MagicTest(unittest.TestCase):
            def test_accepted(self):
                self.assertEqual(m.accept_upload("a.PNG", "image/png", PNG), "png")
                self.assertEqual(m.accept_upload("a.jpg", "image/jpeg", JPEG), "jpeg")
                self.assertEqual(m.accept_upload("a.jpeg", "IMAGE/JPEG; q=1", JPEG), "jpeg")
                self.assertEqual(m.accept_upload("anim.gif", "image/gif", GIF), "gif")
                self.assertEqual(m.accept_upload("anim.gif", "image/gif", b"GIF87a" + b"\x00"), "gif")
                self.assertEqual(m.accept_upload("doc.pdf", "application/pdf", PDF), "pdf")
                self.assertEqual(m.accept_upload("a.b.png", "image/png", PNG + b"x" * 1000), "png")
                self.assertEqual(m.accept_upload("a.png", "image/png", bytearray(PNG)), "png")
                self.assertEqual(m.accept_upload("big.png", "image/png", PNG + b"\x00" * (m.MAX_SIZE - len(PNG))), "png")

            def test_refused(self):
                html = b"<html><script>alert(1)</script></html>"
                cases = [("a.png", "image/png", html), ("a.png", "image/png", b""), ("a.png", "image/png", PNG + b"\x00" * m.MAX_SIZE), ("x.gif", "image/png", PNG), ("a.png", "image/gif", PNG),
                         ("a.png", "text/html", PNG), ("a.png", "", PNG), ("a.png", None, PNG), ("a.html", "image/png", PNG), ("a", "image/png", PNG), ("a.png", "image/png", JPEG), ("a.pdf", "application/pdf", PNG),
                         ("a.jpg", "image/png", JPEG), ("a.png", "image/png", b"GIF89a"[:5]), ("a.png", "image/png", b"  " + PNG), ("a.svg", "image/svg+xml", b"<svg onload=alert(1)>"), ("a.png", "image/png", "text"),
                         ("a.png", "image/png", b"%PDF-1.4"), ("a.pdf", "application/pdf", b"<!DOCTYPE html>")]
                for filename, ctype, data in cases:
                    self.assertIsNone(attempt(m.accept_upload, filename, ctype, data), (filename, ctype, data[:12] if isinstance(data, bytes) else data))
                    self.assertRaises(ValueError, m.accept_upload, filename, ctype, data)


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

STORED = dd(r'''
    """Storage of uploaded files."""
    import os


    def store_upload(directory, original_name, data):
        """Save the bytes `data` of an upload inside `directory` and describe the result: `{"id": <32 lower-case hex characters, random>, "path": <path of the stored file>, "original": original_name}`.
        The stored file is named `<id><ext>` where ext is the lower-case extension of the original name including the dot (the part after the last dot, when something other than a dot comes
        before that dot), but only when it is 1 to 8 ASCII letters or digits long (otherwise there is no extension). The original name is only reported back, it never influences where or under which name the file is written: names with directory parts, `..`, absolute paths or backslashes
        stay inside `directory`, and two uploads with the same name never overwrite each other."""
        path = os.path.join(directory, original_name)
        with open(path, "wb") as fh:
            fh.write(data)
        return {"id": original_name, "path": path, "original": original_name}
''')

UP.append(dict(
    slug="stored-filename", d=3, product="the upload storage", func="store_upload", cwe="CWE-73",
    finding="`store_upload` writes the file under the name the client chose: `../../app/config.py` escapes the upload directory, `/etc/cron.d/x` goes wherever the process may write, and two users uploading `report.pdf` overwrite each other's file.",
    start={"storage.py": STORED, "README.md": readme("upload storage", "`store_upload(directory, original_name, data)` returns `{\"id\", \"path\", \"original\"}` as described: a random 128-bit hex id, the file `<id><ext>` created exclusively inside `directory`, the client's name only echoed back. Extensions are kept only if they are 1-8 ASCII letters or digits (lower-cased) and not just a leading dot (`.bashrc` has none).")},
    solution={"storage.py": patched(STORED, ('"""Storage of uploaded files."""\nimport os\n', '"""Storage of uploaded files."""\nimport os\nimport re\nimport secrets\n'), (
        '''    path = os.path.join(directory, original_name)
    with open(path, "wb") as fh:
        fh.write(data)
    return {"id": original_name, "path": path, "original": original_name}
''', '''    match = re.search(r"[^.]\\.([A-Za-z0-9]{1,8})\\Z", original_name)
    ext = "." + match.group(1).lower() if match else ""
    while True:
        upload_id = secrets.token_hex(16)
        path = os.path.join(directory, upload_id + ext)
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            continue
        break
    with os.fdopen(fd, "wb") as fh:
        fh.write(data)
    return {"id": upload_id, "path": path, "original": original_name}
'''))},
    hidden={"tests/test_storage_security.py": P + dd(r'''
        import re

        import storage as m


        def tree(root):
            return sorted(os.path.relpath(os.path.join(d, f), root) for d, _, files in os.walk(root) for f in files)


        class StorageTest(unittest.TestCase):
            def setUp(self):
                self.root = tmpdir()
                self.addCleanup(shutil.rmtree, self.root, True)
                self.dir = os.path.join(self.root, "uploads", "store")
                os.makedirs(self.dir)

            def test_names_and_contents(self):
                a = m.store_upload(self.dir, "Report.PDF", b"one")
                b = m.store_upload(self.dir, "Report.PDF", b"two")
                self.assertNotEqual(a["id"], b["id"])
                for r, data in ((a, b"one"), (b, b"two")):
                    self.assertRegex(r["id"], r"^[0-9a-f]{32}$")
                    self.assertEqual(r["original"], "Report.PDF")
                    self.assertEqual(r["path"], os.path.join(self.dir, r["id"] + ".pdf"))
                    self.assertEqual(read(r["path"]), data)
                for name, ext in [("noext", ""), ("a.tar.gz", ".gz"), ("x.toolongextension", ""), ("x.", ""), ("x.p-g", ""), ("x.PnG", ".png"), (".bashrc", ""), ("a.é", "")]:
                    r = m.store_upload(self.dir, name, b"d")
                    self.assertEqual(os.path.basename(r["path"]), r["id"] + ext, (name, r))
                    self.assertEqual(os.path.dirname(r["path"]), self.dir)

            def test_hostile_names_stay_inside(self):
                before = tree(self.root)
                names = ["../../escape.txt", os.path.join(self.root, "absolute-escape.txt"), "a/b/c.png", "..\\..\\win.txt", "../x", "..", ".", "", "sub/dir/", "/", "a\x00b.png", "x" * 300 + ".png", "..%2f..%2fx", "uploads/store/../../../outside.png"]
                results = [attempt(m.store_upload, self.dir, n, b"payload") for n in names]
                after = tree(self.root)
                new = [f for f in after if f not in before]
                for f in new:
                    self.assertEqual(os.path.dirname(f), os.path.join("uploads", "store"), f)
                    self.assertRegex(os.path.basename(f), r"^[0-9a-f]{32}(\.[a-z0-9]{1,8})?$")
                for r in results:
                    if r:
                        self.assertEqual(os.path.dirname(r["path"]), self.dir)
                self.assertFalse(os.path.exists(os.path.join(self.root, "escape.txt")))
                self.assertFalse(os.path.exists(os.path.join(self.root, "absolute-escape.txt")))
                self.assertFalse(os.path.exists(os.path.join(self.root, "outside.png")))
                self.assertFalse(os.path.exists(os.path.join(self.root, "uploads", "escape.txt")))


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

SERVE = dd(r'''
    """Download endpoint of the file locker."""


    def download_headers(filename, content_type):
        """Response headers (a dict) for serving a stored upload.

        * `Content-Type`: the lower-cased `content_type` without parameters when it is one of image/png, image/jpeg, image/gif, application/pdf or text/plain; anything else (html, svg, javascript,
          unknown) is served as `application/octet-stream`.
        * `X-Content-Type-Options: nosniff` and `Content-Security-Policy: sandbox; default-src 'none'` are always present.
        * `Content-Disposition`: `inline` for image/png, image/jpeg and image/gif, `attachment` for everything else, followed by `; filename="NAME"` where NAME is `filename` with every character that
          is not a letter, digit, space, `.`, `_`, `-`, `(` or `)` replaced by `_` (one `_` per character).
        Exactly these four headers, with exactly these names."""
        return {"Content-Type": content_type, "Content-Disposition": 'inline; filename="%s"' % filename}
''')

UP.append(dict(
    slug="serve-headers", d=3, product="the file locker downloads", func="download_headers", cwe="CWE-79",
    finding="`download_headers` serves every stored upload inline with the content type the uploader declared: a user uploads `profile.html` (or an SVG) as `text/html`, shares the link, and the script runs in the application's origin (stored XSS); the file name goes unescaped into the header as well.",
    start={"serving.py": SERVE, "README.md": readme("downloads", "`download_headers(filename, content_type)` returns exactly the four headers described in its docstring (names `Content-Type`, `X-Content-Type-Options`, `Content-Security-Policy`, `Content-Disposition`). Examples: `(\"cat.PNG\", \"IMAGE/PNG; x=1\")` gives type `image/png` and `inline; filename=\"cat.PNG\"`; `(\"page.html\", \"text/html\")` gives `application/octet-stream` and `attachment; filename=\"page.html\"`.")},
    solution={"serving.py": patched(SERVE, ('"""Download endpoint of the file locker."""\n', '"""Download endpoint of the file locker."""\nimport re\n\nSAFE_TYPES = {"image/png", "image/jpeg", "image/gif", "application/pdf", "text/plain"}\nINLINE = {"image/png", "image/jpeg", "image/gif"}\n'), (
        '    return {"Content-Type": content_type, "Content-Disposition": \'inline; filename="%s"\' % filename}\n', '''    declared = str(content_type).split(";")[0].strip().lower()
    served = declared if declared in SAFE_TYPES else "application/octet-stream"
    disposition = "inline" if served in INLINE else "attachment"
    name = re.sub(r"[^A-Za-z0-9 ._()-]", "_", str(filename))
    return {"Content-Type": served, "X-Content-Type-Options": "nosniff", "Content-Security-Policy": "sandbox; default-src 'none'",
            "Content-Disposition": '%s; filename="%s"' % (disposition, name)}
'''))},
    hidden={"tests/test_serving_security.py": P + dd(r'''
        import serving as m

        CSP = "sandbox; default-src 'none'"


        def expect(ctype, disposition, name):
            return {"Content-Type": ctype, "X-Content-Type-Options": "nosniff", "Content-Security-Policy": CSP, "Content-Disposition": '%s; filename="%s"' % (disposition, name)}


        class ServingTest(unittest.TestCase):
            def test_safe_types(self):
                self.assertEqual(m.download_headers("cat.PNG", "IMAGE/PNG; x=1"), expect("image/png", "inline", "cat.PNG"))
                self.assertEqual(m.download_headers("a.jpg", "image/jpeg"), expect("image/jpeg", "inline", "a.jpg"))
                self.assertEqual(m.download_headers("a.gif", " image/gif "), expect("image/gif", "inline", "a.gif"))
                self.assertEqual(m.download_headers("doc (1).pdf", "application/pdf"), expect("application/pdf", "attachment", "doc (1).pdf"))
                self.assertEqual(m.download_headers("notes.txt", "text/plain; charset=utf-8"), expect("text/plain", "attachment", "notes.txt"))

            def test_everything_else_is_a_download(self):
                for ctype in ["text/html", "text/html; charset=utf-8", "image/svg+xml", "application/javascript", "application/xhtml+xml", "", "unknown/type", "IMAGE/SVG+XML", "text/xml", None, "image/png2"]:
                    self.assertEqual(m.download_headers("page.html", ctype), expect("application/octet-stream", "attachment", "page.html"), ctype)

            def test_file_names_cannot_break_the_header(self):
                for name, safe in [('a"b.png', "a_b.png"), ("x\r\nSet-Cookie: a=b", "x__Set-Cookie_ a_b"), ("café;x.png", "caf_ _x.png".replace(" ", "")), ("a\\b.png", "a_b.png"), ("päth/x.png", "p_th_x.png")]:
                    got = m.download_headers(name, "image/png")
                    self.assertEqual(got["Content-Disposition"], 'inline; filename="%s"' % safe, name)
                    for value in got.values():
                        self.assertNotIn("\r", value)
                        self.assertNotIn("\n", value)
                self.assertEqual(set(m.download_headers("a", "image/png")), {"Content-Type", "X-Content-Type-Options", "Content-Security-Policy", "Content-Disposition"})


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

UP_ORDER = ["extension-filter", "magic-bytes", "stored-filename", "serve-headers"]
UP.sort(key=lambda s: (s["d"], UP_ORDER.index(s["slug"])))


@family("security-uploads", category="security", lang="python", kind="fix", n=4,
        summary="upload handling: extension tricks, content sniffing, server-chosen names, safe download headers")
def gen_uploads(rng, n):
    return list(_sec.emit(rng, UP[:n], tags=["uploads"]))


# =================================================================================================================================
#  log injection
# =================================================================================================================================
LG = []

LOGT = P + dd(r'''
    import io
    import json
    import logging


    class Capture(logging.Handler):
        """Collects the messages of the records it receives."""

        def __init__(self):
            super().__init__(logging.DEBUG)
            self.messages = []
            self.records = []

        def emit(self, record):
            self.records.append(record)
            self.messages.append(record.getMessage())


    def make_logger(name):
        logger = logging.getLogger(name)
        logger.handlers[:] = []
        logger.setLevel(logging.DEBUG)
        logger.propagate = False
        handler = Capture()
        logger.addHandler(handler)
        return logger, handler


''')

LOGIN_LOG = dd(r'''
    """Audit logging of the login form."""


    def log_login_failure(logger, username, ip):
        """Log the WARNING `login failed for user <username> from <ip>`. Both values come from the request: every control character in them is written as an escape so that nobody can forge or split log
        lines: `\\n`, `\\r` and `\\t` become the two characters backslash + `n`, `r` or `t`; every other character with a code below 32, or from 127 to 159, becomes `\\xNN` (two lower-case hex digits);
        U+2028 and U+2029 become `\u2028` and `\u2029`. Everything else, including spaces, quotes, backslashes and non-ASCII letters, stays as it is."""
        logger.warning("login failed for user %s from %s", username, ip)
''')

LG.append(dict(
    slug="forged-log-lines", d=1, product="the login audit log", func="log_login_failure", cwe="CWE-117",
    finding="`log_login_failure` writes the submitted user name into the log line as typed: a user name like `admin from 10.0.0.5\\nINFO login succeeded for user admin from 10.0.0.5` forges a second log entry that the security team (and the log-based alerting) will believe.",
    start={"auditlog.py": LOGIN_LOG, "README.md": readme("audit log", "`log_login_failure(logger, username, ip)` logs exactly `login failed for user <username> from <ip>` with the control-character escaping of its docstring applied to both values, so that every call produces one single line. Normal values - ordinary names, spaces, quotes, backslashes, accented and CJK letters - are logged unchanged.")},
    solution={"auditlog.py": patched(LOGIN_LOG, ('"""Audit logging of the login form."""\n', '''"""Audit logging of the login form."""

SHORT = {"\\n": "\\\\n", "\\r": "\\\\r", "\\t": "\\\\t"}


def clean(value):
    out = []
    for ch in str(value):
        code = ord(ch)
        if ch in SHORT:
            out.append(SHORT[ch])
        elif code < 32 or 127 <= code <= 159:
            out.append("\\\\x%02x" % code)
        elif code in (0x2028, 0x2029):
            out.append("\\\\u%04x" % code)
        else:
            out.append(ch)
    return "".join(out)
'''), ('logger.warning("login failed for user %s from %s", username, ip)', 'logger.warning("login failed for user %s from %s", clean(username), clean(ip))'))},
    hidden={"tests/test_auditlog_security.py": LOGT + dd(r'''
        import auditlog as m


        class AuditLogTest(unittest.TestCase):
            def setUp(self):
                self.logger, self.h = make_logger("audit-test")

            def test_normal_values(self):
                for name in ["ann", "Ann O'Neil", 'say "hi"', "back\\slash", "émile 中文", "a b  c", "50% = ok", ""]:
                    m.log_login_failure(self.logger, name, "10.0.0.1")
                    self.assertEqual(self.h.messages[-1], "login failed for user %s from 10.0.0.1" % name)
                self.assertEqual(self.h.records[-1].levelname, "WARNING")

            def test_forged_lines(self):
                cases = [("admin\nINFO login succeeded for user admin", "admin\\nINFO login succeeded for user admin"), ("a\r\nb", "a\\r\\nb"), ("tab\there", "tab\\there"), ("esc\x1b[31mred", "esc\\x1b[31mred"),
                         ("nul\x00x", "nul\\x00x"), ("bell\x07", "bell\\x07"), ("del\x7f", "del\\x7f"), ("c1\x85next", "c1\\x85next"), ("ls\u2028ps\u2029end", "ls\\u2028ps\\u2029end"), ("\n\n", "\\n\\n")]
                for raw, escaped in cases:
                    m.log_login_failure(self.logger, raw, "1.2.3.4")
                    msg = self.h.messages[-1]
                    self.assertEqual(msg, "login failed for user %s from 1.2.3.4" % escaped)
                    self.assertEqual(len(msg.splitlines()), 1)
                m.log_login_failure(self.logger, "ann", "1.2.3.4\nINFO forged")
                self.assertEqual(self.h.messages[-1], "login failed for user ann from 1.2.3.4\\nINFO forged")


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

PWLOG = dd(r'''
    """Login handler of the shop."""


    def handle_login(form, logger, authenticate):
        """Handle a posted login `form` (a dict with at least `user` and `password`, possibly more fields such as a CSRF token): returns `authenticate(user, password)`.
        Logs exactly one INFO message per attempt: `login attempt for <user>: success` or `login attempt for <user>: failure`. If `authenticate` raises, an ERROR message
        `login error for <user>` is logged (without exc_info) and the exception propagates. No message, argument or traceback may contain the password or any other field of the form."""
        logger.info("login attempt: %s", form)
        result = authenticate(form["user"], form["password"])
        return result
''')

LG.append(dict(
    slug="password-in-log", d=2, product="the shop login", func="handle_login", cwe="CWE-532",
    finding="`handle_login` logs the whole submitted form with `logger.info(\"login attempt: %s\", form)`: every password (and CSRF token, and mistyped password of a real user) lands in the application log, the log shipper and the support team's search tool.",
    start={"login.py": PWLOG, "README.md": readme("login handler", "`handle_login(form, logger, authenticate)` returns the result of `authenticate` and logs exactly the messages of its docstring: user name and outcome only, nothing from the rest of the form, nothing from exceptions raised by `authenticate`.")},
    solution={"login.py": patched(PWLOG, (
        '''    logger.info("login attempt: %s", form)
    result = authenticate(form["user"], form["password"])
    return result
''', '''    user = form["user"]
    try:
        result = authenticate(user, form["password"])
    except Exception:
        logger.error("login error for %s", user)
        raise
    logger.info("login attempt for %s: %s", user, "success" if result else "failure")
    return result
'''))},
    hidden={"tests/test_login_security.py": LOGT + dd(r'''
        import login as m


        class LoginLogTest(unittest.TestCase):
            def setUp(self):
                self.logger, self.h = make_logger("login-test")

            def test_messages(self):
                form = {"user": "ann", "password": "hunter2-very-secret", "csrf_token": "tok-123-abc", "remember": "1"}
                self.assertIs(m.handle_login(form, self.logger, lambda u, p: True), True)
                self.assertIs(m.handle_login(form, self.logger, lambda u, p: False), False)
                self.assertEqual(self.h.messages, ["login attempt for ann: success", "login attempt for ann: failure"])
                self.assertEqual([r.levelname for r in self.h.records], ["INFO", "INFO"])

            def test_nothing_secret_is_logged(self):
                form = {"user": "bob", "password": "S3cr3t!pass", "csrf_token": "tok-999", "card": "4111111111111111"}

                def boom(u, p):
                    raise RuntimeError("backend failed for password " + p)

                with self.assertRaises(RuntimeError):
                    m.handle_login(form, self.logger, boom)
                m.handle_login(form, self.logger, lambda u, p: p == "S3cr3t!pass")
                self.assertEqual(self.h.messages, ["login error for bob", "login attempt for bob: success"])
                self.assertEqual([r.levelname for r in self.h.records], ["ERROR", "INFO"])
                blob = repr([(r.msg, r.args, r.exc_info, r.exc_text, r.getMessage()) for r in self.h.records])
                for secret in ("S3cr3t!pass", "tok-999", "4111111111111111"):
                    self.assertNotIn(secret, blob)
                self.assertTrue(all(r.exc_info is None for r in self.h.records))


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

JSONLOG = dd(r'''
    """Structured (JSON lines) logging."""


    def log_event(stream, level, message, **fields):
        """Write one JSON object per line to `stream` (a text stream): the object has the keys `level`, `message` and the extra fields (their values must be JSON-compatible), is serialised with
        `json.dumps(record, sort_keys=True)` and followed by a single `\n`. Whatever the values contain, a call writes exactly one line,
        the line is valid JSON, and the record read back has exactly the keys and values that were given."""
        extras = "".join(', "%s": "%s"' % (k, v) for k, v in fields.items())
        stream.write('{"level": "%s", "message": "%s"%s}\n' % (level, message, extras))
''')

LG.append(dict(
    slug="json-log-forging", d=2, product="the structured logger", func="log_event", cwe="CWE-117",
    finding="`log_event` builds the JSON line with string formatting: a message such as `x\", \"level\": \"debug` (or one containing a newline, a backslash or a quote) changes the fields of the record, injects whole fake entries, or produces invalid JSON that the log pipeline drops - including the entries around it.",
    start={"jsonlog.py": JSONLOG, "README.md": readme("structured logging", "`log_event(stream, level, message, **fields)` writes the record serialised by `json.dumps(record, sort_keys=True)` plus `\\n` (so `{\"level\": \"info\", \"message\": \"hi\", \"user\": \"ann\"}` for `log_event(s, \"info\", \"hi\", user=\"ann\")`); values that are not JSON-compatible raise `TypeError`, and nothing is written for refused calls.")},
    solution={"jsonlog.py": patched(JSONLOG, ('"""Structured (JSON lines) logging."""\n', '"""Structured (JSON lines) logging."""\nimport json\n'), (
        '''    extras = "".join(', "%s": "%s"' % (k, v) for k, v in fields.items())
    stream.write('{"level": "%s", "message": "%s"%s}\\n' % (level, message, extras))
''', '''    line = json.dumps(dict(fields, level=level, message=message), sort_keys=True)
    stream.write(line + "\\n")
'''))},
    hidden={"tests/test_jsonlog_security.py": LOGT + dd(r'''
        import jsonlog as m


        def emit(*args, **fields):
            s = io.StringIO()
            m.log_event(s, *args, **fields)
            return s.getvalue()


        class JsonLogTest(unittest.TestCase):
            def test_format(self):
                self.assertEqual(emit("info", "hi", user="ann"), '{"level": "info", "message": "hi", "user": "ann"}\n')
                self.assertEqual(emit("warn", "x", n=3, ok=True, tags=["a", None], nested={"k": 1.5}), '{"level": "warn", "message": "x", "n": 3, "nested": {"k": 1.5}, "ok": true, "tags": ["a", null]}\n')
                self.assertEqual(emit("info", "café"), json.dumps({"level": "info", "message": "café"}, sort_keys=True) + "\n")

            def test_hostile_values(self):
                hostile = ['x", "level": "debug', "line1\nline2", 'quote " and back\\slash', "}\n{\"level\": \"error\", \"message\": \"forged\"}", "\r\n", "tab\t", "\u2028", "\x00", '", "admin": true, "x": "']
                for value in hostile:
                    line = emit("info", value, user=value, other="plain")
                    self.assertTrue(line.endswith("\n"))
                    self.assertEqual(line.count("\n"), 1, repr(line))
                    self.assertEqual(json.loads(line), {"level": "info", "message": value, "user": value, "other": "plain"})
                    self.assertEqual(json.loads(emit(value, "m")), {"level": value, "message": "m"})

            def test_refusals(self):
                s = io.StringIO()
                with self.assertRaises(TypeError):
                    m.log_event(s, "info", "m", bad=object())
                self.assertEqual(s.getvalue(), "")


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

KV = dd(r'''
    """Audit trail lines."""


    def format_event(fields):
        """One audit line for the dict `fields`: `key="value" key="value" ...` in the dict's order, separated by single spaces. Keys must match `[a-z][a-z0-9_]*` (ValueError otherwise). Every value is
        turned into a string with `str()` and written as a JSON string literal (`json.dumps(text)`: quotes and backslashes escaped, newlines as `\\n`, non-ASCII as `\\uXXXX`), so values can never
        add, split or hide fields and the line never contains a raw line break. A line can be parsed back unambiguously."""
        return " ".join("%s=%s" % (key, value) for key, value in fields.items())
''')

LG.append(dict(
    slug="audit-key-value", d=3, product="the audit trail", func="format_event", cwe="CWE-117",
    finding="`format_event` joins `key=value` pairs without quoting: an action such as `delete user=admin role=root` (typed into a free-text field) adds fields to the entry, a value with a newline writes a second, forged entry, and values with spaces make the line impossible to parse reliably.",
    start={"audit.py": KV, "README.md": readme("audit trail", "`format_event(fields)` follows its docstring exactly. Example: `{\"user\": \"ann\", \"action\": \"delete user=admin\"}` becomes `user=\"ann\" action=\"delete user=admin\"`; values are `str()`-ed first (`{\"n\": 5}` gives `n=\"5\"`, `None` gives `\"None\"`).")},
    solution={"audit.py": patched(KV, ('"""Audit trail lines."""\n', '"""Audit trail lines."""\nimport json\nimport re\n'), (
        '    return " ".join("%s=%s" % (key, value) for key, value in fields.items())\n', '''    parts = []
    for key, value in fields.items():
        if not isinstance(key, str) or not re.fullmatch(r"[a-z][a-z0-9_]*", key):
            raise ValueError("bad field name %r" % (key,))
        parts.append("%s=%s" % (key, json.dumps(str(value))))
    return " ".join(parts)
'''))},
    hidden={"tests/test_audit_security.py": P + dd(r'''
        import json
        import re

        import audit as m

        PAIR = re.compile(r'([a-z][a-z0-9_]*)=("(?:[^"\\]|\\.)*")(?: |$)')


        def parse(line):
            """The (key, value) pairs of a line, or None when the line is not made of pairs only."""
            pos, out = 0, []
            while pos < len(line):
                match = PAIR.match(line, pos)
                if not match:
                    return None
                out.append((match.group(1), json.loads(match.group(2))))
                pos = match.end()
            return out


        class AuditTest(unittest.TestCase):
            def test_examples(self):
                self.assertEqual(m.format_event({"user": "ann", "action": "delete user=admin"}), 'user="ann" action="delete user=admin"')
                self.assertEqual(m.format_event({"n": 5, "none": None, "ok": True}), 'n="5" none="None" ok="True"')
                self.assertEqual(m.format_event({}), "")
                self.assertEqual(m.format_event({"k": 'a"b\\c\nd é'}), 'k="a\\"b\\\\c\\nd \\u00e9"')

            def test_values_cannot_change_the_structure(self):
                hostile = ['x" role="root', "x\nuser=\"admin\" action=\"forged\"", "a b=c", "\\", '"', "\r\n", "trailing\\", "", "\u2028 \u0085", 'x" ', " role=root"]
                for value in hostile:
                    line = m.format_event({"user": "ann", "action": value, "ip": "10.0.0.1"})
                    self.assertNotIn("\n", line)
                    self.assertNotIn("\r", line)
                    self.assertEqual(parse(line), [("user", "ann"), ("action", value), ("ip", "10.0.0.1")], repr(value))

            def test_bad_keys(self):
                for key in ["User", "a b", "a=b", "1a", "", "a-b", "é", "a\nb", 'a"b', "role=root user"]:
                    self.assertIsNone(attempt(m.format_event, {key: "v"}), repr(key))
                    self.assertRaises(ValueError, m.format_event, {"ok": "v", key: "v"})


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

FLOOD = dd(r'''
    """Access logging."""


    def describe_request(method, path, user_agent):
        """The access-log line for a request: `<method> <path> ua=<user_agent>`. Path and user agent come from the client: each of the two is shortened to its first 200 characters followed by
        `...(+N chars)` (N = number of characters cut off) when it is longer than 200, and control characters in it are written as escapes (`\n`, `\r`, `\t` as backslash + letter, every other
        character below 32 or equal to 127 as `\\xNN` with two lower-case hex digits) - after shortening. `method` is one of GET, POST, PUT, DELETE, HEAD, OPTIONS, PATCH, otherwise ValueError."""
        return "%s %s ua=%s" % (method, path, user_agent)
''')

LG.append(dict(
    slug="log-flooding", d=3, product="the access log", func="describe_request", cwe="CWE-400",
    finding="`describe_request` writes the request path and user agent unbounded and unescaped: one request with a 5 MB path fills the log disk (and every downstream indexer), and control characters in the user agent split lines or paint terminal escape sequences into an admin's `tail -f`.",
    start={"accesslog.py": FLOOD, "README.md": readme("access log", "`describe_request(method, path, user_agent)` follows its docstring: values up to 200 characters pass unchanged (apart from escaping), longer ones are cut to 200 characters plus `...(+N chars)`; escaping applies to what is left after cutting. Unknown methods raise `ValueError`.")},
    solution={"accesslog.py": patched(FLOOD, ('"""Access logging."""\n', '''"""Access logging."""

METHODS = {"GET", "POST", "PUT", "DELETE", "HEAD", "OPTIONS", "PATCH"}
SHORT = {"\\n": "\\\\n", "\\r": "\\\\r", "\\t": "\\\\t"}


def _clean(value, limit=200):
    value = str(value)
    suffix = ""
    if len(value) > limit:
        suffix = "...(+%d chars)" % (len(value) - limit)
        value = value[:limit]
    out = []
    for ch in value:
        if ch in SHORT:
            out.append(SHORT[ch])
        elif ord(ch) < 32 or ord(ch) == 127:
            out.append("\\\\x%02x" % ord(ch))
        else:
            out.append(ch)
    return "".join(out) + suffix
'''), ('    return "%s %s ua=%s" % (method, path, user_agent)\n', '''    if method not in METHODS:
        raise ValueError("unknown method")
    return "%s %s ua=%s" % (method, _clean(path), _clean(user_agent))
'''))},
    hidden={"tests/test_accesslog_security.py": P + dd(r'''
        import accesslog as m


        class AccessLogTest(unittest.TestCase):
            def test_normal(self):
                self.assertEqual(m.describe_request("GET", "/index.html?a=1&b=2", "Mozilla/5.0 (X11; Linux)"), "GET /index.html?a=1&b=2 ua=Mozilla/5.0 (X11; Linux)")
                self.assertEqual(m.describe_request("POST", "/é/中", "agent \"quoted\" back\\slash"), 'POST /é/中 ua=agent "quoted" back\\slash')
                self.assertEqual(m.describe_request("DELETE", "/x" * 100, "u" * 200), "DELETE " + "/x" * 100 + " ua=" + "u" * 200)
                self.assertEqual(m.describe_request("GET", "/", ""), "GET / ua=")

            def test_long_values_are_cut(self):
                self.assertEqual(m.describe_request("GET", "/" + "a" * 1000, "ua"), "GET /" + "a" * 199 + "...(+801 chars) ua=ua")
                self.assertEqual(m.describe_request("GET", "/", "u" * 201), "GET / ua=" + "u" * 200 + "...(+1 chars)")
                big = m.describe_request("GET", "/" + "p" * 5_000_000, "x" * 3_000_000)
                self.assertLess(len(big), 500)
                self.assertTrue(big.startswith("GET /ppp"))
                self.assertIn("...(+4999801 chars)", big)
                self.assertTrue(big.endswith("...(+2999800 chars)"))

            def test_control_characters(self):
                self.assertEqual(m.describe_request("GET", "/a\r\nGET /forged", "x\ty\x1b[31m\x7f\x00"), "GET /a\\r\\nGET /forged ua=x\\ty\\x1b[31m\\x7f\\x00")
                line = m.describe_request("PUT", "/" + "\n" * 300, "\r" * 300)
                self.assertNotIn("\n", line)
                self.assertNotIn("\r", line)
                self.assertEqual(line, "PUT /" + "\\n" * 199 + "...(+101 chars) ua=" + "\\r" * 200 + "...(+100 chars)")

            def test_methods(self):
                for method in ["GET", "POST", "PUT", "DELETE", "HEAD", "OPTIONS", "PATCH"]:
                    self.assertTrue(m.describe_request(method, "/", "u").startswith(method + " /"))
                for method in ["get", "TRACE", "GET /x HTTP/1.1\r\nHost: evil", "", None, "CONNECT"]:
                    self.assertIsNone(attempt(m.describe_request, method, "/", "u"), repr(method))


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

LG_ORDER = ["forged-log-lines", "password-in-log", "json-log-forging", "audit-key-value", "log-flooding"]
LG.sort(key=lambda s: (s["d"], LG_ORDER.index(s["slug"])))


@family("security-log-injection", category="security", lang="python", kind="fix", n=5,
        summary="log forging and leakage: control characters, passwords in logs, JSON and key=value injection, unbounded values")
def gen_logs(rng, n):
    return list(_sec.emit(rng, LG[:n], tags=["logging"]))

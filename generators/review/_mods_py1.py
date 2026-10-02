"""Slot modules (python), part 1."""
from fx import dd

from ._slots import Bad, Module, Slot

# ---------------------------------------------------------------------------------------------------------------------
# parcel locker bank
# ---------------------------------------------------------------------------------------------------------------------

LOCKERS_TEMPLATE = dd('''
    """Parcel locker bank: assigns parcels to compartments, issues pickup codes and releases them."""
    import csv
    import hashlib
    import hmac
    import logging
    import sqlite3

    log = logging.getLogger("lockers")

    SIZE_RANK = {"S": 1, "M": 2, "L": 3}
    HOLD_SECONDS = 72 * 3600


    class LockerError(Exception):
        """Base class for locker failures."""


    class NoFreeCompartment(LockerError):
        """No free compartment is large enough for the parcel."""


    class BadCode(LockerError):
        """The pickup code does not match."""


    @@validate@@


    class Bank:
        def __init__(self, compartments, secret):
            self.sizes = dict(compartments)  # compartment id -> size letter
            self.secret = secret  # bytes
            self.parcels = {}  # compartment id -> {"ref", "size", "since"}
            self.audit = sqlite3.connect(":memory:")
            self.audit.execute("CREATE TABLE audit (ts INTEGER, event TEXT, comp TEXT, ref TEXT)")

        @@pick@@

        @@code@@

        @@verify@@

        @@store@@

        @@release@@

        @@expire@@

        @@audit@@

        @@history@@

        @@export@@

        @@free@@
''')

_VALIDATE_GOOD = dd('''
    def validate_parcel(ref, size):
        """Parcel references are 1-16 letters or digits; the size must be S, M or L."""
        if not isinstance(ref, str) or not 1 <= len(ref) <= 16 or not ref.isalnum():
            raise ValueError(f"bad parcel reference: {ref!r}")
        if size not in SIZE_RANK:
            raise ValueError(f"unknown size: {size!r}")
''')

_PICK_GOOD = dd('''
    def pick_compartment(self, size):
        """The smallest free compartment that fits the parcel; ties go to the lowest id."""
        need = SIZE_RANK[size]
        best = None
        for comp, sz in sorted(self.sizes.items()):
            if comp in self.parcels or SIZE_RANK[sz] < need:
                continue
            if best is None or SIZE_RANK[sz] < SIZE_RANK[self.sizes[best]]:
                best = comp
        if best is None:
            raise NoFreeCompartment(size)
        return best
''')

_EXPIRE_GOOD = dd('''
    def expire_overdue(self, now):
        """References of parcels held for more than HOLD_SECONDS, returned to sender; their compartments are freed."""
        expired = [c for c, p in self.parcels.items() if now - p["since"] > HOLD_SECONDS]
        refs = []
        for comp in sorted(expired):
            refs.append(self.parcels.pop(comp)["ref"])
            self._audit(now, "expire", comp, refs[-1])
        return refs
''')

_RELEASE_GOOD = dd('''
    def release(self, comp, code, now):
        if not self.verify_code(comp, code):
            self._audit(now, "bad-code", comp, "")
            raise BadCode(comp)
        parcel = self.parcels.pop(comp)
        self._audit(now, "release", comp, parcel["ref"])
        log.info("released %s from %s", parcel["ref"], comp)
        return parcel["ref"]
''')

_EXPORT_GOOD = dd('''
    def export_audit(self, path):
        """Write the whole audit trail to a CSV file; returns the number of rows."""
        rows = self.audit.execute("SELECT ts, event, comp, ref FROM audit ORDER BY rowid").fetchall()
        with open(path, "w", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(["ts", "event", "comp", "ref"])
            writer.writerows(rows)
        return len(rows)
''')

LOCKERS = Module(
    name="py-lockers", lang="python", path="lockers/bank.py", difficulty=3,
    title="Locker bank: best-fit compartments, hold expiry and audit trail",
    blurb="The `lockers` package runs the parcel locker banks of a courier network.",
    intro=dd('''
        Until now a parcel only went into a compartment of exactly its own size, which left L compartments empty while
        S parcels were turned away. This change reworks how parcels are placed and tracked:
    '''),
    outro=dd('''
        Tested by hand against the staging bank. Compartment ids come straight from the touchscreen, parcel references from
        the barcode scanner.
    '''),
    template=LOCKERS_TEMPLATE,
    ctx={
        "README.md": dd('''
            # lockers

            Back-end logic of the parcel locker banks. `lockers/bank.py` holds the `Bank` class; the kiosk software calls
            `store()` when a courier scans a parcel and `release()` when a customer types their pickup code.
        '''),
        "lockers/__init__.py": '"""Parcel lockers."""\n',
    },
    scenario_path="scenario.py",
    scenario=dd('''
        import logging
        import os
        import sys

        from lockers.bank import Bank, LockerError

        logging.basicConfig(stream=sys.stdout, level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
        T0 = 1_700_000_000
        H = 3600


        def attempt(label, fn, *args):
            try:
                out = fn(*args)
            except (LockerError, ValueError) as exc:
                print(f"{label}: refused ({type(exc).__name__}: {exc})")
                return None
            print(f"{label}: ok {out if not isinstance(out, tuple) else out[0]}")
            return out


        bank = Bank({"B2": "M", "A1": "S", "C3": "L", "A2": "S"}, secret=b"k3y")
        codes = {}
        for ref, size, t in [("P1", "S", T0), ("P2", "S", T0), ("P3", "S", T0 + H), ("P4", "M", T0 + 2 * H), ("P5", "L", T0 + 3 * H)]:
            res = attempt(f"store {ref}/{size}", bank.store, ref, size, t)
            if res:
                codes[res[0]] = res[1]
        attempt("store duplicate P1", bank.store, "P1", "S", T0 + 4 * H)
        attempt("store empty ref", bank.store, "", "S", T0 + 4 * H)
        attempt("store size XL", bank.store, "P9", "XL", T0 + 4 * H)
        print("free:", bank.free_by_size())
        attempt("release A1 with a wrong code", bank.release, "A1", "000000", T0 + 5 * H)
        attempt("release A1 with the right code", bank.release, "A1", codes["A1"], T0 + 5 * H + 60)
        attempt("hostile compartment id", bank.release, "A2'; DROP TABLE audit; --", "123456", T0 + 6 * H)
        print("expire at exactly 72h:", bank.expire_overdue(T0 + 72 * H))
        print("expire at 72h + 1s:", bank.expire_overdue(T0 + 72 * H + 1))
        print("expire at 80h:", bank.expire_overdue(T0 + 80 * H))
        print("history P3:", bank.history("P3"))
        os.makedirs("out", exist_ok=True)
        print("exported rows:", bank.export_audit("out/audit.csv"))
        print("free:", bank.free_by_size())
    '''),
    slots=[
        Slot("validate", "validate_parcel", _VALIDATE_GOOD, [
            Bad(_VALIDATE_GOOD.replace('''    if size not in SIZE_RANK:
        raise ValueError(f"unknown size: {size!r}")
''', ""), "validation", "the size is never validated, so an unknown size reaches the compartment search and fails there with a KeyError", ("size", "SIZE_RANK", "validate")),
            Bad(_VALIDATE_GOOD.replace("not 1 <= len(ref)", "not 0 <= len(ref)"), "off-by-one", "an empty reference passes because the length check starts at 0 instead of 1", ("empty", "length", "0 <=")),
        ], nit=_VALIDATE_GOOD.replace('if not isinstance(ref, str) or not 1 <= len(ref) <= 16 or not ref.isalnum():', 'if not (isinstance(ref, str) and 1 <= len(ref) <= 16 and ref.isalnum()):')),
        Slot("pick", "Bank.pick_compartment", _PICK_GOOD, [
            Bad(_PICK_GOOD.replace("SIZE_RANK[sz] < need", "SIZE_RANK[sz] <= need"), "off-by-one", "`<= need` skips compartments of exactly the parcel's size; only strictly larger ones are considered", ("<=", "exact", "need", "size")),
            Bad(_PICK_GOOD.replace("SIZE_RANK[sz] < SIZE_RANK[self.sizes[best]]", "SIZE_RANK[sz] > SIZE_RANK[self.sizes[best]]"), "logic", "the comparison is reversed: the largest free compartment wins instead of the smallest that fits", ("largest", "smallest", ">", "best-fit")),
            Bad(_PICK_GOOD.replace("sorted(self.sizes.items())", "self.sizes.items()"), "logic", "the loop is not sorted, so ties go to the compartment inserted first instead of the lowest id", ("sorted", "tie", "order", "lowest id")),
        ], old=dd('''
            def pick_compartment(self, size):
                """First free compartment of exactly the parcel's size."""
                for comp, sz in sorted(self.sizes.items()):
                    if comp not in self.parcels and sz == size:
                        return comp
                raise NoFreeCompartment(size)
        '''), note="picks the *smallest free compartment that fits* (ties: lowest id), so an S parcel may use an M or L one"),
        Slot("code", "Bank.pickup_code", dd('''
            def pickup_code(self, comp, ref):
                """Six digit code, derived from the secret so it never has to be stored."""
                digest = hmac.new(self.secret, f"{comp}:{ref}".encode(), hashlib.sha256).hexdigest()
                return f"{int(digest, 16) % 1_000_000:06d}"
        '''), [
            Bad(dd('''
                def pickup_code(self, comp, ref):
                    """Six digit code, derived from the secret so it never has to be stored."""
                    digest = hashlib.md5(self.secret + f"{comp}:{ref}".encode()).hexdigest()
                    return f"{int(digest, 16) % 1_000_000:06d}"
            '''), "security", "the code is a home-made MAC: md5(secret + message) instead of HMAC, which is weak and open to length extension", ("md5", "hmac", "mac", "secret")),
            Bad(dd('''
                def pickup_code(self, comp, ref):
                    """Six digit code, derived from the secret so it never has to be stored."""
                    return f"{hash((self.secret, comp, ref)) % 1_000_000:06d}"
            '''), "api-misuse", "the builtin hash() of a tuple of bytes/str is randomised per process, so codes are not reproducible after a restart", ("hash", "PYTHONHASHSEED", "restart", "process")),
        ]),
        Slot("verify", "Bank.verify_code", dd('''
            def verify_code(self, comp, code):
                parcel = self.parcels.get(comp)
                if parcel is None:
                    return False
                return hmac.compare_digest(self.pickup_code(comp, parcel["ref"]), code)
        '''), [
            Bad(dd('''
                def verify_code(self, comp, code):
                    parcel = self.parcels.get(comp)
                    if parcel is None:
                        return False
                    return self.pickup_code(comp, parcel["ref"]) == code
            '''), "security", "the code is compared with `==`, which leaks timing information; use hmac.compare_digest", ("compare_digest", "timing", "==", "constant")),
        ], trap=dd('''
            def verify_code(self, comp, code):
                parcel = self.parcels.get(comp)
                if parcel is None:
                    return False
                return hmac.compare_digest(self.pickup_code(comp, parcel["ref"]).encode(), str(code).encode())
        ''')),
        Slot("store", "Bank.store", dd('''
            def store(self, ref, size, now):
                validate_parcel(ref, size)
                if any(p["ref"] == ref for p in self.parcels.values()):
                    raise LockerError(f"parcel {ref} is already stored")
                comp = self.pick_compartment(size)
                self.parcels[comp] = {"ref": ref, "size": size, "since": now}
                self._audit(now, "store", comp, ref)
                log.info("stored %s in %s", ref, comp)
                return comp, self.pickup_code(comp, ref)
        '''), [
            Bad(dd('''
                def store(self, ref, size, now):
                    validate_parcel(ref, size)
                    comp = self.pick_compartment(size)
                    self.parcels[comp] = {"ref": ref, "size": size, "since": now}
                    self._audit(now, "store", comp, ref)
                    log.info("stored %s in %s", ref, comp)
                    return comp, self.pickup_code(comp, ref)
            '''), "validation", "the duplicate-reference check is missing: a parcel scanned twice occupies two compartments", ("duplicate", "already", "twice", "ref")),
        ], old=dd('''
            def store(self, ref, size, now):
                validate_parcel(ref, size)
                comp = self.pick_compartment(size)
                self.parcels[comp] = {"ref": ref, "size": size, "since": now}
                log.info("stored %s in %s", ref, comp)
                return comp, self.pickup_code(comp, ref)
        '''), note="refuses to store the same parcel reference twice and writes an audit record", deps=("audit",)),
        Slot("release", "Bank.release", _RELEASE_GOOD, [
            Bad(dd('''
                def release(self, comp, code, now):
                    parcel = self.parcels.pop(comp, None)
                    if parcel is None or self.pickup_code(comp, parcel["ref"]) != code:
                        self._audit(now, "bad-code", comp, "")
                        raise BadCode(comp)
                    self._audit(now, "release", comp, parcel["ref"])
                    log.info("released %s from %s", parcel["ref"], comp)
                    return parcel["ref"]
            '''), "logic", "the parcel is popped before the code is checked, so a wrong code removes it from the compartment and it is lost", ("pop", "wrong code", "lost", "before")),
            Bad(_RELEASE_GOOD.replace('log.info("released %s from %s", parcel["ref"], comp)', 'log.info("released %s from %s with code %s", parcel["ref"], comp, code)'),
                "security", "the customer's pickup code is written to the application log", ("log", "code", "secret", "sensitive")),
        ], old=dd('''
            def release(self, comp, code, now):
                if not self.verify_code(comp, code):
                    raise BadCode(comp)
                parcel = self.parcels.pop(comp)
                log.info("released %s from %s", parcel["ref"], comp)
                return parcel["ref"]
        '''), note="records failed pickups and releases in the audit trail", deps=("audit",)),
        Slot("expire", "Bank.expire_overdue", _EXPIRE_GOOD, [
            Bad(_EXPIRE_GOOD.replace('> HOLD_SECONDS]', '>= HOLD_SECONDS]'), "off-by-one", "`>=` expires a parcel at exactly 72 hours; the rule says more than 72 hours", (">=", "exactly", "boundary", "72")),
            Bad(_EXPIRE_GOOD.replace('> HOLD_SECONDS]', '> HOLD_SECONDS / 3600]'), "logic", "HOLD_SECONDS is divided by 3600, so parcels expire after 72 seconds instead of 72 hours (unit mix-up)", ("3600", "seconds", "hours", "unit")),
            Bad(dd('''
                def expire_overdue(self, now):
                    """References of parcels held for more than HOLD_SECONDS, returned to sender; their compartments are freed."""
                    refs = []
                    for comp, p in self.parcels.items():
                        if now - p["since"] > HOLD_SECONDS:
                            refs.append(self.parcels.pop(comp)["ref"])
                            self._audit(now, "expire", comp, refs[-1])
                    return refs
            '''), "logic", "parcels are removed from the dict while it is being iterated, which raises RuntimeError (dictionary changed size during iteration)", ("iterat", "pop", "RuntimeError", "changed size")),
        ], old="", note="adds `expire_overdue()`: parcels held for **more than** 72 hours are returned to sender and their compartment is freed", deps=("audit",)),
        Slot("audit", "Bank._audit", dd('''
            def _audit(self, ts, event, comp, ref):
                self.audit.execute("INSERT INTO audit VALUES (?, ?, ?, ?)", (ts, event, comp, ref))
        '''), [
            Bad(dd('''
                def _audit(self, ts, event, comp, ref):
                    self.audit.execute(f"INSERT INTO audit VALUES ({ts}, '{event}', '{comp}', '{ref}')")
            '''), "security", "the audit row is built with an f-string; the compartment id comes straight from the touchscreen, so this is SQL injection", ("sql", "injection", "f-string", "parameter", "placeholder")),
        ], old="", note="adds an in-memory SQLite audit table that every store / release / failed pickup / expiry writes to"),
        Slot("history", "Bank.history", dd('''
            def history(self, ref):
                """Audit events of one parcel reference, oldest first."""
                rows = self.audit.execute("SELECT ts, event, comp FROM audit WHERE ref = ? ORDER BY ts", (ref,))
                return rows.fetchall()
        '''), [
            Bad(dd('''
                def history(self, ref):
                    """Audit events of one parcel reference, oldest first."""
                    rows = self.audit.execute(f"SELECT ts, event, comp FROM audit WHERE ref = '{ref}' ORDER BY ts")
                    return rows.fetchall()
            '''), "security", "the reference is interpolated into the SQL text instead of being bound as a parameter", ("sql", "injection", "f-string", "parameter")),
            Bad(dd('''
                def history(self, ref):
                    """Audit events of one parcel reference, oldest first."""
                    rows = self.audit.execute("SELECT ts, event, comp FROM audit WHERE ref = ? ORDER BY ts DESC", (ref,))
                    return rows.fetchall()
            '''), "logic", "the events come back newest first although the docstring (and the dashboard) expect oldest first", ("DESC", "order", "oldest", "newest")),
        ], old="", note="adds `history(ref)`: the audit events of one parcel, oldest first", deps=("audit",)),
        Slot("export", "Bank.export_audit", _EXPORT_GOOD, [
            Bad(dd('''
                def export_audit(self, path):
                    """Write the whole audit trail to a CSV file; returns the number of rows."""
                    rows = self.audit.execute("SELECT ts, event, comp, ref FROM audit ORDER BY rowid").fetchall()
                    fh = open(path, "w", newline="")
                    writer = csv.writer(fh)
                    writer.writerow(["ts", "event", "comp", "ref"])
                    writer.writerows(rows)
                    return len(rows)
            '''), "resource-leak", "the file is opened without `with` and never closed, so the last buffered rows may not be flushed and the descriptor leaks", ("close", "with", "file", "handle", "flush")),
            Bad(_EXPORT_GOOD.replace("writer.writerows(rows)", "writer.writerows(rows[1:])"), "off-by-one", "`rows[1:]` drops the first audit event from the export while the returned count still includes it", ("rows[1:]", "first", "skip", "drops")),
        ], old="", note="adds `export_audit(path)` to dump the audit trail as CSV", deps=("audit",)),
        Slot("free", "Bank.free_by_size", dd('''
            def free_by_size(self):
                """How many free compartments there are of each size letter."""
                free = {s: 0 for s in SIZE_RANK}
                for comp, sz in self.sizes.items():
                    if comp not in self.parcels:
                        free[sz] += 1
                return free
        '''), [
            Bad(dd('''
                def free_by_size(self):
                    """How many free compartments there are of each size letter."""
                    free = {s: 0 for s in SIZE_RANK}
                    for comp, sz in self.sizes.items():
                        if comp in self.parcels:
                            free[sz] += 1
                    return free
            '''), "logic", "the condition is inverted: it counts occupied compartments instead of free ones", ("inverted", "occupied", "free", "not in")),
        ], nit=dd('''
            def free_by_size(self):
                """How many free compartments there are of each size letter."""
                free = {s: 0 for s in SIZE_RANK}
                for comp, sz in self.sizes.items():
                    if (comp not in self.parcels):
                        free[sz] += 1
                return free
        '''), old="", note="adds `free_by_size()` for the dashboard"),
    ],
)

from ._slots import validate_module
MODULES = [LOCKERS]

from ._traps import apply_traps  # noqa: E402

apply_traps(MODULES)

for _m in MODULES:
    validate_module(_m)

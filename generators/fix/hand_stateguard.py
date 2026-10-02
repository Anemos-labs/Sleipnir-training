"""State machines whose transitions skip a guard: document approval (python), order lifecycle (java), device fleet (go)."""
from fx import dd, family, langs
from generators.fix._hand_kit import Base, Bug, tasks_from

# ------------------------------------------------------------------------------------------------------------------
# Base A (python): document approval workflow.
# ------------------------------------------------------------------------------------------------------------------

A_README = dd('''
    # docflow

    The approval workflow of a publishing tool. States: `draft`, `review`, `approved`, `rejected`, `published`, `archived`.
    Every operation raises `GuardError` when it is not allowed (and then changes nothing).

    * `submit(who)`: only the author; needs a non-blank title and body; `draft` -> `review`.
    * `approve(reviewer)`: only in `review`; the author may not approve their own document; every **distinct** reviewer counts once.
      With 2 distinct approvals the document becomes `approved`.
    * `reject(reviewer, reason)`: only in `review`, with a non-blank reason; clears all approvals; `review` -> `rejected`.
    * `reopen(who)`: `rejected` -> `draft`.
    * `edit(who, title=None, body=None)`: only the author, never on `published` or `archived` documents. Editing an `approved`
      document wipes its approvals and sends it back to `review`.
    * `publish(who, now, admin=False)`: only from `approved`; before the embargo time (`now < embargo`) it is refused,
      unless `admin` is true (an admin may ignore the embargo, **nothing else**).
    * `archive(who)`: `published` -> `archived`.
    * `doc.history` lists `(from_state, to_state, who)` for every state change.
''')

A_ERRORS = dd('''
    class GuardError(Exception):
        pass
''')

A_WORKFLOW = dd('''
    from .errors import GuardError

    TRANSITIONS = {
        "draft": {"review"},
        "review": {"approved", "rejected"},
        "rejected": {"draft"},
        "approved": {"published", "review"},
        "published": {"archived"},
        "archived": set(),
    }

    REQUIRED_APPROVALS = 2


    class Document:
        def __init__(self, doc_id, author, title="", body="", embargo=None):
            self.id = doc_id
            self.author = author
            self.title = title
            self.body = body
            self.embargo = embargo
            self.state = "draft"
            self.approvals = set()
            self.reason = None
            self.history = []

        def _move(self, new, who):
            if new not in TRANSITIONS[self.state]:
                raise GuardError(f"cannot go from {self.state} to {new}")
            self.history.append((self.state, new, who))
            self.state = new

        def submit(self, who):
            if who != self.author:
                raise GuardError("only the author can submit")
            if not self.title.strip() or not self.body.strip():
                raise GuardError("title and body are required")
            self._move("review", who)

        def approve(self, reviewer):
            if self.state != "review":
                raise GuardError("only documents in review can be approved")
            if reviewer == self.author:
                raise GuardError("authors cannot approve their own document")
            self.approvals.add(reviewer)
            if len(self.approvals) >= REQUIRED_APPROVALS:
                self._move("approved", reviewer)

        def reject(self, reviewer, reason):
            if self.state != "review":
                raise GuardError("only documents in review can be rejected")
            if not reason.strip():
                raise GuardError("a reason is required")
            self.approvals.clear()
            self.reason = reason
            self._move("rejected", reviewer)

        def reopen(self, who):
            self._move("draft", who)

        def edit(self, who, title=None, body=None):
            if who != self.author:
                raise GuardError("only the author can edit")
            if self.state in ("published", "archived"):
                raise GuardError("published documents are read-only")
            if title is not None:
                self.title = title
            if body is not None:
                self.body = body
            if self.state == "approved":
                self.approvals.clear()
                self._move("review", who)

        def publish(self, who, now, admin=False):
            if self.state != "approved":
                raise GuardError("only approved documents can be published")
            if self.embargo is not None and now < self.embargo and not admin:
                raise GuardError("embargo has not ended")
            self._move("published", who)

        def archive(self, who):
            self._move("archived", who)
''')

A_VISIBLE = {
    "tests/test_flow.py": dd('''
        import unittest

        from docflow.errors import GuardError
        from docflow.workflow import Document


        def reviewed():
            d = Document("d1", "ann", "Title", "Body text")
            d.submit("ann")
            d.approve("bob")
            d.approve("cy")
            return d


        class FlowTests(unittest.TestCase):
            def test_happy_path(self):
                d = reviewed()
                self.assertEqual(d.state, "approved")
                d.publish("ann", now=10)
                self.assertEqual(d.state, "published")
                self.assertEqual(d.history[0], ("draft", "review", "ann"))

            def test_blank_title_cannot_be_submitted(self):
                d = Document("d2", "ann", "  ", "Body")
                with self.assertRaises(GuardError):
                    d.submit("ann")


        if __name__ == "__main__":
            unittest.main()
    '''),
}

A_HIDDEN = {
    "tests/test_hidden_flow.py": dd('''
        import unittest

        from docflow.errors import GuardError
        from docflow.workflow import Document


        def doc(**kw):
            return Document("d", "ann", kw.get("title", "Title"), kw.get("body", "Body"), kw.get("embargo"))


        def in_review():
            d = doc()
            d.submit("ann")
            return d


        def approved():
            d = in_review()
            d.approve("bob")
            d.approve("cy")
            return d


        class Submitting(unittest.TestCase):
            def test_only_the_author_submits(self):
                d = doc()
                with self.assertRaises(GuardError):
                    d.submit("bob")
                self.assertEqual(d.state, "draft")

            def test_blank_fields_are_refused(self):
                for kw in ({"title": ""}, {"body": "   "}):
                    with self.assertRaises(GuardError):
                        doc(**kw).submit("ann")

            def test_cannot_submit_twice(self):
                d = in_review()
                with self.assertRaises(GuardError):
                    d.submit("ann")


        class Approving(unittest.TestCase):
            def test_authors_cannot_approve(self):
                d = in_review()
                with self.assertRaises(GuardError):
                    d.approve("ann")
                self.assertEqual(d.approvals, set())

            def test_two_distinct_reviewers_are_needed(self):
                d = in_review()
                d.approve("bob")
                self.assertEqual(d.state, "review")
                d.approve("bob")
                self.assertEqual(d.state, "review")
                d.approve("cy")
                self.assertEqual(d.state, "approved")

            def test_only_in_review(self):
                d = doc()
                with self.assertRaises(GuardError):
                    d.approve("bob")
                a = approved()
                with self.assertRaises(GuardError):
                    a.approve("dee")


        class Rejecting(unittest.TestCase):
            def test_reason_required_and_approvals_cleared(self):
                d = in_review()
                d.approve("bob")
                with self.assertRaises(GuardError):
                    d.reject("cy", "  ")
                self.assertEqual(d.state, "review")
                d.reject("cy", "needs sources")
                self.assertEqual((d.state, d.reason, d.approvals), ("rejected", "needs sources", set()))

            def test_a_resubmitted_document_starts_with_no_approvals(self):
                d = in_review()
                d.approve("bob")
                d.reject("cy", "fix typos")
                d.reopen("ann")
                d.submit("ann")
                d.approve("cy")
                self.assertEqual(d.state, "review")
                d.approve("dee")
                self.assertEqual(d.state, "approved")


        class Editing(unittest.TestCase):
            def test_edit_of_an_approved_document_returns_it_to_review(self):
                d = approved()
                d.edit("ann", body="Changed body")
                self.assertEqual((d.state, d.approvals, d.body), ("review", set(), "Changed body"))
                d.approve("bob")
                self.assertEqual(d.state, "review")

            def test_only_the_author_edits_and_not_after_publication(self):
                d = approved()
                with self.assertRaises(GuardError):
                    d.edit("bob", body="x")
                d.publish("ann", now=1)
                with self.assertRaises(GuardError):
                    d.edit("ann", body="x")
                d.archive("ann")
                with self.assertRaises(GuardError):
                    d.edit("ann", title="x")

            def test_editing_a_draft_keeps_it_a_draft(self):
                d = doc()
                d.edit("ann", title="New")
                self.assertEqual((d.state, d.title), ("draft", "New"))


        class Publishing(unittest.TestCase):
            def test_embargo(self):
                d = doc(embargo=100)
                d.submit("ann")
                d.approve("bob")
                d.approve("cy")
                with self.assertRaises(GuardError):
                    d.publish("ann", now=99)
                self.assertEqual(d.state, "approved")
                d.publish("ann", now=100)
                self.assertEqual(d.state, "published")

            def test_admin_may_skip_the_embargo(self):
                d = doc(embargo=100)
                d.submit("ann")
                d.approve("bob")
                d.approve("cy")
                d.publish("root", now=1, admin=True)
                self.assertEqual(d.state, "published")

            def test_admin_may_not_skip_the_approvals(self):
                for prepare in (lambda d: None, lambda d: d.submit("ann")):
                    d = doc()
                    prepare(d)
                    before = d.state
                    with self.assertRaises(GuardError):
                        d.publish("root", now=1, admin=True)
                    self.assertEqual(d.state, before)
                    self.assertEqual(d.history[-1][1] if d.history else None, "review" if d.history else None)

            def test_history_and_archive(self):
                d = approved()
                d.publish("ann", now=5)
                d.archive("ann")
                self.assertEqual([(a, b) for a, b, _ in d.history], [("draft", "review"), ("review", "approved"), ("approved", "published"), ("published", "archived")])
                with self.assertRaises(GuardError):
                    d.archive("ann")


        if __name__ == "__main__":
            unittest.main()
    '''),
}


def _a_prompts():
    p = {}
    p["author-approves"] = (
        "A colleague approved their own article and with one more approval from the editor it went live. Our policy (and the README) "
        "says authors cannot approve their own documents. How did that get through?"
    )
    p["same-reviewer-twice"] = (
        "One reviewer clicked 'approve' twice (double-click on a slow connection) and the document was published with only a "
        "single reviewer's sign-off. Two *different* reviewers are required."
    )
    p["reject-keeps"] = (
        "A document was rejected, fixed and resubmitted, and then one new approval was enough to publish it because the old "
        "approval from before the rejection still counted. Approvals must be cleared when a document is rejected."
    )
    p["admin-bypass"] = (
        "The admin 'publish now' button published a draft that nobody had reviewed. The admin flag is only supposed to override the "
        "embargo date; the document must still be approved. Please close the loophole without breaking the embargo override."
    )
    p["edit-keeps"] = (
        "An author changed the text of an already approved article (swapped a paragraph) and it was still publishable without another "
        "review. Editing an approved document should send it back to review and wipe the approvals. Careful: other transitions "
        "must keep working."
    )
    p["two"] = (
        "Compliance found an article that went live after its text had been changed following approval, signed off by a single "
        "reviewer who clicked twice. I suspect two separate holes in the approval logic, please close all of them: the "
        "visible tests only cover the happy path."
    )
    return p


def _base_a() -> Base:
    P = _a_prompts()
    good = {"README.md": A_README, "docflow/__init__.py": '"""Approval workflow."""\n', "docflow/errors.py": A_ERRORS, "docflow/workflow.py": A_WORKFLOW}
    w = "docflow/workflow.py"
    dup = [("            self.approvals = set()\n            self.reason = None\n", "            self.approvals = []\n            self.reason = None\n"),
           ("            self.approvals.add(reviewer)\n", "            self.approvals.append(reviewer)\n")]
    dup = [("        self.approvals = set()\n        self.reason = None\n", "        self.approvals = []\n        self.reason = None\n"),
           ("        self.approvals.add(reviewer)\n", "        self.approvals.append(reviewer)\n")]
    editbug = ("        if self.state == \"approved\":\n            self.approvals.clear()\n            self._move(\"review\", who)\n", "")
    bugs = [
        Bug("author-can-approve", 2, {w: [("        if reviewer == self.author:\n            raise GuardError(\"authors cannot approve their own document\")\n", "")]}, P["author-approves"]),
        Bug("approvals-counted-per-click", 3, {w: dup}, P["same-reviewer-twice"]),
        Bug("rejection-keeps-approvals", 2, {w: [("        self.approvals.clear()\n        self.reason = reason\n", "        self.reason = reason\n")]}, P["reject-keeps"]),
        Bug("admin-publish-skips-review", 4, {w: [("        if self.state != \"approved\":\n            raise GuardError(\"only approved documents can be published\")\n",
                                                   "        if admin and self.state in (\"draft\", \"review\"):\n            self.history.append((self.state, \"published\", who))\n            self.state = \"published\"\n            return\n        if self.state != \"approved\":\n            raise GuardError(\"only approved documents can be published\")\n")]}, P["admin-bypass"]),
        Bug("edit-keeps-approval", 3, {w: [editbug]}, P["edit-keeps"]),
        Bug("duplicate-approvals-and-edit", 5, {w: dup + [editbug]}, P["two"]),
    ]
    return Base("docflow", "python", good, A_VISIBLE, A_HIDDEN, bugs)


# ------------------------------------------------------------------------------------------------------------------
# Base B (java): order lifecycle with idempotent events.
# ------------------------------------------------------------------------------------------------------------------

B_README = dd('''
    # orders

    Order lifecycle of a web shop (plain Java: `rm -rf build && mkdir -p build && javac -d build $(find . -name '*.java') &&
    java -cp build TestMain`). `orders.Order(total)` starts in `CREATED`. Every operation takes the id of the event that
    caused it.

    * `pay(eventId, amount)`: only in `CREATED`; the amount must equal the total exactly (any other amount is an
      `IllegalArgumentException` and nothing changes); `CREATED` -> `PAID`.
    * `pack(eventId)`: only in `PAID` -> `PACKED`. `ship(eventId)`: only in `PACKED` -> `SHIPPED`. `deliver(eventId)`: only in
      `SHIPPED` -> `DELIVERED`.
    * `cancel(eventId)`: allowed in `CREATED`, `PAID` and `PACKED`, becomes `CANCELLED`; when the order had been paid
      (`PAID` or `PACKED`) the whole total is refunded (`refunded()` returns it). A shipped, delivered or cancelled order cannot be
      cancelled.
    * An operation that is not allowed in the current state throws `IllegalStateException` and changes nothing.
    * Events are idempotent: every operation returns `true` when it changed the order and `false` when the same `eventId` had
      already been applied, in which case nothing happens (not even a state check).
''')

B_STATE = dd('''
    package orders;

    public enum State {
        CREATED, PAID, PACKED, SHIPPED, DELIVERED, CANCELLED
    }
''')

B_ORDER = dd('''
    package orders;

    import java.util.HashSet;
    import java.util.Set;

    public final class Order {
        private final long total;
        private State state = State.CREATED;
        private long refunded = 0;
        private final Set<String> seen = new HashSet<>();

        public Order(long total) {
            this.total = total;
        }

        public State state() {
            return state;
        }

        public long refunded() {
            return refunded;
        }

        private boolean duplicate(String eventId) {
            return !seen.add(eventId);
        }

        private void require(State expected, String what) {
            if (state != expected) {
                throw new IllegalStateException(what + " is not allowed in state " + state);
            }
        }

        public boolean pay(String eventId, long amount) {
            if (seen.contains(eventId)) {
                return false;
            }
            require(State.CREATED, "pay");
            if (amount != total) {
                throw new IllegalArgumentException("payment of " + amount + " does not match the total " + total);
            }
            seen.add(eventId);
            state = State.PAID;
            return true;
        }

        public boolean pack(String eventId) {
            if (seen.contains(eventId)) {
                return false;
            }
            require(State.PAID, "pack");
            seen.add(eventId);
            state = State.PACKED;
            return true;
        }

        public boolean ship(String eventId) {
            if (seen.contains(eventId)) {
                return false;
            }
            require(State.PACKED, "ship");
            seen.add(eventId);
            state = State.SHIPPED;
            return true;
        }

        public boolean deliver(String eventId) {
            if (seen.contains(eventId)) {
                return false;
            }
            require(State.SHIPPED, "deliver");
            seen.add(eventId);
            state = State.DELIVERED;
            return true;
        }

        public boolean cancel(String eventId) {
            if (seen.contains(eventId)) {
                return false;
            }
            if (state != State.CREATED && state != State.PAID && state != State.PACKED) {
                throw new IllegalStateException("cancel is not allowed in state " + state);
            }
            seen.add(eventId);
            if (state == State.PAID || state == State.PACKED) {
                refunded = total;
            }
            state = State.CANCELLED;
            return true;
        }
    }
''')

B_VISIBLE = {
    "tests/TestMain.java": dd('''
        import orders.Order;
        import orders.State;

        public class TestMain {
            static int failures = 0;

            static void check(String what, boolean ok) {
                if (!ok) {
                    failures++;
                    System.out.println("FAIL " + what);
                }
            }

            public static void main(String[] args) {
                Order o = new Order(500);
                check("pay", o.pay("e1", 500) && o.state() == State.PAID);
                check("pack", o.pack("e2") && o.state() == State.PACKED);
                check("ship", o.ship("e3") && o.state() == State.SHIPPED);
                check("deliver", o.deliver("e4") && o.state() == State.DELIVERED);
                if (failures > 0) {
                    System.exit(1);
                }
                System.out.println("all checks passed");
            }
        }
    '''),
}


def _b_hidden() -> str:
    return dd('''
        import orders.Order;
        import orders.State;

        public class TestMain {
            static int failures = 0;

            static void check(String what, boolean ok) {
                if (!ok) {
                    failures++;
                    System.out.println("FAIL " + what);
                }
            }

            static void illegalState(String what, Runnable r) {
                try {
                    r.run();
                } catch (IllegalStateException e) {
                    return;
                } catch (RuntimeException e) {
                    failures++;
                    System.out.println("FAIL " + what + ": wrong exception " + e);
                    return;
                }
                failures++;
                System.out.println("FAIL " + what + ": expected IllegalStateException");
            }

            static void illegalArgument(String what, Runnable r) {
                try {
                    r.run();
                } catch (IllegalArgumentException e) {
                    return;
                } catch (RuntimeException e) {
                    failures++;
                    System.out.println("FAIL " + what + ": wrong exception " + e);
                    return;
                }
                failures++;
                System.out.println("FAIL " + what + ": expected IllegalArgumentException");
            }

            static Order paid() {
                Order o = new Order(500);
                o.pay("p", 500);
                return o;
            }

            static Order packed() {
                Order o = paid();
                o.pack("k");
                return o;
            }

            static Order shipped() {
                Order o = packed();
                o.ship("s");
                return o;
            }

            public static void main(String[] args) {
                // payments
                Order o = new Order(500);
                illegalArgument("underpay", () -> o.pay("a", 499));
                illegalArgument("overpay", () -> o.pay("b", 501));
                check("still created after bad payments", o.state() == State.CREATED);
                check("exact payment", o.pay("c", 500) && o.state() == State.PAID);
                illegalState("second payment", () -> o.pay("d", 500));

                // order of steps
                Order fresh = new Order(100);
                illegalState("pack before pay", () -> fresh.pack("x"));
                illegalState("ship before pay", () -> fresh.ship("x2"));
                illegalState("deliver before pay", () -> fresh.deliver("x3"));
                Order pd = paid();
                illegalState("ship unpacked", () -> pd.ship("y"));
                illegalState("deliver unpacked", () -> pd.deliver("y2"));
                Order pk = packed();
                illegalState("deliver unshipped", () -> pk.deliver("z"));
                illegalState("pack twice", () -> pk.pack("z2"));
                check("packed stays packed", pk.state() == State.PACKED);
                Order sh = shipped();
                check("deliver", sh.deliver("d") && sh.state() == State.DELIVERED);

                // cancellation
                Order c1 = new Order(500);
                check("cancel created", c1.cancel("c1") && c1.state() == State.CANCELLED && c1.refunded() == 0);
                Order c2 = paid();
                check("cancel paid refunds", c2.cancel("c2") && c2.state() == State.CANCELLED && c2.refunded() == 500);
                Order c3 = packed();
                check("cancel packed refunds", c3.cancel("c3") && c3.state() == State.CANCELLED && c3.refunded() == 500);
                Order c4 = shipped();
                illegalState("cancel shipped", () -> c4.cancel("c4"));
                check("shipped stays shipped", c4.state() == State.SHIPPED && c4.refunded() == 0);
                Order c5 = shipped();
                c5.deliver("dd");
                illegalState("cancel delivered", () -> c5.cancel("c5"));
                Order c6 = new Order(500);
                c6.cancel("c6");
                illegalState("cancel twice (new event)", () -> c6.cancel("c6b"));
                illegalState("pay a cancelled order", () -> c6.pay("late", 500));

                // idempotent events
                Order d = new Order(500);
                check("pay first time", d.pay("ev-1", 500));
                check("pay replay", !d.pay("ev-1", 500));
                check("pack", d.pack("ev-2"));
                check("pay replay after pack", !d.pay("ev-1", 500) && d.state() == State.PACKED);
                check("pack replay", !d.pack("ev-2") && d.state() == State.PACKED);
                check("ship", d.ship("ev-3"));
                check("ship replay", !d.ship("ev-3") && d.state() == State.SHIPPED);
                check("deliver", d.deliver("ev-4"));
                check("deliver replay", !d.deliver("ev-4") && d.state() == State.DELIVERED);
                Order e = paid();
                check("cancel", e.cancel("x-1") && e.refunded() == 500);
                check("cancel replay does not refund twice", !e.cancel("x-1") && e.refunded() == 500 && e.state() == State.CANCELLED);
                Order f = new Order(10);
                f.pay("same", 10);
                illegalState("a new event id with the same effect is a real second call", () -> f.pay("other", 10));
                check("a failed call does not use up the event id", tryAndReplay());

                if (failures > 0) {
                    System.out.println(failures + " check(s) failed");
                    System.exit(1);
                }
                System.out.println("all checks passed");
            }

            static boolean tryAndReplay() {
                Order o = new Order(100);
                try {
                    o.pack("id-1");
                } catch (IllegalStateException e) {
                    // expected: not paid yet
                }
                o.pay("id-0", 100);
                return o.pack("id-1") && o.state() == State.PACKED;
            }
        }
    ''')


def _b_prompts():
    p = {}
    p["cancel-shipped"] = (
        "Support cancelled an order that was already on the truck and the system happily marked it CANCELLED (no refund, parcel still "
        "delivered). Shipped and delivered orders must not be cancellable."
    )
    p["overpay"] = (
        "A customer paid 501 for a 500 order (double-tapped a currency field) and the order went to PAID without complaint. The README "
        "requires the payment to equal the total exactly."
    )
    p["refund-packed"] = (
        "Cancelling an order that was already packed leaves the money with us: `refunded()` is 0 although the customer had "
        "paid. For paid and packed orders the whole total must be refunded."
    )
    p["deliver-skips"] = (
        "Orders can be marked delivered straight from PACKED, so the carrier's 'delivered' webhook arriving before 'shipped' (they "
        "are not always in order) silently skips a state. A delivery must only be accepted for shipped orders."
    )
    p["replay"] = (
        "Our event bus redelivers messages. A replayed `cancel` event (same event id) blows up with an IllegalStateException in the "
        "consumer instead of being ignored like the other replayed events are. Something about the way the cancel path records "
        "event ids is different."
    )
    return p


def _base_b() -> Base:
    P = _b_prompts()
    good = {"README.md": B_README, "src/orders/State.java": B_STATE, "src/orders/Order.java": B_ORDER}
    o = "src/orders/Order.java"
    bugs = [
        Bug("shipped-orders-can-be-cancelled", 1, {o: [("        if (state != State.CREATED && state != State.PAID && state != State.PACKED) {\n            throw new IllegalStateException(\"cancel is not allowed in state \" + state);\n        }\n",
                                                        "        if (state == State.CANCELLED || state == State.DELIVERED) {\n            throw new IllegalStateException(\"cancel is not allowed in state \" + state);\n        }\n")]}, P["cancel-shipped"]),
        Bug("overpayment-accepted", 3, {o: [("        if (amount != total) {\n", "        if (amount < total) {\n")]}, P["overpay"]),
        Bug("packed-cancel-without-refund", 3, {o: [("        if (state == State.PAID || state == State.PACKED) {\n            refunded = total;\n        }\n", "        if (state == State.PAID) {\n            refunded = total;\n        }\n")]}, P["refund-packed"]),
        Bug("deliver-from-packed", 2, {o: [("        require(State.SHIPPED, \"deliver\");\n", "        if (state != State.SHIPPED && state != State.PACKED) {\n            throw new IllegalStateException(\"deliver is not allowed in state \" + state);\n        }\n")]}, P["deliver-skips"]),
        Bug("cancel-event-id-not-remembered", 4, {o: [("        seen.add(eventId);\n        if (state == State.PAID || state == State.PACKED) {\n", "        if (state == State.PAID || state == State.PACKED) {\n")]}, P["replay"]),
    ]
    return Base("orders", "java", good, B_VISIBLE, {"tests/TestMain.java": _b_hidden()}, bugs)


# ------------------------------------------------------------------------------------------------------------------
# Base C (go): device fleet lifecycle.
# ------------------------------------------------------------------------------------------------------------------

C_README = dd('''
    # fleet

    Lifecycle of IoT devices. `Device.State` is one of `New`, `Registered`, `Provisioned`, `Active`, `Retired`. Every operation
    returns an error when it is not allowed and then changes nothing.

    * `Register()`: `New` -> `Registered`. On a device that is already registered, provisioned or active it returns
      `ErrAlreadyRegistered` and the device keeps its state; on a retired device it returns `ErrState`.
    * `Provision(cert, firmware)`: only `Registered` -> `Provisioned` (else `ErrState`); an empty `cert` is `ErrNoCert`.
    * `Activate()`: only `Provisioned` -> `Active` (else `ErrState`); `Firmware` must be at least `MinFirmware` (3), otherwise
      `ErrOldFirmware`.
    * `Heartbeat()`: only `Active`; counts in `Beats` (else `ErrState`).
    * `Retire()`: from any state except `Retired` (which gives `ErrState`).
''')

C_FLEET = dd('''
    package fleet

    import "errors"

    // State of a device in its life cycle.
    type State int

    const (
    	New State = iota
    	Registered
    	Provisioned
    	Active
    	Retired
    )

    // MinFirmware is the oldest firmware version that may be activated.
    const MinFirmware = 3

    var (
    	ErrState             = errors.New("operation not allowed in this state")
    	ErrAlreadyRegistered = errors.New("device is already registered")
    	ErrNoCert            = errors.New("certificate required")
    	ErrOldFirmware       = errors.New("firmware too old")
    )

    // Device is one managed device.
    type Device struct {
    	ID       string
    	State    State
    	Cert     string
    	Firmware int
    	Beats    int
    }

    func (d *Device) Register() error {
    	switch d.State {
    	case New:
    		d.State = Registered
    		return nil
    	case Retired:
    		return ErrState
    	default:
    		return ErrAlreadyRegistered
    	}
    }

    func (d *Device) Provision(cert string, firmware int) error {
    	if d.State != Registered {
    		return ErrState
    	}
    	if cert == "" {
    		return ErrNoCert
    	}
    	d.Cert = cert
    	d.Firmware = firmware
    	d.State = Provisioned
    	return nil
    }

    func (d *Device) Activate() error {
    	if d.State != Provisioned {
    		return ErrState
    	}
    	if d.Firmware < MinFirmware {
    		return ErrOldFirmware
    	}
    	d.State = Active
    	return nil
    }

    func (d *Device) Heartbeat() error {
    	if d.State != Active {
    		return ErrState
    	}
    	d.Beats++
    	return nil
    }

    func (d *Device) Retire() error {
    	if d.State == Retired {
    		return ErrState
    	}
    	d.State = Retired
    	return nil
    }
''')

C_VISIBLE = {
    "fleet_test.go": dd('''
        package fleet

        import "testing"

        func TestHappyPath(t *testing.T) {
        	d := &Device{ID: "d1"}
        	if err := d.Register(); err != nil {
        		t.Fatal(err)
        	}
        	if err := d.Provision("cert", 4); err != nil {
        		t.Fatal(err)
        	}
        	if err := d.Activate(); err != nil {
        		t.Fatal(err)
        	}
        	if err := d.Heartbeat(); err != nil || d.Beats != 1 {
        		t.Fatalf("beats %d err %v", d.Beats, err)
        	}
        }
    '''),
}

C_HIDDEN = {
    "fleet_hidden_test.go": dd('''
        package fleet

        import (
        	"errors"
        	"testing"
        )

        func device(t *testing.T, to State) *Device {
        	t.Helper()
        	d := &Device{ID: "d"}
        	steps := []func() error{
        		d.Register,
        		func() error { return d.Provision("cert", 3) },
        		d.Activate,
        		d.Retire,
        	}
        	for i := 0; i < int(to); i++ {
        		if err := steps[i](); err != nil {
        			t.Fatalf("setup step %d: %v", i, err)
        		}
        	}
        	if d.State != to {
        		t.Fatalf("setup reached %v, want %v", d.State, to)
        	}
        	return d
        }

        func TestRegisterIsNotARestart(t *testing.T) {
        	for _, s := range []State{Registered, Provisioned, Active} {
        		d := device(t, s)
        		beats, cert := d.Beats, d.Cert
        		if err := d.Register(); !errors.Is(err, ErrAlreadyRegistered) {
        			t.Errorf("Register in state %v: got %v, want ErrAlreadyRegistered", s, err)
        		}
        		if d.State != s || d.Beats != beats || d.Cert != cert {
        			t.Errorf("Register in state %v changed the device: %+v", s, d)
        		}
        	}
        	d := device(t, Retired)
        	if err := d.Register(); !errors.Is(err, ErrState) || d.State != Retired {
        		t.Errorf("Register on a retired device: %v, state %v", err, d.State)
        	}
        }

        func TestProvision(t *testing.T) {
        	d := device(t, Registered)
        	if err := d.Provision("", 5); !errors.Is(err, ErrNoCert) || d.State != Registered || d.Firmware != 0 {
        		t.Fatalf("empty cert: %v %+v", err, d)
        	}
        	for _, s := range []State{New, Provisioned, Active, Retired} {
        		x := device(t, s)
        		if err := x.Provision("c", 9); !errors.Is(err, ErrState) {
        			t.Errorf("Provision in state %v: %v", s, err)
        		}
        		if s != New && x.Cert == "c" && s != Provisioned {
        			t.Errorf("state %v: certificate was overwritten", s)
        		}
        	}
        }

        func TestActivateNeedsRecentFirmware(t *testing.T) {
        	d := &Device{ID: "x"}
        	d.Register()
        	d.Provision("cert", MinFirmware-1)
        	if err := d.Activate(); !errors.Is(err, ErrOldFirmware) || d.State != Provisioned {
        		t.Fatalf("old firmware: %v, state %v", err, d.State)
        	}
        	d2 := &Device{ID: "y"}
        	d2.Register()
        	d2.Provision("cert", MinFirmware)
        	if err := d2.Activate(); err != nil || d2.State != Active {
        		t.Fatalf("minimum firmware: %v, state %v", err, d2.State)
        	}
        	for _, s := range []State{New, Registered, Active, Retired} {
        		if err := device(t, s).Activate(); !errors.Is(err, ErrState) {
        			t.Errorf("Activate in state %v: %v", s, err)
        		}
        	}
        }

        func TestHeartbeatOnlyWhenActive(t *testing.T) {
        	for _, s := range []State{New, Registered, Provisioned, Retired} {
        		d := device(t, s)
        		if err := d.Heartbeat(); !errors.Is(err, ErrState) || d.Beats != 0 {
        			t.Errorf("Heartbeat in state %v: %v, beats %d", s, err, d.Beats)
        		}
        	}
        	d := device(t, Active)
        	for i := 0; i < 3; i++ {
        		if err := d.Heartbeat(); err != nil {
        			t.Fatal(err)
        		}
        	}
        	if d.Beats != 3 {
        		t.Fatalf("beats %d", d.Beats)
        	}
        }

        func TestRetire(t *testing.T) {
        	for _, s := range []State{New, Registered, Provisioned, Active} {
        		d := device(t, s)
        		if err := d.Retire(); err != nil || d.State != Retired {
        			t.Errorf("Retire in state %v: %v, state %v", s, err, d.State)
        		}
        	}
        	d := device(t, Retired)
        	if err := d.Retire(); !errors.Is(err, ErrState) {
        		t.Errorf("Retire twice: %v", err)
        	}
        }
    '''),
}


def _c_prompts():
    p = {}
    p["register-resets"] = (
        "A device that re-sends its registration message after a reboot gets knocked back to `Registered` and stops sending data "
        "until someone re-activates it. A registration of a device that is already registered must be rejected and leave the "
        "device alone."
    )
    p["old-firmware"] = (
        "Devices with firmware 1 and 2 are going active in the field and then fail their first OTA handshake; the activation guard that "
        "requires `MinFirmware` seems to be missing."
    )
    p["heartbeat-everywhere"] = (
        "Heartbeats from retired and not-yet-active devices are counted in the dashboard (a retired sensor shows as 'alive'). Only active "
        "devices may count heartbeats."
    )
    return p


def _base_c() -> Base:
    P = _c_prompts()
    good = {"README.md": C_README, "go.mod": langs.go_mod("fleet"), "fleet.go": C_FLEET}
    f = "fleet.go"
    bugs = [
        Bug("register-restarts-the-device", 3, {f: [("\tcase Retired:\n\t\treturn ErrState\n\tdefault:\n\t\treturn ErrAlreadyRegistered\n\t}\n", "\tcase Retired:\n\t\treturn ErrState\n\tdefault:\n\t\td.State = Registered\n\t\treturn nil\n\t}\n")]}, P["register-resets"]),
        Bug("activate-ignores-firmware", 3, {f: [("\tif d.Firmware < MinFirmware {\n\t\treturn ErrOldFirmware\n\t}\n", "")]}, P["old-firmware"]),
        Bug("heartbeat-in-any-live-state", 1, {f: [("\tif d.State != Active {\n\t\treturn ErrState\n\t}\n\td.Beats++\n", "\tif d.State == New {\n\t\treturn ErrState\n\t}\n\td.Beats++\n")]}, P["heartbeat-everywhere"]),
    ]
    return Base("fleet", "go", good, C_VISIBLE, C_HIDDEN, bugs)


@family("fix-hand-state-guard", category="fix", lang="python", kind="fix", n=14,
        summary="state machines that skip a guard: document approval (python), order lifecycle (java), device fleet (go)")
def gen(rng, n):
    return tasks_from([_base_a(), _base_b(), _base_c()])

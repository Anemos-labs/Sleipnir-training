"""vouchers (java): a gift-voucher ledger extended with batches, extensions, holders, minimums, retries, audit and transfers."""
import random

from fx import dd
from generators.feature._slices import App, Slice, fmt, register_app

README = dd('''
    # vouchers

    The ledger behind a shop's gift vouchers (Java 17, standard library only). Money is in cents, time is a plain whole
    number of days (day 0 is the day the shop opened). The tests are a plain `TestMain` (no JUnit):
    `javac -d build $(find . -name '*.java') && java -cp build TestMain`.

    ## Layout

    * `src/vouchers/VoucherBook.java`: the rules.
    * `src/vouchers/Voucher.java`: one voucher.
    * `test/TestMain.java`: tests.

    ## Basics

    * `VoucherBook.issue(code, valueCents, expiresDay)` creates and returns a `Voucher`. The code must match
      `[A-Z0-9][A-Z0-9-]{2,23}`, the value must be positive and the expiry day not negative (`IllegalArgumentException`);
      a code that already exists is an `IllegalStateException`.
    * `Voucher` has `code()`, `initialCents()`, `balanceCents()` and `expiresDay()`. `VoucherBook.voucher(code)` returns the
      voucher (`NoSuchElementException` for an unknown code) and `balance(code)` its balance.
    * `VoucherBook.redeem(code, amountCents, day)` takes money off a voucher and returns the balance that is left. The amount
      must be positive and the day not negative (`IllegalArgumentException`). A voucher can be used up to and including its
      expiry day: later days are an `IllegalStateException`, and so is an amount larger than the balance. Partial use is fine.
      Unknown codes are a `NoSuchElementException`. A failed call changes nothing.
''')

BOOK = '''\
package vouchers;

import java.util.*;
@@uniq imports

/** All vouchers of the shop. */
public class VoucherBook {
    private final Map<String, Voucher> vouchers = new LinkedHashMap<>();
    @@slot fields

    public Voucher issue(String code, int valueCents, int expiresDay) {
        if (code == null || !code.matches("[A-Z0-9][A-Z0-9-]{2,23}")) {
            throw new IllegalArgumentException("bad voucher code: " + code);
        }
        if (valueCents <= 0) {
            throw new IllegalArgumentException("value must be positive");
        }
        if (expiresDay < 0) {
            throw new IllegalArgumentException("expiry day must not be negative");
        }
        if (vouchers.containsKey(code)) {
            throw new IllegalStateException("duplicate code: " + code);
        }
        @@slot issue_checks
        Voucher v = new Voucher(code, valueCents, expiresDay);
        vouchers.put(code, v);
        @@slot on_issue
        return v;
    }

    public Voucher voucher(String code) {
        Voucher v = vouchers.get(code);
        if (v == null) {
            throw new NoSuchElementException("no such voucher: " + code);
        }
        return v;
    }

    public int balance(String code) {
        return voucher(code).balanceCents();
    }

    public int redeem(String code, int amountCents, int day) {
        Voucher v = voucher(code);
        if (amountCents <= 0) {
            throw new IllegalArgumentException("amount must be positive");
        }
        if (day < 0) {
            throw new IllegalArgumentException("day must not be negative");
        }
        if (day > v.expiresDay()) {
            throw new IllegalStateException("voucher expired on day " + v.expiresDay());
        }
        if (amountCents > v.balanceCents()) {
            throw new IllegalStateException("balance is only " + v.balanceCents());
        }
        @@slot redeem_checks
        v.setBalance(v.balanceCents() - amountCents);
        @@slot on_redeem
        return v.balanceCents();
    }

    @@blocks methods
}
'''

VOUCHER = '''\
package vouchers;

/** One gift voucher. */
public final class Voucher {
    private final String code;
    private final int initialCents;
    private int balanceCents;
    private int expiresDay;
    @@slot fields

    Voucher(String code, int initialCents, int expiresDay) {
        this.code = code;
        this.initialCents = initialCents;
        this.balanceCents = initialCents;
        this.expiresDay = expiresDay;
        @@slot ctor
    }

    public String code() {
        return code;
    }

    public int initialCents() {
        return initialCents;
    }

    public int balanceCents() {
        return balanceCents;
    }

    public int expiresDay() {
        return expiresDay;
    }

    void setBalance(int cents) {
        this.balanceCents = cents;
    }

    void setExpiresDay(int day) {
        this.expiresDay = day;
    }

    @@blocks methods
}
'''

TEST_HEAD = '''\
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.util.*;
import vouchers.*;
@@uniq imports

public class TestMain {
    static int failures = 0;

    static void eq(Object expected, Object actual, String msg) {
        if (!Objects.equals(expected, actual)) {
            failures++;
            System.out.println("FAIL: " + msg + ": expected <" + expected + "> but got <" + actual + ">");
        }
    }

    static void check(boolean cond, String msg) {
        if (!cond) {
            failures++;
            System.out.println("FAIL: " + msg);
        }
    }

    static void expect(Class<? extends Throwable> type, Runnable r, String msg) {
        try {
            r.run();
        } catch (Throwable t) {
            if (!type.isInstance(t)) {
                failures++;
                System.out.println("FAIL: " + msg + ": threw " + t);
            }
            return;
        }
        failures++;
        System.out.println("FAIL: " + msg + ": no exception");
    }

    static VoucherBook book() {
        VoucherBook b = new VoucherBook();
        b.issue("A-100", 5000, 30);
        b.issue("B-200", 2000, 10);
        return b;
    }

    static List<String> list(String... xs) {
        return new ArrayList<>(Arrays.asList(xs));
    }

    @@blocks tests

    public static void main(String[] args) throws Exception {
        List<Method> tests = new ArrayList<>();
        for (Method m : TestMain.class.getDeclaredMethods()) {
            if (m.getName().startsWith("test") && m.getParameterCount() == 0) {
                tests.add(m);
            }
        }
        tests.sort(Comparator.comparing(Method::getName));
        for (Method m : tests) {
            try {
                m.invoke(null);
            } catch (InvocationTargetException e) {
                failures++;
                System.out.println("ERROR in " + m.getName() + ": " + e.getCause());
                e.getCause().printStackTrace(System.out);
            }
        }
        System.out.println(tests.size() + " tests, " + failures + " failures");
        if (failures > 0) {
            System.exit(1);
        }
    }
}
'''

VISIBLE_BASE = '''
    static void testIssueAndBalance() {
        VoucherBook b = book();
        Voucher v = b.voucher("A-100");
        eq(5000, v.initialCents(), "initial");
        eq(5000, b.balance("A-100"), "balance");
        eq(30, v.expiresDay(), "expiry");
        expect(IllegalStateException.class, () -> b.issue("A-100", 100, 5), "duplicate");
        expect(IllegalArgumentException.class, () -> b.issue("ab", 100, 5), "bad code");
        expect(java.util.NoSuchElementException.class, () -> b.voucher("Z-999"), "unknown");
    }

    static void testRedeem() {
        VoucherBook b = book();
        eq(3500, b.redeem("A-100", 1500, 5), "partial");
        eq(3500, b.balance("A-100"), "balance after");
        eq(0, b.redeem("A-100", 3500, 30), "use up on the expiry day");
        expect(IllegalStateException.class, () -> b.redeem("B-200", 100, 11), "expired");
        expect(IllegalStateException.class, () -> b.redeem("B-200", 2001, 1), "too much");
    }
'''

HIDDEN_BASE = '''
    static void testBaseValidation() {
        VoucherBook b = book();
        for (String bad : new String[] {null, "", "AB", "a-100", "-AB1", "AB 1", "A".repeat(25)}) {
            expect(IllegalArgumentException.class, () -> b.issue(bad, 100, 5), "bad code " + bad);
        }
        b.issue("ABC", 1, 0);
        b.issue("A".repeat(24), 1, 0);
        expect(IllegalArgumentException.class, () -> b.issue("OK-1", 0, 5), "zero value");
        expect(IllegalArgumentException.class, () -> b.issue("OK-1", -5, 5), "negative value");
        expect(IllegalArgumentException.class, () -> b.issue("OK-1", 5, -1), "negative expiry");
        expect(IllegalStateException.class, () -> b.issue("ABC", 5, 5), "duplicate wins over nothing");
        check(b.voucher("ABC").expiresDay() == 0, "failed issues changed nothing");
        expect(IllegalArgumentException.class, () -> b.redeem("A-100", 0, 5), "zero amount");
        expect(IllegalArgumentException.class, () -> b.redeem("A-100", -1, 5), "negative amount");
        expect(IllegalArgumentException.class, () -> b.redeem("A-100", 10, -1), "negative day");
        expect(java.util.NoSuchElementException.class, () -> b.redeem("NOPE", 10, 1), "unknown code");
        expect(java.util.NoSuchElementException.class, () -> b.balance("NOPE"), "unknown balance");
        eq(4990, b.redeem("A-100", 10, 0), "day 0 is valid");
        eq(0, b.redeem("ABC", 1, 0), "expiry day itself");
        expect(IllegalStateException.class, () -> b.redeem("ABC", 1, 0), "empty voucher");
        eq(4990, b.balance("A-100"), "failed redeems changed nothing");
        eq(5000, b.voucher("A-100").initialCents(), "initial value stays");
    }
'''


def make_slices(rng: random.Random):
    batch_max = rng.choice([50, 100, 999])
    min_default = rng.choice([500, 1000])
    cap = rng.choice([20000, 50000])
    S = []

    S.append(Slice(
        id="batch", title="Bulk issue", d=1,
        pitch=("The promotion needs a few hundred vouchers with sequential codes and typing them in one by one is out of the question.",
               "Marketing orders vouchers in batches."),
        reqs=(f"`issueBatch(prefix, count, valueCents, expiresDay)` issues `count` vouchers (1 to {batch_max}) and returns them in order. The codes are the prefix, a dash and a three-digit number counting from 001 (`SPRING-001`, `SPRING-002`, ...). The prefix must be 1 to 12 characters of `A-Z0-9` (`IllegalArgumentException` otherwise, like a `count` outside the range); the value and expiry follow the rules of `issue`.",
              "It is all or nothing: if any of the codes already exists, an `IllegalStateException` is thrown and no voucher of the batch is created."),
        code={
            "src/vouchers/VoucherBook.java::methods": f'''
                public List<Voucher> issueBatch(String prefix, int count, int valueCents, int expiresDay) {{
                    if (prefix == null || !prefix.matches("[A-Z0-9]{{1,12}}")) {{
                        throw new IllegalArgumentException("bad prefix: " + prefix);
                    }}
                    if (count < 1 || count > {batch_max}) {{
                        throw new IllegalArgumentException("count must be between 1 and {batch_max}");
                    }}
                    for (int i = 1; i <= count; i++) {{
                        if (vouchers.containsKey(String.format("%s-%03d", prefix, i))) {{
                            throw new IllegalStateException("duplicate code: " + String.format("%s-%03d", prefix, i));
                        }}
                    }}
                    List<Voucher> out = new ArrayList<>();
                    for (int i = 1; i <= count; i++) {{
                        out.add(issue(String.format("%s-%03d", prefix, i), valueCents, expiresDay));
                    }}
                    return out;
                }}
            ''',
        },
        readme=f"## Bulk issue\n\n`issueBatch(prefix, count, valueCents, expiresDay)` issues up to {batch_max} vouchers coded `PREFIX-001`, `PREFIX-002`, ... all or nothing.\n",
        vtests='''
            static void testBatchBasic() {
                VoucherBook b = new VoucherBook();
                eq(3, b.issueBatch("PROMO", 3, 1000, 20).size(), "three vouchers");
            }
        ''',
        tests=fmt('''
            static void testIssueBatch() {
                VoucherBook b = new VoucherBook();
                List<Voucher> made = b.issueBatch("SPRING", 3, 1500, 40);
                eq(list("SPRING-001", "SPRING-002", "SPRING-003"), codes(made), "codes");
                eq(1500, b.balance("SPRING-002"), "value");
                eq(40, b.voucher("SPRING-003").expiresDay(), "expiry");
                eq(__MAX__, b.issueBatch("BIG", __MAX__, 100, 5).size(), "maximum batch");
                eq(String.format("BIG-%03d", __MAX__), b.voucher(String.format("BIG-%03d", __MAX__)).code(), "last code");
                b.issue("X-001", 10, 1);
            }

            static void testIssueBatchIsAllOrNothing() {
                VoucherBook b = new VoucherBook();
                b.issue("MIX-003", 10, 1);
                expect(IllegalStateException.class, () -> b.issueBatch("MIX", 5, 100, 9), "collision");
                expect(java.util.NoSuchElementException.class, () -> b.voucher("MIX-001"), "nothing was created");
                eq(10, b.balance("MIX-003"), "existing voucher untouched");
                eq(2, b.issueBatch("MIX", 2, 100, 9).size(), "a smaller batch fits");
            }

            static void testIssueBatchValidation() {
                VoucherBook b = new VoucherBook();
                expect(IllegalArgumentException.class, () -> b.issueBatch("lower", 2, 100, 9), "lower-case prefix");
                expect(IllegalArgumentException.class, () -> b.issueBatch("", 2, 100, 9), "empty prefix");
                expect(IllegalArgumentException.class, () -> b.issueBatch(null, 2, 100, 9), "null prefix");
                expect(IllegalArgumentException.class, () -> b.issueBatch("A".repeat(13), 2, 100, 9), "long prefix");
                expect(IllegalArgumentException.class, () -> b.issueBatch("OK", 0, 100, 9), "zero count");
                expect(IllegalArgumentException.class, () -> b.issueBatch("OK", __MAX__ + 1, 100, 9), "too many");
                expect(IllegalArgumentException.class, () -> b.issueBatch("OK", 2, 0, 9), "zero value");
                expect(IllegalArgumentException.class, () -> b.issueBatch("OK", 2, 100, -1), "negative expiry");
                expect(java.util.NoSuchElementException.class, () -> b.voucher("OK-001"), "nothing created");
                eq(1, b.issueBatch("A".repeat(12), 1, 100, 0).size(), "12-character prefix");
            }

            static List<String> codes(List<Voucher> vs) {
                List<String> out = new ArrayList<>();
                for (Voucher v : vs) {
                    out.add(v.code());
                }
                return out;
            }
        ''', MAX=batch_max),
    ))

    S.append(Slice(
        id="extend", title="Extending validity", d=2,
        pitch=("Customers phone in after the expiry date and the shop wants to be generous in a controlled way.",
               "Support needs to extend vouchers."),
        reqs=("`extend(code, newExpiresDay)` moves the expiry of a voucher later and returns the voucher. The new day must be after the current expiry day (`IllegalArgumentException` otherwise); an unknown code is a `NoSuchElementException`. A voucher that has already expired can be extended; whether it is expired is decided only by the day given to `redeem`.",),
        code={
            "src/vouchers/VoucherBook.java::methods": '''
                public Voucher extend(String code, int newExpiresDay) {
                    Voucher v = voucher(code);
                    if (newExpiresDay <= v.expiresDay()) {
                        throw new IllegalArgumentException("new expiry must be later than day " + v.expiresDay());
                    }
                    v.setExpiresDay(newExpiresDay);
                    @@slot on_extend
                    return v;
                }
            ''',
        },
        readme="## Extending validity\n\n`extend(code, newExpiresDay)` moves the expiry later (it must be later than the current one); expired vouchers can be extended.\n",
        vtests='''
            static void testExtendBasic() {
                VoucherBook b = book();
                b.extend("B-200", 50);
                eq(50, b.voucher("B-200").expiresDay(), "extended");
            }
        ''',
        tests='''
            static void testExtend() {
                VoucherBook b = book();
                expect(IllegalStateException.class, () -> b.redeem("B-200", 100, 12), "expired first");
                Voucher v = b.extend("B-200", 20);
                eq("B-200", v.code(), "returns the voucher");
                eq(20, b.voucher("B-200").expiresDay(), "new expiry");
                eq(1900, b.redeem("B-200", 100, 12), "usable again");
                expect(IllegalStateException.class, () -> b.redeem("B-200", 100, 21), "expires on the new day");
                expect(IllegalArgumentException.class, () -> b.extend("B-200", 20), "same day");
                expect(IllegalArgumentException.class, () -> b.extend("B-200", 5), "earlier day");
                eq(20, b.voucher("B-200").expiresDay(), "failed extends change nothing");
                expect(java.util.NoSuchElementException.class, () -> b.extend("NOPE", 99), "unknown");
            }
        ''',
    ))

    S.append(Slice(
        id="holder", title="Named vouchers", d=2,
        pitch=("Corporate vouchers must only be spent by the employee they were issued to.",
               "Some vouchers are personal and must not be redeemed by anyone else."),
        reqs=("`bind(code, holder)` ties a voucher to a holder (a non-blank string, else `IllegalArgumentException`; unknown code: `NoSuchElementException`) and `Voucher.holder()` returns the holder (`null` for an unbound voucher). Binding is permanent: binding a voucher that already has a holder is an `IllegalStateException`.",
              "`redeemFor(holder, code, amountCents, day)` is `redeem` on behalf of a person: for a bound voucher the holder must be the same string, otherwise `IllegalStateException`; an unbound voucher can be redeemed by anyone. Plain `redeem` on a bound voucher is an `IllegalStateException`. The holder rule is checked after the checks `redeem` already does and a refused call changes nothing."),
        code={
            "src/vouchers/Voucher.java::fields": "private String holder;",
            "src/vouchers/Voucher.java::methods": '''
                public String holder() {
                    return holder;
                }

                void setHolder(String holder) {
                    this.holder = holder;
                }
            ''',
            "src/vouchers/VoucherBook.java::fields": "private String actingHolder;",
            "src/vouchers/VoucherBook.java::redeem_checks": '''
                if (v.holder() != null && !v.holder().equals(actingHolder)) {
                    throw new IllegalStateException("voucher belongs to " + v.holder());
                }
            ''',
            "src/vouchers/VoucherBook.java::methods": '''
                public void bind(String code, String holder) {
                    Voucher v = voucher(code);
                    if (holder == null || holder.isBlank()) {
                        throw new IllegalArgumentException("holder is required");
                    }
                    if (v.holder() != null) {
                        throw new IllegalStateException("voucher already belongs to " + v.holder());
                    }
                    v.setHolder(holder);
                    @@slot on_bind
                }

                public int redeemFor(String holder, String code, int amountCents, int day) {
                    actingHolder = holder;
                    try {
                        return redeem(code, amountCents, day);
                    } finally {
                        actingHolder = null;
                    }
                }
            ''',
        },
        readme="## Named vouchers\n\n`bind(code, holder)` (permanent) and `Voucher.holder()`; `redeemFor(holder, code, amount, day)` must match the holder of a bound voucher, and plain `redeem` refuses bound vouchers.\n",
        vtests='''
            static void testBindBasic() {
                VoucherBook b = book();
                b.bind("A-100", "ana");
                eq("ana", b.voucher("A-100").holder(), "holder");
            }
        ''',
        tests='''
            static void testBinding() {
                VoucherBook b = book();
                check(b.voucher("A-100").holder() == null, "unbound by default");
                b.bind("A-100", "ana");
                eq("ana", b.voucher("A-100").holder(), "holder");
                expect(IllegalStateException.class, () -> b.bind("A-100", "bob"), "rebind");
                expect(IllegalStateException.class, () -> b.bind("A-100", "ana"), "rebind to the same person");
                expect(IllegalArgumentException.class, () -> b.bind("B-200", " "), "blank holder");
                expect(IllegalArgumentException.class, () -> b.bind("B-200", null), "null holder");
                expect(java.util.NoSuchElementException.class, () -> b.bind("NOPE", "ana"), "unknown");
                check(b.voucher("B-200").holder() == null, "failed binds change nothing");
            }

            static void testRedeemFor() {
                VoucherBook b = book();
                b.bind("A-100", "ana");
                expect(IllegalStateException.class, () -> b.redeem("A-100", 100, 1), "plain redeem of a bound voucher");
                expect(IllegalStateException.class, () -> b.redeemFor("bob", "A-100", 100, 1), "wrong holder");
                expect(IllegalStateException.class, () -> b.redeemFor(null, "A-100", 100, 1), "no holder");
                eq(5000, b.balance("A-100"), "refusals change nothing");
                eq(4900, b.redeemFor("ana", "A-100", 100, 1), "right holder");
                eq(1900, b.redeemFor("anyone", "B-200", 100, 1), "unbound vouchers are open");
                eq(1800, b.redeem("B-200", 100, 1), "plain redeem still works for unbound vouchers");
                expect(IllegalStateException.class, () -> b.redeemFor("ana", "A-100", 99999, 1), "balance is still checked");
                expect(IllegalStateException.class, () -> b.redeemFor("ana", "B-200", 100, 11), "expiry is still checked");
                expect(IllegalArgumentException.class, () -> b.redeemFor("ana", "A-100", 0, 1), "amount is still checked");
                eq(4900, b.balance("A-100"), "still 4900");
            }
        ''',
    ))

    S.append(Slice(
        id="min-spend", title="Minimum spend", d=2,
        pitch=("Redeeming 20 cents at a time clogs the tills.",
               "The shop wants to stop tiny partial redemptions."),
        reqs=(f"`VoucherBook.setMinimum(code, cents)` sets the smallest amount that may be taken off a voucher in one `redeem` (`cents` at least 0, otherwise `IllegalArgumentException`; unknown code: `NoSuchElementException`; 0 means no minimum). New vouchers have no minimum.",
              "`redeem` of an amount below the minimum is an `IllegalArgumentException`, except when the amount is exactly the whole remaining balance (so the last crumbs can always be used up). The check comes after the existing ones and a refused call changes nothing.",
              f"`VoucherBook.DEFAULT_MINIMUM` is a public `int` constant, {min_default}, that `setMinimum` callers can use as a standard value; it is not applied automatically."),
        code={
            "src/vouchers/Voucher.java::fields": "private int minimumCents;",
            "src/vouchers/Voucher.java::methods": '''
                public int minimumCents() {
                    return minimumCents;
                }

                void setMinimum(int cents) {
                    this.minimumCents = cents;
                }
            ''',
            "src/vouchers/VoucherBook.java::fields": f"public static final int DEFAULT_MINIMUM = {min_default};",
            "src/vouchers/VoucherBook.java::redeem_checks": '''
                if (amountCents < v.minimumCents() && amountCents != v.balanceCents()) {
                    throw new IllegalArgumentException("minimum spend is " + v.minimumCents());
                }
            ''',
            "src/vouchers/VoucherBook.java::methods": '''
                public void setMinimum(String code, int cents) {
                    Voucher v = voucher(code);
                    if (cents < 0) {
                        throw new IllegalArgumentException("minimum must not be negative");
                    }
                    v.setMinimum(cents);
                }
            ''',
        },
        readme=f"## Minimum spend\n\n`setMinimum(code, cents)` sets the smallest amount per `redeem` (0 = none); the whole remaining balance can always be taken. `VoucherBook.DEFAULT_MINIMUM` is {min_default}.\n",
        vtests='''
            static void testMinimumBasic() {
                VoucherBook b = book();
                b.setMinimum("A-100", 500);
                expect(IllegalArgumentException.class, () -> b.redeem("A-100", 100, 1), "below minimum");
            }
        ''',
        tests=fmt('''
            static void testMinimum() {
                VoucherBook b = book();
                eq(__D__, VoucherBook.DEFAULT_MINIMUM, "constant");
                eq(4900, b.redeem("A-100", 100, 1), "no minimum by default");
                b.setMinimum("A-100", 1000);
                expect(IllegalArgumentException.class, () -> b.redeem("A-100", 999, 1), "just below");
                eq(4900, b.balance("A-100"), "refused call changes nothing");
                eq(3900, b.redeem("A-100", 1000, 1), "exactly the minimum");
                eq(1900, b.redeem("A-100", 2000, 1), "above the minimum");
                eq(900, b.redeem("A-100", 1000, 1), "again");
                eq(0, b.redeem("A-100", 900, 1), "the whole remaining balance is allowed");
                b.setMinimum("A-100", 0);
                b.setMinimum("B-200", 50);
                eq(1950, b.redeem("B-200", 50, 1), "small minimum");
            }

            static void testMinimumValidationAndOrder() {
                VoucherBook b = book();
                expect(IllegalArgumentException.class, () -> b.setMinimum("A-100", -1), "negative minimum");
                expect(java.util.NoSuchElementException.class, () -> b.setMinimum("NOPE", 5), "unknown code");
                b.setMinimum("B-200", 500);
                expect(IllegalStateException.class, () -> b.redeem("B-200", 100, 11), "expiry is reported first");
                expect(IllegalStateException.class, () -> b.redeem("B-200", 5000, 1), "so is a too large amount");
                eq(2000, b.balance("B-200"), "unchanged");
            }
        ''', D=min_default),
    ))
    return S


APP = App(
    name="vouchers", lang="java", title="the gift voucher ledger", role="a shop owner", key="VCH",
    base={
        "README.md": README + "\n@@blocks features\n",
        "src/vouchers/VoucherBook.java": BOOK,
        "src/vouchers/Voucher.java": VOUCHER,
        ".gitignore": "build/\n",
    },
    visible={"test/TestMain.java": TEST_HEAD.replace("@@blocks tests", VISIBLE_BASE + "\n    @@blocks tests")},
    hidden={"test/TestMain.java": TEST_HEAD.replace("@@blocks tests", HIDDEN_BASE + "\n    @@blocks tests")},
)

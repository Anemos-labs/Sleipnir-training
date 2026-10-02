"""Library loans: due dates, renewals, fines and a holds queue (java): bugs injected into a circulation-desk library."""
from fx import Lib, dd
from generators.fix._lang2 import JAVA_CHECK, java_test_main, register_libs

README = dd(r'''
    # loandesk

    The circulation desk of a small public library. Plain Java 17, no dependencies; sources in `src/lending/`.

    Days are whole numbers of days since 1970-01-01 (day `0` was a Thursday, so day `4` is a Monday and day `3` a Sunday).
    Money is `int` cents.

    ## `ItemClass` and `PatronTier`

    | class | loan days | renewals | fine per open day | fine cap |
    |---|---|---|---|---|
    | `BOOK` | 21 | 2 | 25 | 1000 |
    | `DVD` | 7 | 1 | 100 | 2000 |
    | `PERIODICAL` | 7 | 0 | 15 | 200 |
    | `TOOL` | 3 | 1 | 500 | 5000 |

    Fields: `days`, `maxRenewals`, `finePerDay`, `fineCap`. Tiers: `STANDARD`, `SENIOR`, `CHILD`, `STAFF`.

    * Loan period (`LoanDesk.period(cls, tier)`): `cls.days`, plus 7 for `SENIOR`, doubled for `STAFF`.
    * Renewals allowed: `cls.maxRenewals`, plus one more for `STAFF`.
    * Daily fine rate (`LoanDesk.rate(cls, tier)`): `cls.finePerDay`; `STAFF` pay nothing; `CHILD` pay half, rounded half up
      (25 becomes 13).

    ## `Calendar(Set<Integer> holidays)`

    * `weekday(day)`: `0` for Monday up to `6` for Sunday (works for negative days too).
    * `isOpen(day)`: the library is closed on Sundays and on the holidays.
    * `nextOpen(day)`: the first open day on or after `day`.
    * `openDaysBetween(from, to)`: the number of open days after `from` up to and including `to` (`0` when `to <= from`).

    ## `LoanDesk(Calendar calendar)`

    * `checkout(cls, tier, day)` returns a `Loan` (`cls`, `tier`, `checkout`, `due`, `renewals`) due on
      `calendar.nextOpen(day + period)`, with `0` renewals.
    * `renew(loan, day, holdsWaiting)` returns a new `Loan` with `renewals + 1`. It throws `IllegalArgumentException` when `day`
      is before the checkout day, and `IllegalStateException` when other patrons wait for the item (`holdsWaiting > 0`), when no
      renewals are left, or when the item is already overdue (`day > due`; renewing *on* the due day is fine). The new due day is
      `nextOpen(max(day, oldDue) + period)`: renewing early does not lose the days that were left.
    * `fine(loan, returnDay)`: `0` when `returnDay <= due`. Otherwise the number of open days late is
      `openDaysBetween(due, returnDay)`; the first of them is a grace day, so the billable days are one fewer (never below 0);
      the fine is billable days times the daily rate, at most `fineCap`. `returnDay` before the checkout day is an
      `IllegalArgumentException`.

    ## `HoldQueue`

    Hold lists per item id (a `String`). The order inside a queue: `SENIOR` and `CHILD` patrons first, then `STANDARD`, then
    `STAFF`; within the same group by the order in which the holds were placed.

    * `place(itemId, patronId, tier)`: adds a hold; a patron who already waits for that item gives `IllegalStateException`.
    * `position(itemId, patronId)`: 1-based place in the queue, `0` if the patron is not waiting.
    * `size(itemId)`: number of holds (`0` for unknown items).
    * `pop(itemId)`: removes the first hold and returns the patron id, or `null` for an empty queue.
    * `cancel(itemId, patronId)`: removes the hold, returning whether there was one.
''')

ITEMCLASS = dd(r'''
    package lending;

    public enum ItemClass {
        BOOK(21, 2, 25, 1000),
        DVD(7, 1, 100, 2000),
        PERIODICAL(7, 0, 15, 200),
        TOOL(3, 1, 500, 5000);

        public final int days;
        public final int maxRenewals;
        public final int finePerDay;
        public final int fineCap;

        ItemClass(int days, int maxRenewals, int finePerDay, int fineCap) {
            this.days = days;
            this.maxRenewals = maxRenewals;
            this.finePerDay = finePerDay;
            this.fineCap = fineCap;
        }
    }
''')

TIER = dd(r'''
    package lending;

    public enum PatronTier {
        STANDARD,
        SENIOR,
        CHILD,
        STAFF
    }
''')

LOAN = dd(r'''
    package lending;

    public final class Loan {
        public final ItemClass cls;
        public final PatronTier tier;
        public final int checkout;
        public final int due;
        public final int renewals;

        public Loan(ItemClass cls, PatronTier tier, int checkout, int due, int renewals) {
            this.cls = cls;
            this.tier = tier;
            this.checkout = checkout;
            this.due = due;
            this.renewals = renewals;
        }
    }
''')

CALENDAR = dd(r'''
    package lending;

    import java.util.HashSet;
    import java.util.Set;

    public final class Calendar {
        private final Set<Integer> holidays;

        public Calendar(Set<Integer> holidays) {
            this.holidays = new HashSet<>(holidays);
        }

        public int weekday(int day) {
            return Math.floorMod(day + 3, 7);
        }

        public boolean isOpen(int day) {
            return weekday(day) != 6 && !holidays.contains(day);
        }

        public int nextOpen(int day) {
            int d = day;
            while (!isOpen(d)) {
                d++;
            }
            return d;
        }

        public int openDaysBetween(int from, int to) {
            int n = 0;
            for (int d = from + 1; d <= to; d++) {
                if (isOpen(d)) {
                    n++;
                }
            }
            return n;
        }
    }
''')

DESK = dd(r'''
    package lending;

    public final class LoanDesk {
        private final Calendar calendar;

        public LoanDesk(Calendar calendar) {
            this.calendar = calendar;
        }

        public static int period(ItemClass cls, PatronTier tier) {
            if (tier == PatronTier.SENIOR) {
                return cls.days + 7;
            }
            if (tier == PatronTier.STAFF) {
                return cls.days * 2;
            }
            return cls.days;
        }

        public static int rate(ItemClass cls, PatronTier tier) {
            if (tier == PatronTier.STAFF) {
                return 0;
            }
            if (tier == PatronTier.CHILD) {
                return (cls.finePerDay + 1) / 2;
            }
            return cls.finePerDay;
        }

        public Loan checkout(ItemClass cls, PatronTier tier, int day) {
            return new Loan(cls, tier, day, calendar.nextOpen(day + period(cls, tier)), 0);
        }

        public Loan renew(Loan loan, int day, int holdsWaiting) {
            if (day < loan.checkout) {
                throw new IllegalArgumentException("day is before the checkout");
            }
            if (holdsWaiting > 0) {
                throw new IllegalStateException("the item is on hold");
            }
            int allowed = loan.cls.maxRenewals + (loan.tier == PatronTier.STAFF ? 1 : 0);
            if (loan.renewals >= allowed) {
                throw new IllegalStateException("no renewals left");
            }
            if (day > loan.due) {
                throw new IllegalStateException("the item is overdue");
            }
            int due = calendar.nextOpen(Math.max(day, loan.due) + period(loan.cls, loan.tier));
            return new Loan(loan.cls, loan.tier, loan.checkout, due, loan.renewals + 1);
        }

        public int fine(Loan loan, int returnDay) {
            if (returnDay < loan.checkout) {
                throw new IllegalArgumentException("returned before checkout");
            }
            if (returnDay <= loan.due) {
                return 0;
            }
            int late = calendar.openDaysBetween(loan.due, returnDay);
            int billable = Math.max(0, late - 1);
            long fine = (long) billable * rate(loan.cls, loan.tier);
            return (int) Math.min(fine, loan.cls.fineCap);
        }
    }
''')

QUEUE = dd(r'''
    package lending;

    import java.util.ArrayList;
    import java.util.HashMap;
    import java.util.List;
    import java.util.Map;

    public final class HoldQueue {
        private static final class Hold {
            final String patron;
            final PatronTier tier;
            final int seq;

            Hold(String patron, PatronTier tier, int seq) {
                this.patron = patron;
                this.tier = tier;
                this.seq = seq;
            }
        }

        private final Map<String, List<Hold>> queues = new HashMap<>();
        private int counter = 0;

        private static int group(PatronTier tier) {
            switch (tier) {
                case SENIOR:
                case CHILD:
                    return 0;
                case STANDARD:
                    return 1;
                default:
                    return 2;
            }
        }

        private List<Hold> queue(String itemId) {
            return queues.computeIfAbsent(itemId, k -> new ArrayList<>());
        }

        public void place(String itemId, String patronId, PatronTier tier) {
            List<Hold> q = queue(itemId);
            for (Hold h : q) {
                if (h.patron.equals(patronId)) {
                    throw new IllegalStateException("already waiting");
                }
            }
            counter++;
            q.add(new Hold(patronId, tier, counter));
            q.sort((a, b) -> group(a.tier) != group(b.tier) ? Integer.compare(group(a.tier), group(b.tier)) : Integer.compare(a.seq, b.seq));
        }

        public int position(String itemId, String patronId) {
            List<Hold> q = queue(itemId);
            for (int i = 0; i < q.size(); i++) {
                if (q.get(i).patron.equals(patronId)) {
                    return i + 1;
                }
            }
            return 0;
        }

        public int size(String itemId) {
            return queue(itemId).size();
        }

        public String pop(String itemId) {
            List<Hold> q = queue(itemId);
            return q.isEmpty() ? null : q.remove(0).patron;
        }

        public boolean cancel(String itemId, String patronId) {
            return queue(itemId).removeIf(h -> h.patron.equals(patronId));
        }
    }
''')

BASIC = dd(r'''
    import java.util.Set;
    import lending.Calendar;
    import lending.ItemClass;
    import lending.Loan;
    import lending.LoanDesk;
    import lending.PatronTier;

    public class BasicTests {
        public static void run() {
            Check.test("a book is due after three weeks", () -> {
                LoanDesk desk = new LoanDesk(new Calendar(Set.of()));
                Loan loan = desk.checkout(ItemClass.BOOK, PatronTier.STANDARD, 4);
                Check.eq(25, loan.due);
            });
            Check.test("weekday", () -> {
                Calendar cal = new Calendar(Set.of());
                Check.eq(0, cal.weekday(4));
                Check.eq(6, cal.weekday(3));
            });
        }
    }
''')

FULL = dd(r'''
    import java.util.HashSet;
    import java.util.Set;
    import lending.Calendar;
    import lending.HoldQueue;
    import lending.ItemClass;
    import lending.Loan;
    import lending.LoanDesk;
    import lending.PatronTier;

    public class FullTests {
        static Calendar plain() {
            return new Calendar(new HashSet<>());
        }

        static LoanDesk desk() {
            return new LoanDesk(plain());
        }

        public static void run() {
            Check.test("weekdays from the epoch", () -> {
                Calendar c = plain();
                Check.eq(3, c.weekday(0));
                Check.eq(4, c.weekday(1));
                Check.eq(5, c.weekday(2));
                Check.eq(6, c.weekday(3));
                Check.eq(0, c.weekday(4));
                Check.eq(0, c.weekday(25));
                Check.eq(2, c.weekday(-1));
                Check.eq(0, c.weekday(-3));
                Check.eq(6, c.weekday(-4));
                Check.eq(6, c.weekday(10));
            });

            Check.test("sundays and holidays are closed", () -> {
                Calendar c = new Calendar(Set.of(5, 20));
                Check.yes(c.isOpen(4), "monday");
                Check.yes(!c.isOpen(3), "sunday");
                Check.yes(!c.isOpen(10), "sunday");
                Check.yes(!c.isOpen(5), "holiday");
                Check.yes(c.isOpen(6), "wednesday");
                Check.yes(!c.isOpen(20), "holiday");
                Check.yes(c.isOpen(19), "day before holiday");
                Check.yes(c.isOpen(21), "day after holiday");
            });

            Check.test("nextOpen", () -> {
                Calendar c = new Calendar(Set.of(4, 5));
                Check.eq(6, c.nextOpen(3));
                Check.eq(6, c.nextOpen(4));
                Check.eq(6, c.nextOpen(6));
                Check.eq(7, c.nextOpen(7));
                Check.eq(11, c.nextOpen(10));
                Check.eq(2, plain().nextOpen(2));
                Check.eq(4, plain().nextOpen(3));
            });

            Check.test("calendar copies the holiday set", () -> {
                Set<Integer> hol = new HashSet<>(Set.of(5));
                Calendar c = new Calendar(hol);
                hol.add(6);
                Check.yes(c.isOpen(6), "later changes are not seen");
                Check.yes(!c.isOpen(5), "original holiday");
            });

            Check.test("openDaysBetween", () -> {
                Calendar c = new Calendar(Set.of(27));
                Check.eq(0, c.openDaysBetween(25, 25));
                Check.eq(0, c.openDaysBetween(25, 20));
                Check.eq(1, c.openDaysBetween(25, 26));
                Check.eq(1, c.openDaysBetween(25, 27));
                Check.eq(2, c.openDaysBetween(25, 28));
                Check.eq(5, c.openDaysBetween(25, 32));
                Check.eq(5, plain().openDaysBetween(25, 31));
                Check.eq(6, plain().openDaysBetween(25, 32));
                Check.eq(42, plain().openDaysBetween(25, 74));
                Check.eq(0, plain().openDaysBetween(2, 3));
                Check.eq(1, plain().openDaysBetween(2, 4));
            });

            Check.test("periods and rates", () -> {
                Check.eq(21, LoanDesk.period(ItemClass.BOOK, PatronTier.STANDARD));
                Check.eq(28, LoanDesk.period(ItemClass.BOOK, PatronTier.SENIOR));
                Check.eq(21, LoanDesk.period(ItemClass.BOOK, PatronTier.CHILD));
                Check.eq(42, LoanDesk.period(ItemClass.BOOK, PatronTier.STAFF));
                Check.eq(14, LoanDesk.period(ItemClass.DVD, PatronTier.SENIOR));
                Check.eq(14, LoanDesk.period(ItemClass.PERIODICAL, PatronTier.STAFF));
                Check.eq(3, LoanDesk.period(ItemClass.TOOL, PatronTier.STANDARD));
                Check.eq(25, LoanDesk.rate(ItemClass.BOOK, PatronTier.STANDARD));
                Check.eq(25, LoanDesk.rate(ItemClass.BOOK, PatronTier.SENIOR));
                Check.eq(13, LoanDesk.rate(ItemClass.BOOK, PatronTier.CHILD));
                Check.eq(0, LoanDesk.rate(ItemClass.BOOK, PatronTier.STAFF));
                Check.eq(50, LoanDesk.rate(ItemClass.DVD, PatronTier.CHILD));
                Check.eq(8, LoanDesk.rate(ItemClass.PERIODICAL, PatronTier.CHILD));
                Check.eq(250, LoanDesk.rate(ItemClass.TOOL, PatronTier.CHILD));
                Check.eq(100, LoanDesk.rate(ItemClass.DVD, PatronTier.STANDARD));
            });

            Check.test("checkout due dates", () -> {
                LoanDesk d = desk();
                Loan book = d.checkout(ItemClass.BOOK, PatronTier.STANDARD, 4);
                Check.eq(25, book.due);
                Check.eq(4, book.checkout);
                Check.eq(0, book.renewals);
                Check.eq(ItemClass.BOOK, book.cls);
                Check.eq(PatronTier.STANDARD, book.tier);
                Check.eq(32, d.checkout(ItemClass.BOOK, PatronTier.SENIOR, 4).due);
                Check.eq(46, d.checkout(ItemClass.BOOK, PatronTier.STAFF, 4).due);
                Check.eq(12, d.checkout(ItemClass.DVD, PatronTier.STANDARD, 5).due);
                Check.eq(11, d.checkout(ItemClass.PERIODICAL, PatronTier.STANDARD, 3).due);
            });

            Check.test("a due date on a closed day moves to the next open day", () -> {
                LoanDesk d = desk();
                Check.eq(4, d.checkout(ItemClass.TOOL, PatronTier.STANDARD, 0).due);
                LoanDesk h = new LoanDesk(new Calendar(Set.of(4)));
                Check.eq(5, h.checkout(ItemClass.TOOL, PatronTier.STANDARD, 0).due);
                LoanDesk h2 = new LoanDesk(new Calendar(Set.of(4, 5, 6)));
                Check.eq(7, h2.checkout(ItemClass.TOOL, PatronTier.STANDARD, 0).due);
            });

            Check.test("renewing extends from the later of today and the due date", () -> {
                LoanDesk d = desk();
                Loan loan = d.checkout(ItemClass.BOOK, PatronTier.STANDARD, 4);
                Loan once = d.renew(loan, 20, 0);
                Check.eq(46, once.due);
                Check.eq(1, once.renewals);
                Check.eq(4, once.checkout);
                Loan twice = d.renew(once, 40, 0);
                Check.eq(67, twice.due);
                Check.eq(2, twice.renewals);
                Loan onDueDay = d.renew(loan, 25, 0);
                Check.eq(46, onDueDay.due);
            });

            Check.test("renewal lands on an open day", () -> {
                LoanDesk d = desk();
                Loan loan = d.checkout(ItemClass.TOOL, PatronTier.STANDARD, 4);
                Check.eq(7, loan.due);
                Loan r = d.renew(loan, 5, 0);
                Check.eq(11, r.due);
            });

            Check.test("renewal limits per class and tier", () -> {
                LoanDesk d = desk();
                Loan book = d.checkout(ItemClass.BOOK, PatronTier.STANDARD, 4);
                Loan b2 = d.renew(d.renew(book, 5, 0), 6, 0);
                Check.raises(IllegalStateException.class, () -> d.renew(b2, 7, 0));
                Loan staff = d.checkout(ItemClass.BOOK, PatronTier.STAFF, 4);
                Loan s3 = d.renew(d.renew(d.renew(staff, 5, 0), 6, 0), 7, 0);
                Check.eq(3, s3.renewals);
                Check.raises(IllegalStateException.class, () -> d.renew(s3, 8, 0));
                Loan mag = d.checkout(ItemClass.PERIODICAL, PatronTier.STANDARD, 4);
                Check.raises(IllegalStateException.class, () -> d.renew(mag, 5, 0));
                Loan magStaff = d.checkout(ItemClass.PERIODICAL, PatronTier.STAFF, 4);
                Check.eq(1, d.renew(magStaff, 5, 0).renewals);
                Loan dvd = d.checkout(ItemClass.DVD, PatronTier.SENIOR, 4);
                Loan dvd1 = d.renew(dvd, 5, 0);
                Check.raises(IllegalStateException.class, () -> d.renew(dvd1, 6, 0));
            });

            Check.test("renewal refusals", () -> {
                LoanDesk d = desk();
                Loan loan = d.checkout(ItemClass.BOOK, PatronTier.STANDARD, 4);
                Check.raises(IllegalStateException.class, () -> d.renew(loan, 10, 1));
                Check.raises(IllegalStateException.class, () -> d.renew(loan, 10, 5));
                Check.raises(IllegalStateException.class, () -> d.renew(loan, 26, 0));
                Check.raises(IllegalStateException.class, () -> d.renew(loan, 40, 0));
                Check.raises(IllegalArgumentException.class, () -> d.renew(loan, 3, 0));
                Check.eq(1, d.renew(loan, 4, 0).renewals);
                Check.eq(1, d.renew(loan, 25, 0).renewals);
            });

            Check.test("fines: no fine on time and a grace day", () -> {
                LoanDesk d = desk();
                Loan loan = d.checkout(ItemClass.BOOK, PatronTier.STANDARD, 4);
                Check.eq(0, d.fine(loan, 4));
                Check.eq(0, d.fine(loan, 24));
                Check.eq(0, d.fine(loan, 25));
                Check.eq(0, d.fine(loan, 26));
                Check.eq(25, d.fine(loan, 27));
                Check.eq(50, d.fine(loan, 28));
                Check.eq(75, d.fine(loan, 29));
                Check.eq(100, d.fine(loan, 30));
            });

            Check.test("fines: closed days do not count", () -> {
                LoanDesk d = desk();
                Loan loan = d.checkout(ItemClass.BOOK, PatronTier.STANDARD, 4);
                Check.eq(100, d.fine(loan, 31));
                Check.eq(125, d.fine(loan, 32));
                Check.eq(100, d.fine(loan, 31));
                LoanDesk h = new LoanDesk(new Calendar(Set.of(27, 28)));
                Loan l2 = h.checkout(ItemClass.BOOK, PatronTier.STANDARD, 4);
                Check.eq(0, h.fine(l2, 27));
                Check.eq(0, h.fine(l2, 28));
                Check.eq(25, h.fine(l2, 29));
                Check.eq(50, h.fine(l2, 30));
            });

            Check.test("fines: the cap", () -> {
                LoanDesk d = desk();
                Loan loan = d.checkout(ItemClass.BOOK, PatronTier.STANDARD, 4);
                Check.eq(975, d.fine(loan, 71));
                Check.eq(1000, d.fine(loan, 72));
                Check.eq(1000, d.fine(loan, 73));
                Check.eq(1000, d.fine(loan, 74));
                Check.eq(1000, d.fine(loan, 500));
                Loan mag = d.checkout(ItemClass.PERIODICAL, PatronTier.STANDARD, 4);
                Check.eq(0, d.fine(mag, 12));
                Check.eq(15, d.fine(mag, 13));
                Check.eq(195, d.fine(mag, 27));
                Check.eq(200, d.fine(mag, 28));
                Check.eq(200, d.fine(mag, 40));
            });

            Check.test("fines by class and tier", () -> {
                LoanDesk d = desk();
                Loan dvd = d.checkout(ItemClass.DVD, PatronTier.STANDARD, 5);
                Check.eq(12, dvd.due);
                Check.eq(200, d.fine(dvd, 15));
                Loan kid = d.checkout(ItemClass.BOOK, PatronTier.CHILD, 4);
                Check.eq(26, d.fine(kid, 28));
                Check.eq(13, d.fine(kid, 27));
                Loan staff = d.checkout(ItemClass.BOOK, PatronTier.STAFF, 4);
                Check.eq(0, d.fine(staff, 200));
                Loan tool = d.checkout(ItemClass.TOOL, PatronTier.STANDARD, 4);
                Check.eq(7, tool.due);
                Check.eq(0, d.fine(tool, 8));
                Check.eq(500, d.fine(tool, 9));
                Check.eq(1500, d.fine(tool, 12));
                Check.eq(5000, d.fine(tool, 30));
                Loan kidDvd = d.checkout(ItemClass.DVD, PatronTier.CHILD, 5);
                Check.eq(100, d.fine(kidDvd, 15));
            });

            Check.test("fine validation", () -> {
                LoanDesk d = desk();
                Loan loan = d.checkout(ItemClass.BOOK, PatronTier.STANDARD, 10);
                Check.raises(IllegalArgumentException.class, () -> d.fine(loan, 9));
                Check.eq(0, d.fine(loan, 10));
            });

            Check.test("hold queue order", () -> {
                HoldQueue q = new HoldQueue();
                q.place("b1", "ann", PatronTier.STANDARD);
                q.place("b1", "bob", PatronTier.STAFF);
                q.place("b1", "cy", PatronTier.SENIOR);
                q.place("b1", "di", PatronTier.CHILD);
                q.place("b1", "ed", PatronTier.STANDARD);
                Check.eq(5, q.size("b1"));
                Check.eq(1, q.position("b1", "cy"));
                Check.eq(2, q.position("b1", "di"));
                Check.eq(3, q.position("b1", "ann"));
                Check.eq(4, q.position("b1", "ed"));
                Check.eq(5, q.position("b1", "bob"));
                Check.eq(0, q.position("b1", "zed"));
                Check.eq(0, q.position("b2", "ann"));
            });

            Check.test("hold queue pop, cancel and duplicates", () -> {
                HoldQueue q = new HoldQueue();
                q.place("b1", "ann", PatronTier.STANDARD);
                q.place("b1", "cy", PatronTier.SENIOR);
                q.place("b2", "ann", PatronTier.STANDARD);
                Check.raises(IllegalStateException.class, () -> q.place("b1", "ann", PatronTier.STAFF));
                Check.eq("cy", q.pop("b1"));
                Check.eq(1, q.size("b1"));
                Check.yes(!q.cancel("b1", "cy"), "cy is gone");
                Check.yes(q.cancel("b1", "ann"), "ann cancels");
                Check.eq(0, q.size("b1"));
                Check.eq(null, q.pop("b1"));
                Check.eq(null, q.pop("nothing"));
                Check.eq(1, q.size("b2"));
                q.place("b1", "ann", PatronTier.STANDARD);
                Check.eq(1, q.position("b1", "ann"));
                Check.eq(0, q.size("unknown"));
            });

            Check.test("hold queue keeps placement order inside a group", () -> {
                HoldQueue q = new HoldQueue();
                q.place("x", "s1", PatronTier.SENIOR);
                q.place("x", "c1", PatronTier.CHILD);
                q.place("x", "s2", PatronTier.SENIOR);
                q.place("x", "t1", PatronTier.STAFF);
                q.place("x", "t0", PatronTier.STAFF);
                Check.eq("s1", q.pop("x"));
                Check.eq("c1", q.pop("x"));
                Check.eq("s2", q.pop("x"));
                Check.eq("t1", q.pop("x"));
                Check.eq("t0", q.pop("x"));
            });
        }
    }
''')

BASIC_MAIN = java_test_main("BasicTests")
FULL_MAIN = java_test_main("BasicTests", "FullTests")

LIB = Lib(
    name="loandesk", lang="java", title="the loandesk library",
    blurb="The circulation desk of the public library uses loandesk to set due dates, handle renewals, charge fines and order the holds queue.",
    files={"src/lending/ItemClass.java": ITEMCLASS, "src/lending/PatronTier.java": TIER, "src/lending/Loan.java": LOAN,
           "src/lending/Calendar.java": CALENDAR, "src/lending/LoanDesk.java": DESK, "src/lending/HoldQueue.java": QUEUE,
           "README.md": README, ".gitignore": "build/\n"},
    visible_tests={"test/Check.java": JAVA_CHECK, "test/BasicTests.java": BASIC, "test/TestMain.java": BASIC_MAIN},
    hidden_tests={"test/FullTests.java": FULL, "test/TestMain.java": FULL_MAIN},
    mutate=["src/lending/LoanDesk.java", "src/lending/Calendar.java", "src/lending/HoldQueue.java"], difficulty=3, tags=["library", "loans", "fines"],
    probe_import="import java.util.*;\nimport lending.*;",
    probes=[
        "new Calendar(new HashSet<Integer>()).weekday(-4)", "new Calendar(new HashSet<Integer>()).nextOpen(3)", "new Calendar(new HashSet<Integer>(List.of(4, 5))).nextOpen(3)",
        "new Calendar(new HashSet<Integer>()).openDaysBetween(25, 31)", "new Calendar(new HashSet<Integer>()).openDaysBetween(25, 32)", "new Calendar(new HashSet<Integer>(List.of(5))).isOpen(5)",
        "LoanDesk.period(ItemClass.BOOK, PatronTier.SENIOR)", "LoanDesk.period(ItemClass.BOOK, PatronTier.STAFF)", "LoanDesk.rate(ItemClass.BOOK, PatronTier.CHILD)", "LoanDesk.rate(ItemClass.PERIODICAL, PatronTier.CHILD)",
        "new LoanDesk(new Calendar(new HashSet<Integer>())).checkout(ItemClass.TOOL, PatronTier.STANDARD, 0).due",
        "new LoanDesk(new Calendar(new HashSet<Integer>())).checkout(ItemClass.BOOK, PatronTier.SENIOR, 4).due",
        "new LoanDesk(new Calendar(new HashSet<Integer>())).fine(new LoanDesk(new Calendar(new HashSet<Integer>())).checkout(ItemClass.BOOK, PatronTier.STANDARD, 4), 27)",
        "new LoanDesk(new Calendar(new HashSet<Integer>())).fine(new LoanDesk(new Calendar(new HashSet<Integer>())).checkout(ItemClass.BOOK, PatronTier.STANDARD, 4), 31)",
        "new LoanDesk(new Calendar(new HashSet<Integer>())).fine(new LoanDesk(new Calendar(new HashSet<Integer>())).checkout(ItemClass.BOOK, PatronTier.STANDARD, 4), 72)",
        "new LoanDesk(new Calendar(new HashSet<Integer>())).fine(new LoanDesk(new Calendar(new HashSet<Integer>())).checkout(ItemClass.BOOK, PatronTier.CHILD, 4), 28)",
        "new LoanDesk(new Calendar(new HashSet<Integer>())).renew(new LoanDesk(new Calendar(new HashSet<Integer>())).checkout(ItemClass.BOOK, PatronTier.STANDARD, 4), 20, 0).due",
        "new LoanDesk(new Calendar(new HashSet<Integer>())).renew(new LoanDesk(new Calendar(new HashSet<Integer>())).checkout(ItemClass.BOOK, PatronTier.STANDARD, 4), 25, 0).renewals",
        "new LoanDesk(new Calendar(new HashSet<Integer>())).renew(new LoanDesk(new Calendar(new HashSet<Integer>())).checkout(ItemClass.BOOK, PatronTier.STANDARD, 4), 26, 0)",
        "new LoanDesk(new Calendar(new HashSet<Integer>())).renew(new LoanDesk(new Calendar(new HashSet<Integer>())).checkout(ItemClass.PERIODICAL, PatronTier.STAFF, 4), 5, 0).renewals",
    ],
)

register_libs([LIB], n=8)

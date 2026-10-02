"""queuedesk (java): a help-desk ticket queue extended with reopening, bulk close, agents, escalation, tags, SLA, merging, history, limits."""
import random

from fx import dd
from generators.feature._slices import App, Slice, fmt, register_app

README = dd('''
    # queuedesk

    The ticket queue of a small help desk (Java 17, standard library only). Priorities run from 1 (most urgent) to 4, time is a
    plain tick counter that the desk advances by hand. The tests are a plain `TestMain` (no JUnit):
    `javac -d build $(find . -name '*.java') && java -cp build TestMain`.

    ## Layout

    * `src/queuedesk/Desk.java`: the queue.
    * `src/queuedesk/Ticket.java`: one ticket.
    * `test/TestMain.java`: tests.

    ## Basics

    * `Desk.open(subject, priority)` creates and returns a `Ticket` with ids 1, 2, 3, ... The subject must not be blank (it is
      stripped) and the priority must be 1 to 4 (`IllegalArgumentException`). A new ticket is open and remembers the tick it was
      opened at.
    * `Ticket` has `id()`, `subject()`, `priority()`, `openedAt()` and `closed()`. `Desk.get(id)` returns a ticket
      (`NoSuchElementException` for an unknown id).
    * `Desk.tick()` advances the clock by one, `Desk.now()` returns it (it starts at 0).
    * `Desk.openTickets()` lists the open tickets, most urgent first and by id within one priority. `Desk.next()` returns the first
      of them as an `Optional<Ticket>`.
    * `Desk.close(id)` closes an open ticket and returns it (an already closed ticket is an `IllegalStateException`). `Desk.count(open)`
      counts the open (`true`) or closed (`false`) tickets.
''')

DESK = '''\
package queuedesk;

import java.util.*;
@@uniq imports

/** The ticket queue. */
public class Desk {
    private final Map<Integer, Ticket> tickets = new LinkedHashMap<>();
    private int now = 0;
    @@slot fields

    public Ticket open(String subject, int priority) {
        if (subject == null || subject.isBlank()) {
            throw new IllegalArgumentException("subject is required");
        }
        if (priority < 1 || priority > 4) {
            throw new IllegalArgumentException("priority must be 1 to 4");
        }
        @@slot open_checks
        Ticket t = new Ticket(tickets.size() + 1, subject.strip(), priority, now);
        tickets.put(t.id(), t);
        @@slot on_open
        return t;
    }

    public Ticket get(int id) {
        Ticket t = tickets.get(id);
        if (t == null) {
            throw new NoSuchElementException("no ticket " + id);
        }
        return t;
    }

    public void tick() {
        now++;
    }

    public int now() {
        return now;
    }

    public List<Ticket> openTickets() {
        List<Ticket> out = new ArrayList<>();
        for (Ticket t : tickets.values()) {
            if (!t.closed()) {
                out.add(t);
            }
        }
        out.sort(Comparator.comparingInt(Ticket::priority).thenComparingInt(Ticket::id));
        return out;
    }

    @@default next_method
    public Optional<Ticket> next() {
        return openTickets().stream().findFirst();
    }
    @@end

    public Ticket close(int id) {
        Ticket t = get(id);
        if (t.closed()) {
            throw new IllegalStateException("ticket " + id + " is already closed");
        }
        t.setClosed(true);
        @@slot on_close
        return t;
    }

    public int count(boolean open) {
        int n = 0;
        for (Ticket t : tickets.values()) {
            if (t.closed() != open) {
                n++;
            }
        }
        return n;
    }

    @@blocks methods
}
'''

TICKET = '''\
package queuedesk;

import java.util.*;
@@uniq imports

/** One help-desk ticket. */
public final class Ticket {
    private final int id;
    private final String subject;
    private int priority;
    private final int openedAt;
    private boolean closed;
    @@slot fields

    Ticket(int id, String subject, int priority, int openedAt) {
        this.id = id;
        this.subject = subject;
        this.priority = priority;
        this.openedAt = openedAt;
    }

    public int id() {
        return id;
    }

    public String subject() {
        return subject;
    }

    public int priority() {
        return priority;
    }

    public int openedAt() {
        return openedAt;
    }

    public boolean closed() {
        return closed;
    }

    void setPriority(int priority) {
        this.priority = priority;
    }

    void setClosed(boolean closed) {
        this.closed = closed;
    }

    @@blocks methods
}
'''

TEST_HEAD = '''\
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.util.*;
import queuedesk.*;
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

    /** Four tickets: 1 printer (p3), 2 login (p2), 3 wifi (p3), 4 server (p1), all opened at tick 0. */
    static Desk desk() {
        Desk d = new Desk();
        d.open("Printer jam", 3);
        d.open("Cannot log in", 2);
        d.open("Slow wifi", 3);
        d.open("Server down", 1);
        return d;
    }

    static List<Integer> ids(List<Ticket> ts) {
        List<Integer> out = new ArrayList<>();
        for (Ticket t : ts) {
            out.add(t.id());
        }
        return out;
    }

    static List<Integer> ints(Integer... xs) {
        return new ArrayList<>(Arrays.asList(xs));
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
    static void testOpenAndGet() {
        Desk d = desk();
        Ticket t = d.get(2);
        eq("Cannot log in", t.subject(), "subject");
        eq(2, t.priority(), "priority");
        check(!t.closed(), "open");
        expect(IllegalArgumentException.class, () -> d.open(" ", 2), "blank subject");
        expect(IllegalArgumentException.class, () -> d.open("x", 5), "bad priority");
        expect(NoSuchElementException.class, () -> d.get(9), "unknown id");
    }

    static void testOrderAndClose() {
        Desk d = desk();
        eq(ints(4, 2, 1, 3), ids(d.openTickets()), "order");
        eq(4, d.next().get().id(), "next");
        d.close(4);
        eq(2, d.next().get().id(), "next after close");
        eq(3, d.count(true), "open count");
        expect(IllegalStateException.class, () -> d.close(4), "close twice");
    }
'''

HIDDEN_BASE = '''
    static void testBaseOpen() {
        Desk d = new Desk();
        check(d.next().isEmpty(), "no ticket yet");
        eq(0, d.now(), "clock starts at 0");
        d.tick();
        d.tick();
        Ticket t = d.open("  Broken screen  ", 4);
        eq(1, t.id(), "first id");
        eq("Broken screen", t.subject(), "subject is stripped");
        eq(2, t.openedAt(), "opened at the current tick");
        eq(2, d.now(), "now");
        for (int p : new int[] {0, 5, -1}) {
            expect(IllegalArgumentException.class, () -> d.open("x", p), "priority " + p);
        }
        expect(IllegalArgumentException.class, () -> d.open(null, 2), "null subject");
        expect(IllegalArgumentException.class, () -> d.open("", 2), "empty subject");
        eq(2, d.open("Next one", 1).id(), "ids continue");
        eq(2, d.count(true), "count");
    }

    static void testBaseQueue() {
        Desk d = desk();
        eq(ints(4, 2, 1, 3), ids(d.openTickets()), "order");
        d.close(2);
        eq(ints(4, 1, 3), ids(d.openTickets()), "closed tickets are not listed");
        eq(Integer.valueOf(4), d.next().get().id(), "next");
        eq(4, d.close(4).id(), "close returns the ticket");
        d.open("Late p1", 1);
        eq(5, d.next().get().id(), "a new p1 comes first");
        eq(3, d.count(true), "open");
        eq(2, d.count(false), "closed");
        check(d.get(4).closed() && d.get(2).closed(), "closed flags");
        expect(IllegalStateException.class, () -> d.close(2), "already closed");
        expect(NoSuchElementException.class, () -> d.close(99), "unknown");
        eq(2, d.get(2).priority(), "closing keeps the priority");
        List<Ticket> snapshot = d.openTickets();
        snapshot.clear();
        eq(3, d.openTickets().size(), "openTickets is a copy");
    }
'''


def make_slices(rng: random.Random):
    batch_max = rng.choice([5, 10, 20])
    sla = rng.choice([(2, 4, 8, 16), (1, 3, 6, 12), (4, 8, 12, 24)])
    tag_max = rng.choice([12, 16, 24])
    S = []

    S.append(Slice(
        id="reopen", title="Reopening tickets", d=1,
        pitch=("Customers reply to closed tickets and support has to open a duplicate by hand.",
               "A closed ticket must be brought back when the problem returns."),
        reqs=("`Desk.reopen(id)` makes a closed ticket open again and returns it. Priority and opening tick stay as they were. An open ticket is an `IllegalStateException`; an unknown id is a `NoSuchElementException`.",),
        code={
            "src/queuedesk/Desk.java::methods": '''
                public Ticket reopen(int id) {
                    Ticket t = get(id);
                    if (!t.closed()) {
                        throw new IllegalStateException("ticket " + id + " is not closed");
                    }
                    @@slot reopen_checks
                    t.setClosed(false);
                    @@slot on_reopen
                    return t;
                }
            ''',
        },
        readme="## Reopening tickets\n\n`reopen(id)` opens a closed ticket again (priority and opening tick unchanged); open tickets are an `IllegalStateException`.\n",
        vtests='''
            static void testReopenBasic() {
                Desk d = desk();
                d.close(4);
                d.reopen(4);
                eq(4, d.next().get().id(), "back at the front");
            }
        ''',
        tests='''
            static void testReopen() {
                Desk d = desk();
                d.tick();
                d.tick();
                Ticket x = d.open("Late one", 2);
                d.tick();
                d.close(x.id());
                eq(4, d.count(true), "closed");
                Ticket back = d.reopen(x.id());
                eq(x.id(), back.id(), "returns the ticket");
                check(!d.get(x.id()).closed(), "open again");
                eq(2, d.get(x.id()).priority(), "priority is kept");
                eq(2, d.get(x.id()).openedAt(), "opening tick is kept");
                eq(ints(4, 2, 5, 1, 3), ids(d.openTickets()), "sorted into the queue");
                expect(IllegalStateException.class, () -> d.reopen(x.id()), "already open");
                expect(NoSuchElementException.class, () -> d.reopen(99), "unknown");
                d.close(1);
                d.reopen(1);
                d.close(1);
                eq(4, d.count(true), "can be closed and reopened repeatedly");
            }
        ''',
    ))

    S.append(Slice(
        id="bulk-close", title="Closing several tickets", d=1,
        pitch=("After the outage forty tickets have to be closed one call at a time.",
               "Support leads want to close a batch of tickets in one go."),
        reqs=(f"`Desk.closeAll(List<Integer> ids)` closes all the given tickets and returns how many it closed. The list must have 1 to {batch_max} entries without duplicates (`IllegalArgumentException`, checked first). Then the ids are checked in the order given: an unknown id is a `NoSuchElementException`, an already closed ticket an `IllegalStateException`.",
              "It is all or nothing: when any check fails no ticket is closed."),
        code={
            "src/queuedesk/Desk.java::methods": f'''
                public int closeAll(List<Integer> ids) {{
                    if (ids == null || ids.isEmpty() || ids.size() > {batch_max}) {{
                        throw new IllegalArgumentException("give between 1 and {batch_max} ids");
                    }}
                    if (new HashSet<>(ids).size() != ids.size()) {{
                        throw new IllegalArgumentException("duplicate id in the list");
                    }}
                    for (int id : ids) {{
                        if (get(id).closed()) {{
                            throw new IllegalStateException("ticket " + id + " is already closed");
                        }}
                    }}
                    for (int id : ids) {{
                        close(id);
                    }}
                    return ids.size();
                }}
            ''',
        },
        readme=f"## Closing several tickets\n\n`closeAll(ids)` closes 1 to {batch_max} distinct tickets, all or nothing, and returns the number closed.\n",
        vtests='''
            static void testCloseAllBasic() {
                Desk d = desk();
                eq(2, d.closeAll(ints(1, 3)), "closed");
                eq(2, d.count(true), "open left");
            }
        ''',
        tests=fmt('''
            static void testCloseAll() {
                Desk d = desk();
                eq(3, d.closeAll(ints(3, 1, 4)), "three closed");
                eq(ints(2), ids(d.openTickets()), "only ticket 2 is left");
                eq(1, d.closeAll(ints(2)), "single id");
                eq(0, d.count(true), "none open");
            }

            static void testCloseAllIsAllOrNothing() {
                Desk d = desk();
                d.close(2);
                expect(NoSuchElementException.class, () -> d.closeAll(ints(1, 99)), "unknown id");
                expect(IllegalStateException.class, () -> d.closeAll(ints(1, 2)), "already closed");
                expect(NoSuchElementException.class, () -> d.closeAll(ints(99, 2)), "unknown is reported in list order");
                expect(IllegalStateException.class, () -> d.closeAll(ints(2, 99)), "closed is reported in list order");
                eq(ints(4, 1, 3), ids(d.openTickets()), "nothing was closed");
            }

            static void testCloseAllValidatesTheList() {
                Desk d = desk();
                expect(IllegalArgumentException.class, () -> d.closeAll(ints()), "empty list");
                expect(IllegalArgumentException.class, () -> d.closeAll(null), "null list");
                expect(IllegalArgumentException.class, () -> d.closeAll(ints(1, 1)), "duplicates");
                expect(IllegalArgumentException.class, () -> d.closeAll(ints(99, 99)), "duplicates before unknown ids");
                List<Integer> many = new ArrayList<>();
                for (int i = 0; i < __M__ + 1; i++) {
                    many.add(i + 1);
                }
                expect(IllegalArgumentException.class, () -> d.closeAll(many), "too many ids");
                eq(4, d.count(true), "nothing changed");
                for (int i = 4; i < __M__; i++) {
                    d.open("filler " + i, 4);
                }
                List<Integer> max = new ArrayList<>();
                for (int i = 0; i < __M__; i++) {
                    max.add(i + 1);
                }
                eq(__M__, d.closeAll(max), "the maximum is fine");
            }
        ''', M=batch_max),
    ))

    S.append(Slice(
        id="assign", title="Assigning tickets to agents", d=2,
        pitch=("Everybody grabs the top ticket from the queue and two agents end up working on the same problem.",
               "Tickets need an owner so agents stop picking the same one."),
        reqs=("`Desk.assign(id, agent)` gives an open ticket to an agent and returns the ticket; `Ticket.agent()` returns the agent (`null` for a ticket nobody owns). The agent name must not be blank (it is stripped). Errors in this order: unknown ticket (`NoSuchElementException`), blank agent (`IllegalArgumentException`), closed ticket (`IllegalStateException`). A ticket can be handed to another agent later. Closing a ticket keeps its agent.",
              "`Desk.workload(agent)` counts the open tickets owned by the agent. `Desk.next(agent)` is like `next()` but only considers open tickets that are unassigned or assigned to that agent."),
        code={
            "src/queuedesk/Ticket.java::fields": "private String agent;",
            "src/queuedesk/Ticket.java::methods": '''
                public String agent() {
                    return agent;
                }

                void setAgent(String agent) {
                    this.agent = agent;
                }
            ''',
            "src/queuedesk/Desk.java::methods": '''
                public Ticket assign(int id, String agent) {
                    Ticket t = get(id);
                    if (agent == null || agent.isBlank()) {
                        throw new IllegalArgumentException("agent is required");
                    }
                    if (t.closed()) {
                        throw new IllegalStateException("ticket " + id + " is closed");
                    }
                    @@slot assign_checks
                    t.setAgent(agent.strip());
                    @@slot on_assign
                    return t;
                }

                public int workload(String agent) {
                    int n = 0;
                    for (Ticket t : tickets.values()) {
                        if (!t.closed() && agent != null && agent.equals(t.agent())) {
                            n++;
                        }
                    }
                    return n;
                }

                public Optional<Ticket> next(String agent) {
                    for (Ticket t : openTickets()) {
                        if (t.agent() == null || t.agent().equals(agent)) {
                            return Optional.of(t);
                        }
                    }
                    return Optional.empty();
                }
            ''',
        },
        readme="## Assigning tickets to agents\n\n`assign(id, agent)` (unknown ticket, blank agent, closed ticket, in that order), `Ticket.agent()`, `workload(agent)` and `next(agent)` (unassigned tickets or the agent's own).\n",
        vtests='''
            static void testAssignBasic() {
                Desk d = desk();
                d.assign(4, "ana");
                eq("ana", d.get(4).agent(), "agent");
            }
        ''',
        tests='''
            static void testAssign() {
                Desk d = desk();
                check(d.get(1).agent() == null, "nobody by default");
                eq(4, d.assign(4, "  ana ").id(), "returns the ticket");
                eq("ana", d.get(4).agent(), "stripped");
                d.assign(2, "ana");
                d.assign(1, "bob");
                eq(2, d.workload("ana"), "ana");
                eq(1, d.workload("bob"), "bob");
                eq(0, d.workload("cy"), "cy");
                eq(0, d.workload(null), "null agent");
                d.assign(2, "bob");
                eq(1, d.workload("ana"), "reassigned");
                eq(2, d.workload("bob"), "to bob");
                d.close(4);
                eq(0, d.workload("ana"), "closed tickets do not count");
                eq("ana", d.get(4).agent(), "but keep their agent");
            }

            static void testAssignErrorsInOrder() {
                Desk d = desk();
                d.close(3);
                expect(NoSuchElementException.class, () -> d.assign(99, " "), "unknown comes first");
                expect(IllegalArgumentException.class, () -> d.assign(3, " "), "blank comes before closed");
                expect(IllegalArgumentException.class, () -> d.assign(1, null), "null agent");
                expect(IllegalStateException.class, () -> d.assign(3, "ana"), "closed ticket");
                check(d.get(3).agent() == null && d.get(1).agent() == null, "nothing assigned");
            }

            static void testNextForAgent() {
                Desk d = desk();
                d.assign(4, "ana");
                eq(2, d.next("bob").get().id(), "bob skips ana's ticket");
                eq(4, d.next("ana").get().id(), "ana gets her own first");
                eq(4, d.next().get().id(), "plain next ignores owners");
            }
        ''',
        cross={
            "reopen": {"tests": '''
                static void testReopenKeepsTheAgent() {
                    Desk d = desk();
                    d.assign(4, "ana");
                    d.close(4);
                    d.reopen(4);
                    eq("ana", d.get(4).agent(), "agent is kept");
                    eq(1, d.workload("ana"), "and counts again");
                }
            '''},
        },
    ))

    S.append(Slice(
        id="escalate", title="Escalating tickets", d=2,
        pitch=("A p3 ticket from the CEO sits at the back of the queue until someone notices.",
               "Support leads need to raise the urgency of a ticket that turned out to be serious."),
        reqs=("`Desk.escalate(id)` makes an open ticket one step more urgent (priority minus one) and returns it. A closed ticket and a ticket that already has priority 1 are an `IllegalStateException`; an unknown id is a `NoSuchElementException`. The ticket moves to its new place in the queue.",),
        code={
            "src/queuedesk/Desk.java::methods": '''
                public Ticket escalate(int id) {
                    Ticket t = get(id);
                    if (t.closed()) {
                        throw new IllegalStateException("ticket " + id + " is closed");
                    }
                    if (t.priority() == 1) {
                        throw new IllegalStateException("ticket " + id + " is already at the highest priority");
                    }
                    t.setPriority(t.priority() - 1);
                    @@slot on_escalate
                    return t;
                }
            ''',
        },
        readme="## Escalating tickets\n\n`escalate(id)` lowers the priority number by one (never below 1) for open tickets and returns the ticket.\n",
        vtests='''
            static void testEscalateBasic() {
                Desk d = desk();
                eq(2, d.escalate(1).priority(), "p3 becomes p2");
            }
        ''',
        tests='''
            static void testEscalate() {
                Desk d = desk();
                eq(2, d.escalate(3).priority(), "p3 to p2");
                eq(ints(4, 2, 3, 1), ids(d.openTickets()), "joins the p2 tickets by id");
                eq(1, d.escalate(3).priority(), "p2 to p1");
                eq(ints(3, 4, 2, 1), ids(d.openTickets()), "p1 by id");
                expect(IllegalStateException.class, () -> d.escalate(3), "already p1");
                expect(IllegalStateException.class, () -> d.escalate(4), "p1 from the start");
                d.close(1);
                expect(IllegalStateException.class, () -> d.escalate(1), "closed");
                expect(NoSuchElementException.class, () -> d.escalate(99), "unknown");
                eq(3, d.get(1).priority(), "closed ticket unchanged");
            }
        ''',
    ))

    S.append(Slice(
        id="tags", title="Ticket tags", d=2,
        pitch=("Tickets about the VPN are spread over the whole queue and nobody can find them together.",
               "Support wants to label tickets and list them by label."),
        reqs=(f"`Desk.tag(id, tag)` adds a tag to a ticket (open or closed) and returns whether it was new. A tag is 1 to {tag_max} characters from `a-z`, `0-9` and `-`, not starting with a dash (`IllegalArgumentException`); an unknown ticket is checked first (`NoSuchElementException`). `Desk.untag(id, tag)` removes a tag and returns whether it was there (an unknown ticket is a `NoSuchElementException`, any string is accepted as a tag to remove).",
              "`Ticket.tags()` returns a new list of the tags in alphabetical order. `Desk.withTag(tag)` returns the tickets (open or closed) that have the tag, ordered by id."),
        code={
            "src/queuedesk/Ticket.java::fields": "private final TreeSet<String> tags = new TreeSet<>();",
            "src/queuedesk/Ticket.java::methods": '''
                public List<String> tags() {
                    return new ArrayList<>(tags);
                }

                boolean addTag(String tag) {
                    return tags.add(tag);
                }

                boolean removeTag(String tag) {
                    return tags.remove(tag);
                }
            ''',
            "src/queuedesk/Desk.java::methods": f'''
                public boolean tag(int id, String tag) {{
                    Ticket t = get(id);
                    if (tag == null || !tag.matches("[a-z0-9][a-z0-9-]{{0,{tag_max - 1}}}")) {{
                        throw new IllegalArgumentException("bad tag: " + tag);
                    }}
                    boolean added = t.addTag(tag);
                    if (added) {{
                        @@slot on_tag
                    }}
                    return added;
                }}

                public boolean untag(int id, String tag) {{
                    Ticket t = get(id);
                    boolean removed = t.removeTag(tag);
                    if (removed) {{
                        @@slot on_untag
                    }}
                    return removed;
                }}

                public List<Ticket> withTag(String tag) {{
                    List<Ticket> out = new ArrayList<>();
                    for (Ticket t : tickets.values()) {{
                        if (t.tags().contains(tag)) {{
                            out.add(t);
                        }}
                    }}
                    return out;
                }}
            ''',
        },
        readme=f"## Ticket tags\n\n`tag(id, tag)` / `untag(id, tag)` return whether something changed; tags are 1 to {tag_max} characters of `a-z0-9-` (not starting with a dash). `Ticket.tags()` is sorted, `withTag(tag)` lists tickets by id.\n",
        vtests='''
            static void testTagsBasic() {
                Desk d = desk();
                check(d.tag(1, "vpn"), "new tag");
                eq(ints(1), ids(d.withTag("vpn")), "found");
            }
        ''',
        tests=fmt('''
            static void testTags() {
                Desk d = desk();
                check(d.tag(1, "vpn"), "new");
                check(!d.tag(1, "vpn"), "again");
                d.tag(1, "billing");
                d.tag(3, "vpn");
                d.tag(2, "0day");
                eq(list("billing", "vpn"), d.get(1).tags(), "sorted");
                eq(ints(1, 3), ids(d.withTag("vpn")), "by id");
                eq(ints(), ids(d.withTag("nothing")), "none");
                d.close(3);
                eq(ints(1, 3), ids(d.withTag("vpn")), "closed tickets are included");
                check(d.tag(3, "late"), "closed tickets can be tagged");
                check(d.untag(1, "vpn"), "removed");
                check(!d.untag(1, "vpn"), "removed twice");
                check(!d.untag(1, "Whatever Goes"), "unknown tags are fine");
                eq(ints(3), ids(d.withTag("vpn")), "after untag");
                d.get(1).tags().clear();
                eq(list("billing"), d.get(1).tags(), "tags() is a copy");
            }

            static void testTagValidation() {
                Desk d = desk();
                String longest = "a".repeat(__M__);
                for (String bad : new String[] {"", "VPN", "-x", "a b", "a_b", "x!", longest + "a"}) {
                    expect(IllegalArgumentException.class, () -> d.tag(1, bad), "tag '" + bad + "'");
                }
                expect(IllegalArgumentException.class, () -> d.tag(1, null), "null tag");
                expect(NoSuchElementException.class, () -> d.tag(99, "BAD"), "unknown ticket first");
                expect(NoSuchElementException.class, () -> d.untag(99, "x"), "untag unknown ticket");
                check(d.get(1).tags().isEmpty(), "nothing was added");
                check(d.tag(1, longest), "longest tag");
                check(d.tag(1, "9"), "digit");
                check(d.tag(1, "a-b-c"), "dashes inside");
            }
        ''', M=tag_max),
        cross={
            "merge": {
                "reqs": ("A merge adds the tags of the duplicate to the kept ticket.",),
                "code": {"src/queuedesk/Desk.java::merge_extra": '''
                    for (String tg : dup.tags()) {
                        keep.addTag(tg);
                    }
                '''},
                "tests": '''
                    static void testMergeUnionsTags() {
                        Desk d = desk();
                        d.tag(1, "vpn");
                        d.tag(1, "a");
                        d.tag(3, "vpn");
                        d.tag(3, "wifi");
                        d.merge(1, 3);
                        eq(list("a", "vpn", "wifi"), d.get(1).tags(), "union");
                        eq(list("vpn", "wifi"), d.get(3).tags(), "the duplicate keeps its tags");
                    }
                '''},
        },
    ))

    s1, s2, s3, s4 = sla
    S.append(Slice(
        id="sla", title="Response deadlines", d=3,
        pitch=("Nobody notices that the urgent tickets have been sitting unanswered for a day.",
               "Management wants to see which open tickets have run past their response deadline."),
        reqs=(f"Every priority has a deadline in ticks after the opening tick: priority 1 gets {s1}, priority 2 gets {s2}, priority 3 gets {s3} and priority 4 gets {s4}. `Desk.slaTicks(priority)` is a public static method returning that number (`IllegalArgumentException` outside 1 to 4) and `Desk.deadline(id)` returns `openedAt + slaTicks(priority)` using the ticket's current priority (`NoSuchElementException` for an unknown id).",
              "`Desk.breached()` returns the open tickets whose deadline is strictly before `now()`, ordered by deadline and then by id. Closed tickets never appear."),
        code={
            "src/queuedesk/Desk.java::methods": f'''
                public static int slaTicks(int priority) {{
                    switch (priority) {{
                        case 1:
                            return {s1};
                        case 2:
                            return {s2};
                        case 3:
                            return {s3};
                        case 4:
                            return {s4};
                        default:
                            throw new IllegalArgumentException("priority must be 1 to 4");
                    }}
                }}

                public int deadline(int id) {{
                    Ticket t = get(id);
                    return t.openedAt() + slaTicks(t.priority());
                }}

                public List<Ticket> breached() {{
                    List<Ticket> out = new ArrayList<>();
                    for (Ticket t : openTickets()) {{
                        if (deadline(t.id()) < now) {{
                            out.add(t);
                        }}
                    }}
                    out.sort(Comparator.comparingInt((Ticket t) -> deadline(t.id())).thenComparingInt(Ticket::id));
                    return out;
                }}
            ''',
        },
        readme=f"## Response deadlines\n\nDeadlines after the opening tick: p1 {s1}, p2 {s2}, p3 {s3}, p4 {s4}. `Desk.slaTicks(priority)`, `deadline(id)` and `breached()` (open tickets with deadline before `now()`, by deadline then id).\n",
        vtests=fmt('''
            static void testSlaBasic() {
                Desk d = desk();
                eq(__S1__, d.deadline(4), "p1 deadline");
            }
        ''', S1=s1),
        tests=fmt('''
            static void testSlaTable() {
                eq(__S1__, Desk.slaTicks(1), "p1");
                eq(__S2__, Desk.slaTicks(2), "p2");
                eq(__S3__, Desk.slaTicks(3), "p3");
                eq(__S4__, Desk.slaTicks(4), "p4");
                expect(IllegalArgumentException.class, () -> Desk.slaTicks(0), "p0");
                expect(IllegalArgumentException.class, () -> Desk.slaTicks(5), "p5");
                Desk d = desk();
                d.tick();
                d.tick();
                Ticket late = d.open("Opened at two", 2);
                eq(2 + __S2__, d.deadline(late.id()), "deadline counts from the opening tick");
                eq(__S3__, d.deadline(1), "ticket 1");
                expect(NoSuchElementException.class, () -> d.deadline(99), "unknown");
            }

            static void testBreached() {
                Desk d = desk();
                eq(ints(), ids(d.breached()), "nothing at the start");
                for (int i = 0; i < __S1__; i++) {
                    d.tick();
                }
                eq(ints(), ids(d.breached()), "exactly at the deadline is not breached");
                d.tick();
                eq(ints(4), ids(d.breached()), "one tick later the p1 ticket is");
                while (d.now() <= __S2__) {
                    d.tick();
                }
                eq(ints(4, 2), ids(d.breached()), "ordered by deadline");
                d.close(4);
                eq(ints(2), ids(d.breached()), "closed tickets drop out");
                while (d.now() <= __S3__) {
                    d.tick();
                }
                eq(ints(2, 1, 3), ids(d.breached()), "equal deadlines by id");
            }
        ''', S1=s1, S2=s2, S3=s3, S4=s4),
        cross={
            "escalate": {
                "reqs": ("Escalating changes the deadline: it is always computed from the opening tick and the current priority.",),
                "tests": fmt('''
                    static void testEscalateMovesTheDeadline() {
                        Desk d = desk();
                        eq(__S3__, d.deadline(1), "before");
                        d.escalate(1);
                        eq(__S2__, d.deadline(1), "after");
                        while (d.now() <= __S2__) {
                            d.tick();
                        }
                        check(ids(d.breached()).contains(1), "breached under the new priority");
                    }
                ''', S2=s2, S3=s3)},
            "reopen": {
                "tests": fmt('''
                    static void testReopenedTicketKeepsItsOriginalDeadline() {
                        Desk d = desk();
                        d.close(4);
                        for (int i = 0; i < __S1__ + 3; i++) {
                            d.tick();
                        }
                        check(!ids(d.breached()).contains(4), "closed ticket is not breached");
                        d.reopen(4);
                        check(ids(d.breached()).contains(4), "reopened ticket is measured from its opening tick");
                    }
                ''', S1=s1)},
        },
    ))

    S.append(Slice(
        id="merge", title="Merging duplicates", d=3,
        pitch=("Five customers report the same outage and five agents answer them separately.",
               "Duplicate tickets must be folded into one."),
        reqs=("`Desk.merge(keepId, dupId)` folds a duplicate ticket into another one and returns the kept ticket. The duplicate gets closed and `Ticket.mergedInto()` returns the id of the kept ticket (an `Integer`, `null` for tickets that were not merged away). The kept ticket takes over the more urgent of the two priorities.",
              "Errors in this order: the same id twice (`IllegalArgumentException`), an unknown id (`NoSuchElementException`, `keepId` first), a ticket that is already closed (`IllegalStateException`). A failed merge changes nothing."),
        code={
            "src/queuedesk/Ticket.java::fields": "private Integer mergedInto;",
            "src/queuedesk/Ticket.java::methods": '''
                public Integer mergedInto() {
                    return mergedInto;
                }

                void setMergedInto(Integer id) {
                    this.mergedInto = id;
                }
            ''',
            "src/queuedesk/Desk.java::methods": '''
                public Ticket merge(int keepId, int dupId) {
                    if (keepId == dupId) {
                        throw new IllegalArgumentException("cannot merge a ticket into itself");
                    }
                    Ticket keep = get(keepId);
                    Ticket dup = get(dupId);
                    if (keep.closed() || dup.closed()) {
                        throw new IllegalStateException("both tickets must be open");
                    }
                    if (dup.priority() < keep.priority()) {
                        keep.setPriority(dup.priority());
                    }
                    @@slot merge_extra
                    dup.setMergedInto(keepId);
                    dup.setClosed(true);
                    @@slot on_merge
                    return keep;
                }
            ''',
        },
        readme="## Merging duplicates\n\n`merge(keepId, dupId)` closes the duplicate (`Ticket.mergedInto()` = kept id) and gives the kept ticket the more urgent priority. Errors in order: same id, unknown id, closed ticket.\n",
        vtests='''
            static void testMergeBasic() {
                Desk d = desk();
                d.merge(1, 3);
                check(d.get(3).closed(), "duplicate closed");
            }
        ''',
        tests='''
            static void testMerge() {
                Desk d = desk();
                Ticket kept = d.merge(1, 4);
                eq(1, kept.id(), "returns the kept ticket");
                eq(1, d.get(1).priority(), "takes the more urgent priority");
                check(d.get(4).closed(), "duplicate closed");
                eq(Integer.valueOf(1), d.get(4).mergedInto(), "mergedInto");
                check(d.get(1).mergedInto() == null && d.get(2).mergedInto() == null, "others are not merged");
                eq(ints(1, 2, 3), ids(d.openTickets()), "queue");
                d.merge(2, 3);
                eq(2, d.get(2).priority(), "the keeper stays more urgent");
                eq(3, d.get(3).priority(), "the duplicate keeps its own priority");
                eq(Integer.valueOf(2), d.get(3).mergedInto(), "second merge");
                eq(2, d.count(true), "open tickets left");
            }

            static void testMergeErrors() {
                Desk d = desk();
                d.close(2);
                expect(IllegalArgumentException.class, () -> d.merge(1, 1), "same id");
                expect(IllegalArgumentException.class, () -> d.merge(99, 99), "same id before unknown");
                expect(NoSuchElementException.class, () -> d.merge(99, 2), "unknown keep first");
                expect(NoSuchElementException.class, () -> d.merge(2, 99), "unknown duplicate");
                expect(IllegalStateException.class, () -> d.merge(1, 2), "closed duplicate");
                expect(IllegalStateException.class, () -> d.merge(2, 1), "closed keeper");
                check(!d.get(1).closed() && d.get(1).priority() == 3, "nothing changed");
                check(d.get(1).mergedInto() == null, "not merged");
                d.merge(1, 3);
                expect(IllegalStateException.class, () -> d.merge(1, 3), "merging twice");
            }
        ''',
        cross={
            "assign": {
                "reqs": ("If the kept ticket has no agent and the duplicate has one, the kept ticket takes over the duplicate's agent (limits, if any, are not checked).",),
                "code": {"src/queuedesk/Desk.java::merge_extra": '''
                    if (keep.agent() == null && dup.agent() != null) {
                        keep.setAgent(dup.agent());
                    }
                '''},
                "tests": '''
                    static void testMergeInheritsAnAgent() {
                        Desk d = desk();
                        d.assign(3, "ana");
                        d.merge(1, 3);
                        eq("ana", d.get(1).agent(), "inherited");
                        d.assign(2, "bob");
                        d.assign(4, "cy");
                        d.merge(2, 4);
                        eq("bob", d.get(2).agent(), "an existing agent is kept");
                    }
                '''},
            "reopen": {
                "reqs": ("A ticket that was merged away cannot be reopened (`IllegalStateException`).",),
                "code": {"src/queuedesk/Desk.java::reopen_checks": '''
                    if (t.mergedInto() != null) {
                        throw new IllegalStateException("ticket " + id + " was merged into " + t.mergedInto());
                    }
                '''},
                "tests": '''
                    static void testMergedTicketsStayClosed() {
                        Desk d = desk();
                        d.merge(1, 3);
                        expect(IllegalStateException.class, () -> d.reopen(3), "merged away");
                        check(d.get(3).closed(), "still closed");
                        d.close(2);
                        d.reopen(2);
                    }
                '''},
        },
    ))

    S.append(Slice(
        id="history", title="Ticket history", d=3,
        pitch=("When a customer disputes what happened to their ticket nobody can say who did what and when.",
               "Every ticket should carry a log of what happened to it."),
        reqs=("`Desk.history(id)` returns a new list of strings, oldest first (`NoSuchElementException` for an unknown id). Each entry is `TICK: TEXT` with the value of `now()` at the time. Opening a ticket logs `opened pN` (its priority) and closing it logs `closed`. A failed call logs nothing.",),
        code={
            "src/queuedesk/Desk.java::fields": "private final Map<Integer, List<String>> log = new HashMap<>();",
            "src/queuedesk/Desk.java::on_open": 'note(t.id(), "opened p" + priority);',
            "src/queuedesk/Desk.java::on_close": 'note(id, "closed");',
            "src/queuedesk/Desk.java::methods": '''
                private void note(int id, String text) {
                    log.computeIfAbsent(id, k -> new ArrayList<>()).add(now + ": " + text);
                }

                public List<String> history(int id) {
                    get(id);
                    return new ArrayList<>(log.getOrDefault(id, List.of()));
                }
            ''',
        },
        readme="## Ticket history\n\n`history(id)` lists `TICK: TEXT` entries: `opened pN` and `closed` (more events are listed with the features that cause them).\n",
        vtests='''
            static void testHistoryBasic() {
                Desk d = desk();
                eq(list("0: opened p3"), d.history(1), "opened");
            }
        ''',
        tests='''
            static void testHistory() {
                Desk d = desk();
                d.tick();
                d.tick();
                d.close(1);
                d.tick();
                Ticket late = d.open("Later", 2);
                eq(list("0: opened p3", "2: closed"), d.history(1), "ticket 1");
                eq(list("0: opened p2"), d.history(2), "ticket 2");
                eq(list("3: opened p2"), d.history(late.id()), "later ticket");
                expect(IllegalStateException.class, () -> d.close(1), "second close");
                expect(IllegalArgumentException.class, () -> d.open("x", 7), "failed open");
                eq(2, d.history(1).size(), "failed calls log nothing");
                d.history(1).add("tampered");
                eq(2, d.history(1).size(), "history is a copy");
                expect(NoSuchElementException.class, () -> d.history(99), "unknown");
            }
        ''',
        cross={
            "bulk-close": {"tests": '''
                static void testBulkCloseIsLogged() {
                    Desk d = desk();
                    d.tick();
                    d.closeAll(ints(1, 2));
                    expect(NoSuchElementException.class, () -> d.closeAll(ints(3, 99)), "fails");
                    eq(list("0: opened p3", "1: closed"), d.history(1), "ticket 1");
                    eq(list("0: opened p2", "1: closed"), d.history(2), "ticket 2");
                    eq(list("0: opened p3"), d.history(3), "ticket 3 stays untouched");
                }
            '''},
            "reopen": {
                "reqs": ("Reopening logs `reopened`.",),
                "code": {"src/queuedesk/Desk.java::on_reopen": 'note(id, "reopened");'},
                "tests": '''
                    static void testReopenIsLogged() {
                        Desk d = desk();
                        d.tick();
                        d.close(1);
                        d.tick();
                        d.tick();
                        d.reopen(1);
                        expect(IllegalStateException.class, () -> d.reopen(1), "fails");
                        eq(list("0: opened p3", "1: closed", "3: reopened"), d.history(1), "log");
                    }
                '''},
            "assign": {
                "reqs": ("Assigning logs `assigned to AGENT` (the stripped name), also when the ticket is handed to another agent.",),
                "code": {"src/queuedesk/Desk.java::on_assign": 'note(id, "assigned to " + t.agent());'},
                "tests": '''
                    static void testAssignIsLogged() {
                        Desk d = desk();
                        d.assign(1, " ana ");
                        d.tick();
                        d.assign(1, "bob");
                        expect(IllegalArgumentException.class, () -> d.assign(1, " "), "fails");
                        eq(list("0: opened p3", "0: assigned to ana", "1: assigned to bob"), d.history(1), "log");
                    }
                '''},
            "escalate": {
                "reqs": ("Escalating logs `escalated to pN` with the new priority.",),
                "code": {"src/queuedesk/Desk.java::on_escalate": 'note(id, "escalated to p" + t.priority());'},
                "tests": '''
                    static void testEscalateIsLogged() {
                        Desk d = desk();
                        d.tick();
                        d.escalate(1);
                        d.escalate(1);
                        expect(IllegalStateException.class, () -> d.escalate(1), "fails");
                        eq(list("0: opened p3", "1: escalated to p2", "1: escalated to p1"), d.history(1), "log");
                    }
                '''},
            "tags": {
                "reqs": ("Tagging logs `tagged TAG` and untagging `untagged TAG`, only when the tag set really changed.",),
                "code": {
                    "src/queuedesk/Desk.java::on_tag": 'note(id, "tagged " + tag);',
                    "src/queuedesk/Desk.java::on_untag": 'note(id, "untagged " + tag);',
                },
                "tests": '''
                    static void testTagsAreLogged() {
                        Desk d = desk();
                        d.tag(2, "vpn");
                        d.tag(2, "vpn");
                        d.tick();
                        d.untag(2, "vpn");
                        d.untag(2, "vpn");
                        eq(list("0: opened p2", "0: tagged vpn", "1: untagged vpn"), d.history(2), "log");
                    }
                '''},
            "merge": {
                "reqs": ("A merge logs `merged into #K` for the duplicate (instead of `closed`) and `absorbed #D` for the kept ticket.",),
                "code": {"src/queuedesk/Desk.java::on_merge": '''
                    note(dupId, "merged into #" + keepId);
                    note(keepId, "absorbed #" + dupId);
                '''},
                "tests": '''
                    static void testMergeIsLogged() {
                        Desk d = desk();
                        d.tick();
                        d.merge(1, 3);
                        eq(list("0: opened p3", "1: absorbed #3"), d.history(1), "kept ticket");
                        eq(list("0: opened p3", "1: merged into #1"), d.history(3), "duplicate");
                    }
                '''},
        },
    ))

    S.append(Slice(
        id="agent-limit", title="Workload limits", d=4, needs=("assign",),
        pitch=("One agent has 30 open tickets while the others have two, and nothing stops the lead from piling on more.",
               "Agents need a maximum number of open tickets that the desk enforces."),
        reqs=("`Desk.setLimit(agent, max)` sets how many open tickets an agent may own (`max` 0 removes the limit; a negative `max` or a blank agent is an `IllegalArgumentException`; the agent name is stripped) and `Desk.limit(agent)` returns it (0 means no limit).",
              "`assign` fails with an `IllegalStateException` when the agent already owns `max` open tickets, unless the ticket is already owned by that agent (assigning a ticket to its current owner is always fine). This check comes after the checks `assign` already has, and a refused call changes nothing. Closing a ticket frees a slot."),
        code={
            "src/queuedesk/Desk.java::fields": "private final Map<String, Integer> limits = new HashMap<>();",
            "src/queuedesk/Desk.java::assign_checks": '''
                {
                    String who = agent.strip();
                    Integer max = limits.get(who);
                    if (max != null && !who.equals(t.agent()) && workload(who) >= max) {
                        throw new IllegalStateException("agent " + who + " already has " + max + " open tickets");
                    }
                }
            ''',
            "src/queuedesk/Desk.java::methods": '''
                public void setLimit(String agent, int max) {
                    if (agent == null || agent.isBlank()) {
                        throw new IllegalArgumentException("agent is required");
                    }
                    if (max < 0) {
                        throw new IllegalArgumentException("limit must not be negative");
                    }
                    if (max == 0) {
                        limits.remove(agent.strip());
                    } else {
                        limits.put(agent.strip(), max);
                    }
                }

                public int limit(String agent) {
                    return agent == null ? 0 : limits.getOrDefault(agent, 0);
                }
            ''',
        },
        readme="## Workload limits\n\n`setLimit(agent, max)` (0 removes it) and `limit(agent)`. `assign` refuses an `IllegalStateException` when the agent already owns `max` open tickets (re-assigning to the current owner is fine).\n",
        vtests='''
            static void testLimitBasic() {
                Desk d = desk();
                d.setLimit("ana", 1);
                d.assign(1, "ana");
                expect(IllegalStateException.class, () -> d.assign(2, "ana"), "over the limit");
            }
        ''',
        tests='''
            static void testLimit() {
                Desk d = desk();
                eq(0, d.limit("ana"), "none by default");
                d.setLimit(" ana ", 2);
                eq(2, d.limit("ana"), "stripped");
                d.assign(1, "ana");
                d.assign(2, "ana");
                expect(IllegalStateException.class, () -> d.assign(3, "ana"), "third ticket");
                eq(2, d.workload("ana"), "unchanged");
                check(d.get(3).agent() == null, "not assigned");
                eq("ana", d.assign(2, "ana").agent(), "re-assigning to the owner is fine");
                d.close(1);
                eq("ana", d.assign(3, "ana").agent(), "closing frees a slot");
                d.assign(4, "bob");
                d.setLimit("ana", 0);
                eq(0, d.limit("ana"), "removed");
                d.assign(4, "ana");
                eq(3, d.workload("ana"), "no limit any more");
                d.setLimit("ana", 1);
                eq(1, d.limit("ana"), "lowering below the workload is allowed");
                eq("bob", d.assign(4, "bob").agent(), "other agents are not limited");
                Ticket extra = d.open("one more", 4);
                expect(IllegalStateException.class, () -> d.assign(extra.id(), "ana"), "ana is above her lowered limit");
            }
        ''',
        cross={
            "reopen": {
                "reqs": ("`reopen` of a ticket whose agent already owns `max` open tickets is an `IllegalStateException` (the ticket stays closed).",),
                "code": {"src/queuedesk/Desk.java::reopen_checks": '''
                    if (t.agent() != null) {
                        Integer max = limits.get(t.agent());
                        if (max != null && workload(t.agent()) >= max) {
                            throw new IllegalStateException("agent " + t.agent() + " already has " + max + " open tickets");
                        }
                    }
                '''},
                "tests": '''
                    static void testReopenRespectsTheLimit() {
                        Desk d = desk();
                        d.setLimit("ana", 1);
                        d.assign(1, "ana");
                        d.close(1);
                        d.assign(2, "ana");
                        expect(IllegalStateException.class, () -> d.reopen(1), "ana is full");
                        check(d.get(1).closed(), "still closed");
                        d.close(2);
                        d.reopen(1);
                        check(!d.get(1).closed(), "reopened once there is room");
                    }
                '''},
        },
    ))

    return S


APP = App(
    name="queuedesk", lang="java", title="the help-desk ticket library", role="the support team lead", key="DESK",
    base={
        "README.md": README + "\n@@blocks features\n",
        "src/queuedesk/Desk.java": DESK,
        "src/queuedesk/Ticket.java": TICKET,
        ".gitignore": "build/\n",
    },
    visible={"test/TestMain.java": TEST_HEAD.replace("@@blocks tests", VISIBLE_BASE + "\n    @@blocks tests")},
    hidden={"test/TestMain.java": TEST_HEAD.replace("@@blocks tests", HIDDEN_BASE + "\n    @@blocks tests")},
)

register_app("feature-java-queuedesk", APP, make_slices, n=18, summary="help-desk tickets: reopen, bulk close, agents, escalation, tags, SLA, merging, history, workload limits")

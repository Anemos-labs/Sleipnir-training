"""Slot modules (java), part 1: stockroom counts, report files, task board."""
from fx import dd

from ._slots import Bad, Module, Slot, sub, validate_module

README = "# {name}\n\n{text}\n"

# ---------------------------------------------------------------------------------------------------------------------
# stockroom
# ---------------------------------------------------------------------------------------------------------------------

STOCK_TEMPLATE = dd('''
    package stock;

    @@imports@@

    /** Stock counts of one warehouse room. A count never goes below zero; the room may be used from many threads. */
    public class Stockroom {
        private final String id;
        private final Map<String, Integer> counts = new HashMap<>();

        public Stockroom(String id) {
            this.id = id;
        }

        public String id() {
            return id;
        }

        @@add@@

        @@remove@@

        @@low@@

        @@transfer@@

        @@snapshot@@

        @@total@@
    }
''')

_J_IMPORTS = dd('''
    import java.util.ArrayList;
    import java.util.Collections;
    import java.util.HashMap;
    import java.util.List;
    import java.util.Map;
    import java.util.TreeMap;
''')
_J_ADD = dd('''
    /** Adds qty (at least 1) units of sku and returns the new count; throws ArithmeticException if the count would overflow. */
    public synchronized int add(String sku, int qty) {
        if (qty <= 0) {
            throw new IllegalArgumentException("qty must be positive: " + qty);
        }
        int updated = Math.addExact(counts.getOrDefault(sku, 0), qty);
        counts.put(sku, updated);
        return updated;
    }
''')
_J_REMOVE = dd('''
    /** Removes qty (at least 1) units of sku; throws IllegalStateException if fewer are in stock. Sold-out SKUs stay listed with 0. */
    public synchronized void remove(String sku, int qty) {
        if (qty <= 0) {
            throw new IllegalArgumentException("qty must be positive: " + qty);
        }
        int have = counts.getOrDefault(sku, 0);
        if (have < qty) {
            throw new IllegalStateException("only " + have + " of " + sku + " in stock");
        }
        counts.put(sku, have - qty);
    }
''')
_J_LOW = dd('''
    /** SKUs with fewer than threshold units (sold-out ones included), in alphabetical order. */
    public synchronized List<String> lowStock(int threshold) {
        List<String> out = new ArrayList<>();
        for (Map.Entry<String, Integer> e : counts.entrySet()) {
            if (e.getValue() < threshold) {
                out.add(e.getKey());
            }
        }
        Collections.sort(out);
        return out;
    }
''')
_J_TRANSFER = dd('''
    /** Moves qty units of sku from this room to other. Both rooms are locked in a fixed order (by id) so that two threads
     *  transferring in opposite directions cannot deadlock; if the receiving room rejects the units they go back. */
    public void transfer(Stockroom other, String sku, int qty) {
        if (other == this) {
            throw new IllegalArgumentException("cannot transfer to the same room");
        }
        Stockroom first = id.compareTo(other.id) < 0 ? this : other;
        Stockroom second = first == this ? other : this;
        synchronized (first) {
            synchronized (second) {
                remove(sku, qty);
                try {
                    other.add(sku, qty);
                } catch (RuntimeException e) {
                    add(sku, qty);
                    throw e;
                }
            }
        }
    }
''')
_J_SNAPSHOT = dd('''
    /** A sorted copy of the counts that the caller may keep or change. */
    public synchronized Map<String, Integer> snapshot() {
        return new TreeMap<>(counts);
    }
''')
_J_TOTAL = dd('''
    /** Total units in the room; a long because the sum of int counts can exceed Integer.MAX_VALUE. */
    public synchronized long totalUnits() {
        long sum = 0;
        for (int v : counts.values()) {
            sum += v;
        }
        return sum;
    }
''')

STOCKROOM = Module(
    name="java-stockroom", lang="java", path="src/stock/Stockroom.java", difficulty=3,
    title="Stockroom: counts, low-stock list, atomic transfers between rooms",
    blurb="The `stock` package keeps the shelf counts of a mail-order warehouse; each room is touched by several picker terminals at once.",
    intro="The pickers' terminals used to keep their own counts and drift apart. This PR adds one shared model per room:",
    outro="Tried with 40 simulated pickers. SKUs are upper-case strings from the barcode scanner.",
    new_file=True,
    template=STOCK_TEMPLATE,
    ctx={"README.md": "# stock\n\nWarehouse counts.\n"},
    slots=[
        Slot("imports", "<imports>", _J_IMPORTS, []),
        Slot("add", "Stockroom.add", _J_ADD, [
            Bad(_J_ADD.replace("if (qty <= 0) {", "if (qty < 0) {"), "off-by-one", "adding zero units is accepted although qty must be at least 1", ("qty", "<", "zero", "positive")),
            Bad(_J_ADD.replace("Math.addExact(counts.getOrDefault(sku, 0), qty)", "counts.getOrDefault(sku, 0) + qty"), "logic", "plain int addition overflows silently to a negative count instead of throwing ArithmeticException", ("overflow", "addExact", "int", "negative")),
            Bad(_J_ADD.replace("public synchronized int add", "public int add"), "concurrency", "add is no longer synchronized: concurrent read-modify-write on the HashMap loses updates and can corrupt the map", ("synchronized", "race", "HashMap", "lost update")),
        ], note="adds `add()` with overflow protection"),
        Slot("remove", "Stockroom.remove", _J_REMOVE, [
            Bad(_J_REMOVE.replace("if (have < qty) {", "if (have <= qty) {"), "off-by-one", "the last units can never be removed: removing exactly what is in stock throws", ("<=", "have", "qty", "boundary")),
            Bad(sub(_J_REMOVE, "counts.put(sku, have - qty);", "if (have == qty) {\n    counts.remove(sku);\n} else {\n    counts.put(sku, have - qty);\n}"), "logic", "a sold-out SKU is removed from the map, so lowStock no longer reports it although the contract says sold-out SKUs stay listed", ("sold-out", "remove", "lowStock", "zero")),
            Bad(_J_REMOVE.replace("public synchronized void remove", "public void remove"), "concurrency", "remove is not synchronized, so the check-then-act on the stock level is racy (two threads can both pass the `have < qty` test)", ("synchronized", "race", "check-then-act")),
        ], note="adds `remove()`"),
        Slot("low", "Stockroom.lowStock", _J_LOW, [
            Bad(_J_LOW.replace("e.getValue() < threshold", "e.getValue() <= threshold"), "off-by-one", "SKUs with exactly `threshold` units are reported although the rule is *fewer than* threshold", ("<=", "threshold", "boundary", "fewer")),
            Bad(sub(_J_LOW, "Collections.sort(out);", ""), "logic", "the list is not sorted, so the order follows HashMap iteration order", ("sort", "order", "HashMap")),
        ], note="adds `lowStock()`"),
        Slot("transfer", "Stockroom.transfer", _J_TRANSFER, [
            Bad(sub(_J_TRANSFER, "Stockroom first = id.compareTo(other.id) < 0 ? this : other;\nStockroom second = first == this ? other : this;", "Stockroom first = this;\nStockroom second = other;"), "concurrency", "the rooms are locked in argument order, so two threads transferring in opposite directions can deadlock", ("deadlock", "lock order", "synchronized", "id")),
            Bad(sub(_J_TRANSFER, "try {\nother.add(sku, qty);\n} catch (RuntimeException e) {\nadd(sku, qty);\nthrow e;\n}", "other.add(sku, qty);"), "error-handling", "if the receiving room rejects the units (overflow), they are already removed from this room and are lost", ("rollback", "lost", "exception", "add")),
        ], note="adds `transfer()`: both rooms locked in a fixed order, with rollback"),
        Slot("snapshot", "Stockroom.snapshot", _J_SNAPSHOT, [
            Bad(_J_SNAPSHOT.replace("return new TreeMap<>(counts);", "return counts;"), "concurrency", "the internal map escapes: callers iterate or modify it without the lock (ConcurrentModificationException, corrupted counts)", ("internal", "escape", "copy", "TreeMap")),
        ], note="adds `snapshot()`"),
        Slot("total", "Stockroom.totalUnits", _J_TOTAL, [
            Bad(_J_TOTAL.replace("long sum = 0;", "int sum = 0;"), "logic", "the sum is an int, so a room with many units overflows to a negative total", ("overflow", "int", "long", "sum")),
        ], note="adds `totalUnits()`"),
    ],
)

# ---------------------------------------------------------------------------------------------------------------------
# report files
# ---------------------------------------------------------------------------------------------------------------------

REPORT_TEMPLATE = dd('''
    package reports;

    @@imports@@

    /** File helpers of the monthly report job: CSV output, newest-report lookup, archive import, customer search. */
    public final class ReportFiles {
        private ReportFiles() {
        }

        @@escape@@

        @@write@@

        @@lines@@

        @@latest@@

        @@unzip@@

        @@find@@
    }
''')

_RP_IMPORTS = dd('''
    import java.io.BufferedWriter;
    import java.io.IOException;
    import java.io.InputStream;
    import java.nio.charset.StandardCharsets;
    import java.nio.file.Files;
    import java.nio.file.Path;
    import java.nio.file.StandardCopyOption;
    import java.sql.Connection;
    import java.sql.PreparedStatement;
    import java.sql.ResultSet;
    import java.sql.SQLException;
    import java.util.ArrayList;
    import java.util.Comparator;
    import java.util.List;
    import java.util.Optional;
    import java.util.stream.Collectors;
    import java.util.stream.Stream;
    import java.util.zip.ZipEntry;
    import java.util.zip.ZipInputStream;
''')
_RP_ESCAPE = dd('''
    /** RFC 4180 style quoting: a field containing a comma, a quote or a line break is wrapped in quotes and its quotes doubled. */
    static String csvField(String s) {
        if (s.contains(",") || s.contains("\\"") || s.contains("\\n") || s.contains("\\r")) {
            return "\\"" + s.replace("\\"", "\\"\\"") + "\\"";
        }
        return s;
    }
''')
_RP_WRITE = dd('''
    /** Writes the rows as UTF-8 CSV, one line per row. */
    public static void writeCsv(Path file, List<String[]> rows) throws IOException {
        try (BufferedWriter out = Files.newBufferedWriter(file, StandardCharsets.UTF_8)) {
            for (String[] row : rows) {
                List<String> fields = new ArrayList<>();
                for (String f : row) {
                    fields.add(csvField(f));
                }
                out.write(String.join(",", fields));
                out.newLine();
            }
        }
    }
''')
_RP_LINES = dd('''
    /** All lines of a UTF-8 text file. */
    public static List<String> readLines(Path file) throws IOException {
        try (Stream<String> lines = Files.lines(file, StandardCharsets.UTF_8)) {
            return lines.collect(Collectors.toList());
        }
    }
''')
_RP_LATEST = dd('''
    /** The most recently modified regular file in dir, if any. */
    public static Optional<Path> newest(Path dir) throws IOException {
        try (Stream<Path> files = Files.list(dir)) {
            return files.filter(Files::isRegularFile).max(Comparator.comparing(p -> p.toFile().lastModified()));
        }
    }
''')
_RP_UNZIP = dd('''
    /** Extracts a zip archive below dir; entries that would land outside dir are rejected with an IOException. */
    public static void unzip(InputStream archive, Path dir) throws IOException {
        Path root = dir.toAbsolutePath().normalize();
        try (ZipInputStream zip = new ZipInputStream(archive)) {
            ZipEntry entry;
            while ((entry = zip.getNextEntry()) != null) {
                Path target = root.resolve(entry.getName()).normalize();
                if (!target.startsWith(root)) {
                    throw new IOException("zip entry escapes the target directory: " + entry.getName());
                }
                if (entry.isDirectory()) {
                    Files.createDirectories(target);
                } else {
                    Files.createDirectories(target.getParent());
                    Files.copy(zip, target, StandardCopyOption.REPLACE_EXISTING);
                }
            }
        }
    }
''')
_RP_FIND = dd('''
    /** Names of the customers whose name starts with prefix, alphabetically. */
    public static List<String> customersStartingWith(Connection db, String prefix) throws SQLException {
        String sql = "SELECT name FROM customers WHERE name LIKE ? ORDER BY name";
        try (PreparedStatement st = db.prepareStatement(sql)) {
            st.setString(1, prefix + "%");
            try (ResultSet rs = st.executeQuery()) {
                List<String> names = new ArrayList<>();
                while (rs.next()) {
                    names.add(rs.getString(1));
                }
                return names;
            }
        }
    }
''')

REPORTS = Module(
    name="java-reportfiles", lang="java", path="src/reports/ReportFiles.java", difficulty=3,
    title="ReportFiles: CSV writer, newest report, zip import, customer search",
    blurb="The `reports` package is the batch job that produces the monthly sales reports and imports archives sent by shops.",
    intro="The report job shelled out to `zip`, `ls -t` and `sqlite3`. This PR replaces that with plain Java helpers:",
    outro="Archives come from the shops' own systems and customer prefixes from the back-office search box. Ran against last month's data.",
    new_file=True,
    template=REPORT_TEMPLATE,
    ctx={"README.md": "# reports\n\nMonthly report job.\n"},
    slots=[
        Slot("imports", "<imports>", _RP_IMPORTS, []),
        Slot("escape", "csvField", _RP_ESCAPE, [
            Bad(_RP_ESCAPE.replace(' || s.contains("\\"") || s.contains("\\n") || s.contains("\\r")', ""), "logic", "only commas trigger quoting; fields with quotes or line breaks corrupt the CSV", ("quote", "newline", "csv", "RFC")),
            Bad(_RP_ESCAPE.replace('s.replace("\\"", "\\"\\"")', "s"), "logic", "embedded quotes are not doubled, so a field like `5\" pipe` ends the quoted field early", ("double", "quote", "escape")),
        ], note="adds `csvField()`"),
        Slot("write", "ReportFiles.writeCsv", _RP_WRITE, [
            Bad(dd('''
                /** Writes the rows as UTF-8 CSV, one line per row. */
                public static void writeCsv(Path file, List<String[]> rows) throws IOException {
                    BufferedWriter out = Files.newBufferedWriter(file, StandardCharsets.UTF_8);
                    for (String[] row : rows) {
                        List<String> fields = new ArrayList<>();
                        for (String f : row) {
                            fields.add(csvField(f));
                        }
                        out.write(String.join(",", fields));
                        out.newLine();
                    }
                }
            '''), "resource-leak", "the writer is never closed (no try-with-resources), so the buffered tail is lost and the file handle leaks", ("close", "try-with-resources", "flush", "leak")),
            Bad(_RP_WRITE.replace("for (String[] row : rows) {", "for (int i = 1; i < rows.size(); i++) {\n            String[] row = rows.get(i);"), "off-by-one", "the loop starts at 1, so the first row (the header) is never written", ("loop", "i = 1", "first row", "header")),
        ], note="adds `writeCsv()`"),
        Slot("lines", "ReportFiles.readLines", _RP_LINES, [
            Bad(dd('''
                /** All lines of a UTF-8 text file. */
                public static List<String> readLines(Path file) throws IOException {
                    return Files.lines(file, StandardCharsets.UTF_8).collect(Collectors.toList());
                }
            '''), "resource-leak", "the stream returned by Files.lines is not closed, which keeps the file open until garbage collection", ("close", "Stream", "try-with-resources", "Files.lines")),
        ], note="adds `readLines()`"),
        Slot("latest", "ReportFiles.newest", _RP_LATEST, [
            Bad(dd('''
                /** The most recently modified regular file in dir, if any. */
                public static Optional<Path> newest(Path dir) throws IOException {
                    return Files.list(dir).filter(Files::isRegularFile).max(Comparator.comparing(p -> p.toFile().lastModified()));
                }
            '''), "resource-leak", "Files.list returns a stream that holds the directory open; it is never closed", ("close", "Files.list", "stream", "try-with-resources")),
            Bad(_RP_LATEST.replace(".max(Comparator", ".min(Comparator"), "logic", "min instead of max returns the *oldest* report", ("min", "max", "oldest", "newest")),
        ], note="adds `newest()`"),
        Slot("unzip", "ReportFiles.unzip", _RP_UNZIP, [
            Bad(sub(_RP_UNZIP, "if (!target.startsWith(root)) {\nthrow new IOException(\"zip entry escapes the target directory: \" + entry.getName());\n}", ""), "security", "entry names are not checked, so `../../x` in an archive writes outside the target directory (zip slip)", ("zip slip", "normalize", "startsWith", "traversal")),
            Bad(_RP_UNZIP.replace("root.resolve(entry.getName()).normalize()", "root.resolve(entry.getName())"), "security", "the resolved path is not normalized before the startsWith check, so `a/../../x` passes the check and escapes (zip slip)", ("normalize", "zip slip", "startsWith")),
        ], note="adds `unzip()` for archives from shops"),
        Slot("find", "ReportFiles.customersStartingWith", _RP_FIND, [
            Bad(dd('''
                /** Names of the customers whose name starts with prefix, alphabetically. */
                public static List<String> customersStartingWith(Connection db, String prefix) throws SQLException {
                    String sql = "SELECT name FROM customers WHERE name LIKE '" + prefix + "%' ORDER BY name";
                    try (java.sql.Statement st = db.createStatement(); ResultSet rs = st.executeQuery(sql)) {
                        List<String> names = new ArrayList<>();
                        while (rs.next()) {
                            names.add(rs.getString(1));
                        }
                        return names;
                    }
                }
            '''), "security", "the prefix is concatenated into the SQL text: SQL injection from the back-office search box", ("sql", "injection", "PreparedStatement", "concatenat")),
            Bad(sub(_RP_FIND, "try (ResultSet rs = st.executeQuery()) {\nList<String> names = new ArrayList<>();\nwhile (rs.next()) {\nnames.add(rs.getString(1));\n}\nreturn names;\n}", "ResultSet rs = st.executeQuery();\nList<String> names = new ArrayList<>();\nwhile (rs.next()) {\n    names.add(rs.getString(1));\n}\nreturn names;"), "resource-leak", "the ResultSet is not closed", ("ResultSet", "close", "try-with-resources")),
        ], note="adds `customersStartingWith()` for the back-office search"),
    ],
)

# ---------------------------------------------------------------------------------------------------------------------
# task board
# ---------------------------------------------------------------------------------------------------------------------

BOARD_TEMPLATE = dd('''
    package board;

    @@imports@@

    /** Background work of the booking site: a worker loop, a periodic cache refresh and a few shared helpers. */
    public class TaskBoard {
        private final BlockingQueue<Runnable> queue = new LinkedBlockingQueue<>();
        private final ScheduledExecutorService timer = Executors.newSingleThreadScheduledExecutor();
        private final Object readyLock = new Object();
        private boolean ready;

        @@worker@@

        @@refresh@@

        @@ready@@

        @@stop@@
    }

    @@counter@@
''')

_TB_IMPORTS = dd('''
    import java.util.concurrent.BlockingQueue;
    import java.util.concurrent.Executors;
    import java.util.concurrent.LinkedBlockingQueue;
    import java.util.concurrent.ScheduledExecutorService;
    import java.util.concurrent.TimeUnit;
    import java.util.concurrent.atomic.AtomicInteger;
''')
_TB_WORKER = dd('''
    /** Runs queued tasks until the thread is interrupted. A task that throws must not kill the loop. */
    public void workLoop() {
        while (!Thread.currentThread().isInterrupted()) {
            try {
                Runnable task = queue.take();
                try {
                    task.run();
                } catch (RuntimeException e) {
                    System.err.println("task failed: " + e);
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }
    }
''')
_TB_REFRESH = dd('''
    /** Calls refresh every minute; an exception in one run must not cancel the later runs. */
    public void scheduleRefresh(Runnable refresh) {
        timer.scheduleAtFixedRate(() -> {
            try {
                refresh.run();
            } catch (RuntimeException e) {
                System.err.println("refresh failed: " + e);
            }
        }, 0, 1, TimeUnit.MINUTES);
    }
''')
_TB_READY = dd('''
    /** Blocks until markReady has been called. */
    public void awaitReady() throws InterruptedException {
        synchronized (readyLock) {
            while (!ready) {
                readyLock.wait();
            }
        }
    }

    public void markReady() {
        synchronized (readyLock) {
            ready = true;
            readyLock.notifyAll();
        }
    }
''')
_TB_STOP = dd('''
    /** Stops the timer and waits up to five seconds for a running refresh to finish. */
    public void shutdown() throws InterruptedException {
        timer.shutdown();
        if (!timer.awaitTermination(5, TimeUnit.SECONDS)) {
            timer.shutdownNow();
        }
    }
''')
_TB_COUNTER = dd('''
    /** Counts bookings; used by many request threads. */
    class BookingCounter {
        private final AtomicInteger count = new AtomicInteger();

        int next() {
            return count.incrementAndGet();
        }

        int current() {
            return count.get();
        }
    }
''')

BOARD = Module(
    name="java-taskboard", lang="java", path="src/board/TaskBoard.java", difficulty=4,
    title="TaskBoard: worker loop, periodic refresh, readiness latch, booking counter",
    blurb="The `board` package is the background machinery of a ski-lesson booking site.",
    intro="Background jobs were started ad hoc from servlets. This PR gathers them into one class:",
    outro="Runs under Tomcat with about 60 request threads. Verified by hand with a deliberately failing task and refresh.",
    new_file=True,
    template=BOARD_TEMPLATE,
    ctx={"README.md": "# board\n\nBooking site background tasks.\n"},
    slots=[
        Slot("imports", "<imports>", _TB_IMPORTS, []),
        Slot("worker", "TaskBoard.workLoop", _TB_WORKER, [
            Bad(sub(_TB_WORKER, "} catch (InterruptedException e) {\nThread.currentThread().interrupt();\n}", "} catch (InterruptedException e) {\n// ignore\n}"), "concurrency", "the interrupt is swallowed without restoring the flag, so `isInterrupted()` stays false and the loop can never be stopped by interrupting the thread", ("interrupt", "swallow", "flag", "InterruptedException")),
            Bad(sub(_TB_WORKER, "try {\ntask.run();\n} catch (RuntimeException e) {\nSystem.err.println(\"task failed: \" + e);\n}", "task.run();"), "error-handling", "a task that throws propagates out of the loop and kills the worker thread; every later task is silently never run", ("exception", "worker", "kill", "try")),
            Bad(dd('''
                /** Runs queued tasks until the thread is interrupted. A task that throws must not kill the loop. */
                public void workLoop() {
                    while (!Thread.currentThread().isInterrupted()) {
                        Runnable task = queue.poll();
                        if (task == null) {
                            continue;
                        }
                        try {
                            task.run();
                        } catch (RuntimeException e) {
                            System.err.println("task failed: " + e);
                        }
                    }
                }
            '''), "performance", "poll() returns immediately, so the loop spins at 100% CPU while the queue is empty instead of blocking in take()", ("poll", "busy", "spin", "take")),
        ], note="adds `workLoop()`"),
        Slot("refresh", "TaskBoard.scheduleRefresh", _TB_REFRESH, [
            Bad(sub(_TB_REFRESH, "try {\nrefresh.run();\n} catch (RuntimeException e) {\nSystem.err.println(\"refresh failed: \" + e);\n}", "refresh.run();"), "error-handling", "an exception from one run cancels all later runs of scheduleAtFixedRate silently, so the cache stops refreshing for good", ("scheduleAtFixedRate", "exception", "cancel", "silently")),
            Bad(_TB_REFRESH.replace("}, 0, 1, TimeUnit.MINUTES);", "}, 0, 1, TimeUnit.SECONDS);"), "logic", "the refresh runs every second instead of every minute (wrong TimeUnit)", ("TimeUnit", "SECONDS", "minute")),
        ], note="adds `scheduleRefresh()`"),
        Slot("ready", "TaskBoard.awaitReady", _TB_READY, [
            Bad(_TB_READY.replace("while (!ready) {", "if (!ready) {"), "concurrency", "wait() is guarded by `if` instead of `while`, so a spurious wake-up lets awaitReady return before markReady was called", ("spurious", "while", "wait", "if")),
            Bad(_TB_READY.replace("readyLock.notifyAll();", "readyLock.notify();"), "concurrency", "notify wakes only one of the waiting threads; the others stay blocked although the latch is open", ("notify", "notifyAll", "waiting")),
            Bad(sub(_TB_READY, "synchronized (readyLock) {\nready = true;\nreadyLock.notifyAll();\n}", "ready = true;\nsynchronized (readyLock) {\nreadyLock.notifyAll();\n}"), "concurrency", "`ready` is written outside the lock and is not volatile, so a waiter may never see the update (and a notification can be lost between its check and its wait)", ("volatile", "lock", "visibility", "lost")),
        ], note="adds a readiness latch (`awaitReady` / `markReady`)"),
        Slot("stop", "TaskBoard.shutdown", _TB_STOP, [
            Bad(sub(_TB_STOP, "timer.shutdown();", ""), "resource-leak", "the timer is never shut down, so its non-daemon thread keeps the JVM alive", ("shutdown", "thread", "executor", "leak")),
            Bad(sub(_TB_STOP, "if (!timer.awaitTermination(5, TimeUnit.SECONDS)) {\ntimer.shutdownNow();\n}", ""), "concurrency", "shutdown() returns before a running refresh has finished although the doc promises to wait", ("awaitTermination", "wait", "shutdownNow")),
        ], note="adds `shutdown()`"),
        Slot("counter", "BookingCounter", _TB_COUNTER, [
            Bad(dd('''
                /** Counts bookings; used by many request threads. */
                class BookingCounter {
                    private int count;

                    int next() {
                        return ++count;
                    }

                    int current() {
                        return count;
                    }
                }
            '''), "concurrency", "a plain int incremented from many request threads loses updates and may hand out the same booking number twice", ("AtomicInteger", "race", "increment", "visibility")),
        ], note="adds `BookingCounter`"),
    ],
)

MODULES = [STOCKROOM, REPORTS, BOARD]
for _m in MODULES:
    validate_module(_m)

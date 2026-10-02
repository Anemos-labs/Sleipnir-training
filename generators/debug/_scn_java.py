"""Scenarios (reproduction programs) for the java slot modules of the review bank: ``javac`` everything, then ``java -cp build Scenario``."""
from __future__ import annotations

from fx import dd

STOCKROOM_SCENARIO = dd('''
    import java.util.ArrayList;
    import java.util.List;
    import java.util.Map;
    import stock.Stockroom;

    public class Scenario {
        interface Body {
            Object run() throws Exception;
        }

        static void show(String label, Body body) {
            try {
                System.out.println(label + ": " + body.run());
            } catch (Throwable t) {
                System.out.println(label + ": threw " + t.getClass().getSimpleName() + ": " + t.getMessage());
            }
        }

        public static void main(String[] args) throws Exception {
            Thread watchdog = new Thread(() -> {
                try {
                    Thread.sleep(8000);
                } catch (InterruptedException e) {
                    return;
                }
                System.out.println("scenario stuck for 8s (deadlock?)");
                System.out.flush();
                Runtime.getRuntime().halt(3);
            });
            watchdog.setDaemon(true);
            watchdog.start();

            Stockroom a = new Stockroom("A1");
            Stockroom b = new Stockroom("B2");
            show("add 5 bolts", () -> a.add("bolt", 5));
            show("add 0 bolts", () -> a.add("bolt", 0));
            show("add -1 bolts", () -> a.add("bolt", -1));
            show("add 12 washers", () -> a.add("washer", 12));
            show("add a huge number of nuts", () -> a.add("nut", Integer.MAX_VALUE - 2));
            show("add 5 more nuts", () -> a.add("nut", 5));

            show("remove 2 bolts", () -> {
                a.remove("bolt", 2);
                return "ok";
            });
            show("remove the last 3 bolts", () -> {
                a.remove("bolt", 3);
                return "ok";
            });
            show("remove 1 more bolt", () -> {
                a.remove("bolt", 1);
                return "ok";
            });
            for (String[] s : new String[][] {{"zinc", "1"}, {"axle", "2"}, {"cog", "3"}, {"dowel", "1"}, {"eye", "4"}}) {
                a.add(s[0], Integer.parseInt(s[1]));
            }
            show("lowStock(4)", () -> a.lowStock(4));

            show("snapshot", () -> a.snapshot());
            show("snapshot after the caller changed its copy", () -> {
                Map<String, Integer> copy = a.snapshot();
                copy.put("hacked", 1);
                return a.snapshot().containsKey("hacked");
            });

            show("transfer 5 washers", () -> {
                a.transfer(b, "washer", 5);
                return a.snapshot().get("washer") + " left, " + b.snapshot().get("washer") + " arrived";
            });
            b.add("cog", Integer.MAX_VALUE);
            show("transfer into a full room", () -> {
                a.transfer(b, "cog", 3);
                return "ok";
            });
            show("cogs left in the sending room", () -> a.snapshot().get("cog"));
            show("transfer to the same room", () -> {
                a.transfer(a, "cog", 1);
                return "ok";
            });

            Stockroom big = new Stockroom("C3");
            big.add("a", 2_000_000_000);
            big.add("b", 2_000_000_000);
            show("totalUnits of two big counts", () -> big.totalUnits());

            Stockroom x = new Stockroom("X");
            Stockroom y = new Stockroom("Y");
            x.add("crate", 5000);
            y.add("crate", 5000);
            List<Thread> threads = new ArrayList<>();
            for (int t = 0; t < 2; t++) {
                final boolean forward = t == 0;
                Thread th = new Thread(() -> {
                    for (int i = 0; i < 3000; i++) {
                        if (forward) {
                            x.transfer(y, "crate", 1);
                        } else {
                            y.transfer(x, "crate", 1);
                        }
                    }
                });
                threads.add(th);
                th.start();
            }
            for (Thread th : threads) {
                th.join();
            }
            System.out.println("after 6000 opposite transfers: " + x.totalUnits() + " + " + y.totalUnits());
        }
    }
''')

SCENARIOS = {"java-stockroom": STOCKROOM_SCENARIO}

"""unitconv (java): a unit converter extended with mass, time, listing, custom units, rounding, text parsing, temperatures and ratios."""
import random

from fx import dd
from generators.feature._slices import App, Slice, fmt, register_app

README = dd('''
    # unitconv

    A small unit converter for a recipe and logistics app (Java 17, standard library only). The tests are a plain `TestMain` (no
    JUnit): `javac -d build $(find . -name '*.java') && java -cp build TestMain`.

    ## Layout

    * `src/unitconv/Converter.java`: the converter.
    * `src/unitconv/Unit.java`: a unit (package-private).
    * `test/TestMain.java`: tests.

    ## Basics

    Every unit belongs to a dimension (`length`, ...) and is defined by a factor to the base unit of that dimension.

    * `new Converter()` knows the length units `m` (the base), `km` (1000 m), `cm` (0.01), `mm` (0.001), `mi` (1609.344),
      `yd` (0.9144), `ft` (0.3048) and `in` (0.0254). Unit names are case-sensitive.
    * `converter.convert(value, from, to)` converts a number between two units of the same dimension and returns a `double`
      (`value * factor(from) / factor(to)`). Unknown or `null` unit names, units of different dimensions and values that are
      NaN or infinite are an `IllegalArgumentException`.
''')

CONVERTER = '''\
package unitconv;

import java.util.*;
@@uniq imports

/** Converts numbers between units. */
public class Converter {
    private final Map<String, Unit> units = new LinkedHashMap<>();
    @@slot fields

    public Converter() {
        add("m", 1.0, "length");
        add("km", 1000.0, "length");
        add("cm", 0.01, "length");
        add("mm", 0.001, "length");
        add("mi", 1609.344, "length");
        add("yd", 0.9144, "length");
        add("ft", 0.3048, "length");
        add("in", 0.0254, "length");
        @@slot builtin_units
    }

    private void add(String name, double factor, String dimension) {
        units.put(name, new Unit(name, factor, 0.0, dimension));
    }

    private Unit unit(String name) {
        if (name == null) {
            throw new IllegalArgumentException("unit name is required");
        }
        Unit u = units.get(name);
        @@slot unit_fallback
        if (u == null) {
            throw new IllegalArgumentException("unknown unit: " + name);
        }
        return u;
    }

    public double convert(double value, String from, String to) {
        if (Double.isNaN(value) || Double.isInfinite(value)) {
            throw new IllegalArgumentException("value must be a finite number");
        }
        Unit a = unit(from);
        Unit b = unit(to);
        if (!a.dimension().equals(b.dimension())) {
            throw new IllegalArgumentException("cannot convert " + a.dimension() + " to " + b.dimension());
        }
        @@slot convert_checks
        return (value * a.factor() + a.offset() - b.offset()) / b.factor();
    }

    @@blocks methods
}
'''

UNIT = '''\
package unitconv;

/** A unit: value in the base unit = value * factor + offset. */
record Unit(String name, double factor, double offset, String dimension) {
}
'''

TEST_HEAD = '''\
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.util.*;
import unitconv.*;
@@uniq imports

public class TestMain {
    static int failures = 0;

    static void eq(Object expected, Object actual, String msg) {
        if (!Objects.equals(expected, actual)) {
            failures++;
            System.out.println("FAIL: " + msg + ": expected <" + expected + "> but got <" + actual + ">");
        }
    }

    static void near(double expected, double actual, String msg) {
        if (Double.isNaN(actual) || Math.abs(expected - actual) > 1e-9 * Math.max(1.0, Math.abs(expected))) {
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
    static void testBasicConversions() {
        Converter c = new Converter();
        near(1000.0, c.convert(1, "km", "m"), "km to m");
        near(2.54, c.convert(1, "in", "cm"), "in to cm");
        near(1.0, c.convert(5280, "ft", "mi"), "feet to miles");
        near(5.0, c.convert(5, "m", "m"), "same unit");
    }

    static void testBasicErrors() {
        Converter c = new Converter();
        expect(IllegalArgumentException.class, () -> c.convert(1, "m", "parsec"), "unknown unit");
        expect(IllegalArgumentException.class, () -> c.convert(1, null, "m"), "null unit");
        expect(IllegalArgumentException.class, () -> c.convert(Double.NaN, "m", "km"), "NaN");
    }
'''

HIDDEN_BASE = '''
    static void testBaseLengths() {
        Converter c = new Converter();
        near(1000.0, c.convert(1, "km", "m"), "km");
        near(0.01, c.convert(1, "cm", "m"), "cm");
        near(0.001, c.convert(1, "mm", "m"), "mm");
        near(1609.344, c.convert(1, "mi", "m"), "mi");
        near(0.9144, c.convert(1, "yd", "m"), "yd");
        near(0.3048, c.convert(1, "ft", "m"), "ft");
        near(0.0254, c.convert(1, "in", "m"), "in");
        near(91.44, c.convert(100, "yd", "m"), "100 yd");
        near(3.0, c.convert(1, "yd", "ft"), "yd to ft");
        near(12.0, c.convert(1, "ft", "in"), "ft to in");
        near(1.609344, c.convert(1, "mi", "km"), "mi to km");
        near(-2.54, c.convert(-1, "in", "cm"), "negative values");
        near(0.0, c.convert(0, "mi", "mm"), "zero");
        near(1.0, c.convert(1000000, "mm", "km"), "mm to km");
        near(42.0, c.convert(42, "ft", "ft"), "same unit");
    }

    static void testBaseErrors() {
        Converter c = new Converter();
        for (String bad : new String[] {"parsec", "KM", "Km", "", " m", "m ", "meter", "kg"}) {
            expect(IllegalArgumentException.class, () -> c.convert(1, bad, "m"), "unknown source " + bad);
            expect(IllegalArgumentException.class, () -> c.convert(1, "m", bad), "unknown target " + bad);
        }
        expect(IllegalArgumentException.class, () -> c.convert(1, null, "m"), "null source");
        expect(IllegalArgumentException.class, () -> c.convert(1, "m", null), "null target");
        expect(IllegalArgumentException.class, () -> c.convert(Double.NaN, "m", "km"), "NaN");
        expect(IllegalArgumentException.class, () -> c.convert(Double.POSITIVE_INFINITY, "m", "km"), "infinity");
        expect(IllegalArgumentException.class, () -> c.convert(Double.NEGATIVE_INFINITY, "m", "m"), "negative infinity");
        near(1.0, new Converter().convert(1, "m", "m"), "a second converter works too");
    }
'''


def make_slices(rng: random.Random):
    max_dec = rng.choice([6, 10])
    name_max = rng.choice([16, 24])
    kw1, kw2 = rng.choice([("to", "in"), ("to", "as")])
    S = []

    S.append(Slice(
        id="mass", title="Mass units", d=1,
        pitch=("The recipe app has to convert ounces to grams and the converter only knows lengths.",
               "Weights are missing: people ask for grams, ounces and pounds."),
        reqs=("The converter also knows the dimension `mass`: `kg` (the base), `g` (0.001 kg), `mg` (0.000001 kg), `lb` (0.45359237 kg) and `oz` (0.028349523125 kg). Converting between a mass unit and a length unit is an `IllegalArgumentException`, like any other mix of dimensions.",),
        code={
            "src/unitconv/Converter.java::builtin_units": '''
                add("kg", 1.0, "mass");
                add("g", 0.001, "mass");
                add("mg", 0.000001, "mass");
                add("lb", 0.45359237, "mass");
                add("oz", 0.028349523125, "mass");
            ''',
        },
        readme="## Mass units\n\n`kg` (base), `g`, `mg`, `lb` and `oz` in the dimension `mass`.\n",
        vtests='''
            static void testMassBasic() {
                near(453.59237, new Converter().convert(1, "lb", "g"), "pound");
            }
        ''',
        tests='''
            static void testMass() {
                Converter c = new Converter();
                near(1000.0, c.convert(1, "kg", "g"), "kg to g");
                near(1.0, c.convert(1000000, "mg", "kg"), "mg to kg");
                near(453.59237, c.convert(1, "lb", "g"), "lb to g");
                near(28.349523125, c.convert(1, "oz", "g"), "oz to g");
                near(16.0, c.convert(1, "lb", "oz"), "lb to oz");
                near(2.20462262184878, c.convert(1, "kg", "lb"), "kg to lb");
                near(100.0, c.convert(100, "g", "g"), "g to g");
            }

            static void testMassIsNotLength() {
                Converter c = new Converter();
                expect(IllegalArgumentException.class, () -> c.convert(1, "kg", "m"), "mass to length");
                expect(IllegalArgumentException.class, () -> c.convert(1, "ft", "oz"), "length to mass");
                near(2.0, c.convert(2, "km", "km"), "lengths still work");
                expect(IllegalArgumentException.class, () -> c.convert(1, "KG", "g"), "case matters");
            }
        ''',
    ))

    S.append(Slice(
        id="time", title="Time units", d=1,
        pitch=("Delivery estimates come in minutes and hours and the converter doesn't know either.",
               "People want to convert durations."),
        reqs=("The converter also knows the dimension `time`: `s` (the base), `ms` (0.001 s), `min` (60 s), `h` (3600 s) and `d` (86400 s). Mixing time with other dimensions is an `IllegalArgumentException`.",),
        code={
            "src/unitconv/Converter.java::builtin_units": '''
                add("s", 1.0, "time");
                add("ms", 0.001, "time");
                add("min", 60.0, "time");
                add("h", 3600.0, "time");
                add("d", 86400.0, "time");
            ''',
        },
        readme="## Time units\n\n`s` (base), `ms`, `min`, `h` and `d` in the dimension `time`.\n",
        vtests='''
            static void testTimeBasic() {
                near(90.0, new Converter().convert(1.5, "h", "min"), "hours to minutes");
            }
        ''',
        tests='''
            static void testTime() {
                Converter c = new Converter();
                near(3600.0, c.convert(1, "h", "s"), "h to s");
                near(1.0, c.convert(1000, "ms", "s"), "ms to s");
                near(1440.0, c.convert(1, "d", "min"), "d to min");
                near(24.0, c.convert(1, "d", "h"), "d to h");
                near(0.5, c.convert(30, "min", "h"), "min to h");
                near(172800.0, c.convert(2, "d", "s"), "d to s");
                expect(IllegalArgumentException.class, () -> c.convert(1, "h", "m"), "time to length");
                expect(IllegalArgumentException.class, () -> c.convert(1, "s", "mi"), "time to length again");
                expect(IllegalArgumentException.class, () -> c.convert(1, "H", "min"), "case matters");
                near(1.0, c.convert(1, "m", "m"), "lengths still work");
            }
        ''',
        cross={
            "mass": {"tests": '''
                static void testTimeIsNotMass() {
                    Converter c = new Converter();
                    expect(IllegalArgumentException.class, () -> c.convert(1, "min", "g"), "time to mass");
                    expect(IllegalArgumentException.class, () -> c.convert(1, "kg", "s"), "mass to time");
                    near(2.0, c.convert(120, "s", "min"), "time");
                    near(500.0, c.convert(0.5, "kg", "g"), "mass");
                }
            '''},
        },
    ))

    S.append(Slice(
        id="listing", title="Listing units", d=1,
        pitch=("The conversion dialog needs to offer the known units and nobody wants to hard-code them in the UI.",
               "The app needs to know which units and dimensions the converter supports."),
        reqs=("`converter.units()` returns a new list of all unit names in alphabetical order; `converter.units(dimension)` only those of one dimension (an unknown dimension is an `IllegalArgumentException`). `converter.dimension(unit)` returns the dimension of a unit (`IllegalArgumentException` for unknown or `null` units). Changing a returned list does not change the converter.",),
        code={
            "src/unitconv/Converter.java::methods": '''
                public List<String> units() {
                    List<String> out = new ArrayList<>(units.keySet());
                    Collections.sort(out);
                    return out;
                }

                public List<String> units(String dimension) {
                    List<String> out = new ArrayList<>();
                    for (Unit u : units.values()) {
                        if (u.dimension().equals(dimension)) {
                            out.add(u.name());
                        }
                    }
                    if (out.isEmpty()) {
                        throw new IllegalArgumentException("unknown dimension: " + dimension);
                    }
                    Collections.sort(out);
                    return out;
                }

                public String dimension(String unit) {
                    return unit(unit).dimension();
                }
            ''',
        },
        readme="## Listing units\n\n`units()`, `units(dimension)` (alphabetical copies) and `dimension(unit)`.\n",
        vtests='''
            static void testListingBasic() {
                eq("length", new Converter().dimension("ft"), "dimension");
            }
        ''',
        tests='''
            static void testListing() {
                Converter c = new Converter();
                check(c.units().containsAll(list("cm", "ft", "in", "km", "m", "mi", "mm", "yd")), "all lengths are listed");
                List<String> sorted = new ArrayList<>(c.units());
                Collections.sort(sorted);
                eq(sorted, c.units(), "sorted");
                eq(list("cm", "ft", "in", "km", "m", "mi", "mm", "yd"), c.units("length"), "length units");
                eq("length", c.dimension("mi"), "dimension of mi");
                c.units().clear();
                c.units("length").clear();
                eq(8, c.units("length").size(), "copies");
            }

            static void testListingErrors() {
                Converter c = new Converter();
                expect(IllegalArgumentException.class, () -> c.units("colour"), "unknown dimension");
                expect(IllegalArgumentException.class, () -> c.units((String) null), "null dimension");
                expect(IllegalArgumentException.class, () -> c.dimension("parsec"), "unknown unit");
                expect(IllegalArgumentException.class, () -> c.dimension(null), "null unit");
            }
        ''',
        cross={
            "mass": {"tests": '''
                static void testListingWithMass() {
                    Converter c = new Converter();
                    eq(list("g", "kg", "lb", "mg", "oz"), c.units("mass"), "mass units");
                    eq("mass", c.dimension("oz"), "dimension of oz");
                    check(c.units().containsAll(list("g", "kg", "m")), "all units");
                    check(c.units().size() >= 13, "at least 13 units");
                }
            '''},
            "time": {"tests": '''
                static void testListingWithTime() {
                    Converter c = new Converter();
                    eq(list("d", "h", "min", "ms", "s"), c.units("time"), "time units");
                    eq("time", c.dimension("min"), "dimension of min");
                }
            '''},
        },
    ))

    S.append(Slice(
        id="define", title="Custom units", d=2,
        pitch=("The kitchen counts in tablespoons and the shipping team in pallets, and neither can be added without a code change.",
               "Users need to teach the converter their own units."),
        reqs=(f"`converter.define(name, factor, dimension)` adds a unit. The name must be 1 to {name_max} characters, letters, digits and underscores, starting with a letter (`IllegalArgumentException`); the factor must be finite and greater than 0 (`IllegalArgumentException`); the dimension must be one the converter already knows, i.e. some unit has it (`IllegalArgumentException`); a name that is already taken is an `IllegalStateException`. The factor is relative to the base unit of the dimension, like the factors of the built-in units. The checks run in the order listed, a failed call changes nothing, and the new unit works in `convert` right away.",),
        code={
            "src/unitconv/Converter.java::methods": f'''
                public void define(String name, double factor, String dimension) {{
                    if (name == null || !name.matches("[A-Za-z][A-Za-z0-9_]{{0,{name_max - 1}}}")) {{
                        throw new IllegalArgumentException("bad unit name: " + name);
                    }}
                    if (Double.isNaN(factor) || Double.isInfinite(factor) || factor <= 0) {{
                        throw new IllegalArgumentException("factor must be finite and positive");
                    }}
                    boolean known = false;
                    for (Unit u : units.values()) {{
                        if (u.dimension().equals(dimension)) {{
                            known = true;
                        }}
                    }}
                    if (!known) {{
                        throw new IllegalArgumentException("unknown dimension: " + dimension);
                    }}
                    @@slot define_checks
                    if (units.containsKey(name)) {{
                        throw new IllegalStateException("unit already exists: " + name);
                    }}
                    add(name, factor, dimension);
                }}
            ''',
        },
        readme=f"## Custom units\n\n`converter.define(name, factor, dimension)` adds a unit (name: 1 to {name_max} letters, digits or underscores starting with a letter; positive finite factor relative to the base unit; existing dimension; taken names are an `IllegalStateException`).\n",
        vtests='''
            static void testDefineBasic() {
                Converter c = new Converter();
                c.define("furlong", 201.168, "length");
                near(8.0, c.convert(1, "mi", "furlong"), "furlongs");
            }
        ''',
        tests=fmt('''
            static void testDefine() {
                Converter c = new Converter();
                c.define("furlong", 201.168, "length");
                c.define("Pace_2", 0.75, "length");
                near(8.0, c.convert(1, "mi", "furlong"), "mile in furlongs");
                near(0.75, c.convert(1, "Pace_2", "m"), "pace");
                near(1000.0 / 0.75, c.convert(1, "km", "Pace_2"), "km in paces");
                near(201.168, c.convert(1, "furlong", "m"), "furlong in m");
                c.define("x".repeat(__M__), 2.0, "length");
                near(2.0, c.convert(1, "x".repeat(__M__), "m"), "longest name");
                near(1.0, new Converter().convert(1, "m", "m"), "other converters are not affected");
                expect(IllegalArgumentException.class, () -> new Converter().convert(1, "furlong", "m"), "not shared");
            }

            static void testDefineValidation() {
                Converter c = new Converter();
                for (String bad : new String[] {"", "1abc", "a b", "a-b", "_x", null, "x".repeat(__M__ + 1), "é"}) {
                    expect(IllegalArgumentException.class, () -> c.define(bad, 1.0, "length"), "name '" + bad + "'");
                }
                for (double bad : new double[] {0.0, -1.0, Double.NaN, Double.POSITIVE_INFINITY}) {
                    expect(IllegalArgumentException.class, () -> c.define("foo", bad, "length"), "factor " + bad);
                }
                expect(IllegalArgumentException.class, () -> c.define("foo", 1.0, "colour"), "unknown dimension");
                expect(IllegalArgumentException.class, () -> c.define("foo", 1.0, null), "null dimension");
                expect(IllegalStateException.class, () -> c.define("km", 1.0, "length"), "taken name");
                expect(IllegalArgumentException.class, () -> c.define("km", 0.0, "length"), "factor is checked before the name is looked up");
                expect(IllegalArgumentException.class, () -> c.define("", 0.0, "colour"), "name first");
                expect(IllegalArgumentException.class, () -> c.convert(1, "foo", "m"), "nothing was defined");
                c.define("foo", 1.0, "length");
                expect(IllegalStateException.class, () -> c.define("foo", 2.0, "length"), "twice");
                near(1.0, c.convert(1, "foo", "m"), "first definition stays");
            }
        ''', M=name_max),
        cross={
            "mass": {"tests": '''
                static void testDefineInMass() {
                    Converter c = new Converter();
                    c.define("stone", 6.35029318, "mass");
                    near(14.0, c.convert(1, "stone", "lb"), "stone");
                    expect(IllegalStateException.class, () -> c.define("g", 1.0, "mass"), "taken");
                }
            '''},
            "listing": {"tests": '''
                static void testDefinedUnitsAreListed() {
                    Converter c = new Converter();
                    c.define("furlong", 201.168, "length");
                    check(c.units().contains("furlong"), "listed");
                    check(c.units("length").contains("furlong"), "listed in its dimension");
                    eq("length", c.dimension("furlong"), "dimension");
                    eq(9, c.units("length").size(), "nine length units");
                }
            '''},
        },
    ))

    S.append(Slice(
        id="precision", title="Rounded results", d=2,
        pitch=("Converted amounts show up as 28.349523125 in the shopping list.",
               "Results should be available rounded to a number of decimals."),
        reqs=(f"`converter.convertRounded(value, from, to, decimals)` converts like `convert` and rounds the result half up to `decimals` decimal places (0 to {max_dec}, otherwise `IllegalArgumentException`, checked first). Rounding works on the shortest decimal representation of the converted number, the one `Double.toString` shows: `12.345` with 2 decimals gives `12.35`, and `-12.345` gives `-12.35` (halves round away from zero). All errors of `convert` apply.",),
        code={
            "src/unitconv/Converter.java::imports": "import java.math.BigDecimal;\nimport java.math.RoundingMode;",
            "src/unitconv/Converter.java::methods": f'''
                public double convertRounded(double value, String from, String to, int decimals) {{
                    if (decimals < 0 || decimals > {max_dec}) {{
                        throw new IllegalArgumentException("decimals must be between 0 and {max_dec}");
                    }}
                    double raw = convert(value, from, to);
                    return BigDecimal.valueOf(raw).setScale(decimals, RoundingMode.HALF_UP).doubleValue();
                }}
            ''',
        },
        readme=f"## Rounded results\n\n`converter.convertRounded(value, from, to, decimals)` rounds half up (away from zero for halves) on the shortest decimal representation; `decimals` 0 to {max_dec}.\n",
        vtests='''
            static void testRoundedBasic() {
                eq(2.54, new Converter().convertRounded(1, "in", "cm", 2), "inch in cm");
            }
        ''',
        tests=fmt('''
            static void testRounding() {
                Converter c = new Converter();
                eq(2.54, c.convertRounded(1, "in", "cm", 2), "2 decimals");
                eq(3.0, c.convertRounded(1, "in", "cm", 0), "0 decimals");
                eq(2.5, c.convertRounded(1, "in", "cm", 1), "1 decimal");
                eq(12.35, c.convertRounded(12.345, "m", "m", 2), "12.345 rounds up");
                eq(-12.35, c.convertRounded(-12.345, "m", "m", 2), "negative halves round away from zero");
                eq(12.34, c.convertRounded(12.344, "m", "m", 2), "below half");
                eq(0.0, c.convertRounded(0.004, "m", "m", 2), "to zero");
                eq(1609.34, c.convertRounded(1, "mi", "m", 2), "mile");
                eq(1.609, c.convertRounded(1, "mi", "km", 3), "mile in km");
                eq(5.0, c.convertRounded(5, "m", "m", __M__), "maximum decimals");
                eq(0.123457, c.convertRounded(0.1234567, "m", "m", 6), "six decimals");
            }

            static void testRoundingErrors() {
                Converter c = new Converter();
                expect(IllegalArgumentException.class, () -> c.convertRounded(1, "m", "km", -1), "negative decimals");
                expect(IllegalArgumentException.class, () -> c.convertRounded(1, "m", "km", __M__ + 1), "too many decimals");
                expect(IllegalArgumentException.class, () -> c.convertRounded(1, "m", "km", 99), "far too many");
                expect(IllegalArgumentException.class, () -> c.convertRounded(1, "m", "nope", 2), "unknown unit");
                expect(IllegalArgumentException.class, () -> c.convertRounded(Double.NaN, "m", "km", 2), "NaN");
                expect(IllegalArgumentException.class, () -> c.convertRounded(1, "m", "nope", -1), "decimals are checked first");
            }
        ''', M=max_dec),
    ))

    S.append(Slice(
        id="parse", title="Parsing text requests", d=3,
        pitch=("Users type '12.5 km to mi' into a search box and the app splits the string by hand.",
               "The converter should understand requests written as text."),
        reqs=(f"`converter.parse(text)` converts a request written like `12.5 km {kw1} mi` and returns the result as a `double`. The text is a number, a unit name, the word `{kw1}` or `{kw2}` (any case) and a unit name, separated by white space (several blanks and tabs are fine, and leading or trailing blanks are ignored). The number is an optional sign, digits with an optional fraction (`.5` and `5.` are fine) and an optional exponent (`1e3`, `2.5E-2`). Unit names are everything between the blanks. Anything that does not have this shape, a `null` text and numbers outside the `double` range are an `IllegalArgumentException` whose message starts with `cannot parse`; unknown units and mismatched dimensions are reported as for `convert`.",),
        code={
            "src/unitconv/Converter.java::methods": f'''
                private static final java.util.regex.Pattern REQUEST = java.util.regex.Pattern.compile(
                        "\\\\s*([+-]?(?:\\\\d+\\\\.?\\\\d*|\\\\.\\\\d+)(?:[eE][+-]?\\\\d+)?)\\\\s+(\\\\S+)\\\\s+(?i:{kw1}|{kw2})\\\\s+(\\\\S+)\\\\s*");

                public double parse(String text) {{
                    java.util.regex.Matcher m = text == null ? null : REQUEST.matcher(text);
                    if (m == null || !m.matches()) {{
                        throw new IllegalArgumentException("cannot parse: " + text);
                    }}
                    double value;
                    try {{
                        value = Double.parseDouble(m.group(1));
                    }} catch (NumberFormatException e) {{
                        throw new IllegalArgumentException("cannot parse: " + text);
                    }}
                    if (Double.isInfinite(value)) {{
                        throw new IllegalArgumentException("cannot parse: " + text + " (number out of range)");
                    }}
                    return convert(value, m.group(2), m.group(3));
                }}
            ''',
        },
        readme=f"## Parsing text requests\n\n`converter.parse(\"12.5 km {kw1} mi\")` (the word is `{kw1}` or `{kw2}`, any case) returns the converted number; malformed text is an `IllegalArgumentException` starting with `cannot parse`.\n",
        vtests=f'''
            static void testParseBasic() {{
                near(1000.0, new Converter().parse("1 km {kw1} m"), "parse");
            }}
        ''',
        tests=fmt('''
            static void testParse() {
                Converter c = new Converter();
                near(1000.0, c.parse("1 km __K1__ m"), "plain");
                near(1000.0, c.parse("  1   km\\t__K1__    m  "), "blanks");
                near(12500.0 / 1609.344, c.parse("12.5 km __K1__ mi"), "fraction");
                near(0.0254 * 0.5, c.parse(".5 in __K2__ m"), "leading point");
                near(5.0, c.parse("5. m __K1__ m"), "trailing point");
                near(25.4, c.parse("1e3 in __K1__ m"), "exponent");
                near(0.0254 * 0.025, c.parse("2.5E-2 in __K1__ m"), "capital exponent");
                near(-2.54, c.parse("-1 in __K1__ cm"), "negative");
                near(2.54, c.parse("+1 in __K1__ cm"), "plus sign");
                near(1000.0, c.parse("1 km __K1U__ m"), "keyword in capitals");
                near(1000.0, c.parse("1 km __K2U__ m"), "second keyword");
            }

            static void testParseErrors() {
                Converter c = new Converter();
                for (String bad : new String[] {"", "   ", "km to m", "1 km", "1 km to", "1 km to m extra", "1 to m", "one km to m", "1 km into m",
                        "1,5 km to m", "1 km __K1__", "1km __K1__ m", "1e km __K1__ m", "-- 1 km __K1__ m", "1 km  m", "1 km x m"}) {
                    expect(IllegalArgumentException.class, () -> c.parse(bad), "text '" + bad + "'");
                }
                expect(IllegalArgumentException.class, () -> c.parse(null), "null text");
                try {
                    c.parse("1 km into m");
                    check(false, "no exception");
                } catch (IllegalArgumentException e) {
                    check(e.getMessage().startsWith("cannot parse"), "message: " + e.getMessage());
                }
                try {
                    c.parse("1e999 km __K1__ m");
                    check(false, "no exception for huge numbers");
                } catch (IllegalArgumentException e) {
                    check(e.getMessage().startsWith("cannot parse"), "message: " + e.getMessage());
                }
                expect(IllegalArgumentException.class, () -> c.parse("1 parsec __K1__ m"), "unknown unit");
                expect(IllegalArgumentException.class, () -> c.parse("1 m __K1__ parsec"), "unknown target");
            }
        ''', K1=kw1, K2=kw2, K1U=kw1.upper(), K2U=kw2.upper()),
        cross={
            "define": {"tests": fmt('''
                static void testParseDefinedUnits() {
                    Converter c = new Converter();
                    c.define("furlong", 201.168, "length");
                    near(8.0, c.parse("1 mi __K1__ furlong"), "defined unit");
                }
            ''', K1=kw1)},
            "mass": {"tests": fmt('''
                static void testParseMass() {
                    Converter c = new Converter();
                    near(453.59237, c.parse("1 lb __K1__ g"), "pounds");
                    expect(IllegalArgumentException.class, () -> c.parse("1 lb __K1__ m"), "mass to length");
                }
            ''', K1=kw1)},
        },
    ))

    S.append(Slice(
        id="temperature", title="Temperatures", d=3,
        pitch=("Oven temperatures come in Fahrenheit and Celsius and the converter only multiplies.",
               "Temperatures need conversions that include an offset."),
        reqs=("The converter also knows the dimension `temperature`: `K` (kelvin, the base), `C` (degrees Celsius: K = C + 273.15) and `F` (degrees Fahrenheit: K = (F - 32) * 5 / 9 + 273.15). Conversions between them add the offsets (`100 C` is `212 F`, `0 C` is `273.15 K`, `-40 C` is `-40 F`). Mixing temperatures with other dimensions is an `IllegalArgumentException`.",
              "A temperature below absolute zero (below 0 K once converted to kelvin, with a tolerance of 1e-9) is an `IllegalArgumentException`, checked on the value that is given (before it is converted)."),
        code={
            "src/unitconv/Converter.java::fields": "private static final double ABSOLUTE_ZERO_TOLERANCE = 1e-9;",
            "src/unitconv/Converter.java::builtin_units": '''
                units.put("K", new Unit("K", 1.0, 0.0, "temperature"));
                units.put("C", new Unit("C", 1.0, 273.15, "temperature"));
                units.put("F", new Unit("F", 5.0 / 9.0, 273.15 - 32.0 * 5.0 / 9.0, "temperature"));
            ''',
            "src/unitconv/Converter.java::convert_checks": '''
                if (a.dimension().equals("temperature") && value * a.factor() + a.offset() < -ABSOLUTE_ZERO_TOLERANCE) {
                    throw new IllegalArgumentException("below absolute zero: " + value + " " + a.name());
                }
            ''',
        },
        readme="## Temperatures\n\n`K` (base), `C` and `F` with offsets (`K = C + 273.15`, `K = (F - 32) * 5 / 9 + 273.15`); values below absolute zero are an `IllegalArgumentException`.\n",
        vtests='''
            static void testTemperatureBasic() {
                near(212.0, new Converter().convert(100, "C", "F"), "boiling");
            }
        ''',
        tests='''
            static void testTemperatures() {
                Converter c = new Converter();
                near(212.0, c.convert(100, "C", "F"), "C to F");
                near(100.0, c.convert(212, "F", "C"), "F to C");
                near(273.15, c.convert(0, "C", "K"), "0 C in K");
                near(-273.15, c.convert(0, "K", "C"), "0 K in C");
                near(-40.0, c.convert(-40, "C", "F"), "-40 is the same");
                near(-40.0, c.convert(-40, "F", "C"), "-40 the other way");
                near(255.3722222222222, c.convert(0, "F", "K"), "0 F in K");
                near(98.6, c.convert(37, "C", "F"), "body temperature");
                near(100.0, c.convert(100, "K", "K"), "kelvin to kelvin");
                near(-459.67, c.convert(0, "K", "F"), "absolute zero in F");
                near(350.0, c.convert(176.66666666666666, "C", "F"), "oven");
            }

            static void testAbsoluteZero() {
                Converter c = new Converter();
                near(0.0, c.convert(0, "K", "K"), "0 K itself is fine");
                near(-273.15, c.convert(-273.15, "C", "C"), "-273.15 C is fine");
                near(-459.67, c.convert(-459.67, "F", "F"), "-459.67 F is fine");
                expect(IllegalArgumentException.class, () -> c.convert(-0.001, "K", "C"), "below 0 K");
                expect(IllegalArgumentException.class, () -> c.convert(-273.16, "C", "F"), "below 0 K in C");
                expect(IllegalArgumentException.class, () -> c.convert(-500, "F", "K"), "below 0 K in F");
                expect(IllegalArgumentException.class, () -> c.convert(-1, "K", "K"), "same unit too");
                expect(IllegalArgumentException.class, () -> c.convert(1, "C", "m"), "temperature to length");
                expect(IllegalArgumentException.class, () -> c.convert(1, "km", "F"), "length to temperature");
                expect(IllegalArgumentException.class, () -> c.convert(1, "c", "F"), "case matters");
                near(-1000.0, c.convert(-1000, "m", "m"), "other dimensions may be negative");
            }
        ''',
        cross={
            "mass": {"tests": '''
                static void testTemperatureIsNotMass() {
                    Converter c = new Converter();
                    expect(IllegalArgumentException.class, () -> c.convert(1, "C", "kg"), "temperature to mass");
                    expect(IllegalArgumentException.class, () -> c.convert(-5, "kg", "K"), "mass to temperature");
                    near(-5.0, c.convert(-5, "kg", "kg"), "negative masses are fine");
                }
            '''},
            "define": {
                "reqs": ("Units cannot be defined in the dimension `temperature` (they would have no offset): `IllegalArgumentException`, checked together with the dimension check.",),
                "code": {"src/unitconv/Converter.java::define_checks": '''
                    if (dimension.equals("temperature")) {
                        throw new IllegalArgumentException("temperature units cannot be defined");
                    }
                '''},
                "tests": '''
                    static void testNoCustomTemperatures() {
                        Converter c = new Converter();
                        expect(IllegalArgumentException.class, () -> c.define("R", 5.0 / 9.0, "temperature"), "Rankine");
                        expect(IllegalArgumentException.class, () -> c.convert(1, "R", "K"), "nothing defined");
                        c.define("furlong", 201.168, "length");
                    }
                '''},
            "listing": {"tests": '''
                static void testListingTemperatures() {
                    Converter c = new Converter();
                    eq(list("C", "F", "K"), c.units("temperature"), "temperature units");
                    eq("temperature", c.dimension("F"), "dimension");
                }
            '''},
        },
    ))

    S.append(Slice(
        id="ratio", title="Rates such as km/h", d=4, needs=("time",),
        pitch=("Speeds and densities come as km/h or g/min and the converter can't handle a slash.",
               "People want to convert rates like kilometres per hour to metres per second."),
        reqs=("A unit name can be a ratio `a/b` of two simple units (exactly one slash, both parts known units, no spaces). The ratio has the dimension `<dimension of a>/<dimension of b>` (`length/time` for `km/h`) and its factor is `factor(a) / factor(b)`, so `36 km/h` is `10 m/s`. Ratios work wherever a unit name is accepted by `convert`; two ratios convert into each other when their dimensions are equal as text (`km/h` and `mi/min` can, `km/h` and `kg/s` cannot, and neither can `km/h` and `m`).",
              "Units with an offset cannot be part of a ratio (an `IllegalArgumentException`). Everything else that does not make a valid ratio (`km/`, `/h`, `km/h/s`, unknown parts) is reported as an unknown unit (`IllegalArgumentException`)."),
        code={
            "src/unitconv/Converter.java::unit_fallback": '''
                if (u == null && name.indexOf('/') > 0) {
                    String[] parts = name.split("/", -1);
                    Unit num = parts.length == 2 ? units.get(parts[0]) : null;
                    Unit den = parts.length == 2 ? units.get(parts[1]) : null;
                    if (num != null && den != null) {
                        if (num.offset() != 0.0 || den.offset() != 0.0) {
                            throw new IllegalArgumentException("units with an offset cannot be used in a ratio: " + name);
                        }
                        u = new Unit(name, num.factor() / den.factor(), 0.0, num.dimension() + "/" + den.dimension());
                    }
                }
            ''',
        },
        readme="## Rates such as km/h\n\nA unit name `a/b` (two simple units) is a ratio with dimension `dim(a)/dim(b)` and factor `factor(a) / factor(b)`; ratios convert into each other when their dimensions match. Offset units are refused.\n",
        vtests='''
            static void testRatioBasic() {
                near(10.0, new Converter().convert(36, "km/h", "m/s"), "speed");
            }
        ''',
        tests='''
            static void testRatios() {
                Converter c = new Converter();
                near(10.0, c.convert(36, "km/h", "m/s"), "km/h to m/s");
                near(36.0, c.convert(10, "m/s", "km/h"), "m/s to km/h");
                near(1000.0 / 1609.344 / 60.0, c.convert(1, "km/h", "mi/min"), "km/h to mi/min");
                near(60.0, c.convert(1, "m/s", "m/min"), "per second to per minute");
                near(1000.0, c.convert(1, "m/ms", "m/s"), "per millisecond");
                near(3.0, c.convert(3, "km/h", "km/h"), "same ratio");
                near(0.001, c.convert(1, "m/km", "m/m"), "ratio of equal dimensions");
                near(1.0, c.convert(1, "ft/h", "ft/h"), "feet per hour");
            }

            static void testRatioErrors() {
                Converter c = new Converter();
                expect(IllegalArgumentException.class, () -> c.convert(1, "km/h", "m"), "ratio to plain unit");
                expect(IllegalArgumentException.class, () -> c.convert(1, "m", "km/h"), "plain unit to ratio");
                expect(IllegalArgumentException.class, () -> c.convert(1, "km/h", "m/m"), "length/time to length/length");
                for (String bad : new String[] {"km/", "/h", "km/h/s", "km/parsec", "parsec/h", "/", "km//h", "km /h", "km/ h", "m/s/"}) {
                    expect(IllegalArgumentException.class, () -> c.convert(1, bad, "m/s"), "unit '" + bad + "'");
                    expect(IllegalArgumentException.class, () -> c.convert(1, "m/s", bad), "target '" + bad + "'");
                }
                near(36.0, c.convert(36, "km/h", "km/h"), "valid after the failures");
            }
        ''',
        cross={
            "temperature": {
                "reqs": ("A ratio with `C` or `F` in it is an `IllegalArgumentException`; kelvin has no offset, so `K/s` or `m/K` are fine ratios (with the dimensions `temperature/time` and `length/temperature`).",),
                "tests": '''
                    static void testTemperatureRatios() {
                        Converter c = new Converter();
                        expect(IllegalArgumentException.class, () -> c.convert(1, "C/h", "K/h"), "C/h");
                        expect(IllegalArgumentException.class, () -> c.convert(1, "K/h", "F/h"), "F/h");
                        expect(IllegalArgumentException.class, () -> c.convert(1, "m/F", "m/K"), "m/F");
                        near(60.0, c.convert(1, "K/s", "K/min"), "kelvin per second");
                        near(1.0, c.convert(1, "m/K", "m/K"), "metres per kelvin");
                        near(1.0, c.convert(1, "m/s", "m/s"), "other ratios work");
                    }
                '''},
            "define": {"tests": '''
                static void testRatioWithDefinedUnits() {
                    Converter c = new Converter();
                    c.define("furlong", 201.168, "length");
                    near(201.168 / 3600.0, c.convert(1, "furlong/h", "m/s"), "furlongs per hour");
                    near(1.0, c.convert(201.168 / 3600.0, "m/s", "furlong/h"), "and back");
                }
            '''},
            "listing": {
                "reqs": ("`dimension(unit)` accepts ratios (`length/time` for `km/h`); ratios are not part of `units()`.",),
                "tests": '''
                    static void testListingRatios() {
                        Converter c = new Converter();
                        eq("length/time", c.dimension("km/h"), "dimension of km/h");
                        eq("length/length", c.dimension("m/km"), "dimension of m/km");
                        check(!c.units().contains("km/h"), "ratios are not listed");
                        expect(IllegalArgumentException.class, () -> c.units("length/time"), "ratio dimensions are not listed");
                    }
                '''},
            "mass": {"tests": '''
                static void testMassRatios() {
                    Converter c = new Converter();
                    near(1000.0 / 60.0, c.convert(1, "kg/min", "g/s"), "kg per minute");
                    expect(IllegalArgumentException.class, () -> c.convert(1, "kg/h", "m/s"), "mass/time to length/time");
                }
            '''},
            "parse": {"tests": fmt('''
                static void testParseRatios() {
                    Converter c = new Converter();
                    near(10.0, c.parse("36 km/h __K1__ m/s"), "parse a ratio");
                }
            ''', K1=kw1)},
        },
    ))

    return S


APP = App(
    name="unitconv", lang="java", title="the unit converter library", role="a recipe app developer", key="UNIT",
    base={
        "README.md": README + "\n@@blocks features\n",
        "src/unitconv/Converter.java": CONVERTER,
        "src/unitconv/Unit.java": UNIT,
        ".gitignore": "build/\n",
    },
    visible={"test/TestMain.java": TEST_HEAD.replace("@@blocks tests", VISIBLE_BASE + "\n    @@blocks tests")},
    hidden={"test/TestMain.java": TEST_HEAD.replace("@@blocks tests", HIDDEN_BASE + "\n    @@blocks tests")},
)

register_app("feature-java-unitconv", APP, make_slices, n=18, summary="unit converter: mass, time, listing, custom units, rounding, text requests, temperatures, rates")

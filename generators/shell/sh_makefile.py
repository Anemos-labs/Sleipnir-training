"""Shell tasks: writing Makefiles whose incremental behaviour is proven by running make against logging tools (the tests touch files and re-run)."""
from fx import dd, family
from generators.shell import _shkit as K
from generators.shell._shkit import D, F, L, Run, scn

S = K.ShellSpec
RM = "ignore"

CONVERT = dd('''
    #!/bin/sh
    # convert.sh IN OUT : write an upper-cased copy of IN to OUT (the directory of OUT must already exist); logs to build.log
    [ $# -eq 2 ] || { echo "usage: convert.sh IN OUT" >&2; exit 2; }
    [ -f "$1" ] || { echo "convert.sh: no input file $1" >&2; exit 1; }
    [ -d "$(dirname "$2")" ] || { echo "convert.sh: no directory for $2" >&2; exit 1; }
    echo "convert $1 $2" >> build.log
    tr 'a-z' 'A-Z' < "$1" > "$2"
''')
RENDER = dd('''
    #!/bin/sh
    # render.sh --mode MODE IN OUT : write "mode=MODE" and then IN to OUT; logs to build.log
    [ $# -eq 4 ] && [ "$1" = --mode ] || { echo "usage: render.sh --mode MODE IN OUT" >&2; exit 2; }
    [ -f "$3" ] || { echo "render.sh: no input file $3" >&2; exit 1; }
    [ -d "$(dirname "$4")" ] || { echo "render.sh: no directory for $4" >&2; exit 1; }
    echo "render $2 $3 $4" >> build.log
    { echo "mode=$2"; cat "$3"; } > "$4"
''')
SCAN = dd('''
    #!/bin/sh
    # scan.sh SRC OBJ DEP : write "OBJ: SRC headers..." into DEP, headers being the files named by #include "x.h" lines (found in src/)
    [ $# -eq 3 ] || { echo "usage: scan.sh SRC OBJ DEP" >&2; exit 2; }
    [ -f "$1" ] || { echo "scan.sh: no input file $1" >&2; exit 1; }
    [ -d "$(dirname "$3")" ] || { echo "scan.sh: no directory for $3" >&2; exit 1; }
    echo "scan $1" >> build.log
    hdrs=$(sed -n 's/^#include "\\(.*\\)"$/src\\/\\1/p' "$1" | tr '\\n' ' ')
    printf '%s: %s %s\\n' "$2" "$1" "$hdrs" > "$3"
''')
CC = dd('''
    #!/bin/sh
    # cc.sh SRC OBJ : "compile" SRC into OBJ (a copy); the directory of OBJ must exist; logs to build.log
    [ $# -eq 2 ] || { echo "usage: cc.sh SRC OBJ" >&2; exit 2; }
    [ -f "$1" ] || { echo "cc.sh: no input file $1" >&2; exit 1; }
    [ -d "$(dirname "$2")" ] || { echo "cc.sh: no directory for $2" >&2; exit 1; }
    echo "cc $1 $2" >> build.log
    cat "$1" > "$2"
''')
SPLIT = dd('''
    #!/bin/sh
    # split.sh IN OUTDIR : write the first two lines of IN to OUTDIR/head.txt and the rest to OUTDIR/tail.txt; logs to build.log
    [ $# -eq 2 ] || { echo "usage: split.sh IN OUTDIR" >&2; exit 2; }
    [ -f "$1" ] || { echo "split.sh: no input file $1" >&2; exit 1; }
    [ -d "$2" ] || { echo "split.sh: no directory $2" >&2; exit 1; }
    echo "split $1 $2" >> build.log
    head -n 2 "$1" > "$2/head.txt"
    tail -n +3 "$1" > "$2/tail.txt"
''')
CHECK = dd('''
    #!/bin/sh
    # check.sh FILE : succeeds unless FILE contains the word FAIL; logs to build.log
    [ $# -eq 1 ] || { echo "usage: check.sh FILE" >&2; exit 2; }
    [ -f "$1" ] || { echo "check.sh: no file $1" >&2; exit 1; }
    echo "check $1" >> build.log
    if grep -q FAIL "$1"; then echo "check.sh: $1 failed" >&2; exit 1; fi
''')
TOOLS = {"tools/convert.sh": CONVERT, "tools/render.sh": RENDER, "tools/scan.sh": SCAN, "tools/cc.sh": CC, "tools/split.sh": SPLIT, "tools/check.sh": CHECK}


def tools(*names):
    return {f"tools/{n}.sh": F(TOOLS[f"tools/{n}.sh"], x=True) for n in names}


def extra_tools(*names):
    return {f"tools/{n}.sh": TOOLS[f"tools/{n}.sh"] for n in names}


def srcs(names, ext="txt", d="src", text=None):
    return {f"{d}/{n}.{ext}": F(text(n) if text else f"text of {n}\n") for n in names}


T0, T1 = 1700001000, 1700002000  # everything built so far is rewound to T0; a "changed" source gets T1 (still in the past, so later builds are newer)


def touch(*paths):
    """ops that make the given paths newer than everything that was built: sources go back to the fixture time, build outputs are rewound to T0, then the paths get T1"""
    ops = [{"op": "touchall", "path": r, "m": 1700000000} for r in ("src", "docs", "data", "modules")]
    ops += [{"op": "touchall", "path": r, "m": T0} for r in ("build", "site")]
    return ops + [{"op": "touch", "path": p, "m": T1} for p in paths]


def mk(*args, **kw):
    kw.setdefault("stdout", RM)
    return Run(*args, **kw)


# ------------------------------------------------------------------------------------------------ 1. basic build

REF_BASIC = dd('''
    SRC := $(wildcard src/*.txt)
    OUT := $(patsubst src/%.txt,build/%.out,$(SRC))

    all: $(OUT)

    build/%.out: src/%.txt
    \tmkdir -p build
    \t./tools/convert.sh $< $@

    clean:
    \trm -rf build

    .PHONY: all clean
''')


def make_basic(rng):
    t = tools("convert")
    ex = scn("example", {**t, **srcs(["a", "b", "c"])}, mk(), mk(ops=touch("src/b.txt")), sorted_files=["build.log"])
    f = {**t, **srcs(["north", "south", "east2", "west_x", "m1"])}
    return ex, [scn("build, no-op, touch one source", f, mk(), mk(), mk(ops=touch("src/east2.txt")), mk("build/m1.out"), sorted_files=["build.log"]),
                scn("clean and rebuild", f, mk(), mk("clean"), mk(), sorted_files=["build.log"]),
                scn("single target and parallel build", f, mk("build/north.out"), mk("-j4"), sorted_files=["build.log"]),
                scn("unknown target and empty project", {**t}, mk("nothing"), mk(), sorted_files=["build.log"])]


# ------------------------------------------------------------------------------------------------ 2. phony targets and default goal

REF_PHONY = dd('''
    PAGES := $(patsubst docs/%.md,site/%.html,$(wildcard docs/*.md))

    help:
    \t@echo "targets: all clean"

    all: $(PAGES)

    site/%.html: docs/%.md
    \tmkdir -p site
    \t./tools/render.sh --mode release $< $@

    clean:
    \trm -rf site

    .PHONY: help all clean
    .DEFAULT_GOAL := all
''')


def make_phony(rng):
    t = tools("render")
    d = srcs(["intro", "usage", "faq"], "md", "docs")
    ex = scn("example", {**t, **d}, mk(), mk("clean"), sorted_files=["build.log"], dirs="all")
    trap = {**t, **d, "all": F("a file called all\n"), "clean": F("a file called clean\n"), "help": F("a file called help\n")}
    return ex, [scn("default goal is all", {**t, **srcs(["one", "two"], "md", "docs")}, mk(), sorted_files=["build.log"]),
                scn("files named like targets", trap, mk(), mk("clean"), mk("all"), sorted_files=["build.log"]),
                scn("help is not the default", {**t, **d}, mk("help"), mk(), sorted_files=["build.log"])]


# ------------------------------------------------------------------------------------------------ 3. generated header dependencies

REF_HDEPS = dd('''
    SRC := $(wildcard src/*.src)
    OBJ := $(patsubst src/%.src,build/%.o,$(SRC))
    DEP := $(OBJ:.o=.d)

    all: $(OBJ)

    build:
    \tmkdir -p build

    build/%.d: src/%.src | build
    \t./tools/scan.sh $< build/$*.o $@

    build/%.o: src/%.src | build
    \t./tools/cc.sh $< $@

    -include $(DEP)

    clean:
    \trm -rf build

    .PHONY: all clean
''')


def make_hdeps(rng):
    t = tools("scan", "cc")
    base = {"src/a.src": F('#include "common.h"\n#include "a.h"\nint a;\n'), "src/b.src": F('#include "common.h"\nint b;\n'), "src/c.src": F('int c;\n'), "src/common.h": F("// common\n"), "src/a.h": F("// a\n")}
    ex = scn("example", {**t, **base}, mk(), mk(ops=touch("src/common.h")), sorted_files=["build.log"])
    big = {**base, "src/d.src": F('#include "a.h"\n#include "d.h"\n'), "src/d.h": F("// d\n")}
    return ex, [scn("first build and no-op", {**t, **big}, mk(), mk(), sorted_files=["build.log"]),
                scn("header change rebuilds only its users", {**t, **big}, mk(), mk(ops=touch("src/common.h")), mk(ops=touch("src/d.h")), mk(), sorted_files=["build.log"]),
                scn("source change rescans and rebuilds", {**t, **big}, mk(), mk(ops=touch("src/c.src")), mk(ops=touch("src/a.h")), sorted_files=["build.log"]),
                scn("clean", {**t, **big}, mk(), mk("clean"), mk(), sorted_files=["build.log"])]


# ------------------------------------------------------------------------------------------------ 4. nested output directories

REF_NESTED = dd('''
    SRC := $(shell find src -type f -name '*.txt' | sort)
    OUT := $(patsubst src/%.txt,build/%.out,$(SRC))

    all: $(OUT)

    build/%.out: src/%.txt
    \t@mkdir -p $(@D)
    \t./tools/convert.sh $< $@

    clean:
    \trm -rf build

    .PHONY: all clean
''')


def make_nested(rng):
    t = tools("convert")
    base = {**srcs(["top"]), **srcs(["x", "y"], d="src/area1"), **srcs(["deep"], d="src/area2/inner")}
    ex = scn("example", {**t, **base}, mk(), mk(ops=touch("build")), sorted_files=["build.log"])
    return ex, [scn("mirrors the tree", {**t, **base}, mk(), mk(), sorted_files=["build.log"]),
                scn("touching directories rebuilds nothing", {**t, **base}, mk(), mk(ops=touch("build", "build/area1", "build/area2/inner")), mk(ops=touch("src/area1/y.txt")), sorted_files=["build.log"]),
                scn("clean", {**t, **base}, mk(), mk("clean"), mk("build/area2/inner/deep.out"), sorted_files=["build.log"])]


# ------------------------------------------------------------------------------------------------ 5. MODE override

REF_MODE = dd('''
    MODE ?= debug
    SRC := $(wildcard src/*.md)
    OUT := $(patsubst src/%.md,build/%.html,$(SRC))

    all: $(OUT)

    build/%.html: src/%.md
    \tmkdir -p build
    \t./tools/render.sh --mode $(MODE) $< $@

    clean:
    \trm -rf build

    .PHONY: all clean
''')


def make_mode(rng):
    t = tools("render")
    d = srcs(["a", "b"], "md")
    ex = scn("example", {**t, **d}, mk("MODE=release"), sorted_files=["build.log"])
    return ex, [scn("default is debug", {**t, **d, **srcs(["c"], "md")}, mk(), sorted_files=["build.log"]),
                scn("command line override", {**t, **d}, mk("MODE=release"), sorted_files=["build.log"]),
                scn("environment override", {**t, **d}, mk(env={"MODE": "profile"}), mk("clean"), mk("MODE=release", env={"MODE": "profile"}), sorted_files=["build.log"])]


# ------------------------------------------------------------------------------------------------ 5b. rebuild when MODE changes

REF_MODE2 = dd('''
    MODE ?= debug
    SRC := $(wildcard src/*.md)
    OUT := $(patsubst src/%.md,build/%.html,$(SRC))

    all: $(OUT)

    build/.mode: FORCE
    \t@mkdir -p build
    \t@echo '$(MODE)' | cmp -s - $@ || echo '$(MODE)' > $@

    build/%.html: src/%.md build/.mode
    \t./tools/render.sh --mode $(MODE) $< $@

    FORCE:

    clean:
    \trm -rf build

    .PHONY: all clean FORCE
''')


def make_mode2(rng):
    t = tools("render")
    d = srcs(["a", "b", "c"], "md")
    ex = scn("example", {**t, **d}, mk(), mk("MODE=release"), sorted_files=["build.log"])
    return ex, [scn("switching modes rebuilds, repeating does not", {**t, **d}, mk(), mk(), mk("MODE=release"), mk("MODE=release"), mk(), sorted_files=["build.log"]),
                scn("source change under the same mode", {**t, **d}, mk("MODE=fast"), mk("MODE=fast", ops=touch("src/b.md")), mk("MODE=fast"), sorted_files=["build.log"]),
                scn("environment mode", {**t, **d}, mk(env={"MODE": "x"}), mk(env={"MODE": "x"}), mk(env={"MODE": "y"}), sorted_files=["build.log"])]


# ------------------------------------------------------------------------------------------------ 6. grouped outputs

REF_GROUP = dd('''
    all: build/head.txt build/tail.txt

    build/head.txt build/tail.txt &: data/input.txt
    \tmkdir -p build
    \t./tools/split.sh $< build

    clean:
    \trm -rf build

    .PHONY: all clean
''')


def make_group(rng):
    t = tools("split")
    inp = {"data/input.txt": F("one\ntwo\nthree\nfour\n")}
    ex = scn("example", {**t, **inp}, mk(), mk(ops=touch("data/input.txt")), sorted_files=["build.log"])
    return ex, [scn("one run produces both files", {**t, **{"data/input.txt": F("l1\nl2\nl3\nl4\nl5\nl6\n")}}, mk(), mk(), sorted_files=["build.log"]),
                scn("either target alone", {**t, **inp}, mk("build/tail.txt"), mk("build/head.txt"), mk(ops=touch("data/input.txt")), mk("build/head.txt", "build/tail.txt"), sorted_files=["build.log"]),
                scn("a deleted output is rebuilt", {**t, **inp}, mk(), mk(ops=[{"op": "rm", "path": "build/head.txt"}]), mk(), sorted_files=["build.log"])]


# ------------------------------------------------------------------------------------------------ 7. keep intermediates

REF_KEEP = dd('''
    SRC := $(wildcard src/*.txt)
    OUT := $(patsubst src/%.txt,build/%.out,$(SRC))

    .SECONDARY:

    all: $(OUT)

    build/%.tmp: src/%.txt
    \tmkdir -p build
    \t./tools/convert.sh $< $@

    build/%.out: build/%.tmp
    \t./tools/convert.sh $< $@

    clean:
    \trm -rf build

    .PHONY: all clean
''')


def make_keep(rng):
    t = tools("convert")
    d = srcs(["alpha", "beta", "gamma"])
    ex = scn("example", {**t, **d}, mk(), mk(), sorted_files=["build.log"])
    return ex, [scn("intermediates stay", {**t, **d}, mk(), mk(), sorted_files=["build.log"]),
                scn("change rebuilds both stages", {**t, **d}, mk(), mk(ops=touch("src/beta.txt")), mk(), sorted_files=["build.log"]),
                scn("clean removes everything", {**t, **d}, mk(), mk("clean"), mk("build/gamma.out"), sorted_files=["build.log"])]


# ------------------------------------------------------------------------------------------------ 8. test target

REF_TEST = dd('''
    SRC := $(wildcard src/*.txt)
    OUT := $(patsubst src/%.txt,build/%.out,$(SRC))

    all: $(OUT)

    build/%.out: src/%.txt
    \tmkdir -p build
    \t./tools/convert.sh $< $@

    test: all
    \t@status=0; for f in $(sort $(OUT)); do ./tools/check.sh $$f || status=1; done; exit $$status

    clean:
    \trm -rf build

    .PHONY: all test clean
''')


def make_test(rng):
    t = tools("convert", "check")
    good = srcs(["a", "b", "c"])
    bad = {**srcs(["a", "c"]), "src/b.txt": F("this will fail now\n")}
    ex = scn("example", {**t, **good}, mk("test"), sorted_files=["build.log"])
    return ex, [scn("all checks pass", {**t, **good}, mk("test"), mk("test"), sorted_files=["build.log"]),
                scn("a failing check does not stop the others", {**t, **bad}, mk("test"), sorted_files=["build.log"]),
                scn("build only when needed", {**t, **good}, mk(), mk("test"), mk(ops=touch("src/c.txt")), mk("test"), sorted_files=["build.log"])]


# ------------------------------------------------------------------------------------------------ 9. install

REF_INSTALL = dd('''
    PREFIX ?= /usr/local
    DESTDIR ?=
    SRC := $(wildcard src/*.txt)
    OUT := $(patsubst src/%.txt,build/%.out,$(SRC))
    APPDIR := $(DESTDIR)$(PREFIX)/share/app

    all: $(OUT)

    build/%.out: src/%.txt
    \tmkdir -p build
    \t./tools/convert.sh $< $@

    install: all
    \tinstall -d $(APPDIR)
    \tfor f in $(OUT); do install -m 644 $$f $(APPDIR)/; done

    uninstall:
    \trm -f $(addprefix $(APPDIR)/,$(notdir $(OUT)))

    clean:
    \trm -rf build

    .PHONY: all install uninstall clean
''')


def make_install(rng):
    t = tools("convert")
    d = srcs(["one", "two"])
    ex = scn("example", {**t, **d}, mk("install", "DESTDIR=stage", "PREFIX=/opt/app"), sorted_files=["build.log"])
    return ex, [scn("install under DESTDIR and PREFIX", {**t, **srcs(["x", "y", "z"])}, mk("install", "DESTDIR=stage", "PREFIX=/opt/tool"), mk("install", "DESTDIR=stage", "PREFIX=/opt/tool"), sorted_files=["build.log"]),
                scn("default prefix", {**t, **d}, mk("install", "DESTDIR=root"), sorted_files=["build.log"]),
                scn("uninstall", {**t, **d}, mk("install", "DESTDIR=stage", "PREFIX=/p"), mk("uninstall", "DESTDIR=stage", "PREFIX=/p"), sorted_files=["build.log"], dirs="all")]


# ------------------------------------------------------------------------------------------------ 10. sub-makes

REF_SUBS = dd('''
    MODULES := $(patsubst modules/%/Makefile,%,$(wildcard modules/*/Makefile))

    all: $(MODULES)

    $(MODULES):
    \t$(MAKE) -C modules/$@

    clean:
    \t@for m in $(MODULES); do $(MAKE) -C modules/$$m clean; done

    .PHONY: all clean $(MODULES)
''')
SUBMK = dd('''
    all:
    \t@echo "built $(notdir $(CURDIR))" >> ../../build.log

    clean:
    \t@echo "cleaned $(notdir $(CURDIR))" >> ../../build.log

    .PHONY: all clean
''')


def make_subs(rng):
    def mods(*names):
        d = {f"modules/{n}/Makefile": F(SUBMK) for n in names}
        d["modules/not-a-module/readme.txt"] = F("no makefile here\n")
        return d
    ex = scn("example", mods("core", "ui"), mk(), mk("clean"), sorted_files=["build.log"])
    return ex, [scn("all modules", mods("alpha", "beta", "gamma"), mk(), mk(), sorted_files=["build.log"]),
                scn("one module", mods("alpha", "beta", "gamma"), mk("beta"), mk("clean"), sorted_files=["build.log"]),
                scn("no modules and unknown module", {"modules/x/readme": F("x")}, mk(), mk("ghost"), sorted_files=["build.log"])]


# ------------------------------------------------------------------------------------------------ 11. vpath

REF_VPATH = dd('''
    vpath %.txt src/a src/b src/c

    NAMES := $(basename $(notdir $(wildcard src/*/*.txt)))
    OUT := $(addprefix build/,$(addsuffix .out,$(NAMES)))

    all: $(OUT)

    build/%.out: %.txt
    \tmkdir -p build
    \t./tools/convert.sh $< $@

    clean:
    \trm -rf build

    .PHONY: all clean
''')


def make_vpath(rng):
    t = tools("convert")
    d = {**srcs(["one", "two"], d="src/a"), **srcs(["three"], d="src/b"), **srcs(["four", "five"], d="src/c")}
    ex = scn("example", {**t, **d}, mk(), mk(ops=touch("src/b/three.txt")), sorted_files=["build.log"])
    return ex, [scn("sources in several directories", {**t, **d}, mk(), mk(), sorted_files=["build.log"]),
                scn("touching one source", {**t, **d}, mk(), mk(ops=touch("src/c/five.txt")), mk(ops=touch("src/a/one.txt")), sorted_files=["build.log"]),
                scn("single target by name", {**t, **d}, mk("build/four.out"), mk(), sorted_files=["build.log"])]


SPECS = [
    S("basic-incremental-build", 2,
      "Write the `Makefile` for a tiny text pipeline: every `src/*.txt` is converted by `tools/convert.sh` into `build/NAME.out`. It has to rebuild only what changed. Details in the README.",
      "`make` (default goal `all`) converts every file `src/NAME.txt` into `build/NAME.out` with `./tools/convert.sh IN OUT` (the script fails if the output directory does not exist, so the Makefile must create `build/`). "
      "The set of sources is discovered, not hard-coded: any `src/*.txt` counts. A second `make` does nothing; after a source changes only its output is rebuilt; `make build/NAME.out` builds just that file; `make -j4` works. "
      "`make clean` removes the `build` directory. An unknown target is an error. `build.log` (written by the tool, not by you) shows what ran.",
      REF_BASIC, make_basic, script="Makefile", kind="make", extra=extra_tools("convert"), lang="bash", title="Incremental text build",
      wrong=("all:\n\t@true\n",)),
    S("phony-targets-and-default", 2,
      "Write a `Makefile` for the docs: `docs/*.md` are rendered into `site/*.html`. It also has `help` and `clean` targets; `all` must stay the default goal, and files that happen to be called `all` or `clean` must not break anything.",
      "Targets: `all` (default goal, even though `help` is listed first in the file) renders each `docs/NAME.md` to `site/NAME.html` with `./tools/render.sh --mode release IN OUT` (create `site/` yourself); `help` prints a line `targets: all clean`; "
      "`clean` removes `site/`. `all`, `help` and `clean` are not files: a file or directory with such a name in the project directory must not stop them from running. Sources are discovered, not hard-coded. "
      "Use only GNU make features available in make 4.3.",
      REF_PHONY, make_phony, script="Makefile", kind="make", extra=extra_tools("render"), lang="bash", title="Docs makefile with phony targets",
      wrong=("help:\n\t@echo help\nall: site/x.html\nsite/x.html:\n\ttouch $@\nclean:\n\trm -rf site\n",)),
    S("generated-header-dependencies", 4,
      "Write a `Makefile` that compiles `src/*.src` into `build/*.o` and rebuilds an object when one of the headers it includes changes. The header list must be generated with `tools/scan.sh`, not typed in.",
      "For each `src/NAME.src` build `build/NAME.o` with `./tools/cc.sh SRC OBJ`. The headers a source includes (`#include \"x.h\"` lines, living in `src/`) must be tracked automatically: generate `build/NAME.d` with "
      "`./tools/scan.sh SRC build/NAME.o build/NAME.d` (it writes a ready-made make rule `build/NAME.o: src/NAME.src src/x.h ...`) and `include` those files so that touching a header rebuilds exactly the objects that include it, "
      "while an unchanged source is not scanned again. Both tools need `build/` to exist, and the directory's own timestamp must not trigger rebuilds. `make clean` removes `build/`. Default goal `all`.",
      REF_HDEPS, make_hdeps, script="Makefile", kind="make", extra=extra_tools("scan", "cc"), lang="bash", title="Automatic header dependencies",
      wrong=("SRC := $(wildcard src/*.src)\nOBJ := $(patsubst src/%.src,build/%.o,$(SRC))\nall: $(OBJ)\nbuild/%.o: src/%.src\n\tmkdir -p build\n\t./tools/cc.sh $< $@\nclean:\n\trm -rf build\n.PHONY: all clean\n",)),
    S("mirror-tree-output-dirs", 3,
      "Write a `Makefile` that converts every `.txt` under `src/` (any depth) into the same relative path under `build/` with a `.out` extension. Creating output directories must not cause needless rebuilds.",
      "`make` converts each `src/PATH/NAME.txt` (found at any depth) into `build/PATH/NAME.out` with `./tools/convert.sh IN OUT` (the tool needs the output directory to exist). A second `make` must do nothing, even if "
      "the timestamp of a build directory changes (touching `build/` or `build/sub/` must not rebuild anything). Changing one source rebuilds only that output. `make clean` removes `build/`. Default goal `all`.",
      REF_NESTED, make_nested, script="Makefile", kind="make", extra=extra_tools("convert"), lang="bash", title="Mirror a source tree",
      wrong=("SRC := $(shell find src -type f -name '*.txt')\nOUT := $(patsubst src/%.txt,build/%.out,$(SRC))\nall: $(OUT)\nbuild/%.out: src/%.txt build\n\t./tools/convert.sh $< $@\nbuild:\n\tmkdir -p build\n",)),
    S("mode-variable-override", 2,
      "Write a `Makefile` for a page renderer that takes a `MODE` variable (default `debug`) from the command line or from the environment and passes it to the tool.",
      "`make` renders each `src/NAME.md` into `build/NAME.html` with `./tools/render.sh --mode $(MODE) IN OUT` (create `build/` yourself). `MODE` defaults to `debug`; it can be overridden on the command line (`make MODE=release`) "
      "and also through the environment (`MODE=profile make`): the environment value must win over the default, and the command line must win over both. Sources are discovered. `make clean` removes `build/`. Default goal `all`.",
      REF_MODE, make_mode, script="Makefile", kind="make", extra=extra_tools("render"), lang="bash", title="MODE override",
      wrong=("MODE = debug\nSRC := $(wildcard src/*.md)\nOUT := $(patsubst src/%.md,build/%.html,$(SRC))\nall: $(OUT)\nbuild/%.html: src/%.md\n\tmkdir -p build\n\t./tools/render.sh --mode $(MODE) $< $@\n",)),
    S("rebuild-when-mode-changes", 4,
      "Extend the page renderer's `Makefile`: besides sources, a change of `MODE` (from the previous build) must trigger a rebuild, while repeating the same `MODE` must not.",
      "`make [MODE=x]` builds `build/NAME.html` from `src/NAME.md` with `./tools/render.sh --mode $(MODE) IN OUT` (default mode `debug`, overridable on the command line and through the environment). "
      "The outputs must be rebuilt when a source changes **or when the mode differs from the one used for the previous build**, and must not be rebuilt when nothing changed (same sources, same mode). "
      "Remember the mode in a file inside `build/` without touching it when the mode is unchanged. `make clean` removes `build/`. Default goal `all`.",
      REF_MODE2, make_mode2, script="Makefile", kind="make", extra=extra_tools("render"), lang="bash", title="Rebuild when the mode changes",
      wrong=(REF_MODE,)),
    S("grouped-outputs-run-once", 4,
      "`tools/split.sh` writes two files from one input in a single run. Write a `Makefile` that runs it exactly once per change, however the two outputs are requested.",
      "`data/input.txt` is split by `./tools/split.sh data/input.txt build` into `build/head.txt` and `build/tail.txt` (the tool needs `build/` to exist). The tool must run **once** when both outputs are missing or out of date, "
      "whether you ask for `all`, for one of the files, or for both; it must not run again when nothing changed; a deleted output is rebuilt. `make clean` removes `build/`. Default goal `all`. (GNU make 4.3 is used.)",
      REF_GROUP, make_group, script="Makefile", kind="make", extra=extra_tools("split"), lang="bash", title="One run, two outputs",
      wrong=("all: build/head.txt build/tail.txt\nbuild/head.txt build/tail.txt: data/input.txt\n\tmkdir -p build\n\t./tools/split.sh $< build\n",)),
    S("keep-intermediate-files", 3,
      "A two-stage pipeline (`src/X.txt` to `build/X.tmp` to `build/X.out`) writes its `.tmp` files and make deletes them afterwards. Write the `Makefile` so they are kept and nothing runs twice.",
      "`make` builds `build/NAME.tmp` from `src/NAME.txt` and `build/NAME.out` from `build/NAME.tmp`, both with `./tools/convert.sh IN OUT` (create `build/` yourself). The `.tmp` files are intermediate products that must **remain** on disk after the build. "
      "A second `make` does nothing; touching a source rebuilds both stages of that file only. `make clean` removes `build/`. Sources are discovered. Default goal `all`.",
      REF_KEEP, make_keep, script="Makefile", kind="make", extra=extra_tools("convert"), lang="bash", title="Keep intermediate files",
      wrong=("SRC := $(wildcard src/*.txt)\nOUT := $(patsubst src/%.txt,build/%.out,$(SRC))\nall: $(OUT)\nbuild/%.tmp: src/%.txt\n\tmkdir -p build\n\t./tools/convert.sh $< $@\nbuild/%.out: build/%.tmp\n\t./tools/convert.sh $< $@\n",)),
    S("test-target-keeps-going", 3,
      "Add a `test` target to the text pipeline's `Makefile`: it builds what is needed and then runs `tools/check.sh` on every output, continuing after a failure but failing overall.",
      "`make` and `make clean` behave as before (`src/NAME.txt` -> `build/NAME.out` through `./tools/convert.sh`, sources discovered, `build/` created by you). `make test` first builds whatever is missing or out of date, then runs `./tools/check.sh build/NAME.out` "
      "for **every** output in byte-wise order of the names, even after one check failed, and finally make must fail (non-zero) if any check failed and succeed if none did. Nothing is rebuilt needlessly.",
      REF_TEST, make_test, script="Makefile", kind="make", extra=extra_tools("convert", "check"), lang="bash", title="A test target that keeps going",
      wrong=("SRC := $(wildcard src/*.txt)\nOUT := $(patsubst src/%.txt,build/%.out,$(SRC))\nall: $(OUT)\nbuild/%.out: src/%.txt\n\tmkdir -p build\n\t./tools/convert.sh $< $@\ntest: all\n\tfor f in $(OUT); do ./tools/check.sh $$f; done\n",)),
    S("install-with-destdir", 3,
      "Add `install` and `uninstall` targets that honour `PREFIX` and `DESTDIR`, the way packagers expect.",
      "Besides the build (`src/NAME.txt` -> `build/NAME.out` via `./tools/convert.sh`), `make install` copies every built output into `$(DESTDIR)$(PREFIX)/share/app/` (creating the directory; building first if needed) with mode 644, and `make uninstall` removes exactly those copies. "
      "`PREFIX` defaults to `/usr/local` and can be overridden on the command line; `DESTDIR` defaults to empty and is a staging root prepended to every installed path. Sources are discovered. Default goal `all`; `make clean` removes `build/`.",
      REF_INSTALL, make_install, script="Makefile", kind="make", extra=extra_tools("convert"), lang="bash", title="Install with DESTDIR",
      wrong=("SRC := $(wildcard src/*.txt)\nOUT := $(patsubst src/%.txt,build/%.out,$(SRC))\nall: $(OUT)\nbuild/%.out: src/%.txt\n\tmkdir -p build\n\t./tools/convert.sh $< $@\ninstall: all\n\tinstall -d $(PREFIX)/share/app\n\tcp $(OUT) $(PREFIX)/share/app/\n",)),
    S("recursive-modules", 4,
      "The repository has `modules/*/Makefile`. Write the top-level `Makefile` that builds every module (and each one by name) and cleans them all, discovering the modules itself.",
      "Every directory `modules/NAME/` that contains a `Makefile` is a module with the targets `all` and `clean`. The top-level `make` (default goal `all`) builds every module by running make inside it (`$(MAKE) -C modules/NAME`); `make NAME` builds only that module; "
      "`make clean` runs `clean` in every module. Modules are discovered with a wildcard, directories without a Makefile are ignored, and an unknown module name is an error. Module builds must always run (they are not files).",
      REF_SUBS, make_subs, script="Makefile", kind="make", lang="bash", title="Top-level makefile for modules",
      wrong=("all:\n\t$(MAKE) -C modules/alpha\n",)),
    S("sources-in-several-directories", 3,
      "Write a `Makefile` for sources spread over `src/a`, `src/b` and `src/c`, producing a flat `build/NAME.out` per source, using `vpath` rather than copying files around.",
      "Each `src/DIR/NAME.txt` (DIR is one of `a`, `b`, `c`; names are unique across the directories) becomes `build/NAME.out` through `./tools/convert.sh IN OUT` with `IN` the real path of the source (create `build/` yourself). "
      "The sources are found with `vpath` (the pattern rule is `build/%.out: %.txt`) and the list of outputs comes from a wildcard over `src/*/*.txt`. Nothing is rebuilt when nothing changed; touching one source rebuilds only its output. `make clean` removes `build/`. Default goal `all`.",
      REF_VPATH, make_vpath, script="Makefile", kind="make", extra=extra_tools("convert"), lang="bash", title="vpath over several source directories",
      wrong=("all:\n\tmkdir -p build\n\tfor f in src/*/*.txt; do ./tools/convert.sh $$f build/$$(basename $$f .txt).out; done\n",)),
]


@family("shell-makefile-authoring", category="shell", lang="bash", kind="feature", n=len(SPECS),
        summary="write Makefiles whose incremental behaviour is proven by touching files and re-running make against logging tools")
def makefile_authoring(rng, n):
    return K.shell_tasks("makefile-authoring", SPECS, rng, n)

"""Shell tasks: repairing broken Makefiles (missing separator, phony targets, dependencies, automatic variables, one-shell recipes, ignored errors, always-rebuild bugs)."""
from fx import dd, family
from generators.shell import _shkit as K
from generators.shell._shkit import D, F, L, Run, scn
from generators.shell.sh_makefile import T0, T1, extra_tools, mk, srcs, tools, touch

S = K.ShellSpec

PACK = dd('''
    #!/bin/sh
    # pack.sh NAME : run it INSIDE the directory that holds manifest.txt; writes NAME.pack there; logs to ./build.log
    [ $# -eq 1 ] || { echo "usage: pack.sh NAME" >&2; exit 2; }
    [ -f manifest.txt ] || { echo "pack.sh: no manifest.txt in the current directory" >&2; exit 1; }
    echo "pack $1" >> build.log
    { echo "packed:"; cat manifest.txt; } > "$1.pack"
''')


# ------------------------------------------------------------------------------------------------ 1. spaces instead of tabs

BUG_SPACES = dd('''
    SRC := $(wildcard src/*.txt)
    OUT := $(patsubst src/%.txt,build/%.out,$(SRC))

    all: $(OUT)

    build/%.out: src/%.txt
        mkdir -p build
        ./tools/convert.sh $< $@

    clean:
        rm -rf build

    .PHONY: all clean
''')
REF_SPACES = BUG_SPACES.replace("\n    ", "\n\t")


def make_spaces(rng):
    t = tools("convert")
    ex = scn("example", {**t, **srcs(["a", "b"])}, mk(), mk("clean"), sorted_files=["build.log"])
    f = {**t, **srcs(["one", "two", "three"])}
    return ex, [scn("build and clean", f, mk(), mk(), mk("clean"), sorted_files=["build.log"]), scn("one target", f, mk("build/two.out"), sorted_files=["build.log"])]


# ------------------------------------------------------------------------------------------------ 2. missing .PHONY

BUG_PHONY = dd('''
    SRC := $(wildcard src/*.md)
    OUT := $(patsubst src/%.md,build/%.html,$(SRC))

    all: $(OUT)

    build/%.html: src/%.md
    \tmkdir -p build
    \t./tools/render.sh --mode release $< $@

    test: all
    \t./tools/check.sh build/index.html

    clean:
    \trm -rf build
''')
REF_PHONY = BUG_PHONY + "\n.PHONY: all test clean\n"


def make_phony(rng):
    t = tools("render", "check")
    d = srcs(["index", "about"], "md")
    ex = scn("example", {**t, **d, "clean": F("stale\n")}, mk("clean"), mk(), mk("test"), sorted_files=["build.log"], dirs="all")
    return ex, [scn("files named like targets", {**t, **d, "clean": F("x\n"), "test": F("y\n"), "all": F("z\n")}, mk(), mk("test"), mk("clean"), mk("test"), sorted_files=["build.log"]),
                scn("a test directory", {**t, **d, "test/readme": F("tests live here\n")}, mk("test"), sorted_files=["build.log"])]


# ------------------------------------------------------------------------------------------------ 3. missing prerequisite

BUG_CFG = dd('''
    MODE := $(shell cat site.cfg)
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
REF_CFG = BUG_CFG.replace("build/%.html: src/%.md", "build/%.html: src/%.md site.cfg")


def make_cfg(rng):
    t = tools("render")
    d = {**srcs(["a", "b", "c"], "md"), "site.cfg": F("draft\n")}
    ex = scn("example", {**t, **d}, mk(), mk(ops=touch("src/b.md")), sorted_files=["build.log"])
    cfg2 = [{"op": "write", "path": "site.cfg", "c": "final\n", "m": T1}]
    return ex, [scn("config change rebuilds everything", {**t, **d}, mk(), mk(), mk(ops=touch() + cfg2), mk(), sorted_files=["build.log"]),
                scn("source change rebuilds one", {**t, **d}, mk(), mk(ops=touch("src/c.md")), mk(), sorted_files=["build.log"])]


# ------------------------------------------------------------------------------------------------ 4. automatic variables

BUG_AUTO = dd('''
    SRC := $(wildcard src/*.txt)
    OUT := $(patsubst src/%.txt,build/%.out,$(SRC))

    all: $(OUT)

    build/%.out: src/%.txt tools/convert.sh
    \tmkdir -p build
    \t./tools/convert.sh $^ $@

    clean:
    \trm -rf build

    .PHONY: all clean
''')
REF_AUTO = BUG_AUTO.replace("./tools/convert.sh $^ $@", "./tools/convert.sh $< $@")


def make_auto(rng):
    t = tools("convert")
    d = srcs(["x", "y", "z"])
    ex = scn("example", {**t, **d}, mk(), mk(ops=touch("tools/convert.sh")), sorted_files=["build.log"])
    return ex, [scn("build", {**t, **d}, mk(), mk(), sorted_files=["build.log"]), scn("the tool itself is a prerequisite", {**t, **d}, mk(), mk(ops=touch("tools/convert.sh")), mk(), sorted_files=["build.log"])]


# ------------------------------------------------------------------------------------------------ 5. each recipe line is its own shell

BUG_CD = dd('''
    all: stage/bundle.pack

    stage/bundle.pack: stage/manifest.txt
    \tcd stage
    \t../tools/pack.sh bundle

    clean:
    \trm -f stage/bundle.pack

    .PHONY: all clean
''')
REF_CD = BUG_CD.replace("\tcd stage\n\t../tools/pack.sh bundle", "\tcd stage && ../tools/pack.sh bundle")


def make_cd(rng):
    t = {"tools/pack.sh": F(PACK, x=True)}
    ex = scn("example", {**t, "stage/manifest.txt": F("a.txt\nb.txt\n")}, mk(), mk(), sorted_files=["stage/build.log"])
    return ex, [scn("packs inside stage", {**t, "stage/manifest.txt": F("one\ntwo\nthree\n")}, mk(), mk(), mk(ops=[{"op": "write", "path": "stage/manifest.txt", "c": "one\nfour\n", "m": T1}, {"op": "touchall", "path": "stage/bundle.pack", "m": T0}]), sorted_files=["stage/build.log"]),
                scn("clean", {**t, "stage/manifest.txt": F("m\n")}, mk(), mk("clean"), mk(), sorted_files=["stage/build.log"])]


# ------------------------------------------------------------------------------------------------ 6. ignored errors

BUG_ERR = dd('''
    SRC := $(wildcard src/*.txt)
    OUT := $(patsubst src/%.txt,build/%.out,$(SRC))

    all: $(OUT)

    build/%.out: src/%.txt
    \tmkdir -p build
    \t./tools/convert.sh $< $@
    \t-./tools/check.sh $@

    clean:
    \trm -rf build

    .PHONY: all clean
''')
REF_ERR = dd('''
    SRC := $(wildcard src/*.txt)
    OUT := $(patsubst src/%.txt,build/%.out,$(SRC))

    .DELETE_ON_ERROR:

    all: $(OUT)

    build/%.out: src/%.txt
    \tmkdir -p build
    \t./tools/convert.sh $< $@
    \t./tools/check.sh $@

    clean:
    \trm -rf build

    .PHONY: all clean
''')


def make_err(rng):
    t = tools("convert", "check")
    good = srcs(["a", "b"])
    bad = {**good, "src/c.txt": F("this will fail the check\n")}
    ex = scn("example", {**t, **bad}, mk(), mk(), sorted_files=["build.log"])
    return ex, [scn("all good", {**t, **good}, mk(), mk(), sorted_files=["build.log"]),
                scn("a failing check fails the build and leaves no output", {**t, **bad}, mk(), mk(), sorted_files=["build.log"]),
                scn("keep going with -k", {**t, **{**bad, "src/d.txt": F("fine\n")}}, mk("-k"), sorted_files=["build.log"])]


# ------------------------------------------------------------------------------------------------ 7. always rebuilds

BUG_ALWAYS = dd('''
    SRC := $(wildcard src/*.txt)
    OUT := $(patsubst src/%.txt,build/%.out,$(SRC))

    all: $(OUT)

    build:
    \tmkdir -p build

    build/%.out: src/%.txt build
    \t./tools/convert.sh $< $@

    clean:
    \trm -rf build

    .PHONY: all clean
''')
REF_ALWAYS = BUG_ALWAYS.replace("build/%.out: src/%.txt build", "build/%.out: src/%.txt | build")


def make_always(rng):
    t = tools("convert")
    d = srcs(["a", "b", "c", "d"])
    ex = scn("example", {**t, **d}, mk(), mk(), sorted_files=["build.log"])
    return ex, [scn("second make is a no-op", {**t, **d}, mk(), mk(), mk(), sorted_files=["build.log"]), scn("touch one source", {**t, **d}, mk(), mk(ops=touch("src/c.txt")), mk(), sorted_files=["build.log"]),
                scn("touching build directory is harmless", {**t, **d}, mk(), mk(ops=touch("build")), sorted_files=["build.log"])]


# ------------------------------------------------------------------------------------------------ 8. hard-coded file list

BUG_LIST = dd('''
    OUT := build/alpha.out build/beta.out build/gamma.out

    all: $(OUT)

    build/%.out: src/%.txt
    \tmkdir -p build
    \t./tools/convert.sh $< $@

    clean:
    \trm -rf build

    .PHONY: all clean
''')
REF_LIST = dd('''
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


def make_list(rng):
    t = tools("convert")
    ex = scn("example", {**t, **srcs(["alpha", "beta", "delta"])}, mk(), sorted_files=["build.log"])
    return ex, [scn("other names", {**t, **srcs(["kilo", "lima", "mike", "november"])}, mk(), mk(), sorted_files=["build.log"]),
                scn("fewer sources than the old list", {**t, **srcs(["alpha"])}, mk(), sorted_files=["build.log"]),
                scn("no sources", {**t}, mk(), sorted_files=["build.log"])]


# ------------------------------------------------------------------------------------------------ 9. shell variables in recipes

BUG_SHVAR = dd('''
    SRC := $(wildcard src/*.txt)
    OUT := $(patsubst src/%.txt,build/%.out,$(SRC))

    all: $(OUT)

    build/%.out: src/%.txt
    \tmkdir -p build
    \t./tools/convert.sh $< $@

    verify: all
    \t@for f in $(OUT); do ./tools/check.sh $f || failed=1; done; echo "checked $(words $(OUT)) files in $(shell basename $PWD)"; exit $failed

    clean:
    \trm -rf build

    .PHONY: all verify clean
''')
REF_SHVAR = BUG_SHVAR.replace('@for f in $(OUT); do ./tools/check.sh $f || failed=1; done; echo "checked $(words $(OUT)) files in $(shell basename $PWD)"; exit $failed',
                              '@failed=0; for f in $(OUT); do ./tools/check.sh $$f || failed=1; done; echo "checked $(words $(OUT)) files in $$(basename "$$PWD")"; exit $$failed')


def make_shvar(rng):
    t = tools("convert", "check")
    d = srcs(["a", "b", "c"])
    ex = scn("example", {**t, **d}, mk("verify"), sorted_files=["build.log"])
    return ex, [scn("checks every output", {**t, **d}, mk("verify"), sorted_files=["build.log"]), scn("a failing file", {**t, **d, "src/b.txt": F("FAIL me\n")}, mk("verify"), sorted_files=["build.log"])]


# ------------------------------------------------------------------------------------------------ 10. optional include

BUG_INC = dd('''
    include local.mk

    PAGES ?= intro
    OUT := $(patsubst %,build/%.html,$(PAGES))

    all: $(OUT)

    build/%.html: src/%.md
    \tmkdir -p build
    \t./tools/render.sh --mode release $< $@

    clean:
    \trm -rf build

    .PHONY: all clean
''')
REF_INC = BUG_INC.replace("include local.mk", "-include local.mk")


def make_inc(rng):
    t = tools("render")
    d = srcs(["intro", "extra", "more"], "md")
    ex = scn("example", {**t, **d}, mk(), sorted_files=["build.log"])
    return ex, [scn("no local.mk", {**t, **d}, mk(), mk(), sorted_files=["build.log"]),
                scn("local.mk overrides", {**t, **d, "local.mk": F("PAGES = extra more\n")}, mk(), sorted_files=["build.log"]),
                scn("command line wins over local.mk", {**t, **d, "local.mk": F("PAGES = extra more\n")}, mk("PAGES=intro"), sorted_files=["build.log"])]


SPECS = [
    S("fix-missing-separator", 1,
      "`make` dies with 'missing separator' on this Makefile (someone's editor turned the tabs into spaces). Repair it.",
      "The Makefile builds `build/NAME.out` from every `src/NAME.txt` through `./tools/convert.sh IN OUT` (default goal `all`, `make clean` removes `build/`). It currently fails to parse; fix it without changing what it does.",
      REF_SPACES, make_spaces, script="Makefile", kind="make", buggy=BUG_SPACES, extra=extra_tools("convert"), lang="bash", title="Makefile that does not parse", wrong=(BUG_SPACES,)),
    S("fix-missing-phony", 1,
      "`make test` says `make: 'test' is up to date.` because there is a `test/` directory, and `make clean` stops working when a file called `clean` exists. Fix the Makefile.",
      "Targets: `all` (default; renders each `src/NAME.md` to `build/NAME.html` with `./tools/render.sh --mode release IN OUT`), `test` (builds, then runs `./tools/check.sh build/index.html`), `clean` (removes `build/`). "
      "`all`, `test` and `clean` are commands, not files: they must run even if files or directories with those names exist. Nothing else may change.",
      REF_PHONY, make_phony, script="Makefile", kind="make", buggy=BUG_PHONY, extra=extra_tools("render", "check"), lang="bash", title="Phony targets", wrong=(BUG_PHONY,)),
    S("fix-config-prerequisite", 2,
      "The site Makefile reads the render mode from `site.cfg`, but changing `site.cfg` doesn't rebuild the pages. Fix the dependencies (and keep passing only the source file to the tool).",
      "`make` renders each `src/NAME.md` into `build/NAME.html` with `./tools/render.sh --mode <contents of site.cfg> IN OUT`. Pages must be rebuilt when their source **or** `site.cfg` changes, and only then; the tool must receive exactly the source file as `IN`. "
      "Default goal `all`, `make clean` removes `build/`.",
      REF_CFG, make_cfg, script="Makefile", kind="make", buggy=BUG_CFG, extra=extra_tools("render"), lang="bash", title="Config file as a prerequisite", wrong=(BUG_CFG,)),
    S("fix-automatic-variable", 2,
      "The Makefile lists the converter script as a prerequisite (so a changed tool triggers rebuilds) but now the tool is called with the wrong arguments. Fix the recipe.",
      "Each `build/NAME.out` depends on `src/NAME.txt` **and** on `tools/convert.sh`; the recipe must call `./tools/convert.sh src/NAME.txt build/NAME.out`. Touching the tool rebuilds every output, touching a source rebuilds only its output. "
      "Default goal `all`, `make clean` removes `build/`.",
      REF_AUTO, make_auto, script="Makefile", kind="make", buggy=BUG_AUTO, extra=extra_tools("convert"), lang="bash", title="Automatic variables", wrong=(BUG_AUTO,)),
    S("fix-recipe-lines-are-separate-shells", 2,
      "`make` fails with 'no manifest.txt in the current directory': the `cd stage` in the recipe doesn't affect the next line. Repair the rule.",
      "`stage/bundle.pack` is built from `stage/manifest.txt` by running `../tools/pack.sh bundle` **inside** `stage/` (the tool wants `manifest.txt` in its working directory and writes `bundle.pack` and its `build.log` there). "
      "It is rebuilt only when the manifest changes. `make clean` removes `stage/bundle.pack`. Default goal `all`.",
      REF_CD, make_cd, script="Makefile", kind="make", buggy=BUG_CD, extra={"tools/pack.sh": PACK}, lang="bash", title="cd in a recipe", wrong=(BUG_CD,)),
    S("fix-ignored-failures", 3,
      "A failing `check.sh` goes unnoticed: make reports success and leaves the bad output behind. Make failures stop the build, and make sure a failed output is not left lying around.",
      "`make` builds `build/NAME.out` with `./tools/convert.sh src/NAME.txt build/NAME.out` and then verifies it with `./tools/check.sh build/NAME.out`. If the check fails, make must fail (non-zero exit) and the bad output file must **not** remain, so that the next `make` tries again; "
      "outputs that passed stay and are not rebuilt. `make -k` builds everything it can. Default goal `all`, `make clean` removes `build/`.",
      REF_ERR, make_err, script="Makefile", kind="make", buggy=BUG_ERR, extra=extra_tools("convert", "check"), lang="bash", title="Failures must fail", wrong=(BUG_ERR,)),
    S("fix-always-rebuilds", 3,
      "Every `make` rebuilds everything, even right after a build. I suspect the `build` directory prerequisite. Fix the Makefile.",
      "`make` builds `build/NAME.out` from `src/NAME.txt` with `./tools/convert.sh IN OUT` (the tool requires `build/` to exist). Running `make` again right away must do nothing, touching one source must rebuild only its output, "
      "and touching the `build` directory itself must rebuild nothing. Default goal `all`, `make clean` removes `build/`.",
      REF_ALWAYS, make_always, script="Makefile", kind="make", buggy=BUG_ALWAYS, extra=extra_tools("convert"), lang="bash", title="Needless rebuilds", wrong=(BUG_ALWAYS,)),
    S("fix-hardcoded-outputs", 1,
      "The Makefile only knows the three files `alpha`, `beta`, `gamma`; other sources in `src/` are ignored and missing ones break the build. Make it discover the sources.",
      "`make` builds `build/NAME.out` from every `src/NAME.txt` that exists (`./tools/convert.sh IN OUT`, create `build/` yourself); no source names are written in the Makefile. Default goal `all`, `make clean` removes `build/`. "
      "With no sources `make` succeeds and builds nothing.",
      REF_LIST, make_list, script="Makefile", kind="make", buggy=BUG_LIST, extra=extra_tools("convert"), lang="bash", title="Hard-coded file list", wrong=(BUG_LIST,)),
    S("fix-shell-variables-in-recipes", 2,
      "`make verify` runs `check.sh` with an empty argument and prints a blank directory name: `$f` and `$PWD` in the recipe are being expanded by make, not the shell. Fix them.",
      "`make verify` builds everything (`build/NAME.out` from `src/NAME.txt` via `./tools/convert.sh`) and then runs `./tools/check.sh` on each output in the list order, continuing after a failure, prints `checked N files in DIR` and finally exits non-zero if any check failed (zero otherwise) where `DIR` is the **base name** of the current directory "
      "(taken from the shell's `$PWD`). The target is a command, not a file. The default goal `all` and `clean` keep working.",
      REF_SHVAR, make_shvar, script="Makefile", kind="make", buggy=BUG_SHVAR, extra=extra_tools("convert", "check"), lang="bash", title="Shell variables in recipes", wrong=(BUG_SHVAR,)),
    S("fix-required-include", 2,
      "A fresh checkout has no `local.mk` and `make` aborts with 'No such file or directory'. `local.mk` is an optional place to override `PAGES`. Fix it.",
      "`local.mk` is optional: if it exists its settings are used, otherwise defaults apply (`PAGES ?= intro`). `make` renders `src/PAGE.md` to `build/PAGE.html` for every page in `PAGES` with `./tools/render.sh --mode release IN OUT`; "
      "`PAGES` given on the command line wins over everything. Default goal `all`, `make clean` removes `build/`.",
      REF_INC, make_inc, script="Makefile", kind="make", buggy=BUG_INC, extra=extra_tools("render"), lang="bash", title="Optional include", wrong=(BUG_INC,)),
]


@family("shell-makefile-repair", category="shell", lang="bash", kind="fix", n=len(SPECS),
        summary="repair broken Makefiles: tabs, phony targets, missing prerequisites, automatic variables, one-shell recipes, ignored errors, always-rebuild")
def makefile_repair(rng, n):
    return K.shell_tasks("makefile-repair", SPECS, rng, n)

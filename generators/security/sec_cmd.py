"""Security family: command injection (shell=True, os.system/popen, argument injection). Commands used are harmless (echo, ls)."""
from fx import dd, family

from . import _sec

P = _sec.PY_PRELUDE + "import subprocess\n\n\n"


def readme(title, body):
    return f"# {title}\n\n{body.strip()}\n"


SC = []

SC.append(dict(
    slug="notify-echo", d=1, product="the alert relay", func="send_alert", cwe="CWE-78",
    finding="`send_alert` builds a shell command line by pasting the message in (`shell=True`), so a message like `x; echo INJECTED` or `$(echo INJECTED)` runs extra commands, and messages with quotes or `$` signs are mangled.",
    start={
        "relay.py": dd('''
            """Alert relay: hands alerts to the local notifier command (stand-in: `echo`)."""
            import subprocess


            def send_alert(message):
                """Run the notifier for `message` and return what it printed. The notifier prints `alert: <message>` and a line feed; the message must arrive verbatim (spaces, quotes, `$`, `*` and so on are ordinary characters)."""
                out = subprocess.run("echo alert: " + message, shell=True, capture_output=True, text=True)
                return out.stdout
        '''),
        "README.md": readme("relay", "`send_alert(message)` returns exactly `alert: <message>\\n` - the notifier (here `echo`) receives the message as one argument, unchanged. Characters such as `;`, `&`, `|`, `$`, backticks, quotes, `*` and newlines have no special meaning."),
    },
    solution={"relay.py": dd('''
        """Alert relay: hands alerts to the local notifier command (stand-in: `echo`)."""
        import subprocess


        def send_alert(message):
            """Run the notifier for `message` and return what it printed. The notifier prints `alert: <message>` and a line feed; the message must arrive verbatim (spaces, quotes, `$`, `*` and so on are ordinary characters)."""
            out = subprocess.run(["echo", "alert:", message], capture_output=True, text=True)
            return out.stdout
    ''')},
    hidden={"tests/test_relay_security.py": P + dd('''
        import relay as m

        MESSAGES = ["disk full", "it's \\"quoted\\"", "$HOME and ${PATH}", "wildcards * ? [a-z]", "tilde ~ and #hash", "a;b", "tab\\there", "ünïcode ✓", "", "back\\\\slash"]
        EVIL = ["x; echo INJECTED", "x && echo INJECTED", "x | echo INJECTED", "$(echo INJECTED)", "`echo INJECTED`", "x\\necho INJECTED", "x & echo INJECTED", "x || echo INJECTED", "'; echo INJECTED; '", "\\"; echo INJECTED; \\""]


        class RelayTest(unittest.TestCase):
            def test_verbatim(self):
                for msg in MESSAGES + EVIL:
                    expected = "alert: " + msg + "\\n"
                    self.assertEqual(m.send_alert(msg), expected, repr(msg))


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

SC.append(dict(
    slug="archive-label", d=2, product="the backup scheduler", func="archive_command", cwe="CWE-78",
    finding="`archive_command` interpolates the archive name and format into a shell command (`shell=True`); a name containing `;`, `$(...)` or a newline runs extra commands, and the format is not validated at all.",
    start={
        "archiver.py": dd('''
            """Prepares archive jobs for the backup scheduler (the real archiver is replaced by `echo` here)."""
            import subprocess


            def archive_command(name, fmt="tgz"):
                """Run the archive job for `name` in format `fmt` and return its output, which is the line `tar -czf <name>.<fmt>` (for fmt tgz) or `zip <name>.<fmt>` (for fmt zip)."""
                tool = "tar -czf" if fmt == "tgz" else "zip"
                return subprocess.check_output("echo %s %s.%s" % (tool, name, fmt), shell=True, text=True)
        '''),
        "README.md": readme("archiver", "`archive_command(name, fmt)` runs the (stand-in) archiver and returns its output line `tar -czf <name>.tgz\\n` for `tgz` or `zip <name>.zip\\n` for `zip`. Only `tgz` and `zip` are valid formats (anything else is a `ValueError`). The name is an ordinary file name and must reach the archiver unchanged - spaces, quotes, `$`, `;` and the like have no special meaning."),
    },
    solution={"archiver.py": dd('''
        """Prepares archive jobs for the backup scheduler (the real archiver is replaced by `echo` here)."""
        import subprocess

        FORMATS = {"tgz": ["tar", "-czf"], "zip": ["zip"]}


        def archive_command(name, fmt="tgz"):
            """Run the archive job for `name` in format `fmt` and return its output, which is the line `tar -czf <name>.<fmt>` (for fmt tgz) or `zip <name>.<fmt>` (for fmt zip)."""
            if fmt not in FORMATS:
                raise ValueError("unknown format")
            return subprocess.check_output(["echo", *FORMATS[fmt], name + "." + fmt], text=True)
    ''')},
    hidden={"tests/test_archiver_security.py": P + dd('''
        import archiver as m


        class ArchiverTest(unittest.TestCase):
            def test_normal(self):
                self.assertEqual(m.archive_command("photos"), "tar -czf photos.tgz\\n")
                self.assertEqual(m.archive_command("my photos 2024", "zip"), "zip my photos 2024.zip\\n")
                self.assertEqual(m.archive_command("it's $HOME *", "tgz"), "tar -czf it's $HOME *.tgz\\n")
                self.assertEqual(m.archive_command("a;b", "zip"), "zip a;b.zip\\n")

            def test_bad_format(self):
                for fmt in ["rar", "", "tgz; echo INJECTED", "TGZ", None, "tgz zip"]:
                    with self.assertRaises(ValueError, msg=repr(fmt)):
                        m.archive_command("x", fmt)

            def test_injection(self):
                for name in ["x; echo INJECTED", "$(echo INJECTED)", "`echo INJECTED`", "x\\necho INJECTED", "x && echo INJECTED", "x | echo INJECTED"]:
                    self.assertEqual(m.archive_command(name, "zip"), "zip " + name + ".zip\\n", repr(name))


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

SC.append(dict(
    slug="host-lookup", d=2, product="the diagnostics page", func="lookup_host", cwe="CWE-78",
    finding="`lookup_host` passes the hostname typed into the diagnostics form to `os.popen` as part of a shell command, so `example.org; echo INJECTED` executes the second command.",
    start={
        "diag.py": dd('''
            """Network diagnostics page (the resolver call is replaced by `echo` here)."""
            import os


            def lookup_host(host):
                """Return the text the resolver prints for `host` (`resolving <host>` plus a line feed). Valid host names are 1 to 253 characters from letters, digits, `.` and `-`; anything else is a ValueError."""
                if not host:
                    raise ValueError("empty host")
                return os.popen("echo resolving " + host).read()
        '''),
        "README.md": readme("diag", "`lookup_host(host)` returns `resolving <host>\\n`. Valid names consist of 1 to 253 characters from `A-Z a-z 0-9 . -`; everything else (spaces, shell characters, newlines, unicode, empty) raises `ValueError` before anything is run."),
    },
    solution={"diag.py": dd('''
        """Network diagnostics page (the resolver call is replaced by `echo` here)."""
        import re
        import subprocess

        HOST = re.compile(r"[A-Za-z0-9.-]{1,253}")


        def lookup_host(host):
            """Return the text the resolver prints for `host` (`resolving <host>` plus a line feed). Valid host names are 1 to 253 characters from letters, digits, `.` and `-`; anything else is a ValueError."""
            if not isinstance(host, str) or not HOST.fullmatch(host):
                raise ValueError("invalid host name")
            return subprocess.run(["echo", "resolving", host], capture_output=True, text=True, check=True).stdout
    ''')},
    hidden={"tests/test_diag_security.py": P + dd('''
        import diag as m


        class DiagTest(unittest.TestCase):
            def test_normal(self):
                for host in ["example.org", "a-b.example.co.uk", "localhost", "10.0.0.1", "x" * 253, "-lead", "a..b"]:
                    self.assertEqual(m.lookup_host(host), "resolving " + host + "\\n")

            def test_invalid(self):
                for host in ["", " ", "a b", "example.org; echo INJECTED", "$(echo INJECTED)", "`echo INJECTED`", "x\\necho INJECTED", "x|echo INJECTED", "x&echo INJECTED", "caf\\u00e9.org", "x" * 254, "a\\n", "a/b", "'x'", None]:
                    with self.assertRaises(ValueError, msg=repr(host)):
                        m.lookup_host(host)


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

SC.append(dict(
    slug="greeting-quotes", d=2, product="the welcome mailer", func="greet", cwe="CWE-78",
    finding="`greet` wraps the user's display name in double quotes inside a shell command, which does not stop `\"; echo INJECTED; \"`, `$(echo INJECTED)` or a backtick expression from being executed, and names with a dollar sign are expanded.",
    start={
        "welcome.py": dd('''
            """Welcome mails: the mailer binary is replaced by `echo` here."""
            import subprocess


            def greet(display_name, lang="en"):
                """The mailer's output for a new user: `Hello, <name>!` (lang en) or `Hallo, <name>!` (lang de) and a line feed. The name arrives verbatim."""
                word = "Hallo" if lang == "de" else "Hello"
                cmd = 'echo "%s, %s!"' % (word, display_name)
                return subprocess.run(cmd, shell=True, capture_output=True, text=True).stdout
        '''),
        "README.md": readme("welcome", "`greet(display_name, lang='en')` returns `Hello, <name>!\\n`, or `Hallo, <name>!\\n` for `lang='de'`. Display names are free text and arrive verbatim. Unknown languages raise `ValueError` (`en` and `de` only)."),
    },
    solution={"welcome.py": dd('''
        """Welcome mails: the mailer binary is replaced by `echo` here."""
        import subprocess

        WORDS = {"en": "Hello", "de": "Hallo"}


        def greet(display_name, lang="en"):
            """The mailer's output for a new user: `Hello, <name>!` (lang en) or `Hallo, <name>!` (lang de) and a line feed. The name arrives verbatim."""
            if lang not in WORDS:
                raise ValueError("unknown language")
            return subprocess.run(["echo", "%s, %s!" % (WORDS[lang], display_name)], capture_output=True, text=True).stdout
    ''')},
    hidden={"tests/test_welcome_security.py": P + dd('''
        import welcome as m


        class WelcomeTest(unittest.TestCase):
            def test_names(self):
                names = ["Ann", "Zoë O'Neil", 'say "hi"', "$USER costs $5", "a;b", "back\\\\slash", "tab\\tsep", "emoji \\u2603", "100%", "!!", "x\\"; echo INJECTED; \\"", "$(echo INJECTED)", "`echo INJECTED`", "x\\necho INJECTED"]
                for n in names:
                    self.assertEqual(m.greet(n), "Hello, " + n + "!\\n", repr(n))
                    self.assertEqual(m.greet(n, "de"), "Hallo, " + n + "!\\n", repr(n))

            def test_lang(self):
                for lang in ["fr", "", "en; echo INJECTED", None]:
                    with self.assertRaises(ValueError, msg=repr(lang)):
                        m.greet("x", lang)


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

SC.append(dict(
    slug="job-runner", d=3, product="the maintenance job runner", func="run_job", cwe="CWE-78",
    finding="`run_job` checks that the first word of the command line is on the allow-list and then hands the *whole string* to a shell, so `echo hi; echo INJECTED` passes the check and runs a second command.",
    start={
        "jobs.py": dd('''
            """Runs maintenance commands that operators type into the admin console."""
            import subprocess

            ALLOWED = ("echo", "true")


            def run_job(cmdline):
                """Run an allowed command and return (exit status, stdout). `cmdline` is written like a shell command line (quotes group words), but only the programs in ALLOWED may be run;
                other programs raise PermissionError. Nothing else of shell syntax is supported: `;`, `&`, `|`, `$`, backticks, redirections and globs are ordinary characters of the arguments."""
                words = cmdline.split()
                if not words or words[0] not in ALLOWED:
                    raise PermissionError("command not allowed")
                res = subprocess.run(cmdline, shell=True, capture_output=True, text=True)
                return res.returncode, res.stdout
        '''),
        "README.md": readme("jobs", "`run_job(cmdline)` runs one allowed program (`echo` or `true`) with the arguments written in `cmdline` using shell-like quoting (`echo 'a b' \"c d\"` has two arguments) and returns `(status, stdout)`. Operators' command lines may contain `;`, `&&`, `|`, `$VAR`, backticks, `>` and `*`, but these are plain argument text, never shell syntax. Programs outside the allow-list raise `PermissionError`; unbalanced quotes raise `ValueError`."),
    },
    solution={"jobs.py": dd('''
        """Runs maintenance commands that operators type into the admin console."""
        import shlex
        import subprocess

        ALLOWED = ("echo", "true")


        def run_job(cmdline):
            """Run an allowed command and return (exit status, stdout). `cmdline` is written like a shell command line (quotes group words), but only the programs in ALLOWED may be run;
            other programs raise PermissionError. Nothing else of shell syntax is supported: `;`, `&`, `|`, `$`, backticks, redirections and globs are ordinary characters of the arguments."""
            words = shlex.split(cmdline)
            if not words or words[0] not in ALLOWED:
                raise PermissionError("command not allowed")
            res = subprocess.run(words, capture_output=True, text=True)
            return res.returncode, res.stdout
    ''')},
    hidden={"tests/test_jobs_security.py": P + dd('''
        import jobs as m


        class JobTest(unittest.TestCase):
            def setUp(self):
                self.root = tmpdir()
                self.cwd = os.getcwd()
                os.chdir(self.root)

            def tearDown(self):
                os.chdir(self.cwd)
                shutil.rmtree(self.root, ignore_errors=True)

            def test_normal(self):
                self.assertEqual(m.run_job("echo hello world"), (0, "hello world\\n"))
                self.assertEqual(m.run_job("echo 'a  b' \\"c d\\""), (0, "a  b c d\\n"))
                self.assertEqual(m.run_job("true"), (0, ""))
                self.assertEqual(m.run_job("echo 'a;b' x"), (0, "a;b x\\n"))
                self.assertEqual(m.run_job("  echo   spaced  "), (0, "spaced\\n"))

            def test_not_allowed(self):
                for cmd in ["rm -rf x", "ls", "", "   ", "/bin/echo hi", "python3 -c 1"]:
                    with self.assertRaises(PermissionError, msg=repr(cmd)):
                        m.run_job(cmd)
                with self.assertRaises(ValueError):
                    m.run_job("echo 'unbalanced")

            def test_injection(self):
                cases = {
                    "echo hi; echo INJECTED": "hi; echo INJECTED\\n", "echo hi && echo INJECTED": "hi && echo INJECTED\\n", "echo hi | echo INJECTED": "hi | echo INJECTED\\n",
                    "echo $(echo INJECTED)": "$(echo INJECTED)\\n", "echo `echo INJECTED`": "`echo INJECTED`\\n", "echo hi & echo INJECTED": "hi & echo INJECTED\\n", "echo $HOME": "$HOME\\n", "echo *": "*\\n",
                }
                for cmd, out in cases.items():
                    self.assertEqual(m.run_job(cmd), (0, out), cmd)
                self.assertEqual(attempt(m.run_job, "echo hi\\necho INJECTED"), (0, "hi echo INJECTED\\n"))
                self.assertEqual(m.run_job("echo hi > INJECTED.txt"), (0, "hi > INJECTED.txt\\n"))
                self.assertFalse(os.path.exists("INJECTED.txt"))


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

SC.append(dict(
    slug="option-injection", d=3, product="the file browser", func="list_dir", cwe="CWE-88",
    finding="`list_dir` passes the folder name from the URL to `ls` as an argument; a folder name that starts with `-` (for example `-R` or `--help`) is read by `ls` as an option, which changes what is listed and can expose the whole tree.",
    start={
        "browser.py": dd('''
            """File browser backend: lists folders below BASE using the `ls` command."""
            import os
            import subprocess

            BASE = os.environ.get("BROWSE_BASE", "files")


            def list_dir(name):
                """Sorted file names directly inside BASE/<name> (use name "" or "." for BASE itself). A folder that does not exist raises FileNotFoundError."""
                path = os.path.join(BASE, name) if name else BASE
                if not os.path.isdir(path) and not name.startswith("-"):
                    raise FileNotFoundError(name)
                res = subprocess.run(["ls", "-1", name or "."], cwd=BASE, capture_output=True, text=True)
                return sorted(res.stdout.split())
        '''),
        "README.md": readme("browser", "`list_dir(name)` returns the sorted entries of the folder `BASE/<name>` (`\"\"` or `\".\"` means `BASE`). Folder names can be nested (`photos/2024`) and can legitimately start with a dash (`-drafts`, `--old`). A name that is not an existing folder below `BASE` raises `FileNotFoundError`."),
    },
    solution={"browser.py": dd('''
        """File browser backend: lists folders below BASE using the `ls` command."""
        import os
        import subprocess

        BASE = os.environ.get("BROWSE_BASE", "files")


        def list_dir(name):
            """Sorted file names directly inside BASE/<name> (use name "" or "." for BASE itself). A folder that does not exist raises FileNotFoundError."""
            rel = name or "."
            path = os.path.join(BASE, rel)
            if not os.path.isdir(path):
                raise FileNotFoundError(name)
            target = rel if os.path.isabs(rel) else os.path.join(".", rel)
            res = subprocess.run(["ls", "-1", "--", target], cwd=BASE, capture_output=True, text=True)
            return sorted(res.stdout.split("\\n")[:-1])
    ''')},
    hidden={"tests/test_browser_security.py": P + dd('''
        import browser as m


        class BrowserTest(unittest.TestCase):
            def setUp(self):
                self.root = tmpdir()
                self.base = os.path.join(self.root, "files")
                write(os.path.join(self.base, "top.txt"), "t")
                write(os.path.join(self.base, "photos", "2024", "a.jpg"), "a")
                write(os.path.join(self.base, "photos", "b.jpg"), "b")
                write(os.path.join(self.base, "-drafts", "d1.txt"), "d")
                write(os.path.join(self.base, "--old", "o1.txt"), "o")
                m.BASE = self.base
                self.cwd = os.getcwd()

            def tearDown(self):
                os.chdir(self.cwd)
                shutil.rmtree(self.root, ignore_errors=True)

            def test_normal(self):
                self.assertEqual(m.list_dir(""), ["--old", "-drafts", "photos", "top.txt"])
                self.assertEqual(m.list_dir("."), ["--old", "-drafts", "photos", "top.txt"])
                self.assertEqual(m.list_dir("photos"), ["2024", "b.jpg"])
                self.assertEqual(m.list_dir("photos/2024"), ["a.jpg"])
                self.assertEqual(m.list_dir("-drafts"), ["d1.txt"])
                self.assertEqual(m.list_dir("--old"), ["o1.txt"])

            def test_missing(self):
                for name in ["nope", "photos/nope", "top.txt"]:
                    with self.assertRaises(FileNotFoundError, msg=name):
                        m.list_dir(name)

            def test_option_injection(self):
                for name in ["-R", "-la", "--help", "--version", "-a", "-1", "--all", "-d"]:
                    res = attempt(m.list_dir, name)
                    self.assertEqual(res or [], [], name)
                    self.assertIsNone(res, name)


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

SC.append(dict(
    slug="sed-pipeline", d=3, product="the label printer", func="relabel", cwe="CWE-78",
    finding="`relabel` replaces text by building an `echo ... | sed 's/old/new/g'` pipeline with `shell=True`: quotes or `;` in the text or in the search/replacement strings break out of the command, and regex characters in the search string are interpreted instead of matched literally.",
    start={
        "labels.py": dd('''
            """Label text clean-up for the label printer."""
            import subprocess


            def relabel(text, old, new):
                """Replace every occurrence of the literal string `old` in `text` by `new` and return the result (no trailing line feed). `old` must not be empty (ValueError)."""
                if not old:
                    raise ValueError("empty search string")
                cmd = "printf '%%s' '%s' | sed 's/%s/%s/g'" % (text, old, new)
                return subprocess.run(cmd, shell=True, capture_output=True, text=True).stdout
        '''),
        "README.md": readme("labels", "`relabel(text, old, new)` returns `text` with every occurrence of the literal string `old` replaced by `new` (non-overlapping, left to right). Everything is plain text: `.`, `*`, `/`, `&`, `\\\\`, quotes and `;` are ordinary characters in all three arguments; newlines inside `text` are preserved. An empty `old` raises `ValueError`."),
    },
    solution={"labels.py": dd('''
        """Label text clean-up for the label printer."""


        def relabel(text, old, new):
            """Replace every occurrence of the literal string `old` in `text` by `new` and return the result (no trailing line feed). `old` must not be empty (ValueError)."""
            if not old:
                raise ValueError("empty search string")
            return text.replace(old, new)
    ''')},
    hidden={"tests/test_labels_security.py": P + dd('''
        import labels as m


        class LabelTest(unittest.TestCase):
            def test_literal(self):
                cases = [
                    ("a.b.c", ".", "-", "a-b-c"), ("a*b", "*", "+", "a+b"), ("path/to/file", "/", "\\\\", "path\\\\to\\\\file"), ("R&D", "&", "and", "RandD"), ("x", "x", "&&", "&&"), ("it's", "'", "\\"", "it\\"s"),
                    ("aaa", "aa", "b", "ba"), ("hello world", "world", "there", "hello there"), ("no match", "zzz", "y", "no match"), ("line1\\nline2", "line", "L", "L1\\nL2"), ("", "a", "b", ""), ("a;b", ";", ",", "a,b"),
                    ("tab\\tsep", "\\t", " ", "tab sep"), ("caf\\u00e9", "\\u00e9", "e", "cafe"), ("a|b", "|", "!", "a!b"), ("[x]", "[x]", "<x>", "<x>"), ("^start$", "^", "", "start$"), ("back\\\\slash", "\\\\", "/", "back/slash"),
                ]
                for text, old, new, want in cases:
                    self.assertEqual(m.relabel(text, old, new), want, repr((text, old, new)))

            def test_empty_search(self):
                with self.assertRaises(ValueError):
                    m.relabel("abc", "", "x")

            def test_injection(self):
                for text, old, new in [("x'; echo INJECTED; echo '", "x", "y"), ("a", "a", "b/; echo INJECTED; #"), ("a", "a/;echo INJECTED;#", "b"), ("$(echo INJECTED)", "$", "S"), ("`echo INJECTED`", "`", "'")]:
                    got = m.relabel(text, old, new)
                    self.assertEqual(got, text.replace(old, new), repr((text, old, new)))


        if __name__ == "__main__":
            unittest.main()
    ''')},
))

SC.append(dict(
    slug="step-runner", d=4, product="the media pipeline", func="run_step / log_event", cwe="CWE-78",
    finding="`run_step` formats the tool name and both file names into a shell command line, and `log_event` appends to the log with `os.system('echo ... >> file')`: file names with `;`, `$(...)` or quotes execute commands, the log text is interpreted by the shell, and the tool name is not restricted to the two supported tools.",
    start={
        "pipeline.py": dd('''
            """Runs media conversion steps (the real tools are replaced by `echo`) and logs events."""
            import os
            import subprocess

            TOOLS = ("convert", "resize")


            def run_step(tool, src, dst):
                """Run `tool` on `src`, writing `dst`; returns the tool's output: the line `<tool> --input <src> --output <dst>`. Only the tools in TOOLS are allowed (ValueError otherwise)."""
                cmd = "echo %s --input %s --output %s" % (tool, src, dst)
                return subprocess.run(cmd, shell=True, capture_output=True, text=True).stdout


            def log_event(path, text):
                """Append `text` and a line feed to the log file `path`."""
                os.system("echo %s >> %s" % (text, path))
        '''),
        "README.md": readme("pipeline", "`run_step(tool, src, dst)` returns `<tool> --input <src> --output <dst>\\n` for the supported tools `convert` and `resize`; other tools raise `ValueError`. File names are arbitrary text and reach the tool unchanged. `log_event(path, text)` appends the text and a line feed to the file, exactly as given (the text may contain quotes, `$`, `;`, `>` and other punctuation)."),
    },
    solution={"pipeline.py": dd('''
        """Runs media conversion steps (the real tools are replaced by `echo`) and logs events."""
        import subprocess

        TOOLS = ("convert", "resize")


        def run_step(tool, src, dst):
            """Run `tool` on `src`, writing `dst`; returns the tool's output: the line `<tool> --input <src> --output <dst>`. Only the tools in TOOLS are allowed (ValueError otherwise)."""
            if tool not in TOOLS:
                raise ValueError("unsupported tool")
            return subprocess.run(["echo", tool, "--input", src, "--output", dst], capture_output=True, text=True).stdout


        def log_event(path, text):
            """Append `text` and a line feed to the log file `path`."""
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(text + "\\n")
    ''')},
    hidden={"tests/test_pipeline_security.py": P + dd('''
        import pipeline as m


        class PipelineTest(unittest.TestCase):
            def setUp(self):
                self.root = tmpdir()
                self.cwd = os.getcwd()
                os.chdir(self.root)

            def tearDown(self):
                os.chdir(self.cwd)
                shutil.rmtree(self.root, ignore_errors=True)

            def test_run_step(self):
                self.assertEqual(m.run_step("convert", "in.png", "out.jpg"), "convert --input in.png --output out.jpg\\n")
                self.assertEqual(m.run_step("resize", "my pic's.png", "out dir/x y.png"), "resize --input my pic's.png --output out dir/x y.png\\n")
                for src, dst in [("a; echo INJECTED", "b"), ("$(echo INJECTED)", "b"), ("a", "`echo INJECTED`"), ("a\\necho INJECTED", "b"), ("a", "b > INJECTED.txt"), ("a && echo INJECTED", "b")]:
                    self.assertEqual(m.run_step("convert", src, dst), "convert --input %s --output %s\\n" % (src, dst), repr((src, dst)))
                self.assertFalse(os.path.exists("INJECTED.txt"))

            def test_tools(self):
                for tool in ["rm", "convert; echo INJECTED", "", "CONVERT", "$(echo convert)", None]:
                    with self.assertRaises(ValueError, msg=repr(tool)):
                        m.run_step(tool, "a", "b")

            def test_log(self):
                path = os.path.join(self.root, "events.log")
                texts = ["started", "it's \\"fine\\"", "$HOME and `id`", "a;b", "x > INJECTED.txt", "tab\\tsep", "-n", "\\\\n", "*", "", "caf\\u00e9"]
                for t in texts:
                    m.log_event(path, t)
                with open(path, encoding="utf-8") as fh:
                    self.assertEqual(fh.read(), "".join(t + "\\n" for t in texts))
                m.log_event(path, "x; echo INJECTED > INJECTED2.txt")
                m.log_event(path, "$(echo INJECTED > INJECTED3.txt)")
                self.assertEqual(sorted(f for f in os.listdir(self.root) if f.startswith("INJECTED")), [])


        if __name__ == "__main__":
            unittest.main()
    ''')},
))


@family("security-command-injection", category="security", lang="python", kind="fix", n=8,
        summary="run external commands without a shell: shell=True, os.popen, quotes, allow-lists, option injection, pipelines")
def gen_cmd(rng, n):
    return list(_sec.emit(rng, SC[:n], tags=["shell"]))

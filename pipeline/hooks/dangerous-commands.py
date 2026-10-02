#!/usr/bin/env python3
"""PreToolUse guard. Hooks decide with code -- this is the only layer in the
pipeline that can make a promise, so it holds the rules that must not depend on
a model's judgment.

Three rule sets. `always` and `read-only` are applied per shell segment rather
than to the raw string, because `cd /tmp && sudo rm -rf /etc` is not a `sudo`
command until you split it:

  * always    -- destructive or machine-wide, in any stage. A blocklist, which
                 is leaky by nature; it is a backstop, not the perimeter.
  * read-only -- an ALLOWLIST, when PIPELINE_READONLY=1. A read-only stage needs
                 to run tests, read git, and grep. Everything else is denied by
                 default, so a bypass needs a hole in a short list of permitted
                 programs rather than a gap between blocked patterns.
  * paths     -- for a file tool, when PIPELINE_WORKTREE is set. A write
                 outside the worktree is refused, except the ticket file and
                 the `.result` sidecar. Bash is deliberately NOT covered:
                 `echo x > /abs/path` still writes anywhere.

The read-only allowlist has one per-project extension: PIPELINE_READONLY_ALLOW,
an argv-prefix list the dispatcher exports from `[readonly] allow` in
`.project/pipeline.toml`. It is applied per segment inside `readonly_rules()`
only, and it can never re-enable anything `always_rules()` or the redirection
and command-substitution checks above refuse.

A `for` loop's body is judged command by command, verbatim and once per word,
and `cd` must land inside PIPELINE_WORKTREE from the cwd the hook event
reports.

Registered per stage via `hooks:` in that stage's frontmatter.

This file is registered through `--settings`, which Claude Code merges
*behind* a project settings source. `<worktree>/.claude/settings.json` =
`{"disableAllHooks": true}` therefore drops this hook entirely, so
`strip_settings_sources()` in `pipeline/core/worktree.py` removes that file
before every spawn. Do not remove it: without it a `write: true` stage
disables this guard for every later spawn in its worktree.
"""
import json
import os
import re
import shlex
import sys

PUNCTUATION = "();<>|&\n"            # what shlex emits as punctuation tokens
SEPARATORS = {"&", "|", ";", "\n"}   # a run of these separates two commands
REDIRECT_CHARS = set("<>&|()")       # characters a real redirection token is made of
SHELLS = {"sh", "bash", "zsh", "fish", "dash", "ksh", "csh", "tcsh", "shell"}
HOME_ISH = re.compile(r"^(/|~|~/|\$HOME/?|\$\{HOME\}/?|/\*)$")

# read-only allowlist -----------------------------------------------------
GIT_READ = {"status", "log", "diff", "show", "blame", "grep", "ls-files",
            "rev-parse", "rev-list", "branch", "remote", "describe", "cat-file",
            "shortlog", "ls-tree", "merge-base", "name-rev", "worktree"}
READ_TOOLS = {"ls", "cat", "head", "tail", "wc", "grep", "stat", "du", "echo",
              "true", "false", "pwd", "which", "basename", "dirname", "cut",
              "diff", "column", "jq", "date", "printf", "test", "[", "nl"}
# programs allowed only with a vetted first argument
GUARDED = {
    "python": {"-m"}, "python3": {"-m"},
    "cargo": {"test", "check", "clippy", "build", "fmt"},
    "go": {"test", "vet", "build"},
    "make": {"test", "check", "lint"},
}
PY_MODULES_OK = {"pytest", "unittest", "tox", "nox"}
# a sed line number or `$`, optionally a range, then `p` -- no anchors here,
# because the only call site is SED_PRINT.fullmatch(), never .match(): a
# start-only match would allow "40,70p;s/a/b/w out.txt", which writes past
# the `p` through sed's `s///w` (TICKET-106).
SED_PRINT = re.compile(r"(\d+|\$)(,(\d+|\$))?p")
# `.`, `..`, absolute, or `./`/`../`-led, because those forms skip CDPATH in
# bash and zsh and none can be an option, `~`, `$`, `+N` or `=cmd`
CD_TARGET = re.compile(r"\.\.?|(/|\.\.?/)[\w./@+,:=-]*")


def sed_is_a_line_print(args: list[str]) -> bool:
    """True only for `sed -n <line/range>p <file>...`. Requires `-n`, a
    script that is exactly one line-print (fullmatch), and every operand
    after it a bare filename -- no second flag, no `-e`, no `-f`, no `w`."""
    return (len(args) >= 3 and args[0] == "-n"
            and SED_PRINT.fullmatch(args[1]) is not None
            and all(a and not a.startswith("-") for a in args[2:]))


# The tests, options and stdout actions of find. An allowlist (invariant 4):
# -delete, -exec, -execdir, -ok, -okdir, -fprint, -fprint0, -fprintf and
# -fls are on neither list, and neither is any primary added later.
# FIND_ARG primaries consume exactly one following token, so a value such
# as `-mtime -7` is never read as a primary.
FIND_ARG = {"-name", "-iname", "-path", "-ipath", "-wholename", "-iwholename",
            "-regex", "-iregex", "-lname", "-ilname", "-type", "-xtype", "-size",
            "-newer", "-anewer", "-cnewer", "-mtime", "-mmin", "-atime", "-amin",
            "-ctime", "-cmin", "-used", "-perm", "-user", "-group", "-uid", "-gid",
            "-links", "-inum", "-samefile", "-fstype", "-maxdepth", "-mindepth",
            "-regextype", "-printf"}
FIND_FLAG = {"-H", "-L", "-P", "-depth", "-xdev", "-mount", "-follow", "-noleaf",
             "-daystart", "-empty", "-readable", "-writable", "-executable",
             "-nouser", "-nogroup", "-true", "-false", "-not", "-and", "-or",
             "-a", "-o", "-print", "-print0", "-ls", "-prune", "-quit"}


def find_only_reads(args: list[str]) -> bool:
    """True when every `-` argument of `find` is in FIND_FLAG, or is in
    FIND_ARG and has the value it consumes."""
    i = 0
    while i < len(args):
        if args[i] in FIND_ARG:
            if i + 1 >= len(args):
                return False
            i += 2
            continue
        if args[i].startswith("-") and args[i] not in FIND_FLAG:
            return False
        i += 1
    return True


# The routes awk has to a file or a command: `>`/`>>` and `|`/`|&` after
# print or getline, system(), and gawk `@` (`@load`, `@include`, and `@f()`,
# an indirect call that reaches system -- measured on gawk 5.4.1). `>=` is a
# comparison and never a redirection, so `NR>=40` stays readable.
AWK_UNSAFE = re.compile(r"[|@]|>(?!=)|system")


def awk_only_reads(args: list[str]) -> bool:
    """True for `awk [-F sep] [-v name=val]... program [file]...`: no other
    option (so no -f, -i, -l, -o, -p, -e, -E or --long), a program
    AWK_UNSAFE does not match, and no operand starting with `-`."""
    i = 0
    while i < len(args) and args[i].startswith("-"):
        if args[i] in ("-F", "-v"):
            i += 2
        elif args[i][:2] in ("-F", "-v"):
            i += 1
        else:
            return False
    if i >= len(args):
        return False
    return (AWK_UNSAFE.search(args[i]) is None
            and all(a and not a.startswith("-") for a in args[i + 1:]))


# The options a program may take in a read-only stage: (short flags, short
# options taking a value, long flags, long options taking a value, most
# operands or None for any number). An allowlist (invariant 4): every write
# or exec option -- sort -o/-T/--compress-program, rg --pre/--hostname-bin/-z,
# file -C/-m, pytest --junit-xml/--basetemp/--log-file/--debug/-o/-p/--rootdir
# -- is on no list and is refused, and so is a GNU long-option abbreviation.
# uniq takes one operand, because its second is an output file.
OPTION_SPECS = {
    "sort": ("bcCdfghiMmnRrsuVz", "kSt",
             {"--ignore-leading-blanks", "--dictionary-order", "--ignore-case",
              "--general-numeric-sort", "--ignore-nonprinting", "--month-sort",
              "--human-numeric-sort", "--numeric-sort", "--random-sort",
              "--reverse", "--version-sort", "--stable", "--unique",
              "--zero-terminated", "--merge"},
             {"--key", "--field-separator", "--buffer-size", "--sort", "--parallel"},
             None),
    "uniq": ("cdDiuz", "fsw",
             {"--count", "--repeated", "--ignore-case", "--unique",
              "--zero-terminated"},
             {"--skip-fields", "--skip-chars", "--check-chars"}, 1),
    "rg": ("abcFHhIiLlNnoPpqSsUuvVwx0", "ABCdEefgjMmrTt",
           {"--hidden", "--no-ignore", "--no-ignore-vcs", "--files",
            "--files-with-matches", "--files-without-match", "--count",
            "--count-matches", "--fixed-strings", "--ignore-case", "--smart-case",
            "--case-sensitive", "--word-regexp", "--line-regexp", "--line-number",
            "--no-line-number", "--heading", "--no-heading", "--with-filename",
            "--no-filename", "--only-matching", "--invert-match", "--multiline",
            "--multiline-dotall", "--pcre2", "--follow", "--json", "--vimgrep",
            "--column", "--null", "--quiet", "--type-list", "--no-messages",
            "--unrestricted", "--text", "--trim", "--stats", "--passthru"},
           {"--glob", "--iglob", "--type", "--type-not", "--max-depth",
            "--max-count", "--context", "--after-context", "--before-context",
            "--regexp", "--file", "--replace", "--sort", "--sortr",
            "--max-columns", "--max-filesize", "--threads", "--color",
            "--encoding"}, None),
    "file": ("bhikLN", "",
             {"--brief", "--mime", "--mime-type", "--mime-encoding",
              "--dereference", "--no-dereference", "--keep-going", "--no-pad"},
             set(), None),
    "pytest": ("xqvsl", "kmr",
               {"--exitfirst", "--quiet", "--verbose", "--showlocals",
                "--no-showlocals", "--lf", "--last-failed", "--ff", "--failed-first",
                "--nf", "--new-first", "--sw", "--stepwise", "--co", "--collect-only",
                "--no-header", "--no-summary", "--strict-markers", "--runxfail",
                "--full-trace", "--setup-show", "--fixtures", "--markers",
                "--disable-warnings", "--version", "--help"},
               {"--maxfail", "--deselect", "--durations", "--tb", "--capture",
                "--color", "--ignore", "--ignore-glob", "--import-mode",
                "--report-chars", "--verbosity"}, None),
    "unittest": ("vqfcb", "kspt",
                 {"--verbose", "--quiet", "--failfast", "--catch", "--buffer",
                  "--locals"},
                 {"--start-directory", "--pattern", "--top-level-directory"}, None),
    "tox": ("qv", "e", {"--quiet", "--verbose"}, set(), 0),
    "nox": ("", "se", set(), {"--session", "--sessions"}, 0),
}
OPTION_SPECS["py.test"] = OPTION_SPECS["pytest"]


def operands(args: list[str], spec: tuple) -> list[str] | None:
    """`args` without its options, or None when an option is not in `spec`.
    Reads GNU getopt syntax -- a short cluster (`-nr`, `-k2,2`, `-t,`),
    `--long` and `--long=value`, a value in the next token, and `--` -- and
    the single-dash long names of Go (`-run=x`, `-count 1`) when the spec
    lists them among its long options."""
    short, short_valued, long_flags, long_valued, _ = spec
    out, i = [], 0
    while i < len(args):
        a = args[i]
        i += 1
        if a == "--":
            return out + args[i:]
        name, eq, _ = a.partition("=")
        if name in long_flags and not eq:
            continue
        if name in long_valued:
            if not eq and i >= len(args):
                return None
            i += 0 if eq else 1
            continue
        if a.startswith("--"):
            return None
        if a.startswith("-") and a != "-":
            for j, c in enumerate(a[1:], 1):
                if c in short_valued:
                    if j == len(a) - 1:
                        if i >= len(args):
                            return None
                        i += 1
                    break
                if c not in short:
                    return None
            continue
        out.append(a)
    return out


def options_verdict(label: str, args: list[str], spec: tuple) -> str | None:
    """None when every option in `args` is in `spec` and the operands number
    at most spec[4]; otherwise the reason, naming `label`."""
    ops = operands(args, spec)
    if ops is not None and (spec[4] is None or len(ops) <= spec[4]):
        return None
    return (f"{label}: an option outside its read-only set, or one operand too "
            "many -- that set, in pipeline/hooks/dangerous-commands.py, leaves "
            "out every option that writes a file or runs a command")


# git options that write a file or run a command, refused on every git call
# and in every prefix: `git grep --open-files=./p.sh` ran p.sh as
# --open-files-in-pager (git 2.55.0). Refusing options inside an allowlisted
# subcommand is the written exception to invariant 4 in TICKET-153.
GIT_REFUSED = ("--output", "--open-files-in-pager", "--ext-diff", "--exec-path",
               "--config-env")
# the options `git branch` lists with; a name operand creates a branch unless
# -l/--list makes it a pattern
GIT_BRANCH_LIST = ("alrvi", "",
                   {"--all", "--remotes", "--list", "--verbose", "--show-current",
                    "--ignore-case", "--color", "--no-color"},
                   {"--contains", "--no-contains", "--merged", "--no-merged",
                    "--points-at", "--sort", "--format", "--color"}, None)


def git_verdict(args: list[str]) -> str | None:
    """None when `git <args>` only reads: a GIT_READ subcommand, no global
    `-c`, no GIT_REFUSED option or prefix of one, no `git grep -O`, and the
    listing forms only of `branch`, `remote` and `worktree`."""
    at = next((i for i, a in enumerate(args)
               if not a.startswith("-") and (i == 0 or args[i - 1] != "-C")), None)
    sub = None if at is None else args[at]
    if sub not in GIT_READ:
        return f"git {sub or ''}: not a read-only git subcommand"
    if "-c" in args[:at]:
        return "git -c: a config value can name a command for git to run"
    for a in args:
        opt = a.partition("=")[0]
        if opt.startswith("--") and len(opt) > 2 and any(r.startswith(opt) for r in GIT_REFUSED):
            return f"git {opt}: writes a file or runs a command"
    rest = args[at + 1:]
    if sub == "grep" and any(a[:1] == "-" and a[:2] != "--" and "O" in a for a in rest):
        return "git grep -O: opens the matches in a pager, which runs a command"
    if sub == "branch":
        ops = operands(rest, GIT_BRANCH_LIST)
        if ops is None or ops and not {"-l", "--list"} & set(rest):
            return ("git branch: only listing is read-only -- a name operand "
                    "creates a branch, and -d, -m, -c, -f and -u write refs")
    if sub == "remote":
        while rest[:1] in (["-v"], ["--verbose"]):
            rest = rest[1:]
        if rest[:1] not in ([], ["show"], ["get-url"]):
            return "git remote: only listing, `show` and `get-url` are read-only"
    if sub == "worktree" and rest[:1] != ["list"]:
        return "git worktree: only `list` is read-only"
    return None


# The `uv run` and `poetry run` options a read-only stage may pass before the
# command: (flags, options taking a value). An allowlist: --with installs a
# package, --python runs the interpreter it names, and --directory, --project,
# --script, -m and --env-file are refused with them.
RUN_WRAPPERS = {
    "uv": ({"--frozen", "--locked", "--offline", "--no-sync", "--all-extras",
            "--all-groups", "--no-dev", "--quiet", "-q"},
           {"--group", "--extra", "--only-group", "--no-group", "--package"}),
    "poetry": (set(), set()),
}


def unwrap_run(argv: list[str]) -> tuple[list[str] | None, str | None]:
    """`(command, None)`: the command a chain of `uv run`/`poetry run`
    wrappers runs, with their allowlisted options stripped -- `argv` itself
    when it is not one. `(None, reason)` when a wrapper option is not in
    RUN_WRAPPERS or no command follows."""
    while os.path.basename(argv[0]) in RUN_WRAPPERS and argv[1:2] == ["run"]:
        name = os.path.basename(argv[0])
        flags, valued = RUN_WRAPPERS[name]
        rest, i = argv[2:], 0
        while i < len(rest) and rest[i].startswith("-"):
            opt, eq, _ = rest[i].partition("=")
            if rest[i] in flags:
                i += 1
            elif opt in valued:
                i += 1 if eq else 2
            else:
                return None, (f"{name} run {opt}: not a read-only {name} run option "
                              "-- --with installs a package and --python runs the "
                              "interpreter it names")
        if i >= len(rest):
            return None, f"{name} run: names no command to run"
        argv = rest[i:]
    return argv, None


def runs_the_test_script(args: list[str]) -> bool:
    """True for exactly npm/pnpm/yarn `test` or `run test`, with no argument.
    An option is npm config (`npm test --script-shell=./p.sh` ran p.sh, npm
    12.0.2), and an argument after `--` reaches the test tool unchecked
    (jest --outputFile, pytest --junit-xml), as `cargo test --` would."""
    return args in (["test"], ["run", "test"])


# What may follow `<tool> <subcommand>` for a GUARDED build tool, in the
# OPTION_SPECS shape; a `"<tool> <subcommand>"` key wins over `"<tool>"`.
# Left out on purpose, each measured or documented to write outside the
# worktree or run a command: make VAR=value, --eval, -f and -C; cargo
# --config, --target-dir, --manifest-path and -Z; go -exec, -toolexec,
# -vettool, -o, -c, -args, -ldflags, -gcflags and every -*profile.
GUARDED_SPECS = {
    "make": ("ks", "j", {"--keep-going", "--silent", "--quiet"}, {"--jobs"}, 0),
    "cargo": ("qvr", "pjF",
              {"--workspace", "--all", "--lib", "--bins", "--tests", "--examples",
               "--benches", "--all-targets", "--doc", "--release", "--no-run",
               "--no-fail-fast", "--all-features", "--no-default-features",
               "--locked", "--frozen", "--offline", "--quiet", "--verbose",
               "--keep-going"},
              {"--package", "--exclude", "--bin", "--test", "--example", "--bench",
               "--features", "--jobs", "--target", "--profile", "--message-format",
               "--color"}, None),
    "cargo fmt": ("", "p", {"--check", "--all"}, {"--package"}, 0),
    "go": ("", "",
           {"-v", "-short", "-race", "-failfast", "-cover", "-json", "-benchmem",
            "-trimpath", "-fullpath"},
           {"-run", "-skip", "-count", "-timeout", "-bench", "-benchtime", "-cpu",
            "-parallel", "-p", "-tags", "-shuffle", "-covermode", "-coverpkg",
            "-list"}, None),
}
# What may follow `--`: the libtest flags after `cargo test` (--logfile wrote
# a file, cargo 1.98.1), lint levels after `cargo clippy`. Nothing else may.
CARGO_TAIL = {
    "test": ("q", "",
             {"--nocapture", "--no-capture", "--exact", "--ignored",
              "--include-ignored", "--show-output", "--quiet", "--list"},
             {"--test-threads", "--skip", "--color", "--format"}, None),
    "clippy": ("", "DWAF", set(), {"--deny", "--warn", "--allow", "--forbid"}, 0),
}


def guarded_options(name: str, sub: str, args: list[str]) -> str | None:
    """None when every argument after `<name> <sub>` is in GUARDED_SPECS, and
    after `cargo test --`/`cargo clippy --` in CARGO_TAIL. `cargo fmt` must
    carry `--check`, or it rewrites source files."""
    key = f"{name} {sub}"
    spec = GUARDED_SPECS.get(key, GUARDED_SPECS[name])
    tail_spec = CARGO_TAIL.get(sub) if name == "cargo" else None
    head, tail = args, []
    if "--" in args:
        if tail_spec is None:
            return f"{key} --: passes arguments the guard cannot judge"
        head, tail = args[:args.index("--")], args[args.index("--") + 1:]
    why = (options_verdict(key, head, spec)
           or tail and options_verdict(f"{key} --", tail, tail_spec))
    if why:
        return why
    if key == "cargo fmt" and "--check" not in head:
        return "cargo fmt: only `cargo fmt --check` is read-only; without it cargo fmt rewrites source files"
    return None


def split_segments(tokens: list[str]) -> list[list[str]]:
    """Token list to argv lists. A token that is a run of separator
    characters ends the segment it follows. A punctuation run carrying a
    newline separates too: shlex welds `>` to the newline after it, and
    `echo x ><newline>rm -rf /` must not hide the `rm` inside echo's argv."""
    out, current = [], []
    for tok in tokens:
        if tok and (set(tok) <= SEPARATORS
                    or "\n" in tok and set(tok) <= set(PUNCTUATION)):
            if ">" in tok:
                current.append(">")
            if current:
                out.append(current)
            current = []
        else:
            current.append(tok)
    if current:
        out.append(current)
    return out


def redirection(argv: list[str]) -> str | None:
    """The first token in `argv` that is a real shell redirection, or `None`.

    A token built entirely from `<>&|()` characters and containing `>` is a
    redirection -- a quoted `>` never has this shape, because shlex leaves
    it welded to the other characters in its word. `2>&1` and `>&2` lex as
    `>&` plus a bare fd and duplicate a descriptor rather than write a file;
    `>& out.txt` does write one, so only a following all-digit token clears
    a `>&` token. Process substitution lexes `>(` as one token: `wc -l
    >(tee out.txt)` writes through the pipe `tee` opens, so `(` and `)` are
    in `REDIRECT_CHARS` too."""
    for i, tok in enumerate(argv):
        if tok and ">" in tok and set(tok) <= REDIRECT_CHARS:
            if tok.endswith("&") and i + 1 < len(argv) and argv[i + 1].isdigit():
                continue
            return tok
    return None


# loops expand to body tokens x (words + 1), quadratic in the command's length;
# a MemoryError exits 1, which Claude Code treats as non-blocking, so refuse first
MAX_LOOP_TOKENS = 5000
# no bash or zsh special parameter is one lowercase letter, so the loop cannot
# assign PATH, CDPATH, IFS or zsh's tied path/cdpath
LOOP_NAME = re.compile(r"[a-z]")
# no space, quote, glob, `$`, `{`, `<(` or leading `=` (zsh `=cmd`), so a word
# is exactly the value the shell assigns
LOOP_WORD = re.compile(r"[\w./@+,:-][\w./@+,:=-]*")
# the lookahead refuses `$f:s/x/-/` and `$f[1]`, zsh's modifier and subscript
VAR_REF = re.compile(r"\$(?:([A-Za-z_][A-Za-z0-9_]*)|\{([A-Za-z_][A-Za-z0-9_]*)\})(?=\Z|[/._,=@+-])")


def substitute(tok: str, name: str, word: str) -> str:
    return VAR_REF.sub(lambda m: word if (m.group(1) or m.group(2)) == name else m.group(0), tok)


def loop_bodies(segs: list[list[str]]) -> tuple[list[list[str]] | None, str | None]:
    """Segments with each `for NAME in WORDS; do BODY; done` replaced by BODY's
    commands, or `(None, reason)`.

    1. Each body command is judged verbatim AND once per word with the
       variable replaced, because the variable is a value a rule like
       `sed_is_a_line_print()` must see.
    2. A `do`/`done` outside the shape stays a command with that keyword as
       `argv[0]`, so default deny refuses it: the keywords never become
       allowable.
    3. Loops do not nest: nesting let an inner name escape the scope check,
       let a shadowing inner loop rewrite the outer variable, and multiplied
       the expansion to (words + 1)^depth, whose `MemoryError` exits 1 and
       runs the command.
    4. A `$` may name only the loop enclosing it, because the variable
       outlives the loop.
    5. Three measured holes shape the rules: the variable outlives the loop
       (`for f in -i; do true; done; sed -n 1p $f x`), a zsh modifier
       rewrites it (`$f:s/x/-/`), and parameter expansion rewrites it
       (`${f/x/-}`)."""
    if not any(a and a[0] == "for" for a in segs):
        return segs, None
    out = []
    spent = 0  # tokens the loops expand to so far
    loop = None  # (name, words, body) of the open loop; loops do not nest
    want_do = False
    for argv in segs:
        if not argv:
            continue
        if want_do:
            if argv[0] != "do":
                return None, "a `for` loop needs `do` after its word list"
            want_do = False
            argv = argv[1:]
            if not argv:
                continue
        if argv[0] == "for":
            if loop is not None:
                return None, "a `for` loop inside another `for` loop is not a read-only loop"
            if (len(argv) < 3 or not LOOP_NAME.fullmatch(argv[1]) or argv[2] != "in"
                    or not all(LOOP_WORD.fullmatch(w) for w in argv[3:])):
                return None, ("only `for x in WORDS; do ...; done` is a read-only loop: "
                              "a one-letter lowercase name, and words with no space, "
                              "quote, glob, `$`, `{`, `<(` or leading `=`")
            loop = (argv[1], argv[3:], [])
            want_do = True
            continue
        if argv == ["done"]:
            if loop is None:
                return None, "`done` closes no `for` loop"
            name, words, body = loop
            if any(c[0] == "cd" for c in body):
                return None, ("`cd` inside a `for` loop runs once per word but is "
                              "judged once -- move it before the loop")
            spent += sum(len(c) + 1 for c in body) * (len(words) + 1)
            if spent > MAX_LOOP_TOKENS:
                return None, (f"`for` loops expand to more than {MAX_LOOP_TOKENS} "
                              "tokens to judge")
            out.extend(body + [[substitute(t, name, w) for t in c]
                               for w in words for c in body])
            loop = None
            continue
        for tok in argv:
            for i, ch in enumerate(tok):
                if ch != "$":
                    continue
                m = VAR_REF.match(tok, i)
                if not m or loop is None or (m.group(1) or m.group(2)) != loop[0]:
                    return None, (f"`{tok}`: a command with a `for` loop may expand only "
                                  "the loop's own variable, as a plain $x or ${x}, "
                                  "inside that loop")
        (loop[2] if loop else out).append(argv)
    if want_do or loop is not None:
        return None, "a `for` loop with no `done`"
    return out, None


def presplit_segments(command: str) -> list[list[str]] | None:
    """The pre-TICKET-057 splitter: split on newlines, lex each line alone.

    Reached only for a command containing a backslash. A line ending in one
    does not lex ("No escaped character"), so a line continuation is refused
    rather than joined, and a newline inside a quoted string is refused
    rather than kept. Both are fail-closed, which is why this is the route.
    """
    out = []
    for line in command.split("\n"):
        if not line.strip():
            continue
        lex = shlex.shlex(line, posix=True, punctuation_chars=True)
        lex.whitespace_split = True
        try:
            out.extend(split_segments(list(lex)))
        except ValueError:
            return None
    return out


def lexed_segments(command: str) -> list[list[str]] | None:
    """The newline-aware splitter, for a command with no backslash in it.

    A newline is a punctuation char here rather than whitespace, so shlex
    emits it as its own token outside quotes and keeps it inside a quoted
    string. Splitting the raw string on newlines instead refuses every
    quoted multi-line command as "does not parse", which is the defect
    TICKET-057 opened on.

    `commenters` is off deliberately. shlex eats the newline that ends a
    comment, so with comments on, `echo hi # note<newline>sudo rm -rf /etc`
    lexes as one argv and the `sudo` rule never sees it.
    """
    lex = shlex.shlex(command, posix=True, punctuation_chars=PUNCTUATION)
    lex.whitespace = " \t\r"
    lex.commenters = ""
    lex.whitespace_split = True
    try:
        return split_segments(list(lex))
    except ValueError:
        return None


def segments(command: str) -> list[list[str]] | None:
    """Split a shell command into argv lists, one per segment. None if the
    string will not lex -- which is itself a reason to refuse.

    A command containing a backslash goes down `presplit_segments()`, which
    refuses more than it parses. This guard does not model shell backslash
    grammar: TICKET-057 hand-rolled that pre-pass three times and every
    pass was found allowing a command the old splitter blocked -- last an
    apostrophe inside double quotes, and a doubled backslash before a
    newline. Refusing what the old splitter cannot parse costs the line
    continuation and buys a grammar with no known escape. Do not add a
    backslash pre-pass.
    """
    if "\\" in command:
        return presplit_segments(command)
    return lexed_segments(command)


def flatten(argv: list[str]) -> list[list[str]]:
    """`sh -c '<cmd>'` hides a whole command inside one argument. Unwrap it so
    the rules below see what actually runs."""
    if not argv:
        return []
    name = os.path.basename(argv[0])
    if name in SHELLS and "-c" in argv:
        i = argv.index("-c")
        if i + 1 < len(argv):
            inner = segments(argv[i + 1])
            return [a for seg in (inner or []) for a in flatten(seg)] or [argv]
    return [argv]


def downloaded_paths(segs: list[list[str]]) -> set[str]:
    """Paths curl/wget wrote, so `curl -o /tmp/x u && bash /tmp/x` is caught."""
    paths = set()
    for argv in segs:
        if not argv or os.path.basename(argv[0]) not in {"curl", "wget"}:
            continue
        for flag in ("-o", "--output", "-O", "--output-document"):
            if flag in argv:
                i = argv.index(flag)
                if i + 1 < len(argv):
                    paths.add(argv[i + 1])
    return paths


def always_rules(segs: list[list[str]], raw: str) -> str | None:
    downloads = downloaded_paths(segs)
    piped_into_shell = re.search(r"\|\s*(sudo\s+)?[\w/]*(" + "|".join(SHELLS) + r")\b", raw)
    fetches = any(argv and os.path.basename(argv[0]) in {"curl", "wget"} for argv in segs)
    if fetches and piped_into_shell:
        return "piping a download straight into a shell"

    for argv in segs:
        if not argv:
            continue
        name = os.path.basename(argv[0])
        args = argv[1:]

        if name == "sudo" or name == "doas":
            return "sudo: agents do not get root"
        if name == "eval":
            return "eval: indirection the guard cannot inspect"
        if name in SHELLS and any(a in downloads for a in args):
            return "running a file that was just downloaded"

        if name == "rm":
            flags = [a for a in args if a.startswith("-")]
            recursive = any("r" in f.lstrip("-") or f in ("--recursive",) for f in flags)
            force = any("f" in f.lstrip("-") or f in ("--force",) for f in flags)
            targets = [a for a in args if not a.startswith("-")]
            if recursive and force and any(HOME_ISH.match(t) for t in targets):
                return "recursive delete of a root or home path"
            if any(re.search(r"bash_history|zsh_history", t) for t in targets):
                return "erasing shell history"

        if name == "git":
            sub = next((a for i, a in enumerate(args)
                        if not a.startswith("-") and (i == 0 or args[i - 1] != "-C")), None)
            rest = args
            if sub == "push":
                if any(f in rest for f in ("--force", "-f", "--force-with-lease")):
                    return "force push"
                if any(b in rest for b in ("main", "master")):
                    return "direct push to the default branch"
            if sub == "clean" and any("f" in a.lstrip("-") for a in rest if a.startswith("-")):
                return "git clean discards untracked work"
            if sub == "worktree" and "remove" in rest:
                return "worktrees are the dispatcher's to manage"

        if name == "mkfs" or name.startswith("mkfs."):
            return "filesystem format"
        if name == "dd" and any(a.startswith("of=/dev/") for a in args):
            return "raw write to a device"
        if name == "chmod" and "777" in args and any(HOME_ISH.match(a) for a in args):
            return "world-writable root or home"
        if name == "history" and "-c" in args:
            return "erasing shell history"

    if re.search(r">\s*/dev/(sd|nvme|disk)", raw):
        return "raw write to a device"
    if re.search(r":\(\)\s*\{.*\|.*&.*\}", raw):
        return "fork bomb"
    return None


READONLY_ALLOW_ENV = "PIPELINE_READONLY_ALLOW"


def readonly_prefixes() -> list[list[str]]:
    """A project's own read-only argv prefixes, from PIPELINE_READONLY_ALLOW.

    Fails closed to `[]`: unparseable JSON, a non-list, or an entry that is
    not a non-empty list of non-empty strings is dropped. An empty entry
    would match every argv (`argv[:0] == []` for any argv), so it is never
    kept rather than treated as a wildcard.
    """
    try:
        raw = json.loads(os.environ.get(READONLY_ALLOW_ENV, "[]"))
    except ValueError:
        return []
    if not isinstance(raw, list):
        return []
    return [p for p in raw if isinstance(p, list) and p
            and all(isinstance(a, str) and a for a in p)]


def within(path: str, root: str) -> bool:
    return path == root or path.startswith(root + os.sep)


def cd_places(cwd: str | None) -> set[str]:
    try:
        here = cwd if isinstance(cwd, str) and os.path.isabs(cwd) else os.getcwd()
        return {os.path.normpath(here), os.path.realpath(here)}
    except (OSError, ValueError):
        return set()


def cd_verdict(argv: list[str], places: set[str],
               worktree: str | None) -> tuple[str | None, set[str]]:
    """`(reason, places)` for one `cd`. `places` is the SET of directories the
    shell may be in: a `cd` can fail or be skipped (`||`, `&&`), so each
    approved `cd` adds its landing paths and removes nothing, and every target
    must land inside the worktree from every member.

    A target must land inside the worktree both logically (`normpath`, bash's
    default `cd -L`) and physically (`realpath`): physical alone passes
    `cd ./inner/../..` through an in-tree symlink, logical alone passes
    `cd ./up` through a symlink to outside. It must also be an existing
    directory, which stops zsh `CDABLE_VARS` reinterpreting a missing one.
    `cd ./packages && cd ./x` is refused on purpose: write one `cd` with the
    full path. Returns a reason, never raises -- an exception exits 1 and
    Claude Code then runs the command."""
    if len(argv) != 2 or not CD_TARGET.fullmatch(argv[1]):
        return ("`cd` takes one directory operand that is `.`, `..`, absolute, or "
                "starts with `./` or `../` -- no options, `-`, `~`, `$`, or a bare "
                "name that CDPATH may redirect", places)
    if not worktree or not os.path.isabs(worktree):
        return "`cd` is judged against PIPELINE_WORKTREE, which is not an absolute path", places
    if not places:
        return "`cd` cannot tell which directory this command starts in", places
    t = argv[1]
    roots = {os.path.normpath(worktree), os.path.realpath(worktree)}
    landed = set()
    for here in places:
        for p in (os.path.normpath(os.path.join(here, t)),
                  os.path.realpath(os.path.join(here, t))):
            if not any(within(p, root) for root in roots):
                return f"`cd {t}` leaves this stage's worktree {worktree}", places
            landed.add(p)
        if not os.path.isdir(os.path.realpath(os.path.join(here, t))):
            return f"`cd {t}` is not a directory from {here}", places
    return None, places | landed


def readonly_rules(segs: list[list[str]], raw: str, cwd: str | None = None) -> str | None:
    # a token-level scan, not a raw-string regex -- DEC-058 keeps this above
    # the allow-prefix loop below, so a project prefix cannot re-enable a
    # redirection. A raw regex cannot tell a real `>` from a quoted one; a
    # token can, because shlex has already stripped the quotes (TICKET-106).
    for argv in segs:
        if redirection(argv):
            return "shell redirection into a file"
    if "$(" in raw or "`" in raw:
        return "command substitution the guard cannot inspect"

    segs, why = loop_bodies(segs)
    if why:
        return why
    # verdict() ran flatten() and always_rules() on segments whose argv[0] was "do", so run both again on the bodies -- DEC-058: a project prefix never re-enables what always_rules() refuses (TICKET-152)
    segs = [a for seg in segs for a in flatten(seg)]
    why = always_rules(segs, raw)
    if why:
        return why

    allow = readonly_prefixes()
    places = None
    for argv in segs:
        if not argv:
            continue
        # above the prefix match, so `[readonly] allow` cannot widen `cd`
        if argv[0] == "cd":
            if places is None:
                places = cd_places(cwd)
            why, places = cd_verdict(argv, places, os.environ.get("PIPELINE_WORKTREE"))
            if why:
                return why
            continue
        # argv[0] is compared verbatim, not by basename, so a project entry
        # like "./pipeline/hooks/test_dangerous_commands.py" matches as written
        if any(argv[:len(p)] == p for p in allow):
            continue
        # `uv run` and `poetry run` are judged by the command they run, so
        # `uv run find . -delete` meets the rules bare `find` meets, and a
        # project prefix matches that command too (TICKET-153)
        inner, why = unwrap_run(argv)
        if why:
            return why
        if inner is not argv and any(inner[:len(p)] == p for p in allow):
            continue
        name = os.path.basename(inner[0])
        args = inner[1:]

        if name == "git":
            why = git_verdict(args)
            if why:
                return why
            continue

        # sed is off the allowlist by name -- TICKET-057 -- except one
        # allowlisted shape: `sed -n <line/range>p <file>...`. That is an
        # allowlist of a known-safe form, not a blocklist of writing flags
        # (invariant 4): sed_is_a_line_print() requires a full match against
        # SED_PRINT, so a script that continues past the `p` (a `;` or a
        # `w`) is refused, same as every other sed shape. The reason below
        # is spelled out because the generic one sends an agent to refile
        # the ticket.
        if name == "sed":
            if sed_is_a_line_print(args):
                continue
            return ("sed is not read-only: a sed script writes with `w`, "
                    "`s///w` and GNU `e` -- use head, tail or grep to read")
        if name == "find":
            if find_only_reads(args):
                continue
            return ("find: only tests and stdout actions are read-only -- "
                    "-delete, -exec, -ok and -fprint write or run a command; "
                    "use grep -r to search file contents")
        if name == "awk":
            if awk_only_reads(args):
                continue
            return ("awk: a read-only awk takes only -F and -v, and its program "
                    "holds no |, @, system or > -- write NR>1 as NR>=2")
        if name in ("npm", "pnpm", "yarn"):
            if runs_the_test_script(args):
                continue
            return (f"{name}: only a bare `{name} test` or `{name} run test` is "
                    "read-only -- another script is package.json text the guard "
                    "cannot judge, an option is npm config such as --script-shell, "
                    "which runs a command, and an argument after `--` reaches the "
                    "test tool unchecked")
        if name in OPTION_SPECS:
            why = options_verdict(name, args, OPTION_SPECS[name])
            if why:
                return why
            continue
        if name in READ_TOOLS:
            continue

        if name in GUARDED:
            if name in ("python", "python3"):
                if len(args) < 2 or args[0] != "-m" or args[1] not in PY_MODULES_OK:
                    return f"{name}: only `-m {'/'.join(sorted(PY_MODULES_OK))}` is allowed"
                why = options_verdict(f"{name} -m {args[1]}", args[2:], OPTION_SPECS[args[1]])
                if why:
                    return why
                continue
            if not args or args[0] not in GUARDED[name]:
                return f"{name} {args[0] if args else ''}: not an allowed subcommand"
            why = guarded_options(name, args[0], args[1:])
            if why:
                return why
            continue

        return f"`{name}` is not on the read-only allowlist"
    return None


def verdict(command: str, readonly: bool, cwd: str | None = None) -> str | None:
    segs = segments(command)
    if segs is None:
        if "\\" in command:
            return ("command does not parse as a shell command: it contains a "
                    "backslash, which this guard refuses rather than models -- "
                    "put the command on one line without one")
        return "command does not parse as a shell command"
    segs = [a for seg in segs for a in flatten(seg)]
    why = always_rules(segs, command)
    if why or not readonly:
        return why
    return readonly_rules(segs, command, cwd)


FILE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
PATH_KEYS = ("file_path", "notebook_path")
PATCH_PATH = re.compile(r"^\*\*\* (?:Add|Update|Delete) File: (.+)$")
PATCH_MOVE = re.compile(r"^\*\*\* Move to: (.+)$")


def resolve(path: str, base: str) -> str | None:
    """A path, resolved against `base` when it is relative. `None` for
    anything that will not resolve -- invariant 5: this reads hostile input."""
    if not path:
        return None
    try:
        full = path if os.path.isabs(path) else os.path.join(base, path)
        return os.path.realpath(full)
    except (OSError, ValueError):
        return None


def path_verdict(path: str, worktree: str, allowed: list[str]) -> str | None:
    """None if `path` resolves inside `worktree` or matches an entry of
    `allowed`; otherwise the reason it is blocked."""
    wt = resolve(worktree, os.getcwd())
    if wt is None:
        return f"PIPELINE_WORKTREE={worktree!r} does not resolve to a path"
    target = resolve(path, wt)
    if target is None:
        return f"{path!r} does not resolve to a path"
    if any(target == resolve(p, wt) for p in allowed):
        return None
    if within(target, wt):
        return None
    return f"{target} is outside this stage's worktree {wt}"


def file_verdict(tool_input: dict) -> str | None:
    wt = os.environ.get("PIPELINE_WORKTREE")
    if not wt:
        return None
    path = next((tool_input.get(k) for k in PATH_KEYS
                 if isinstance(tool_input.get(k), str)), None)
    if path is None:
        return "a file tool with no path the guard can read"
    allowed = [p for p in (os.environ.get("PIPELINE_TICKET"),
                            os.environ.get("PIPELINE_RESULT")) if p]
    return path_verdict(path, wt, allowed)


def patch_verdict(tool_input: dict) -> str | None:
    """Validate every path named by Codex's canonical `apply_patch` tool.

    Codex reports the patch as `tool_input.command`, not as a `file_path`.
    Unknown or pathless patch syntax fails closed: accepting a new patch
    grammar before the guard understands it would silently drop the boundary.
    """
    command = tool_input.get("command")
    if not isinstance(command, str):
        return "apply_patch has no command string the guard can read"
    paths = []
    for line in command.splitlines():
        match = PATCH_PATH.fullmatch(line) or PATCH_MOVE.fullmatch(line)
        if match:
            paths.append(match.group(1))
    if not command.startswith("*** Begin Patch") or not command.rstrip().endswith(
            "*** End Patch") or not paths:
        return "apply_patch does not use a recognised path-bearing patch format"
    wt = os.environ.get("PIPELINE_WORKTREE")
    if not wt:
        return None
    allowed = [p for p in (os.environ.get("PIPELINE_TICKET"),
                            os.environ.get("PIPELINE_RESULT")) if p]
    for path in paths:
        why = path_verdict(path, wt, allowed)
        if why:
            return why
    return None


def mcp_verdict(tool: str) -> str | None:
    """An MCP tool is named `mcp__<server>__<tool>`. The guard parses shell and
    cannot judge `mcp__github__create_pr`, so the rule is a per-server
    allowlist, default deny -- the same shape as the read-only rules."""
    parts = tool.split("__")
    if len(parts) < 3 or not parts[1]:
        return f"{tool} is not a recognisable MCP tool name"
    server = parts[1]
    allow = {s for s in os.environ.get("PIPELINE_MCP_ALLOW", "").split(",") if s}
    if server not in allow:
        return f"MCP server {server} is not declared for this stage"
    if os.environ.get("PIPELINE_READONLY") == "1":
        ro = {s for s in os.environ.get("PIPELINE_MCP_READONLY", "").split(",") if s}
        if server not in ro:
            return f"MCP server {server} is not marked readonly and this stage is read-only"
    return None


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except Exception:
        return 0  # never break the agent over a malformed event
    try:
        return decide(event)
    except BaseException as exc:  # an exit 1 runs the command, so fail closed
        print(f"Blocked by the pipeline guard: the guard failed on this call "
              f"({type(exc).__name__}).", file=sys.stderr)
        return 2


def decide(event) -> int:
    tool = str(event.get("tool_name") or "")
    tool_input = event.get("tool_input") or {}
    if tool == "apply_patch":
        label = "Patch"
        subject = tool_input.get("command", "")
        why = patch_verdict(tool_input)
    elif tool in FILE_TOOLS:
        label = "Path"
        subject = next((tool_input.get(k) for k in PATH_KEYS
                         if isinstance(tool_input.get(k), str)), "")
        why = file_verdict(tool_input)
    elif tool == "Bash":
        label = "Command"
        subject = tool_input.get("command", "")
        cwd = event.get("cwd")
        why = verdict(subject, os.environ.get("PIPELINE_READONLY") == "1",
                      cwd if isinstance(cwd, str) else None)
    elif tool.startswith("mcp__"):
        label, subject = "Tool", tool
        why = mcp_verdict(tool)
    else:
        return 0
    if why is None:
        return 0
    stage = os.environ.get("PIPELINE_STAGE", "this stage")
    print(f"Blocked by the pipeline guard ({stage}): {why}.\n"
          f"{label}: {subject}\n"
          f"If your stage genuinely needs this, stop and report it in the ticket "
          f"rather than working around the guard.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())

//! typeset: lays a text document out on fixed-size pages.
mod blocks;
mod config;
mod paginate;

use std::io::{Read, Write};

use blocks::{parse, render, DocError, Kind};
use config as c;
use paginate::paginate;

struct Options {
    width: usize,
    height: usize,
    orphans: usize,
    widows: usize,
    justify: bool,
}

fn parse_options(argv: &[String]) -> Result<Options, String> {
    let mut o = Options { width: c::WIDTH as usize, height: c::HEIGHT as usize, orphans: c::ORPHANS as usize, widows: c::WIDOWS as usize, justify: false };
    let mut i = 0;
    while i < argv.len() {
        let a = argv[i].as_str();
        if a == "--justify" && c::JUSTIFY_OPT {
            o.justify = true;
            i += 1;
            continue;
        }
        let (lo, hi) = match a {
            "--width" => (10, 120),
            "--height" => (4, 80),
            "--orphans" | "--widows" => (1, 4),
            _ => return Err(format!("unknown option '{}'", a)),
        };
        let v = argv.get(i + 1).ok_or_else(|| format!("missing value for {}", a))?;
        let numeric = !v.is_empty() && v.len() <= 3 && v.chars().all(|ch| ch.is_ascii_digit());
        let n: usize = if numeric { v.parse().unwrap_or(0) } else { 0 };
        if !numeric || n < lo || n > hi {
            return Err(format!("bad value '{}' for {}", v, a));
        }
        match a {
            "--width" => o.width = n,
            "--height" => o.height = n,
            "--orphans" => o.orphans = n,
            _ => o.widows = n,
        }
        i += 2;
    }
    Ok(o)
}

fn layout(opts: &Options, src: &str) -> Result<Vec<Vec<String>>, DocError> {
    let mut doc = parse(src)?;
    for b in doc.iter_mut() {
        b.lines = render(b, opts.width, opts.justify);
        if b.kind == Kind::Figure && b.height > opts.height {
            return Err(DocError(format!("line {}: figure {} is taller than a page", b.line, b.name)));
        }
    }
    Ok(paginate(&doc, opts.height, opts.orphans, opts.widows))
}

fn run(argv: &[String]) -> i32 {
    let opts = match parse_options(argv) {
        Ok(o) => o,
        Err(e) => {
            println!("error: {}", e);
            return 1;
        }
    };
    let mut raw = Vec::new();
    let _ = std::io::stdin().read_to_end(&mut raw);
    let src = String::from_utf8_lossy(&raw).into_owned();
    let pages = match layout(&opts, &src) {
        Ok(p) => p,
        Err(DocError(msg)) => {
            println!("error: {}", msg);
            return 1;
        }
    };
    let mut out = String::new();
    for (n, page) in pages.iter().enumerate() {
        if n > 0 {
            out.push('\n');
        }
        for l in page {
            out.push_str(l.trim_end());
            out.push('\n');
        }
        out.push_str(&format!("-- {}/{} --\n", n + 1, pages.len()));
    }
    let _ = std::io::stdout().write_all(out.as_bytes());
    0
}

fn main() {
    let argv: Vec<String> = std::env::args().skip(1).collect();
    std::process::exit(run(&argv));
}

//! Pagination: placing blocks on pages of a fixed number of lines.
use crate::blocks::{Block, Kind};
use crate::config as c;

/// Lines the block after position `i` must be able to put on the same page as a heading at `i` (None: no requirement).
fn next_min(blocks: &[Block], i: usize, orphans: usize) -> Option<usize> {
    let n = blocks.get(i + 1)?;
    match n.kind {
        Kind::Break => None,
        Kind::Figure => Some(n.lines.len()),
        Kind::Heading => {
            let own = n.lines.len();
            Some(own + next_min(blocks, i + 1, orphans).map_or(0, |rest| 1 + rest))
        }
        _ => Some(n.lines.len().min(orphans)),
    }
}

struct Pager {
    pages: Vec<Vec<String>>,
    prev: Option<Kind>, // kind of the last block placed on the current page
}

impl Pager {
    fn page(&mut self) -> &mut Vec<String> {
        self.pages.last_mut().unwrap()
    }

    fn used(&self) -> usize {
        self.pages.last().unwrap().len()
    }

    fn new_page(&mut self) {
        self.pages.push(Vec::new());
        self.prev = None;
    }

    /// Blank lines needed before placing `b` on the current page.
    fn sep_for(&self, b: &Block) -> usize {
        if self.used() == 0 {
            0
        } else if b.kind == Kind::Item && b.joined && self.prev == Some(Kind::Item) {
            0
        } else {
            1
        }
    }

    fn put(&mut self, sep: usize, lines: &[String]) {
        let page = self.page();
        for _ in 0..sep {
            page.push(String::new());
        }
        page.extend(lines.iter().cloned());
    }
}

pub fn paginate(blocks: &[Block], height: usize, orphans: usize, widows: usize) -> Vec<Vec<String>> {
    let mut pg = Pager { pages: vec![Vec::new()], prev: None };
    for (i, b) in blocks.iter().enumerate() {
        if b.kind == Kind::Break {
            if pg.used() > 0 {
                pg.new_page();
            }
            continue;
        }
        let mut lines: Vec<String> = b.lines.clone();
        if b.kind == Kind::Heading || b.kind == Kind::Figure {
            let mut need = lines.len();
            if b.kind == Kind::Heading && c::KEEP {
                if let Some(nm) = next_min(blocks, i, orphans) {
                    need += 1 + nm;
                }
            }
            let sep = pg.sep_for(b);
            if pg.used() > 0 && need > height.saturating_sub(pg.used() + sep) {
                pg.new_page();
            }
            let sep = pg.sep_for(b);
            pg.put(sep, &lines);
            pg.prev = Some(b.kind);
            continue;
        }
        loop {
            let sep = pg.sep_for(b);
            let remaining = height as i64 - pg.used() as i64 - sep as i64;
            if lines.len() as i64 <= remaining {
                pg.put(sep, &lines);
                pg.prev = Some(b.kind);
                break;
            }
            let top = remaining.min(lines.len() as i64 - 1);
            let split = (1..=top.max(0) as usize).rev().find(|&k| k >= orphans && lines.len() - k >= widows);
            if let Some(k) = split {
                pg.put(sep, &lines[..k]);
                lines.drain(..k);
            } else if pg.used() == 0 {
                // nothing satisfies the rules even on an empty page: fill it
                let take = height.min(lines.len());
                pg.put(0, &lines[..take]);
                lines.drain(..take);
            }
            pg.new_page();
        }
    }
    if pg.pages.len() > 1 && pg.used() == 0 {
        pg.pages.pop();
    }
    pg.pages
}

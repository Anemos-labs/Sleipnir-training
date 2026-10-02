//! Reading the document into blocks and wrapping their text into lines.
use crate::config as c;

pub struct DocError(pub String);

#[derive(Clone, Copy, PartialEq)]
pub enum Kind {
    Para,
    Quote,
    Item,
    Heading,
    Figure,
    Break,
}

pub struct Block {
    pub kind: Kind,
    pub line: usize,
    pub text: String,
    pub level: usize,
    pub name: String,
    pub height: usize,
    pub joined: bool, // an item directly after (a line of) another item
    pub lines: Vec<String>,
}

impl Block {
    fn new(kind: Kind, line: usize) -> Block {
        Block { kind, line, text: String::new(), level: 0, name: String::new(), height: 0, joined: false, lines: Vec::new() }
    }
}

/// `#`, `##` or `###`, then nothing or a space and the text.
fn heading(line: &str) -> Option<(usize, &str)> {
    let level = line.chars().take_while(|&ch| ch == '#').count();
    let rest = &line[level..];
    if (1..=3).contains(&level) && (rest.is_empty() || rest.starts_with(' ')) {
        Some((level, rest))
    } else {
        None
    }
}

/// `@figure NAME HEIGHT`: names of letters, digits, `_`, `-`; a height of one or two digits; one or more spaces between the parts.
fn figure(line: &str) -> Option<(String, usize)> {
    let rest = line.strip_prefix("@figure")?;
    let after_gap = rest.trim_start_matches(' ');
    if after_gap.len() == rest.len() {
        return None;
    }
    let name: String = after_gap.chars().take_while(|ch| ch.is_ascii_alphanumeric() || *ch == '_' || *ch == '-').collect();
    if name.is_empty() {
        return None;
    }
    let tail = &after_gap[name.len()..];
    let digits = tail.trim_start_matches(' ');
    if digits.len() == tail.len() || digits.is_empty() || digits.len() > 2 || !digits.chars().all(|ch| ch.is_ascii_digit()) {
        return None;
    }
    Some((name, digits.parse().ok()?))
}

pub fn parse(src: &str) -> Result<Vec<Block>, DocError> {
    let mut blocks: Vec<Block> = Vec::new();
    let mut cur: Option<usize> = None; // index of the open paragraph, quote or item
    let mut last_item_line = 0usize; // line number of the last line that belonged to an item (0: none yet)
    let bullet = format!("{} ", c::BULLET);
    for (idx, raw) in src.split('\n').enumerate() {
        let n = idx + 1;
        let line = raw.trim_end();
        if line.trim().is_empty() {
            cur = None;
            continue;
        }
        if line == "@break" {
            blocks.push(Block::new(Kind::Break, n));
            cur = None;
        } else if line.starts_with("@figure") {
            match figure(line) {
                Some((name, h)) if h >= 1 => {
                    let mut b = Block::new(Kind::Figure, n);
                    b.name = name;
                    b.height = h;
                    blocks.push(b);
                }
                _ => return Err(DocError(format!("line {}: bad figure", n))),
            }
            cur = None;
        } else if let Some((level, rest)) = heading(line) {
            let text = rest.trim();
            if text.is_empty() {
                return Err(DocError(format!("line {}: empty heading", n)));
            }
            let mut b = Block::new(Kind::Heading, n);
            b.text = text.to_string();
            b.level = level;
            blocks.push(b);
            cur = None;
        } else if let Some(body) = line.strip_prefix('>') {
            let body = body.strip_prefix(' ').unwrap_or(body).trim();
            match cur {
                Some(i) if blocks[i].kind == Kind::Quote => {
                    blocks[i].text.push(' ');
                    blocks[i].text.push_str(body);
                }
                _ => {
                    let mut b = Block::new(Kind::Quote, n);
                    b.text = body.to_string();
                    blocks.push(b);
                    cur = Some(blocks.len() - 1);
                }
            }
        } else if line.starts_with(&bullet) {
            let mut b = Block::new(Kind::Item, n);
            b.text = line[2..].trim().to_string();
            b.joined = last_item_line != 0 && last_item_line == n - 1;
            blocks.push(b);
            cur = Some(blocks.len() - 1);
            last_item_line = n;
        } else if cur.map_or(false, |i| blocks[i].kind == Kind::Item) && line.starts_with("  ") {
            let i = cur.unwrap();
            blocks[i].text.push(' ');
            blocks[i].text.push_str(line.trim());
            last_item_line = n;
        } else if cur.map_or(false, |i| blocks[i].kind == Kind::Para) {
            let i = cur.unwrap();
            blocks[i].text.push(' ');
            blocks[i].text.push_str(line.trim());
        } else {
            let mut b = Block::new(Kind::Para, n);
            b.text = line.trim().to_string();
            blocks.push(b);
            cur = Some(blocks.len() - 1);
        }
    }
    Ok(blocks)
}

/// Greedy wrapping on single spaces; a word longer than the width is cut into pieces of `width` characters (or kept whole).
pub fn wrap(text: &str, width: usize) -> Vec<String> {
    let mut lines: Vec<String> = Vec::new();
    let mut cur = String::new();
    for w in text.split_whitespace() {
        let mut word: Vec<char> = w.chars().collect();
        if c::LONG_WORD == "cut" {
            while word.len() > width {
                if !cur.is_empty() {
                    lines.push(std::mem::take(&mut cur));
                }
                lines.push(word[..width].iter().collect());
                word = word[width..].to_vec();
            }
        }
        let word: String = word.into_iter().collect();
        if cur.is_empty() {
            cur = word;
        } else if cur.chars().count() + 1 + word.chars().count() <= width {
            cur.push(' ');
            cur.push_str(&word);
        } else {
            lines.push(std::mem::take(&mut cur));
            cur = word;
        }
    }
    if !cur.is_empty() {
        lines.push(cur);
    }
    if lines.is_empty() {
        lines.push(String::new());
    }
    lines
}

/// Pad the gaps of a line to `width`, giving the extra spaces to the leftmost gaps first.
pub fn justify(line: &str, width: usize) -> String {
    let words: Vec<&str> = line.split(' ').collect();
    let len = line.chars().count();
    if words.len() < 2 || len >= width {
        return line.to_string();
    }
    let gaps = words.len() - 1;
    let base = (width - len) / gaps;
    let more = (width - len) % gaps;
    let mut out = words[0].to_string();
    for (i, w) in words[1..].iter().enumerate() {
        out.push_str(&" ".repeat(1 + base + usize::from(i < more)));
        out.push_str(w);
    }
    out
}

fn body_lines(text: &str, width: usize, do_justify: bool) -> Vec<String> {
    let mut lines = wrap(text, width);
    if do_justify {
        let last = lines.len() - 1;
        for l in lines[..last].iter_mut() {
            *l = justify(l, width);
        }
    }
    lines
}

pub fn render(block: &Block, width: usize, do_justify: bool) -> Vec<String> {
    match block.kind {
        Kind::Heading => {
            let text = if block.level == 1 && c::UPPER_H1 { block.text.to_ascii_uppercase() } else { block.text.clone() };
            let mut lines = wrap(&text, width);
            let ch = [c::UL1, c::UL2, c::UL3][block.level - 1];
            if !ch.is_empty() {
                let longest = lines.iter().map(|l| l.chars().count()).max().unwrap_or(0);
                lines.push(ch.repeat(longest));
            }
            lines
        }
        Kind::Figure => {
            let mut lines = vec![format!("[figure {}]", block.name)];
            lines.extend(std::iter::repeat("[ ]".to_string()).take(block.height - 1));
            lines
        }
        Kind::Quote => {
            let w = width.saturating_sub(c::QUOTE.chars().count()).max(1);
            body_lines(&block.text, w, do_justify).into_iter().map(|l| format!("{}{}", c::QUOTE, l)).collect()
        }
        Kind::Item => {
            let lines = body_lines(&block.text, width.saturating_sub(2).max(1), do_justify);
            let mut out = vec![format!("{}{}", c::ITEM_OUT, lines[0])];
            out.extend(lines[1..].iter().map(|l| format!("  {}", l)));
            out
        }
        _ => body_lines(&block.text, width, do_justify),
    }
}

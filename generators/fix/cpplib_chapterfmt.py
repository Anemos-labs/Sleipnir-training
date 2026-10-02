"""Podcast chapter list text format (c++): time parsing with fractions, titles with optional URLs, strict ordering, formatting, durations and shifting; bugs injected into the library."""
from fx import Lib, dd

from generators.fix import _lang3

README1 = dd(r'''
    # chapterfmt

    Reads and writes the chapter lists of a podcast episode. A list is plain text, one chapter per line:

        # intro music, then the show
        0:00 Cold open
        00:45.5 Welcome | https://example.org/hello
        1:02:03.250 Interview: the long one
        75:00 A | in the title

        struct Chapter { long start_ms; std::string title; std::string url; };   // an empty url means "no link"

    ## Parsing: `std::vector<Chapter> parse(const std::string &text)`

    * Lines end at `\n`; a `\r` right before it is ignored. Line numbers start at 1 and count every line, including blank and comment lines.
    * A line that is empty or only spaces and tabs, or whose first non-blank character is `#`, is skipped.
    * Any other line is `TIME`, one or more spaces or tabs, then the rest of the line (the *text*), with leading and trailing blanks removed.
    * **TIME** is `MM:SS` or `H:MM:SS`, optionally followed by `.` and **one to three** digits of fraction (`.5` is 500 ms, `.25` is 250 ms, `.007` is 7 ms).
      * two-field form `M...M:SS`: minutes are 1 to 6 digits (may exceed 59: `75:00` is one hour fifteen);
      * three-field form `H...:MM:SS`: hours are 1 to 3 digits, minutes exactly 2 digits and below 60;
      * seconds are exactly 2 digits and below 60.
      Anything else is a *bad time*.
    * The text must not be empty (*empty title*) and, as a title, must not be longer than 200 bytes (*title too long*).
    * **Link**: the text is split at its **last** occurrence of the 3-character separator ` | ` (space, pipe, space). If what follows it starts with `http://` or `https://`
      and contains no space or tab, it is the `url` and what precedes it (trimmed again; it must not be empty) is the title. In every other case the whole text is the
      title, pipes included (`A | in the title`).
    * The first chapter must start at 0 (*first chapter must start at 0*) and each start must be **strictly greater** than the previous one (*not increasing*).
    * A line that holds only a valid TIME and no text is an *empty title*. The checks on a line are made in this order: bad time, empty title, title too long, then (for the first / later chapters) the ordering rule.
    * Errors throw `ParseError`, a `std::runtime_error` with `int line() const` and `const std::string &message() const` (`"bad time"`, `"empty title"`, `"title too long"`,
      `"first chapter must start at 0"`, `"not increasing"`); `what()` is `"line N: message"`. A text without chapters gives an empty list.

    ## Formatting: `std::string format(const std::vector<Chapter> &c, bool short_times = false)`

    One line per chapter, each ending in `\n`: `TIME TITLE`, or `TIME TITLE | URL` when there is a url.

    * long times (default): `HH:MM:SS.mmm` (hours at least 2 digits, no upper limit);
    * short times: `M:SS` below an hour and `H:MM:SS` from one hour on, and a `.mmm` fraction (always 3 digits) only when the start is not a whole second.

    `std::invalid_argument` is thrown for a chapter whose title is empty or contains a newline, or whose url is not empty and does not start with `http://` or `https://` or contains a
    space, tab or newline, or whose `start_ms` is negative. Formatting then parsing gives the same chapters back for every list that `parse` could have produced.

    ## Queries

    * `std::vector<long> durations(const std::vector<Chapter> &c, long total_ms)`: the length of every chapter: the next start minus its own start, and for the last one `total_ms` minus its start.
      `std::invalid_argument` when `total_ms` is not greater than the last start. An empty list gives an empty result (whatever `total_ms`).
    * `int chapter_at(const std::vector<Chapter> &c, long ms)`: the index of the last chapter that starts at or before `ms`; -1 when there is none (`ms` before the first start, or an empty list).
    * `std::vector<Chapter> shift(const std::vector<Chapter> &c, long offset_ms)`: all starts move by `offset_ms`.
      * `offset_ms > 0`: the list would no longer start at 0, so a chapter `{0, "Intro", ""}` is put in front;
      * `offset_ms < 0`: chapters that would start before 0 are dropped, unless no remaining chapter starts at exactly 0 - then the last dropped chapter is kept instead, with its start set to 0, because it
        covers the new beginning (so if every chapter would start before 0, the last one is kept at 0);
      * `offset_ms == 0`, or an empty list: the list is returned unchanged.
''')

F2 = dd(r'''
    #ifndef CHAPTERFMT_HPP
    #define CHAPTERFMT_HPP

    #include <stdexcept>
    #include <string>
    #include <vector>

    namespace chapterfmt {

    struct Chapter {
        long start_ms;
        std::string title;
        std::string url;
    };

    class ParseError : public std::runtime_error {
    public:
        ParseError(int line, const std::string &message);
        int line() const { return line_; }
        const std::string &message() const { return message_; }

    private:
        int line_;
        std::string message_;
    };

    std::vector<Chapter> parse(const std::string &text);
    std::string format(const std::vector<Chapter> &c, bool short_times = false);
    std::vector<long> durations(const std::vector<Chapter> &c, long total_ms);
    int chapter_at(const std::vector<Chapter> &c, long ms);
    std::vector<Chapter> shift(const std::vector<Chapter> &c, long offset_ms);

    }  // namespace chapterfmt

    #endif
''')

F3 = dd(r'''
    #include "chapterfmt.hpp"

    #include <cstdio>

    namespace chapterfmt {

    ParseError::ParseError(int line, const std::string &message)
        : std::runtime_error("line " + std::to_string(line) + ": " + message), line_(line), message_(message) {}

    static bool is_blank(char c) { return c == ' ' || c == '\t'; }

    static bool is_digit(char c) { return c >= '0' && c <= '9'; }

    static std::string trim(const std::string &s) {
        size_t a = 0, b = s.size();
        while (a < b && is_blank(s[a])) a++;
        while (b > a && is_blank(s[b - 1])) b--;
        return s.substr(a, b - a);
    }

    /* digits at s[pos..]: returns the count, value in *v (counts above 9 digits are not needed) */
    static size_t digits(const std::string &s, size_t pos, long *v) {
        size_t n = 0;
        *v = 0;
        while (pos + n < s.size() && is_digit(s[pos + n])) {
            if (n < 9) *v = *v * 10 + (s[pos + n] - '0');
            n++;
        }
        return n;
    }

    /* parse TIME in full; false when malformed */
    static bool parse_time(const std::string &t, long *ms) {
        long a, b, c = 0;
        size_t pos = 0, na, nb, nc = 0;
        na = digits(t, pos, &a);
        if (na == 0 || pos + na >= t.size() || t[pos + na] != ':') return false;
        pos += na + 1;
        nb = digits(t, pos, &b);
        if (nb == 0) return false;
        pos += nb;
        bool three = pos < t.size() && t[pos] == ':';
        long total_s;
        if (three) {
            pos++;
            nc = digits(t, pos, &c);
            if (nc != 2 || c > 59) return false;
            if (na > 3 || nb != 2 || b > 59) return false;
            pos += nc;
            total_s = a * 3600 + b * 60 + c;
        } else {
            if (na > 6 || nb != 2 || b > 59) return false;
            total_s = a * 60 + b;
        }
        long frac = 0;
        if (pos < t.size()) {
            if (t[pos] != '.') return false;
            pos++;
            size_t nf = 0;
            long scale = 100;
            while (pos < t.size() && is_digit(t[pos])) {
                frac += (t[pos] - '0') * scale;
                scale /= 10;
                nf++;
                pos++;
            }
            if (nf < 1 || nf > 3 || pos != t.size()) return false;
        }
        *ms = total_s * 1000 + frac;
        return true;
    }

    static bool has_blank(const std::string &s) {
        for (char c : s) {
            if (is_blank(c)) return true;
        }
        return false;
    }

    static bool is_url(const std::string &s) {
        return s.compare(0, 7, "http://") == 0 || s.compare(0, 8, "https://") == 0;
    }

    std::vector<Chapter> parse(const std::string &text) {
        std::vector<Chapter> out;
        size_t pos = 0;
        int line = 0;
        while (pos <= text.size()) {
            size_t nl = text.find('\n', pos);
            std::string ln = text.substr(pos, nl == std::string::npos ? std::string::npos : nl - pos);
            pos = nl == std::string::npos ? text.size() + 1 : nl + 1;
            line++;
            if (!ln.empty() && ln.back() == '\r') ln.pop_back();
            std::string body = trim(ln);
            if (body.empty() || body[0] == '#') continue;
            size_t sp = 0;
            while (sp < body.size() && !is_blank(body[sp])) sp++;
            long ms;
            if (!parse_time(body.substr(0, sp), &ms)) throw ParseError(line, "bad time");
            std::string rest = trim(body.substr(sp));
            if (rest.empty()) throw ParseError(line, "empty title");
            Chapter c{ms, rest, ""};
            size_t bar = rest.rfind(" | ");
            if (bar != std::string::npos) {
                std::string tail = rest.substr(bar + 3);
                std::string head = trim(rest.substr(0, bar));
                if (is_url(tail) && !has_blank(tail) && !head.empty()) {
                    c.title = head;
                    c.url = tail;
                }
            }
            if (c.title.size() > 200) throw ParseError(line, "title too long");
            if (out.empty()) {
                if (ms != 0) throw ParseError(line, "first chapter must start at 0");
            } else if (ms <= out.back().start_ms) {
                throw ParseError(line, "not increasing");
            }
            out.push_back(c);
        }
        return out;
    }

    static std::string two(long v) {
        char buf[16];
        std::snprintf(buf, sizeof buf, "%02ld", v);
        return buf;
    }

    static std::string time_text(long ms, bool short_times) {
        long total_s = ms / 1000, frac = ms % 1000;
        long h = total_s / 3600, m = (total_s / 60) % 60, s = total_s % 60;
        std::string t;
        if (short_times) {
            if (h > 0) t = std::to_string(h) + ":" + two(m) + ":" + two(s);
            else t = std::to_string(m) + ":" + two(s);
            if (frac != 0) {
                char buf[8];
                std::snprintf(buf, sizeof buf, ".%03ld", frac);
                t += buf;
            }
        } else {
            char buf[16];
            std::snprintf(buf, sizeof buf, ".%03ld", frac);
            t = two(h) + ":" + two(m) + ":" + two(s) + buf;
        }
        return t;
    }

    std::string format(const std::vector<Chapter> &c, bool short_times) {
        std::string out;
        for (const Chapter &ch : c) {
            if (ch.start_ms < 0 || ch.title.empty() || ch.title.find('\n') != std::string::npos) throw std::invalid_argument("bad chapter");
            if (!ch.url.empty()) {
                if (!is_url(ch.url) || has_blank(ch.url) || ch.url.find('\n') != std::string::npos) throw std::invalid_argument("bad url");
            }
            out += time_text(ch.start_ms, short_times) + " " + ch.title;
            if (!ch.url.empty()) out += " | " + ch.url;
            out += "\n";
        }
        return out;
    }

    std::vector<long> durations(const std::vector<Chapter> &c, long total_ms) {
        std::vector<long> out;
        if (c.empty()) return out;
        if (total_ms <= c.back().start_ms) throw std::invalid_argument("total is not after the last chapter");
        for (size_t i = 0; i < c.size(); i++) {
            long end = i + 1 < c.size() ? c[i + 1].start_ms : total_ms;
            out.push_back(end - c[i].start_ms);
        }
        return out;
    }

    int chapter_at(const std::vector<Chapter> &c, long ms) {
        int found = -1;
        for (size_t i = 0; i < c.size(); i++) {
            if (c[i].start_ms <= ms) found = static_cast<int>(i);
            else break;
        }
        return found;
    }

    std::vector<Chapter> shift(const std::vector<Chapter> &c, long offset_ms) {
        std::vector<Chapter> out;
        if (c.empty() || offset_ms == 0) return c;
        if (offset_ms > 0) {
            out.push_back(Chapter{0, "Intro", ""});
            for (const Chapter &ch : c) out.push_back(Chapter{ch.start_ms + offset_ms, ch.title, ch.url});
            return out;
        }
        size_t first = 0;
        while (first + 1 < c.size() && c[first + 1].start_ms + offset_ms <= 0) first++;
        for (size_t i = first; i < c.size(); i++) {
            long s = c[i].start_ms + offset_ms;
            out.push_back(Chapter{s < 0 ? 0 : s, c[i].title, c[i].url});
        }
        return out;
    }

    }  // namespace chapterfmt
''')

V4 = dd(r'''
    #include "chapterfmt.hpp"
    #include "harness.hpp"

    using namespace chapterfmt;

    int main() {
        h_init();
        std::vector<Chapter> c = parse("0:00 Cold open\n1:30.5 Welcome | https://example.org/hi\n");
        CHECK_EQ(c.size(), 2u);
        CHECK_EQ(c[1].start_ms, 90500L);
        CHECK_EQ(c[1].title, std::string("Welcome"));
        CHECK_EQ(c[1].url, std::string("https://example.org/hi"));
        CHECK_EQ(format(c), std::string("00:00:00.000 Cold open\n00:01:30.500 Welcome | https://example.org/hi\n"));
        return h_report();
    }
''')

H5 = dd(r'''
    #include <string>
    #include <vector>

    #include "chapterfmt.hpp"
    #include "harness.hpp"

    using namespace chapterfmt;

    struct RawCh { long ms; const char *title; const char *url; };

    struct ParseCase { const char *text; int err_line; const char *err_msg; const char *dump; int count; };
    struct FormatCase { const RawCh *list; int n; bool short_times; const char *text; };
    struct ShiftCase { const RawCh *list; int n; long offset; const RawCh *result; int rn; };
    struct DurCase { const RawCh *list; int n; long total; int invalid; long result[8]; };
    struct AtCase { const RawCh *list; int n; long ms; int index; };
    struct InvCase { const RawCh *list; int n; };

    static const RawCh LIST0[] = {{0, "Intro", ""}, {61000, "Main", "https://x.org/a"}, {3723500, "Outro", ""}};
    static const RawCh LIST1[] = {{0, "Only", ""}};
    static const RawCh LIST2[] = {{0, "A", ""}, {999, "B", ""}, {1000, "C", ""}, {59999, "D", ""}, {60000, "E", ""}, {3599999, "F", ""}, {3600000, "G", ""}, {360000000, "H", "http://a.b/c"}};
    static const RawCh LIST3[] = {{0, "A", ""}, {1500, "B", ""}, {4000000, "C", ""}};
    static const RawCh LIST4[] = {{0, "Start", ""}, {5000, "Mid", ""}, {10000, "End", ""}};
    static const RawCh LIST5[] = {{0, "A | b", ""}, {100, "c", "https://d"}};
    static const RawCh LIST6[] = {{0, "A", ""}, {10, "B", ""}, {20, "C", ""}, {30, "D", ""}};
    static const RawCh LIST7[] = {{0, "A", ""}, {7200000, "Two hours", "https://example.org/2h"}};
    static const RawCh LIST8[] = {{0, "", ""}};
    static const RawCh LIST9[] = {{0, "Intro", ""}, {1, "Intro", ""}, {61001, "Main", "https://x.org/a"}, {3723501, "Outro", ""}};
    static const RawCh LIST10[] = {{0, "Intro", ""}, {1000, "Intro", ""}, {62000, "Main", "https://x.org/a"}, {3724500, "Outro", ""}};
    static const RawCh LIST11[] = {{0, "Intro", ""}, {60999, "Main", "https://x.org/a"}, {3723499, "Outro", ""}};
    static const RawCh LIST12[] = {{0, "Intro", ""}, {60000, "Main", "https://x.org/a"}, {3722500, "Outro", ""}};
    static const RawCh LIST13[] = {{0, "Intro", ""}, {56000, "Main", "https://x.org/a"}, {3718500, "Outro", ""}};
    static const RawCh LIST14[] = {{0, "Intro", ""}, {55999, "Main", "https://x.org/a"}, {3718499, "Outro", ""}};
    static const RawCh LIST15[] = {{0, "Intro", ""}, {56001, "Main", "https://x.org/a"}, {3718501, "Outro", ""}};
    static const RawCh LIST16[] = {{0, "Intro", ""}, {51000, "Main", "https://x.org/a"}, {3713500, "Outro", ""}};
    static const RawCh LIST17[] = {{0, "Intro", ""}, {50999, "Main", "https://x.org/a"}, {3713499, "Outro", ""}};
    static const RawCh LIST18[] = {{0, "Intro", ""}, {41000, "Main", "https://x.org/a"}, {3703500, "Outro", ""}};
    static const RawCh LIST19[] = {{0, "Outro", ""}};
    static const RawCh LIST20[] = {{0, "Intro", ""}, {500000, "Intro", ""}, {561000, "Main", "https://x.org/a"}, {4223500, "Outro", ""}};
    static const RawCh LIST21[] = {{0, "Intro", ""}, {1, "Only", ""}};
    static const RawCh LIST22[] = {{0, "Intro", ""}, {1000, "Only", ""}};
    static const RawCh LIST23[] = {{0, "Intro", ""}, {500000, "Only", ""}};
    static const RawCh LIST24[] = {{0, "Intro", ""}, {1, "A", ""}, {1000, "B", ""}, {1001, "C", ""}, {60000, "D", ""}, {60001, "E", ""}, {3600000, "F", ""}, {3600001, "G", ""}, {360000001, "H", "http://a.b/c"}};
    static const RawCh LIST25[] = {{0, "Intro", ""}, {1000, "A", ""}, {1999, "B", ""}, {2000, "C", ""}, {60999, "D", ""}, {61000, "E", ""}, {3600999, "F", ""}, {3601000, "G", ""}, {360001000, "H", "http://a.b/c"}};
    static const RawCh LIST26[] = {{0, "A", ""}, {998, "B", ""}, {999, "C", ""}, {59998, "D", ""}, {59999, "E", ""}, {3599998, "F", ""}, {3599999, "G", ""}, {359999999, "H", "http://a.b/c"}};
    static const RawCh LIST27[] = {{0, "C", ""}, {58999, "D", ""}, {59000, "E", ""}, {3598999, "F", ""}, {3599000, "G", ""}, {359999000, "H", "http://a.b/c"}};
    static const RawCh LIST28[] = {{0, "C", ""}, {54999, "D", ""}, {55000, "E", ""}, {3594999, "F", ""}, {3595000, "G", ""}, {359995000, "H", "http://a.b/c"}};
    static const RawCh LIST29[] = {{0, "C", ""}, {54998, "D", ""}, {54999, "E", ""}, {3594998, "F", ""}, {3594999, "G", ""}, {359994999, "H", "http://a.b/c"}};
    static const RawCh LIST30[] = {{0, "C", ""}, {55000, "D", ""}, {55001, "E", ""}, {3595000, "F", ""}, {3595001, "G", ""}, {359995001, "H", "http://a.b/c"}};
    static const RawCh LIST31[] = {{0, "C", ""}, {49999, "D", ""}, {50000, "E", ""}, {3589999, "F", ""}, {3590000, "G", ""}, {359990000, "H", "http://a.b/c"}};
    static const RawCh LIST32[] = {{0, "C", ""}, {49998, "D", ""}, {49999, "E", ""}, {3589998, "F", ""}, {3589999, "G", ""}, {359989999, "H", "http://a.b/c"}};
    static const RawCh LIST33[] = {{0, "C", ""}, {39999, "D", ""}, {40000, "E", ""}, {3579999, "F", ""}, {3580000, "G", ""}, {359980000, "H", "http://a.b/c"}};
    static const RawCh LIST34[] = {{0, "G", ""}, {260000000, "H", "http://a.b/c"}};
    static const RawCh LIST35[] = {{0, "Intro", ""}, {500000, "A", ""}, {500999, "B", ""}, {501000, "C", ""}, {559999, "D", ""}, {560000, "E", ""}, {4099999, "F", ""}, {4100000, "G", ""}, {360500000, "H", "http://a.b/c"}};
    static const RawCh LIST36[] = {{0, "Intro", ""}, {1, "A", ""}, {1501, "B", ""}, {4000001, "C", ""}};
    static const RawCh LIST37[] = {{0, "Intro", ""}, {1000, "A", ""}, {2500, "B", ""}, {4001000, "C", ""}};
    static const RawCh LIST38[] = {{0, "A", ""}, {1499, "B", ""}, {3999999, "C", ""}};
    static const RawCh LIST39[] = {{0, "A", ""}, {500, "B", ""}, {3999000, "C", ""}};
    static const RawCh LIST40[] = {{0, "B", ""}, {3995000, "C", ""}};
    static const RawCh LIST41[] = {{0, "B", ""}, {3994999, "C", ""}};
    static const RawCh LIST42[] = {{0, "B", ""}, {3995001, "C", ""}};
    static const RawCh LIST43[] = {{0, "B", ""}, {3990000, "C", ""}};
    static const RawCh LIST44[] = {{0, "B", ""}, {3989999, "C", ""}};
    static const RawCh LIST45[] = {{0, "B", ""}, {3980000, "C", ""}};
    static const RawCh LIST46[] = {{0, "C", ""}};
    static const RawCh LIST47[] = {{0, "Intro", ""}, {500000, "A", ""}, {501500, "B", ""}, {4500000, "C", ""}};
    static const RawCh LIST48[] = {{0, "Intro", ""}, {1, "Start", ""}, {5001, "Mid", ""}, {10001, "End", ""}};
    static const RawCh LIST49[] = {{0, "Intro", ""}, {1000, "Start", ""}, {6000, "Mid", ""}, {11000, "End", ""}};
    static const RawCh LIST50[] = {{0, "Start", ""}, {4999, "Mid", ""}, {9999, "End", ""}};
    static const RawCh LIST51[] = {{0, "Start", ""}, {4000, "Mid", ""}, {9000, "End", ""}};
    static const RawCh LIST52[] = {{0, "Mid", ""}, {5000, "End", ""}};
    static const RawCh LIST53[] = {{0, "Mid", ""}, {4999, "End", ""}};
    static const RawCh LIST54[] = {{0, "Start", ""}, {1, "Mid", ""}, {5001, "End", ""}};
    static const RawCh LIST55[] = {{0, "End", ""}};
    static const RawCh LIST56[] = {{0, "Intro", ""}, {500000, "Start", ""}, {505000, "Mid", ""}, {510000, "End", ""}};
    static const RawCh LIST57[] = {{0, "Intro", ""}, {1, "A | b", ""}, {101, "c", "https://d"}};
    static const RawCh LIST58[] = {{0, "Intro", ""}, {1000, "A | b", ""}, {1100, "c", "https://d"}};
    static const RawCh LIST59[] = {{0, "A | b", ""}, {99, "c", "https://d"}};
    static const RawCh LIST60[] = {{0, "c", "https://d"}};
    static const RawCh LIST61[] = {{0, "Intro", ""}, {500000, "A | b", ""}, {500100, "c", "https://d"}};
    static const RawCh LIST62[] = {{0, "Intro", ""}, {1, "A", ""}, {11, "B", ""}, {21, "C", ""}, {31, "D", ""}};
    static const RawCh LIST63[] = {{0, "Intro", ""}, {1000, "A", ""}, {1010, "B", ""}, {1020, "C", ""}, {1030, "D", ""}};
    static const RawCh LIST64[] = {{0, "A", ""}, {9, "B", ""}, {19, "C", ""}, {29, "D", ""}};
    static const RawCh LIST65[] = {{0, "D", ""}};
    static const RawCh LIST66[] = {{0, "Intro", ""}, {500000, "A", ""}, {500010, "B", ""}, {500020, "C", ""}, {500030, "D", ""}};
    static const RawCh LIST67[] = {{0, "Intro", ""}, {1, "A", ""}, {7200001, "Two hours", "https://example.org/2h"}};
    static const RawCh LIST68[] = {{0, "Intro", ""}, {1000, "A", ""}, {7201000, "Two hours", "https://example.org/2h"}};
    static const RawCh LIST69[] = {{0, "A", ""}, {7199999, "Two hours", "https://example.org/2h"}};
    static const RawCh LIST70[] = {{0, "A", ""}, {7199000, "Two hours", "https://example.org/2h"}};
    static const RawCh LIST71[] = {{0, "A", ""}, {7195000, "Two hours", "https://example.org/2h"}};
    static const RawCh LIST72[] = {{0, "A", ""}, {7194999, "Two hours", "https://example.org/2h"}};
    static const RawCh LIST73[] = {{0, "A", ""}, {7195001, "Two hours", "https://example.org/2h"}};
    static const RawCh LIST74[] = {{0, "A", ""}, {7190000, "Two hours", "https://example.org/2h"}};
    static const RawCh LIST75[] = {{0, "A", ""}, {7189999, "Two hours", "https://example.org/2h"}};
    static const RawCh LIST76[] = {{0, "A", ""}, {7180000, "Two hours", "https://example.org/2h"}};
    static const RawCh LIST77[] = {{0, "Two hours", "https://example.org/2h"}};
    static const RawCh LIST78[] = {{0, "Intro", ""}, {500000, "A", ""}, {7700000, "Two hours", "https://example.org/2h"}};
    static const RawCh LIST79[] = {{-1, "A", ""}};
    static const RawCh LIST80[] = {{0, "", ""}};
    static const RawCh LIST81[] = {{0, "A\nB", ""}};
    static const RawCh LIST82[] = {{0, "A", "ftp://x"}};
    static const RawCh LIST83[] = {{0, "A", "x.org"}};
    static const RawCh LIST84[] = {{0, "A", "https://x y"}};
    static const RawCh LIST85[] = {{0, "A", "https://x\ty"}};
    static const RawCh LIST86[] = {{0, "A", "https://x\ny"}};
    static const RawCh LIST87[] = {{0, "A", "http:/x"}};
    static const RawCh LIST88[] = {{0, "A", "HTTP://x"}};

    static const ParseCase PARSES[] = {
        {"", 0, "", "", 0},
        {"\n", 0, "", "", 0},
        {"  \n\t\n", 0, "", "", 0},
        {"# only a comment\n", 0, "", "", 0},
        {"0:00 Start", 0, "", "0|Start|", 1},
        {"0:00 Start\n", 0, "", "0|Start|", 1},
        {"0:00\tStart\r\n1:00 Next\r\n", 0, "", "0|Start|\n60000|Next|", 2},
        {"0:00 A\n\n# c\n   \n1:00 B", 0, "", "0|A|\n60000|B|", 2},
        {"0:00 A\n1:00 B\n1:00 C", 3, "not increasing", "", 0},
        {"0:00 A\n1:00 B\n0:59 C", 3, "not increasing", "", 0},
        {"0:00 A\n0:00 B", 2, "not increasing", "", 0},
        {"1:00 A", 1, "first chapter must start at 0", "", 0},
        {"0:01 A", 1, "first chapter must start at 0", "", 0},
        {"0:00", 1, "empty title", "", 0},
        {"0:00   ", 1, "empty title", "", 0},
        {"0:00 \t ", 1, "empty title", "", 0},
        {"0:00 | https://x.org", 0, "", "0|| https://x.org|", 1},
        {"0:00 A | https://x.org", 0, "", "0|A|https://x.org", 1},
        {"0:00 A | http://x.org\n0:10 B | https://y.org", 0, "", "0|A|http://x.org\n10000|B|https://y.org", 2},
        {"0:00 A |https://x.org", 0, "", "0|A |https://x.org|", 1},
        {"0:00 A| https://x.org", 0, "", "0|A| https://x.org|", 1},
        {"0:00 A  |  https://x.org", 0, "", "0|A  |  https://x.org|", 1},
        {"0:00 A | https://x.org ", 0, "", "0|A|https://x.org", 1},
        {"0:00 A |  | https://x.org", 0, "", "0|A ||https://x.org", 1},
        {"0:00 A | | https://x.org", 0, "", "0|A ||https://x.org", 1},
        {"0:00 | | https://x.org", 0, "", "0|||https://x.org", 1},
        {"0:00 A | https://x.org | https://y.org", 0, "", "0|A | https://x.org|https://y.org", 1},
        {"0:00 A | x | https://y.org", 0, "", "0|A | x|https://y.org", 1},
        {"0:00 xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", 0, "", "0|xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx|", 1},
        {"0:00 xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", 1, "title too long", "", 0},
        {"0:00 xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx | https://x.org", 0, "", "0|xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx|https://x.org", 1},
        {"0:00 \303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251", 0, "", "0|\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251|", 1},
        {"0:00 \303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251\303\251", 1, "title too long", "", 0},
        {"0:00 xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx | https://x.org", 0, "", "0|xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx|https://x.org", 1},
        {"0:00 xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx | https://x.org", 1, "title too long", "", 0},
        {"  0:00 A", 0, "", "0|A|", 1},
        {"   \t0:00 A", 0, "", "0|A|", 1},
        {"0:00 A\n  # c\n1:00 B", 0, "", "0|A|\n60000|B|", 2},
        {"0:00 A\n1:00 B\n2:00 C\n\n\n\n3:00 D", 0, "", "0|A|\n60000|B|\n120000|C|\n180000|D|", 4},
        {"\n\n0:00 A", 0, "", "0|A|", 1},
        {"# c\n0:00 A\nbad\n1:00 B", 3, "bad time", "", 0},
        {"0:00 A\n1:00\n", 2, "empty title", "", 0},
        {"0:00 A\nx:00 B", 2, "bad time", "", 0},
        {"0:00 A\n1:00B", 2, "bad time", "", 0},
        {"0:00 Title", 0, "", "0|Title|", 1},
        {"0:00.5 Title", 1, "first chapter must start at 0", "", 0},
        {"00:00 Title", 0, "", "0|Title|", 1},
        {"0:00:00 Title", 0, "", "0|Title|", 1},
        {"00:00:00.000 Title", 0, "", "0|Title|", 1},
        {"0:01 Title", 1, "first chapter must start at 0", "", 0},
        {"0:59 Title", 1, "first chapter must start at 0", "", 0},
        {"1:00 Title", 1, "first chapter must start at 0", "", 0},
        {"1:00.25 Title", 1, "first chapter must start at 0", "", 0},
        {"12:34 Title", 1, "first chapter must start at 0", "", 0},
        {"75:00 Title", 1, "first chapter must start at 0", "", 0},
        {"999999:59 Title", 1, "first chapter must start at 0", "", 0},
        {"1:05:09 Title", 1, "first chapter must start at 0", "", 0},
        {"1:05:09.250 Title", 1, "first chapter must start at 0", "", 0},
        {"10:00:00 Title", 1, "first chapter must start at 0", "", 0},
        {"100:00:00 Title", 1, "first chapter must start at 0", "", 0},
        {"999:59:59.999 Title", 1, "first chapter must start at 0", "", 0},
        {"0:00.007 Title", 1, "first chapter must start at 0", "", 0},
        {"0:00.07 Title", 1, "first chapter must start at 0", "", 0},
        {"0:00.700 Title", 1, "first chapter must start at 0", "", 0},
        {"0:00 A\n0:0 Title", 2, "bad time", "", 0},
        {"0:0 Title", 1, "bad time", "", 0},
        {"0:00 A\n0:5 Title", 2, "bad time", "", 0},
        {"0:5 Title", 1, "bad time", "", 0},
        {"0:00 A\n0:60 Title", 2, "bad time", "", 0},
        {"0:60 Title", 1, "bad time", "", 0},
        {"0:00 A\n1:60 Title", 2, "bad time", "", 0},
        {"1:60 Title", 1, "bad time", "", 0},
        {"0:00 A\n1:2:03 Title", 2, "bad time", "", 0},
        {"1:2:03 Title", 1, "bad time", "", 0},
        {"0:00 A\n1:02:3 Title", 2, "bad time", "", 0},
        {"1:02:3 Title", 1, "bad time", "", 0},
        {"0:00 A\n1:02:60 Title", 2, "bad time", "", 0},
        {"1:02:60 Title", 1, "bad time", "", 0},
        {"0:00 A\n1:60:00 Title", 2, "bad time", "", 0},
        {"1:60:00 Title", 1, "bad time", "", 0},
        {"0:00 A\n1000:00:00 Title", 2, "bad time", "", 0},
        {"1000:00:00 Title", 1, "bad time", "", 0},
        {"0:00 A\n1234567:00 Title", 2, "bad time", "", 0},
        {"1234567:00 Title", 1, "bad time", "", 0},
        {"0:00 A\n0:00. Title", 2, "bad time", "", 0},
        {"0:00. Title", 1, "bad time", "", 0},
        {"0:00 A\n0:00.1234 Title", 2, "bad time", "", 0},
        {"0:00.1234 Title", 1, "bad time", "", 0},
        {"0:00 A\n.5 Title", 2, "bad time", "", 0},
        {".5 Title", 1, "bad time", "", 0},
        {"0:00 A\n0 Title", 2, "bad time", "", 0},
        {"0 Title", 1, "bad time", "", 0},
        {"0:00 A\n Title", 2, "bad time", "", 0},
        {" Title", 1, "bad time", "", 0},
        {"0:00 A\n0: Title", 2, "bad time", "", 0},
        {"0: Title", 1, "bad time", "", 0},
        {"0:00 A\n00:00:00:00 Title", 2, "bad time", "", 0},
        {"00:00:00:00 Title", 1, "bad time", "", 0},
        {"0:00 A\na:00 Title", 2, "bad time", "", 0},
        {"a:00 Title", 1, "bad time", "", 0},
        {"0:00 A\n0:0a Title", 2, "bad time", "", 0},
        {"0:0a Title", 1, "bad time", "", 0},
        {"0:00 A\n0:00:0.5 Title", 2, "bad time", "", 0},
        {"0:00:0.5 Title", 1, "bad time", "", 0},
        {"0:00 A\n-1:00 Title", 2, "bad time", "", 0},
        {"-1:00 Title", 1, "bad time", "", 0},
        {"0:00 A\n0:00,5 Title", 2, "bad time", "", 0},
        {"0:00,5 Title", 1, "bad time", "", 0},
        {"0:00 A\n1.5:00 Title", 2, "bad time", "", 0},
        {"1.5:00 Title", 1, "bad time", "", 0},
        {"0:00 A\n0:00.5.5 Title", 2, "bad time", "", 0},
        {"0:00.5.5 Title", 1, "bad time", "", 0},
        {"0:00 A\n:: Title", 2, "bad time", "", 0},
        {":: Title", 1, "bad time", "", 0},
        {"0:00 A\n0:00: Title", 2, "bad time", "", 0},
        {"0:00: Title", 1, "bad time", "", 0},
        {"00:00:00\ta|b|c \t\n5:02.215 \tCold open\n5:01.215 Welcome \t", 3, "not increasing", "", 0},
        {"0:00 \tu | https://a | not-a-link\n00:00:51.742\tWelcome  \n", 0, "", "0|u | https://a | not-a-link|\n51742|Welcome|", 2},
        {"0:00:00\tWelcome  \n3:33.486 \346\227\245\346\234\254\350\252\236 chapter\n0:09:55.279 Cold open \t\n00:10:29.741  A | in the title  ", 0, "", "0|Welcome|\n213486|\346\227\245\346\234\254\350\252\236 chapter|\n595279|Cold open|\n629741|A | in the title|", 4},
        {"0:00 \t\346\227\245\346\234\254\350\252\236 chapter  \n00:03:35.28  Title |  https://x.org/pad \t\n9:44.404 \txxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx \t", 0, "", "0|\346\227\245\346\234\254\350\252\236 chapter|\n215280|Title |  https://x.org/pad|\n584404|xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx|", 3},
        {"0:00 \346\227\245\346\234\254\350\252\236 chapter\n", 0, "", "0|\346\227\245\346\234\254\350\252\236 chapter|", 1},
        {"\n", 0, "", "", 0},
        {"00:00:00  x | https://a | https://b \t\n0:0a  x | https://a | https://b \t\n0:04:39.760\tWelcome\n4:38.76 \346\227\245\346\234\254\350\252\236 chapter \t\n0:07:18.738 \tA | in the title \t\n\n", 2, "bad time", "", 0},
        {"0:00 \tTitle | http://x.org/a b", 0, "", "0|Title | http://x.org/a b|", 1},
        {"00:00:00  with trailing pipe |  \n0:05:22.699 \tTitle | https://x.org/a b\n10:48.843  a|b|c\n16:50.332  Welcome  \n0:23:25.716\tCold open\r\n", 0, "", "0|with trailing pipe ||\n322699|Title | https://x.org/a b|\n648843|a|b|c|\n1010332|Welcome|\n1405716|Cold open|", 5},
        {"\r\n", 0, "", "", 0},
        {"0:00:00\tInterview: the long one  \n1:30.694\tCold open  \n1:38.924 x | https://a | https://b\n0:01:37.924 \tSponsors \t\n7:24.202  Tab\tinside\n0:09:48.839\txxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx  \r\n", 4, "not increasing", "", 0},
        {"", 0, "", "", 0},
        {"0:00:00 u | https://a | not-a-link  \r\n0:03:37.395 \346\227\245\346\234\254\350\252\236 chapter\r\n#\r\n0:05:08.135 \tTitle |  https://x.org/pad \t\r\n\t# tab comment\r\n0:08:40.317 x | https://a | https://b \t", 0, "", "0|u | https://a | not-a-link|\n217395|\346\227\245\346\234\254\350\252\236 chapter|\n308135|Title |  https://x.org/pad|\n520317|x | https://a|https://b", 4},
        {"0:00:00 Tab\tinside\n00:00:45.305 \tTitle |  https://x.org/pad  \n00:07:12.138  Title | https://x.org/a b \t\n12:45.487  Interview: the long one \t\n18:32.326  xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx\n", 5, "title too long", "", 0},
        {"0:00:00 Interview: the long one", 0, "", "0|Interview: the long one|", 1},
        {"0:00 \346\227\245\346\234\254\350\252\236 chapter\n00:01:24.488  Title |  https://x.org/pad  \n0:04:26.881\tTitle | http://x.org/a b  \n5:16.926  Title | ftp://x.org/f  \n5:16.926\txxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx\r\n", 5, "not increasing", "", 0},
        {"\n\n", 0, "", "", 0},
        {"0:00:00 \tx | https://a | https://b\n0:01:21.091 \tCold open \t\n00:04:20.138\tTitle | ftp://x.org/f  \n10:45.242  | https://only.example/url\n0:00:0.5 \tTitle | http://x.org/a b  \n", 5, "bad time", "", 0},
        {"0:00:00 Title | http://x.org/a b\n0:00:30.369 Title | http://a \t\n00:03:26.944  Interview: the long one", 0, "", "0|Title | http://x.org/a b|\n30369|Title|http://a\n206944|Interview: the long one|", 3},
        {"\r\n00:00:00  Cold open  \r\n5:30.811  | https://only.example/url \t\r\n00:06:26.687  Q&A", 0, "", "0|Cold open|\n330811|| https://only.example/url|\n386687|Q&A|", 3},
        {"\n0:00\tTitle |  https://x.org/pad  \n   \n3:55.998\t\346\227\245\346\234\254\350\252\236 chapter  \n0:07:45.133 \tTitle | https://x.org/a b  \n7:44.133  Title | ftp://x.org/f  \n0:11:39.634 \tSponsors\n\n0:12:59.893\tTitle | https://  \n", 6, "not increasing", "", 0},
        {"\n\n", 0, "", "", 0},
        {"0:00:00\tTitle | ftp://x.org/f \t\n0:26.640\t| https://only.example/url\n5:10.122\tx | https://a | https://b \t\n00:06:49.32  | https://only.example/url\n00:07:56.645\t| https://only.example/url  \n00:07:56.645 Title | http://a  \n\n", 6, "not increasing", "", 0},
        {"0:00\tWelcome \t\r\n0:06:13.914 x | https://a | https://b \t\r\n6:13.914 Q&A  \r\n00:06:13.914 \tTitle | http://x.org/a b\r\n8:40.934 \twith trailing pipe |\r\n00:10:00.713  u | https://a | not-a-link \t\r\r\n", 3, "not increasing", "", 0},
        {"0:00\t  padded  \n\n00:05:08.55  Title | https://x.org/p?q=1&r=2  \n", 0, "", "0|padded|\n308550|Title|https://x.org/p?q=1&r=2", 2},
        {"0:00:00 \t| https://only.example/url \t\n1:02:60\tTitle | not a link  \n0:07:25.638 \tWelcome  \n10:27.034  Title | http://a \t\n00:11:15.931 \tTitle | ftp://x.org/f\na:00\tTitle |  https://x.org/pad\r\n", 2, "bad time", "", 0},
        {"0:00:00\tTitle | not a link \t\r\n1:57.218 \ta|b|c\r\n00:04:36.148  a|b|c  \r\n00:09:39.439\tu | https://a | not-a-link \t\r\n13:55.911 \tTitle | ftp://x.org/f  \r\n\r\n", 0, "", "0|Title | not a link|\n117218|a|b|c|\n276148|a|b|c|\n579439|u | https://a | not-a-link|\n835911|Title | ftp://x.org/f|", 5},
        {"0:00:00  u | https://a | not-a-link \t\n0:42.756 Title | http://a  \n0:00:45.117 xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx\n0:01:13.793\tQ&A \t\r\n", 0, "", "0|u | https://a | not-a-link|\n42756|Title|http://a\n45117|xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx|\n73793|Q&A|", 4},
        {"00:00:00\tTitle | http://x.org/a b  \r\n", 0, "", "0|Title | http://x.org/a b|", 1},
        {"0:00\tu | https://a | not-a-link \t\r\n2:21.784 x | https://a | https://b  ", 0, "", "0|u | https://a | not-a-link|\n141784|x | https://a|https://b", 2},
        {"", 0, "", "", 0},
        {"\r\n", 0, "", "", 0},
        {"\n", 0, "", "", 0},
        {"0:00:00 \tTitle | https://  \n4:23.961 \txxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx  \n00:06:58.339 x | https://a | https://b  \n13:22.774  a|b|c", 2, "title too long", "", 0},
        {"\n", 0, "", "", 0},
        {"\r\r\n", 1, "bad time", "", 0},
        {"00:00:00\tTitle |  https://x.org/pad\n0:00:00 Welcome \t\n00:00:41.073 xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx  \n", 2, "not increasing", "", 0},
        {"0:00:00\tTitle | https://x.org/a b\n00:06:07.007 \tTitle |  https://x.org/pad  \n0:08:02.831  Welcome\n0:09:44.591\tx | https://a | https://b \t\n   \n13:49.455 \tTitle | not a link \t\n00:13:49.455\tInterview: the long one \t\r\n", 7, "not increasing", "", 0},
        {"0:00:00\tTitle | ftp://x.org/f\n00:04:05.357    padded    \r\n", 0, "", "0|Title | ftp://x.org/f|\n245357|padded|", 2},
        {"0:00 \txxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx\r\n0:01:47.489  Sponsors \t\r\n3:06.056 Q&A\r\n00:03:44.95 \t  padded  \r\n1:02:3 | https://only.example/url  \r\n6:28.153 Welcome\r\n", 5, "bad time", "", 0},
        {"0:00:00 \tTitle | ftp://x.org/f\n::  A | in the title\n6:36.688  A | in the title\n10:44.412 \tTitle | http://x.org/a b\n0:15:09.242 x | https://a | https://b  \n\n", 2, "bad time", "", 0},
        {"\n\n", 0, "", "", 0},
        {"0:00  Title | https://x.org/p?q=1&r=2\n0:00:0.5 \tTab\tinside \t\n\n", 2, "bad time", "", 0},
        {"0:00  Title | https://x.org/a b  \n0:02:57.309 \tu | https://a | not-a-link  \n00:07:24.433  Title | http://x.org/a b  \n0:11:59.902 \t  padded    \n00:17:48.192 xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx\n23:49.096  a|b|c \t\r\n", 0, "", "0|Title | https://x.org/a b|\n177309|u | https://a | not-a-link|\n444433|Title | http://x.org/a b|\n719902|padded|\n1068192|xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx|\n1429096|a|b|c|", 6},
        {"0:00:00  \346\227\245\346\234\254\350\252\236 chapter  \n#\n2:35.101 xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx  \r\n", 3, "title too long", "", 0},
        {"0:00\twith trailing pipe | \t\n\n", 0, "", "0|with trailing pipe ||", 1},
        {"0:00:00 \twith trailing pipe |", 0, "", "0|with trailing pipe ||", 1},
        {"\n\n", 0, "", "", 0},
        {"0:00:00 \ta|b|c  \n5:43.074 \tQ&A \t\n00:08:22.621 u | https://a | not-a-link  \n0:00.5.5   padded   \t\n0:17:44.737\tTitle | http://a \t\n0:21:43.874\tSponsors \t\r\n", 4, "bad time", "", 0},
        {"0:00\twith trailing pipe |  \r\n4:33.111\tTitle | https:// \t\r\n0:08:05.633 | https://only.example/url \t\r\n0:12:20.143 \tWelcome\r\n\r\n", 0, "", "0|with trailing pipe ||\n273111|Title|https://\n485633|| https://only.example/url|\n740143|Welcome|", 4},
        {"0:00\tCold open  \r\n0:01:07.446  xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx\r\r\n", 2, "title too long", "", 0},
        {"0:00 Title | http://x.org/a b  \r\n", 0, "", "0|Title | http://x.org/a b|", 1},
        {"0:00  \346\227\245\346\234\254\350\252\236 chapter\n\n", 0, "", "0|\346\227\245\346\234\254\350\252\236 chapter|", 1},
        {"  # indented comment\n0:00 Title |  https://x.org/pad \t\n00:03:36.598\tSponsors  \n\n00:07:00.301 xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx  \n0:12:21.632\tTitle | https://x.org/p?q=1&r=2\n00:17:52.812  xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx  ", 5, "title too long", "", 0},
        {"0:00  u | https://a | not-a-link  \r\n0:44.028 Title | not a link  \r\n1:26.991\tTitle |  https://x.org/pad  \r\n00:04:16.134 xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx \t\r\n#\r\n00:06:44.264 \tInterview: the long one \t", 0, "", "0|u | https://a | not-a-link|\n44028|Title | not a link|\n86991|Title |  https://x.org/pad|\n256134|xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx|\n404264|Interview: the long one|", 5},
        {"0:00:00 Q&A\n1000:00:00  Tab\tinside\n00:02:28.364  xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx \t\n", 2, "bad time", "", 0},
        {"0:00:00 \tx | https://a | https://b \t\r\n3:33.163 A | in the title \t\r\n7:03.805\tTitle | not a link \t\r\n10:27.560  | https://only.example/url \t\r\n00:14:01.209 Title |  https://x.org/pad \t\r\n   \r\n00:14:09.821 xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", 7, "title too long", "", 0},
        {"00:00:00\tTitle | http://x.org/a b\n3:41.644\tQ&A\n0:07:46.669 \tInterview: the long one  \n7:55.466 Title | https://\n13:43.76 \tA | in the title  \n19:44.967\t| https://only.example/url \t\r\n", 0, "", "0|Title | http://x.org/a b|\n221644|Q&A|\n466669|Interview: the long one|\n475466|Title|https://\n823760|A | in the title|\n1184967|| https://only.example/url|", 6},
        {"0:00\tu | https://a | not-a-link \t\r\n4:30.587 \tTitle | http://a\r\n11:09.407\tu | https://a | not-a-link  \r\n12:20.793 \tQ&A\r\n# note\r\n00:14:22.819 \tSponsors \t\r\n\r\n", 0, "", "0|u | https://a | not-a-link|\n270587|Title|http://a\n669407|u | https://a | not-a-link|\n740793|Q&A|\n862819|Sponsors|", 5},
        {"00:00:00\t  padded   \t\n00:00:00  Title | http://x.org/a b  ", 2, "not increasing", "", 0},
        {"0:00  Tab\tinside\r\n00:02:06.653 Title | http://a \t\r\n00:03:16.907  Title | http://a\r\n3:24.697 \tTab\tinside \t\r\n7:22.470  Title | https:// \t", 0, "", "0|Tab\tinside|\n126653|Title|http://a\n196907|Title|http://a\n204697|Tab\tinside|\n442470|Title|https://", 5},
        {"0:00\tu | https://a | not-a-link\n5:22.699  u | https://a | not-a-link\n0:10:30.321\tTab\tinside  ", 0, "", "0|u | https://a | not-a-link|\n322699|u | https://a | not-a-link|\n630321|Tab\tinside|", 3},
        {"00:00:00 Title | ftp://x.org/f\n", 0, "", "0|Title | ftp://x.org/f|", 1},
        {"0:00 \tTitle | not a link\n", 0, "", "0|Title | not a link|", 1},
        {"0:00:00  Sponsors", 0, "", "0|Sponsors|", 1},
        {"00:00:00 \tTitle |  https://x.org/pad \t\n00:02:13.096 \txxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx  \n0:02:13.096  Title | https://x.org/a b \t\n00:02:12.096 \txxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx\n", 2, "title too long", "", 0},
        {"0:00:00  Title | http://a \t\n0:02:53.141 Title | ftp://x.org/f  \n00:05:02.352\tQ&A  \n00:07:11.364    padded  \n8:18.279 \tTitle |  https://x.org/pad \t\n0:08:17.279\tTitle | ftp://x.org/f\n\n", 6, "not increasing", "", 0},
        {"0:00:00 \t  padded   \t\r\n", 0, "", "0|padded|", 1},
        {"00:00:00 Title |  https://x.org/pad\r\n3:58.310 x | https://a | https://b  \r\n00:03:58.947 Title |  https://x.org/pad  \r\n0:06:20.858 \tTitle |  https://x.org/pad \t\r\n00:09:10.341 | https://only.example/url  \r\n00:14:07.267 A | in the title \t", 0, "", "0|Title |  https://x.org/pad|\n238310|x | https://a|https://b\n238947|Title |  https://x.org/pad|\n380858|Title |  https://x.org/pad|\n550341|| https://only.example/url|\n847267|A | in the title|", 6},
        {"0:00:00 Welcome \t\n\n", 0, "", "0|Welcome|", 1},
        {"0:00 \346\227\245\346\234\254\350\252\236 chapter\n00:04:40.446 Title | http://a\n9:44.22 \tQ&A  \n14:31.136 \tInterview: the long one \t\n", 0, "", "0|\346\227\245\346\234\254\350\252\236 chapter|\n280446|Title|http://a\n584220|Q&A|\n871136|Interview: the long one|", 4},
        {"0:00:00 Title |  https://x.org/pad\n00:05:58.581 \tTitle | https:// \t\n  # indented comment\n10:10.057  Title | https://x.org/p?q=1&r=2  \n", 0, "", "0|Title |  https://x.org/pad|\n358581|Title|https://\n610057|Title|https://x.org/p?q=1&r=2", 3},
        {"00:00:00\tTitle | http://a \t\n5:49.915 Title | https://x.org/p?q=1&r=2  ", 0, "", "0|Title|http://a\n349915|Title|https://x.org/p?q=1&r=2", 2},
        {"1:60:00 \t  padded  \n2:00.279 Title | http://a \t\n3:54.186  Title | https://x.org/p?q=1&r=2 \t\r\n", 1, "bad time", "", 0},
        {"0:00  Title | https://x.org/p?q=1&r=2\n\n2:27.777\tQ&A  \n#\n0:03:22.135  Title | https://x.org/p?q=1&r=2  \n3:22.135 a|b|c\n00:06:29.924  A | in the title\n::  Title | https://x.org/a b\n", 6, "not increasing", "", 0},
        {"00:00:00 \ta|b|c\n0:00 \t\346\227\245\346\234\254\350\252\236 chapter \t\n\t# tab comment\n0:03:13.519  x | https://a | https://b\n9:32.462 x | https://a | https://b \t\n", 2, "not increasing", "", 0},
        {"\n", 0, "", "", 0},
        {"\ta|b|c \t\r\n0:04:00.282 \ta|b|c\r\n9:18.729 Cold open  ", 1, "bad time", "", 0},
        {"0:00 u | https://a | not-a-link  \n0:11.566\tCold open  \n00:06:15.157 \tTitle | https://x.org/a b \t\n", 0, "", "0|u | https://a | not-a-link|\n11566|Cold open|\n375157|Title | https://x.org/a b|", 3},
        {"0:00:00  Title | https://x.org/p?q=1&r=2  \r\n00:05:13.071 \tTitle |  https://x.org/pad  \r\n8:44.266 \tTitle | https://x.org/a b\r\n12:50.776 Title | https://\r\n15:07.159 Title | https:// \t\r\n00:19:41.015 \twith trailing pipe | \t\r\n\r\n", 0, "", "0|Title|https://x.org/p?q=1&r=2\n313071|Title |  https://x.org/pad|\n524266|Title | https://x.org/a b|\n770776|Title|https://\n907159|Title|https://\n1181015|with trailing pipe ||", 6},
        {"00:00:00 xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx  \n1:54.626 \twith trailing pipe |\n5:19.959  u | https://a | not-a-link \t\n11:41.189 \tu | https://a | not-a-link  \n\n", 0, "", "0|xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx|\n114626|with trailing pipe ||\n319959|u | https://a | not-a-link|\n701189|u | https://a | not-a-link|", 4},
        {"#\r\n0:00:00 \tA | in the title  \r\n0:04:28.129  u | https://a | not-a-link  \r\n\r\n", 0, "", "0|A | in the title|\n268129|u | https://a | not-a-link|", 2},
        {"00:00:00 \t  padded  \n0:01:15.825 \txxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx\n0:01:36.705  Title | https://x.org/p?q=1&r=2 \t\n00:03:54.648  xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx  \n6:17.310 \tTitle |  https://x.org/pad  \n0:07:51.645  Interview: the long one\r\n", 4, "title too long", "", 0},
        {"00:00:00 \txxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx  \n00:04:11.867 Tab\tinside\n00:04:10.867  u | https://a | not-a-link\n7:02.806 \tu | https://a | not-a-link\n", 3, "not increasing", "", 0},
        {"0:00:00\tTitle | https://\n0:00:00\tTitle | http://x.org/a b  \n0:03:54.397 \t| https://only.example/url\n00:06:06.035  xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx\n7:03.149 \t  padded   \t\n7:10.604 u | https://a | not-a-link \t\n", 2, "not increasing", "", 0},
        {"0:00  Tab\tinside\r\n0:00:00 Title | http://x.org/a b\r\n5:46.347 \tTitle | https://x.org/a b  \r\n", 2, "not increasing", "", 0},
        {"\r\n", 0, "", "", 0},
        {"0:00:00\tTitle |  https://x.org/pad  \n3:53.083 Title | ftp://x.org/f\n\n0:06:34.277 Sponsors \t\r\n", 0, "", "0|Title |  https://x.org/pad|\n233083|Title | ftp://x.org/f|\n394277|Sponsors|", 3},
        {"#\n0:00:00  xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx\n00:03:53.165  Welcome \t", 2, "title too long", "", 0},
        {"\n\n", 0, "", "", 0},
        {"0:00 Sponsors\r\n#\r\n0:00:00.838  Title | http://x.org/a b", 0, "", "0|Sponsors|\n838|Title | http://x.org/a b|", 2},
        {"::\tTab\tinside\r\n00:06:14.499\tx | https://a | https://b \t\r\n0:06:32.704 A | in the title \t\r\n00:12:04.026 Title | http://a  \r\n12:21.537 \tTitle |  https://x.org/pad\r\n\r\n", 1, "bad time", "", 0},
        {"00:00:00 Title | https://\r\n  # indented comment\r\n0:00:00 \tTab\tinside  \r\n0:03:05.289 Title | http://a  \r\n  # indented comment\r\n0:03:04.289 Title | not a link \t\r\r\n", 3, "not increasing", "", 0},
        {"# note\n0:00:00\txxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx\n0:00:54.348 \tTitle | http://x.org/a b  \n00:06:14.509 \tTitle | http://a\n11:30.288  Title | https://x.org/p?q=1&r=2\n16:19.086  Title | https://x.org/a b  \n20:06.017  Cold open \t", 0, "", "0|xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx|\n54348|Title | http://x.org/a b|\n374509|Title|http://a\n690288|Title|https://x.org/p?q=1&r=2\n979086|Title | https://x.org/a b|\n1206017|Cold open|", 6},
        {"0:00:00 Title |  https://x.org/pad  \n0:00 \tInterview: the long one \t\n", 2, "not increasing", "", 0},
        {"00:00:00 \tTitle | http://x.org/a b\n0:00:00 \txxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx\n5:09.458\tA | in the title  \n8:47.419  xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx \t\n0:09:22.316 a|b|c \t\n11:43.556  xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx\r\n", 2, "title too long", "", 0},
        {"0:00\t| https://only.example/url \t\n0:40.246 \tTitle | https://x.org/p?q=1&r=2 \t\n0:02:02.155 Title | http://a  \n", 0, "", "0|| https://only.example/url|\n40246|Title|https://x.org/p?q=1&r=2\n122155|Title|http://a", 3},
        {"00:00:00\tTitle | https://x.org/p?q=1&r=2 \t\n3:53.040\tTitle | https://x.org/p?q=1&r=2 \t\n   \n0:10:05.931 with trailing pipe | \t\n13:00.879  xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx \t", 5, "title too long", "", 0},
        {"\r\r\n", 1, "bad time", "", 0},
        {"0:00:00 \tTitle | ftp://x.org/f\n\n0:04:36.494 xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx\n0:07:13.477  \346\227\245\346\234\254\350\252\236 chapter  \n11:11.223 A | in the title \t\n  # indented comment\n11:15.170\tTitle |  https://x.org/pad  \n00:15:26.321    padded  \n", 3, "title too long", "", 0},
        {"00:00:00  Title | https://x.org/a b \t", 0, "", "0|Title | https://x.org/a b|", 1},
        {"0:00  | https://only.example/url \t\n6:10.824    padded  \n7:51.952  Welcome  \n13:18.941 Title |  https://x.org/pad \t\n", 0, "", "0|| https://only.example/url|\n370824|padded|\n471952|Welcome|\n798941|Title |  https://x.org/pad|", 4},
        {".5 Tab\tinside\r\n00:00:00\tInterview: the long one \t\r\n00:03:09.203  u | https://a | not-a-link \t\r\n0:06:39.325 \tTitle | ftp://x.org/f\r\n0:11:29.39  Title | ftp://x.org/f\r\n#\r\n00:17:22.321\tu | https://a | not-a-link \t\r\n\r\n", 1, "bad time", "", 0},
        {"00:00:00 Q&A  \r\n", 0, "", "0|Q&A|", 1},
        {"0:00\t\346\227\245\346\234\254\350\252\236 chapter \t\n0:00:00 \t  padded  \n5:09.892 Interview: the long one", 2, "not increasing", "", 0},
        {"1234567:00  Title | not a link \t\n0:03:23.38\tTitle | https://x.org/a b \t\r\n", 1, "bad time", "", 0},
        {"\r\n", 0, "", "", 0},
        {"0:00:00 Title |  https://x.org/pad\n0:00:52.104  xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx \t\n00:05:09.273 Welcome\n9:23.047 \tTitle | not a link  \n0:09:51.960\t\346\227\245\346\234\254\350\252\236 chapter  \n16:16.453 \tWelcome  ", 0, "", "0|Title |  https://x.org/pad|\n52104|xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx|\n309273|Welcome|\n563047|Title | not a link|\n591960|\346\227\245\346\234\254\350\252\236 chapter|\n976453|Welcome|", 6},
        {"0:00 \tTitle | ftp://x.org/f \t\n1234567:00\twith trailing pipe |\n00:02:15.212 \t| https://only.example/url \t\n0:02:56.414 Tab\tinside  \n00:04:44.913 A | in the title  \n0:09:02.1\tu | https://a | not-a-link \t\n\n", 2, "bad time", "", 0},
        {"0:00:00 xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx \t\n   \n0:00:25.92\tSponsors \t\n00:05:32.162 Title | https://x.org/a b\n00:05:32.162  Title |  https://x.org/pad\n8:45.428 Title | http://x.org/a b \t\n", 1, "title too long", "", 0},
        {"0:00:00  with trailing pipe |\n#\n00:05:33.895\tA | in the title  \n\n", 0, "", "0|with trailing pipe ||\n333895|A | in the title|", 2},
        {"", 0, "", "", 0},
        {"0:00 with trailing pipe |\n00:03:37.806  Title | not a link  \n   \n0:05:40.338 \346\227\245\346\234\254\350\252\236 chapter \t\n8:31.984\tTitle | https://x.org/a b \t\r\n", 0, "", "0|with trailing pipe ||\n217806|Title | not a link|\n340338|\346\227\245\346\234\254\350\252\236 chapter|\n511984|Title | https://x.org/a b|", 4},
        {"0:00:00  Title | ftp://x.org/f \t\r\n0:04:36.927 \t  padded   \t\r\n5:39.011\tTitle | http://a\r\n9:17.881 x | https://a | https://b \t\r\n\r\n0:14:07.526  xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx \t\r\n0:17:22.667\txxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx  ", 6, "title too long", "", 0},
        {"0:00:00  Title | https://x.org/p?q=1&r=2\n0:05:50.034  Sponsors \t\n", 0, "", "0|Title|https://x.org/p?q=1&r=2\n350034|Sponsors|", 2},
        {"  # indented comment\r\n0:00:00  Title |  https://x.org/pad  \r\n4:13.473  Title | http://x.org/a b\r\n9:52.597 \tTab\tinside \t\r\n11:44.562 Title | http://a\r\n0:00.5.5\tTitle | http://a  \r\n0:12:50.224  Title | https://x.org/p?q=1&r=2", 6, "bad time", "", 0},
        {"#\n0:00  Title | https://x.org/a b \t\n0:00 Sponsors  \n0:45.014 Title | http://x.org/a b  \n0:02:04.067 \ta|b|c \t\n\n", 3, "not increasing", "", 0},
        {"00:00:00  Title | ftp://x.org/f \t\n4:30.436 \twith trailing pipe | \t\n0:06:48.173 Title |  https://x.org/pad\r\n", 0, "", "0|Title | ftp://x.org/f|\n270436|with trailing pipe ||\n408173|Title |  https://x.org/pad|", 3},
        {"00:00:00\ta|b|c \t\n0:01:10.142  Title | https:// \t\n1:14.007 Title | ftp://x.org/f\n3:29.379 with trailing pipe |  \r\n", 0, "", "0|a|b|c|\n70142|Title|https://\n74007|Title | ftp://x.org/f|\n209379|with trailing pipe ||", 4},
        {"00:00:00\tTitle | http://x.org/a b \t\n00:00:00\txxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx  \n0:06:12.387  Title | https://x.org/a b\n#\n00:08:05.445 xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx\na:00 Sponsors \t\n.5 \t  padded    ", 2, "title too long", "", 0},
        {"00:00:00 \tTitle |  https://x.org/pad  \n00:03:36.228\tTitle | ftp://x.org/f  \n6:43.577 Welcome \t\n9:53.321 Title | https:// \t\n", 0, "", "0|Title |  https://x.org/pad|\n216228|Title | ftp://x.org/f|\n403577|Welcome|\n593321|Title|https://", 4},
        {"0:00 Cold open\n1:01.709 \tTitle | https://x.org/a b \t\n0:05:32.52  Sponsors \t", 0, "", "0|Cold open|\n61709|Title | https://x.org/a b|\n332520|Sponsors|", 3},
        {"0:5 xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx  \n0:04:40.689 \tCold open\n10:48.41 Title | http://a\n16:05.235 \346\227\245\346\234\254\350\252\236 chapter \t\n", 1, "bad time", "", 0},
        {"0:00:00 Cold open \t\n00:05:28.935\tQ&A\n0:10:13.317\tTitle | not a link  \n12:44.917 Title | not a link \t\n0:12:43.917 \tTitle | http://a\n14:23.412\tTitle | http://a  \n\n", 5, "not increasing", "", 0},
        {"", 0, "", "", 0},
        {"00:00:00  Title | https://x.org/p?q=1&r=2 \t\r\n0:24.424 \tTitle | ftp://x.org/f\r\n0  x | https://a | https://b  \r\n\r\n", 3, "bad time", "", 0},
        {"0:00 \tx | https://a | https://b\n2:00.610  Title | https://x.org/a b\n1:60:00  Title | http://x.org/a b\n0:0\tInterview: the long one\n0:13:40.277 \tQ&A \t\n", 3, "bad time", "", 0},
        {"00:00:00 \t\346\227\245\346\234\254\350\252\236 chapter  \n3:06.872  A | in the title  \n", 0, "", "0|\346\227\245\346\234\254\350\252\236 chapter|\n186872|A | in the title|", 2},
        {"0:00\tx | https://a | https://b\r\n", 0, "", "0|x | https://a|https://b", 1},
        {"# note\r\n00:00:00\ta|b|c \t\r\n00:06:06.444  with trailing pipe |\r\n00:09:08.201 | https://only.example/url\r\n10:30.969  xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx\r\n0:14:26.030   padded   \t\r\n  # indented comment\r\n00:19:23.149 Welcome  ", 5, "title too long", "", 0},
        {"00:00:00   padded   \t\n00:00:15.608\tCold open \t\n3:38.992  a|b|c  \n#\n0:08:18.139  | https://only.example/url  \n", 0, "", "0|padded|\n15608|Cold open|\n218992|a|b|c|\n498139|| https://only.example/url|", 4},
        {"# note\n0:00:00 u | https://a | not-a-link", 0, "", "0|u | https://a | not-a-link|", 1},
        {"", 0, "", "", 0},
        {"\n\n", 0, "", "", 0},
        {"   \n00:00:00  x | https://a | https://b\n00:05:40.654\tTitle | not a link  \n00:12:04.161\tQ&A\n", 0, "", "0|x | https://a|https://b\n340654|Title | not a link|\n724161|Q&A|", 3},
        {"0:00  Tab\tinside  \n0:02:27.795 \txxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx\r\n", 0, "", "0|Tab\tinside|\n147795|xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx|", 2},
        {"0:00:00  Sponsors\n0:00:07.984 \tA | in the title  \n1:49.959\tTitle | https://\n6:49.473 xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx \t\n0:10:06.046 \346\227\245\346\234\254\350\252\236 chapter \t\n00:16:33.992\tCold open \t\n", 0, "", "0|Sponsors|\n7984|A | in the title|\n109959|Title|https://\n409473|xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx|\n606046|\346\227\245\346\234\254\350\252\236 chapter|\n993992|Cold open|", 6},
        {"", 0, "", "", 0},
        {"0:00:00 with trailing pipe |\n", 0, "", "0|with trailing pipe ||", 1},
        {"0:00 \t  padded    \n0:00:44.943 \twith trailing pipe | \t\n00:02:25.2  Sponsors  \n0:03:30.839 Cold open  \n.5  Title | https://x.org/a b\n\t# tab comment\n00:09:11.599 Title | ftp://x.org/f\n\n", 5, "bad time", "", 0},
        {"00:00:00\twith trailing pipe | \t\n00:01:22.726 \tTitle | http://a  ", 0, "", "0|with trailing pipe ||\n82726|Title|http://a", 2},
        {"0:00 \tTab\tinside  \n", 0, "", "0|Tab\tinside|", 1},
        {"", 0, "", "", 0},
        {"0:00 Title | not a link  \n\t# tab comment\n00:01:17.426 | https://only.example/url  \n00:01:16.426\tTitle | ftp://x.org/f \t\n0:01:16.426 xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", 4, "not increasing", "", 0},
        {"0:00  xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx\n00:05:56.030 \tTitle | not a link\n9:12.404 u | https://a | not-a-link\n00:13:22.968 Q&A\n00:17:25.867  Title |  https://x.org/pad  \n\n", 0, "", "0|xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx|\n356030|Title | not a link|\n552404|u | https://a | not-a-link|\n802968|Q&A|\n1045867|Title |  https://x.org/pad|", 5},
        {"\r\n", 0, "", "", 0},
        {"# note\n0:00 Title | https:// \t\n00:00:53.455\tu | https://a | not-a-link \t\r\n", 0, "", "0|Title|https://\n53455|u | https://a | not-a-link|", 2},
        {"0:00:00  Cold open \t\r\n0:00  Tab\tinside\r\n   \r\n00:02:19.289\tTab\tinside \t\r\n0:03:23.107 \tInterview: the long one", 2, "not increasing", "", 0},
        {"\t# tab comment\r\n0:60\tQ&A \t\r\n0:03:48.858  Tab\tinside\r\n0:06:34.871\tTitle | https://x.org/a b  \r\n00:06:34.871\tQ&A \t\r\n7:44.163 \tTitle | ftp://x.org/f\r\n", 2, "bad time", "", 0},
        {"\r\n\r\n", 0, "", "", 0},
        {"\r\n", 0, "", "", 0},
        {"# note\n0:00 Tab\tinside\n  # indented comment\n1:55.421\tTitle | http://x.org/a b\n00:02:53.706    padded    \n00:04:12.918 Title | not a link \t\n\n", 0, "", "0|Tab\tinside|\n115421|Title | http://x.org/a b|\n173706|padded|\n252918|Title | not a link|", 4},
        {"   \n0:00:00 \txxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx\n\t# tab comment\n5:04.522 u | https://a | not-a-link \t\n0:09:30.245 Title | not a link\n\t# tab comment\n0:11:27.621 \tTitle |  https://x.org/pad \t\n0:17:53.546  Title | https://x.org/p?q=1&r=2 \t", 0, "", "0|xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx|\n304522|u | https://a | not-a-link|\n570245|Title | not a link|\n687621|Title |  https://x.org/pad|\n1073546|Title|https://x.org/p?q=1&r=2", 5},
        {"00:00:00  \346\227\245\346\234\254\350\252\236 chapter\r\n00:03:38.888  A | in the title \t\r\n0:06:35.482  u | https://a | not-a-link\r\n00:06:35.482  Q&A  \r\n8:50.644 \tCold open \t\r\n0:10:13.111  Cold open\r\n", 4, "not increasing", "", 0},
        {"0:00:00 \t  padded   \t\n0:06:04.758\tTitle | http://x.org/a b \t\n   \n0:12:34.981\tTitle | ftp://x.org/f  \n0:13:27.119 Title | not a link\n19:43.608 \tInterview: the long one \t\n00:24:38.961 \tQ&A \t\n\n", 0, "", "0|padded|\n364758|Title | http://x.org/a b|\n754981|Title | ftp://x.org/f|\n807119|Title | not a link|\n1183608|Interview: the long one|\n1478961|Q&A|", 6},
        {"0:00 Sponsors  \n\n", 0, "", "0|Sponsors|", 1},
        {"0:00 Q&A\n00:00:42.375 \tTitle | not a link\n00:05:37.109 \t  padded   \t\n11:47.353  Sponsors  \n0:14:07.936 \tTitle | ftp://x.org/f\n", 0, "", "0|Q&A|\n42375|Title | not a link|\n337109|padded|\n707353|Sponsors|\n847936|Title | ftp://x.org/f|", 5},
        {"0:00 Welcome  \n\n", 0, "", "0|Welcome|", 1},
        {"\n", 0, "", "", 0},
        {"\n\n", 0, "", "", 0},
        {"0:00:00 Title | https://  \n2:38.994  Title | http://a  \n00:03:04.895  Tab\tinside  \n6:22.709  Title | https://x.org/p?q=1&r=2 \t\n11:37.295  x | https://a | https://b  \n12:28.22  Title | http://a \t\n", 0, "", "0|Title|https://\n158994|Title|http://a\n184895|Tab\tinside|\n382709|Title|https://x.org/p?q=1&r=2\n697295|x | https://a|https://b\n748220|Title|http://a", 6},
        {"0:00:00 \ta|b|c \t\n\n", 0, "", "0|a|b|c|", 1},
        {"0:00 \tA | in the title  \n0:08.645  Sponsors\n0:06:21.743 \tA | in the title  \n  # indented comment\n0:11:49.266  \346\227\245\346\234\254\350\252\236 chapter", 0, "", "0|A | in the title|\n8645|Sponsors|\n381743|A | in the title|\n709266|\346\227\245\346\234\254\350\252\236 chapter|", 4},
        {"0:00 Title |  https://x.org/pad  \n", 0, "", "0|Title |  https://x.org/pad|", 1},
        {"0:00:00\tTitle | https://x.org/p?q=1&r=2  \r\n00:00:00 \tTitle | https://  \r\n1:2:03 xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx\r\n0:04:57.275\ta|b|c\r\n0:00: Welcome \t\r\r\n", 2, "not increasing", "", 0},
        {"0:00 \txxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx\n0:00:00 x | https://a | https://b\n0:00 Cold open  \r\n", 1, "title too long", "", 0},
        {"0: \t| https://only.example/url\n0:00 xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx \t\n1:38.245  Interview: the long one\n4:47.554  A | in the title\n8:59.160\t| https://only.example/url \t\n11:37.562 a|b|c", 1, "bad time", "", 0},
        {"0:00 \tCold open \t\n#\n00:01:36.269 xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx\n00:05:40.527 \tTitle |  https://x.org/pad\n00:12:09.792\tTitle |  https://x.org/pad \t\n15:14.686 \tInterview: the long one \t\n", 0, "", "0|Cold open|\n96269|xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx|\n340527|Title |  https://x.org/pad|\n729792|Title |  https://x.org/pad|\n914686|Interview: the long one|", 5},
        {"\n", 0, "", "", 0},
        {"00:00:00\tA | in the title\n0:04:16.632 \tInterview: the long one \t\n4:43.521 Welcome\n00:06:26.526 Title | http://x.org/a b  \n0:07:49.775  with trailing pipe |\r\n", 0, "", "0|A | in the title|\n256632|Interview: the long one|\n283521|Welcome|\n386526|Title | http://x.org/a b|\n469775|with trailing pipe ||", 5},
        {"0:5\tTitle | http://a\n  # indented comment\n00:01:57.265\tTitle |  https://x.org/pad  \n   \n0:01:56.265\tCold open\n0:01:57.265 Sponsors  \n3:17.409 A | in the title \t\n1:60:00 \tTitle |  https://x.org/pad\n", 1, "bad time", "", 0},
        {"00:00:00 \tTitle | https:// \t\n#\n0:19.811 Tab\tinside\n# note\n3:11.248\tTitle | https://x.org/a b", 0, "", "0|Title|https://\n19811|Tab\tinside|\n191248|Title | https://x.org/a b|", 3},
        {"00:00:00 \tQ&A  \n0:01:00.880 Title | ftp://x.org/f \t", 0, "", "0|Q&A|\n60880|Title | ftp://x.org/f|", 2},
        {"1234567:00 u | https://a | not-a-link\n0:02:58.876\tTab\tinside \t\n0:04:21.219 \tTitle |  https://x.org/pad  \n\n", 1, "bad time", "", 0},
        {"0:00 with trailing pipe |\n00:00:46.756 \tTitle | https://  \n0:01:20.846 \346\227\245\346\234\254\350\252\236 chapter\n", 0, "", "0|with trailing pipe ||\n46756|Title|https://\n80846|\346\227\245\346\234\254\350\252\236 chapter|", 3},
        {"0:00\ta|b|c \t\n0:03:54.277\tTitle | ftp://x.org/f \t\r\n", 0, "", "0|a|b|c|\n234277|Title | ftp://x.org/f|", 2},
        {"0:00:00  Title | http://a  \n00:00:09.854 \t\346\227\245\346\234\254\350\252\236 chapter\n00:03:55.588 Tab\tinside\n0:10:09.531 Interview: the long one  \n0:10:26.124 A | in the title \t\n", 0, "", "0|Title|http://a\n9854|\346\227\245\346\234\254\350\252\236 chapter|\n235588|Tab\tinside|\n609531|Interview: the long one|\n626124|A | in the title|", 5},
        {"0:00 \tWelcome \t\n00:03:31.127  Title | https://  \n00:04:15.053 Tab\tinside  \r\n", 0, "", "0|Welcome|\n211127|Title|https://\n255053|Tab\tinside|", 3},
        {"00:00:00 \tTitle | not a link  \n0:06:28.716  a|b|c\n00:10:31.821 \tInterview: the long one\n-1:00  A | in the title  \n16:12.724 \tu | https://a | not-a-link  \n00:18:30.46\tCold open  ", 4, "bad time", "", 0},
        {"0:00  Q&A \t\r\n\r\n", 0, "", "0|Q&A|", 1},
        {"0:00:00 Title | http://a \t\n0:01:39.718 A | in the title  \n0:05:54.609 \346\227\245\346\234\254\350\252\236 chapter  \r\n", 0, "", "0|Title|http://a\n99718|A | in the title|\n354609|\346\227\245\346\234\254\350\252\236 chapter|", 3},
        {"\r\n\r\n", 0, "", "", 0},
        {"00:00:00\tTitle | http://x.org/a b\n00:03:14.383 Tab\tinside \t\r\n", 0, "", "0|Title | http://x.org/a b|\n194383|Tab\tinside|", 2},
        {"00:00:00  a|b|c\n0:01:20.712  x | https://a | https://b  \n6:06.157  a|b|c \t\n\n", 0, "", "0|a|b|c|\n80712|x | https://a|https://b\n366157|a|b|c|", 3},
        {"0:00  Sponsors \t\n0:00:00 u | https://a | not-a-link  \n5:25.123 \tTitle | https://x.org/a b \t\n\t# tab comment\n00:09:22.773\twith trailing pipe |\n", 2, "not increasing", "", 0},
        {"# note\n0:00  Title | https://x.org/p?q=1&r=2 \t\n0:08.628  x | https://a | https://b\n00:05:16.767 \tTitle | not a link \t\n11:23.814 Title | https://\n   \n00:12:18.746 Sponsors  \n", 0, "", "0|Title|https://x.org/p?q=1&r=2\n8628|x | https://a|https://b\n316767|Title | not a link|\n683814|Title|https://\n738746|Sponsors|", 5},
        {"\n", 0, "", "", 0},
        {"0:00\tQ&A \t\r\n   \r\n1.5:00\t| https://only.example/url  \r\n\r\n", 3, "bad time", "", 0},
        {"   \r\n0:00  Title | ftp://x.org/f\r\n\r\n", 0, "", "0|Title | ftp://x.org/f|", 1},
        {"0:00:00 a|b|c \t\n00:04:18.890 \tTitle | http://x.org/a b\n0:00:0.5\txxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", 3, "bad time", "", 0},
        {"0:00:00  x | https://a | https://b \t\n00:03:10.432  | https://only.example/url \t\n8:20.63\ta|b|c  \r\n", 0, "", "0|x | https://a|https://b\n190432|| https://only.example/url|\n500630|a|b|c|", 3},
        {"", 0, "", "", 0},
        {"0:00:00 \tx | https://a | https://b\n4:39.806\tWelcome\n0:07:41.892 a|b|c \t\n00:08:44.967  Title | https://x.org/p?q=1&r=2 \t\n13:45.899 \t  padded   \t\n0:17:02.530 Title | https://x.org/a b\r\n", 0, "", "0|x | https://a|https://b\n279806|Welcome|\n461892|a|b|c|\n524967|Title|https://x.org/p?q=1&r=2\n825899|padded|\n1022530|Title | https://x.org/a b|", 6},
        {"00:00:00 | https://only.example/url  \r\n00:03:44.345 \t\346\227\245\346\234\254\350\252\236 chapter \t\r\n0:04:29.849 \tTitle | ftp://x.org/f  \r\n0:05:11.452\tTab\tinside \t\r\n", 0, "", "0|| https://only.example/url|\n224345|\346\227\245\346\234\254\350\252\236 chapter|\n269849|Title | ftp://x.org/f|\n311452|Tab\tinside|", 4},
        {"00:00:00\tA | in the title \t\n", 0, "", "0|A | in the title|", 1},
        {"\n", 0, "", "", 0},
        {"\txxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx\r\n5:24.89 \twith trailing pipe | \t\r\n  # indented comment\r\n5:24.89 \tx | https://a | https://b  \r\n9:33.707 \txxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx \t\r\n\r\n", 1, "bad time", "", 0},
        {"0:00:00 \tTitle | http://x.org/a b  \r\n2:23.318 A | in the title\r\n00:08:48.033  Tab\tinside\r\n#\r\n0:08:47.033  Welcome \t\r\n\r\n", 5, "not increasing", "", 0},
        {"0:00 Title | not a link \t\n", 0, "", "0|Title | not a link|", 1},
        {"0:00  a|b|c  ", 0, "", "0|a|b|c|", 1},
    };

    static const FormatCase FORMATS[] = {
        {LIST0, 3, false, "00:00:00.000 Intro\n00:01:01.000 Main | https://x.org/a\n01:02:03.500 Outro\n"},
        {LIST0, 3, true, "0:00 Intro\n1:01 Main | https://x.org/a\n1:02:03.500 Outro\n"},
        {LIST1, 1, false, "00:00:00.000 Only\n"},
        {LIST1, 1, true, "0:00 Only\n"},
        {LIST2, 8, false, "00:00:00.000 A\n00:00:00.999 B\n00:00:01.000 C\n00:00:59.999 D\n00:01:00.000 E\n00:59:59.999 F\n01:00:00.000 G\n100:00:00.000 H | http://a.b/c\n"},
        {LIST2, 8, true, "0:00 A\n0:00.999 B\n0:01 C\n0:59.999 D\n1:00 E\n59:59.999 F\n1:00:00 G\n100:00:00 H | http://a.b/c\n"},
        {LIST3, 3, false, "00:00:00.000 A\n00:00:01.500 B\n01:06:40.000 C\n"},
        {LIST3, 3, true, "0:00 A\n0:01.500 B\n1:06:40 C\n"},
        {LIST4, 3, false, "00:00:00.000 Start\n00:00:05.000 Mid\n00:00:10.000 End\n"},
        {LIST4, 3, true, "0:00 Start\n0:05 Mid\n0:10 End\n"},
        {LIST5, 2, false, "00:00:00.000 A | b\n00:00:00.100 c | https://d\n"},
        {LIST5, 2, true, "0:00 A | b\n0:00.100 c | https://d\n"},
        {LIST6, 4, false, "00:00:00.000 A\n00:00:00.010 B\n00:00:00.020 C\n00:00:00.030 D\n"},
        {LIST6, 4, true, "0:00 A\n0:00.010 B\n0:00.020 C\n0:00.030 D\n"},
        {LIST7, 2, false, "00:00:00.000 A\n02:00:00.000 Two hours | https://example.org/2h\n"},
        {LIST7, 2, true, "0:00 A\n2:00:00 Two hours | https://example.org/2h\n"},
        {LIST8, 0, false, ""},
        {LIST8, 0, true, ""},
    };

    static const ShiftCase SHIFTS[] = {
        {LIST0, 3, 0, LIST0, 3},
        {LIST0, 3, 1, LIST9, 4},
        {LIST0, 3, 1000, LIST10, 4},
        {LIST0, 3, -1, LIST11, 3},
        {LIST0, 3, -1000, LIST12, 3},
        {LIST0, 3, -5000, LIST13, 3},
        {LIST0, 3, -5001, LIST14, 3},
        {LIST0, 3, -4999, LIST15, 3},
        {LIST0, 3, -10000, LIST16, 3},
        {LIST0, 3, -10001, LIST17, 3},
        {LIST0, 3, -20000, LIST18, 3},
        {LIST0, 3, -100000000, LIST19, 1},
        {LIST0, 3, 500000, LIST20, 4},
        {LIST1, 1, 0, LIST1, 1},
        {LIST1, 1, 1, LIST21, 2},
        {LIST1, 1, 1000, LIST22, 2},
        {LIST1, 1, -1, LIST1, 1},
        {LIST1, 1, -1000, LIST1, 1},
        {LIST1, 1, -5000, LIST1, 1},
        {LIST1, 1, -5001, LIST1, 1},
        {LIST1, 1, -4999, LIST1, 1},
        {LIST1, 1, -10000, LIST1, 1},
        {LIST1, 1, -10001, LIST1, 1},
        {LIST1, 1, -20000, LIST1, 1},
        {LIST1, 1, -100000000, LIST1, 1},
        {LIST1, 1, 500000, LIST23, 2},
        {LIST2, 8, 0, LIST2, 8},
        {LIST2, 8, 1, LIST24, 9},
        {LIST2, 8, 1000, LIST25, 9},
        {LIST2, 8, -1, LIST26, 8},
        {LIST2, 8, -1000, LIST27, 6},
        {LIST2, 8, -5000, LIST28, 6},
        {LIST2, 8, -5001, LIST29, 6},
        {LIST2, 8, -4999, LIST30, 6},
        {LIST2, 8, -10000, LIST31, 6},
        {LIST2, 8, -10001, LIST32, 6},
        {LIST2, 8, -20000, LIST33, 6},
        {LIST2, 8, -100000000, LIST34, 2},
        {LIST2, 8, 500000, LIST35, 9},
        {LIST3, 3, 0, LIST3, 3},
        {LIST3, 3, 1, LIST36, 4},
        {LIST3, 3, 1000, LIST37, 4},
        {LIST3, 3, -1, LIST38, 3},
        {LIST3, 3, -1000, LIST39, 3},
        {LIST3, 3, -5000, LIST40, 2},
        {LIST3, 3, -5001, LIST41, 2},
        {LIST3, 3, -4999, LIST42, 2},
        {LIST3, 3, -10000, LIST43, 2},
        {LIST3, 3, -10001, LIST44, 2},
        {LIST3, 3, -20000, LIST45, 2},
        {LIST3, 3, -100000000, LIST46, 1},
        {LIST3, 3, 500000, LIST47, 4},
        {LIST4, 3, 0, LIST4, 3},
        {LIST4, 3, 1, LIST48, 4},
        {LIST4, 3, 1000, LIST49, 4},
        {LIST4, 3, -1, LIST50, 3},
        {LIST4, 3, -1000, LIST51, 3},
        {LIST4, 3, -5000, LIST52, 2},
        {LIST4, 3, -5001, LIST53, 2},
        {LIST4, 3, -4999, LIST54, 3},
        {LIST4, 3, -10000, LIST55, 1},
        {LIST4, 3, -10001, LIST55, 1},
        {LIST4, 3, -20000, LIST55, 1},
        {LIST4, 3, -100000000, LIST55, 1},
        {LIST4, 3, 500000, LIST56, 4},
        {LIST5, 2, 0, LIST5, 2},
        {LIST5, 2, 1, LIST57, 3},
        {LIST5, 2, 1000, LIST58, 3},
        {LIST5, 2, -1, LIST59, 2},
        {LIST5, 2, -1000, LIST60, 1},
        {LIST5, 2, -5000, LIST60, 1},
        {LIST5, 2, -5001, LIST60, 1},
        {LIST5, 2, -4999, LIST60, 1},
        {LIST5, 2, -10000, LIST60, 1},
        {LIST5, 2, -10001, LIST60, 1},
        {LIST5, 2, -20000, LIST60, 1},
        {LIST5, 2, -100000000, LIST60, 1},
        {LIST5, 2, 500000, LIST61, 3},
        {LIST6, 4, 0, LIST6, 4},
        {LIST6, 4, 1, LIST62, 5},
        {LIST6, 4, 1000, LIST63, 5},
        {LIST6, 4, -1, LIST64, 4},
        {LIST6, 4, -1000, LIST65, 1},
        {LIST6, 4, -5000, LIST65, 1},
        {LIST6, 4, -5001, LIST65, 1},
        {LIST6, 4, -4999, LIST65, 1},
        {LIST6, 4, -10000, LIST65, 1},
        {LIST6, 4, -10001, LIST65, 1},
        {LIST6, 4, -20000, LIST65, 1},
        {LIST6, 4, -100000000, LIST65, 1},
        {LIST6, 4, 500000, LIST66, 5},
        {LIST7, 2, 0, LIST7, 2},
        {LIST7, 2, 1, LIST67, 3},
        {LIST7, 2, 1000, LIST68, 3},
        {LIST7, 2, -1, LIST69, 2},
        {LIST7, 2, -1000, LIST70, 2},
        {LIST7, 2, -5000, LIST71, 2},
        {LIST7, 2, -5001, LIST72, 2},
        {LIST7, 2, -4999, LIST73, 2},
        {LIST7, 2, -10000, LIST74, 2},
        {LIST7, 2, -10001, LIST75, 2},
        {LIST7, 2, -20000, LIST76, 2},
        {LIST7, 2, -100000000, LIST77, 1},
        {LIST7, 2, 500000, LIST78, 3},
        {LIST8, 0, 0, LIST8, 0},
        {LIST8, 0, 1, LIST8, 0},
        {LIST8, 0, 1000, LIST8, 0},
        {LIST8, 0, -1, LIST8, 0},
        {LIST8, 0, -1000, LIST8, 0},
        {LIST8, 0, -5000, LIST8, 0},
        {LIST8, 0, -5001, LIST8, 0},
        {LIST8, 0, -4999, LIST8, 0},
        {LIST8, 0, -10000, LIST8, 0},
        {LIST8, 0, -10001, LIST8, 0},
        {LIST8, 0, -20000, LIST8, 0},
        {LIST8, 0, -100000000, LIST8, 0},
        {LIST8, 0, 500000, LIST8, 0},
    };

    static const DurCase DURS[] = {
        {LIST0, 3, 1, 1, {0}},
        {LIST0, 3, 10, 1, {0}},
        {LIST0, 3, 31, 1, {0}},
        {LIST0, 3, 1001, 1, {0}},
        {LIST0, 3, 5001, 1, {0}},
        {LIST0, 3, 10001, 1, {0}},
        {LIST0, 3, 3723501, 0, {61000, 3662500, 1}},
        {LIST0, 3, 7200001, 0, {61000, 3662500, 3476501}},
        {LIST0, 3, 400000000, 0, {61000, 3662500, 396276500}},
        {LIST1, 1, 1, 0, {1}},
        {LIST1, 1, 10, 0, {10}},
        {LIST1, 1, 31, 0, {31}},
        {LIST1, 1, 1001, 0, {1001}},
        {LIST1, 1, 5001, 0, {5001}},
        {LIST1, 1, 10001, 0, {10001}},
        {LIST1, 1, 3723501, 0, {3723501}},
        {LIST1, 1, 7200001, 0, {7200001}},
        {LIST1, 1, 400000000, 0, {400000000}},
        {LIST2, 8, 1, 1, {0}},
        {LIST2, 8, 10, 1, {0}},
        {LIST2, 8, 31, 1, {0}},
        {LIST2, 8, 1001, 1, {0}},
        {LIST2, 8, 5001, 1, {0}},
        {LIST2, 8, 10001, 1, {0}},
        {LIST2, 8, 3723501, 1, {0}},
        {LIST2, 8, 7200001, 1, {0}},
        {LIST2, 8, 400000000, 0, {999, 1, 58999, 1, 3539999, 1, 356400000, 40000000}},
        {LIST3, 3, 1, 1, {0}},
        {LIST3, 3, 10, 1, {0}},
        {LIST3, 3, 31, 1, {0}},
        {LIST3, 3, 1001, 1, {0}},
        {LIST3, 3, 5001, 1, {0}},
        {LIST3, 3, 10001, 1, {0}},
        {LIST3, 3, 3723501, 1, {0}},
        {LIST3, 3, 7200001, 0, {1500, 3998500, 3200001}},
        {LIST3, 3, 400000000, 0, {1500, 3998500, 396000000}},
        {LIST4, 3, 1, 1, {0}},
        {LIST4, 3, 10, 1, {0}},
        {LIST4, 3, 31, 1, {0}},
        {LIST4, 3, 1001, 1, {0}},
        {LIST4, 3, 5001, 1, {0}},
        {LIST4, 3, 10001, 0, {5000, 5000, 1}},
        {LIST4, 3, 3723501, 0, {5000, 5000, 3713501}},
        {LIST4, 3, 7200001, 0, {5000, 5000, 7190001}},
        {LIST4, 3, 400000000, 0, {5000, 5000, 399990000}},
        {LIST5, 2, 1, 1, {0}},
        {LIST5, 2, 10, 1, {0}},
        {LIST5, 2, 31, 1, {0}},
        {LIST5, 2, 1001, 0, {100, 901}},
        {LIST5, 2, 5001, 0, {100, 4901}},
        {LIST5, 2, 10001, 0, {100, 9901}},
        {LIST5, 2, 3723501, 0, {100, 3723401}},
        {LIST5, 2, 7200001, 0, {100, 7199901}},
        {LIST5, 2, 400000000, 0, {100, 399999900}},
        {LIST6, 4, 1, 1, {0}},
        {LIST6, 4, 10, 1, {0}},
        {LIST6, 4, 31, 0, {10, 10, 10, 1}},
        {LIST6, 4, 1001, 0, {10, 10, 10, 971}},
        {LIST6, 4, 5001, 0, {10, 10, 10, 4971}},
        {LIST6, 4, 10001, 0, {10, 10, 10, 9971}},
        {LIST6, 4, 3723501, 0, {10, 10, 10, 3723471}},
        {LIST6, 4, 7200001, 0, {10, 10, 10, 7199971}},
        {LIST6, 4, 400000000, 0, {10, 10, 10, 399999970}},
        {LIST7, 2, 1, 1, {0}},
        {LIST7, 2, 10, 1, {0}},
        {LIST7, 2, 31, 1, {0}},
        {LIST7, 2, 1001, 1, {0}},
        {LIST7, 2, 5001, 1, {0}},
        {LIST7, 2, 10001, 1, {0}},
        {LIST7, 2, 3723501, 1, {0}},
        {LIST7, 2, 7200001, 0, {7200000, 1}},
        {LIST7, 2, 400000000, 0, {7200000, 392800000}},
        {LIST8, 0, 1, 0, {0}},
        {LIST8, 0, 10, 0, {0}},
        {LIST8, 0, 31, 0, {0}},
        {LIST8, 0, 1001, 0, {0}},
        {LIST8, 0, 5001, 0, {0}},
        {LIST8, 0, 10001, 0, {0}},
        {LIST8, 0, 3723501, 0, {0}},
        {LIST8, 0, 7200001, 0, {0}},
        {LIST8, 0, 400000000, 0, {0}},
    };

    static const AtCase ATS[] = {
        {LIST0, 3, -1, -1},
        {LIST0, 3, 0, 0},
        {LIST0, 3, 1, 0},
        {LIST0, 3, 999, 0},
        {LIST0, 3, 1000, 0},
        {LIST0, 3, 1499, 0},
        {LIST0, 3, 1500, 0},
        {LIST0, 3, 4999, 0},
        {LIST0, 3, 5000, 0},
        {LIST0, 3, 10000, 0},
        {LIST0, 3, 59999, 0},
        {LIST0, 3, 60000, 0},
        {LIST0, 3, 61000, 1},
        {LIST0, 3, 3599999, 1},
        {LIST0, 3, 3600000, 1},
        {LIST0, 3, 3723499, 1},
        {LIST0, 3, 3723500, 2},
        {LIST0, 3, 9999999999, 2},
        {LIST1, 1, -1, -1},
        {LIST1, 1, 0, 0},
        {LIST1, 1, 1, 0},
        {LIST1, 1, 999, 0},
        {LIST1, 1, 1000, 0},
        {LIST1, 1, 1499, 0},
        {LIST1, 1, 1500, 0},
        {LIST1, 1, 4999, 0},
        {LIST1, 1, 5000, 0},
        {LIST1, 1, 10000, 0},
        {LIST1, 1, 59999, 0},
        {LIST1, 1, 60000, 0},
        {LIST1, 1, 61000, 0},
        {LIST1, 1, 3599999, 0},
        {LIST1, 1, 3600000, 0},
        {LIST1, 1, 3723499, 0},
        {LIST1, 1, 3723500, 0},
        {LIST1, 1, 9999999999, 0},
        {LIST2, 8, -1, -1},
        {LIST2, 8, 0, 0},
        {LIST2, 8, 1, 0},
        {LIST2, 8, 999, 1},
        {LIST2, 8, 1000, 2},
        {LIST2, 8, 1499, 2},
        {LIST2, 8, 1500, 2},
        {LIST2, 8, 4999, 2},
        {LIST2, 8, 5000, 2},
        {LIST2, 8, 10000, 2},
        {LIST2, 8, 59999, 3},
        {LIST2, 8, 60000, 4},
        {LIST2, 8, 61000, 4},
        {LIST2, 8, 3599999, 5},
        {LIST2, 8, 3600000, 6},
        {LIST2, 8, 3723499, 6},
        {LIST2, 8, 3723500, 6},
        {LIST2, 8, 9999999999, 7},
        {LIST3, 3, -1, -1},
        {LIST3, 3, 0, 0},
        {LIST3, 3, 1, 0},
        {LIST3, 3, 999, 0},
        {LIST3, 3, 1000, 0},
        {LIST3, 3, 1499, 0},
        {LIST3, 3, 1500, 1},
        {LIST3, 3, 4999, 1},
        {LIST3, 3, 5000, 1},
        {LIST3, 3, 10000, 1},
        {LIST3, 3, 59999, 1},
        {LIST3, 3, 60000, 1},
        {LIST3, 3, 61000, 1},
        {LIST3, 3, 3599999, 1},
        {LIST3, 3, 3600000, 1},
        {LIST3, 3, 3723499, 1},
        {LIST3, 3, 3723500, 1},
        {LIST3, 3, 9999999999, 2},
        {LIST4, 3, -1, -1},
        {LIST4, 3, 0, 0},
        {LIST4, 3, 1, 0},
        {LIST4, 3, 999, 0},
        {LIST4, 3, 1000, 0},
        {LIST4, 3, 1499, 0},
        {LIST4, 3, 1500, 0},
        {LIST4, 3, 4999, 0},
        {LIST4, 3, 5000, 1},
        {LIST4, 3, 10000, 2},
        {LIST4, 3, 59999, 2},
        {LIST4, 3, 60000, 2},
        {LIST4, 3, 61000, 2},
        {LIST4, 3, 3599999, 2},
        {LIST4, 3, 3600000, 2},
        {LIST4, 3, 3723499, 2},
        {LIST4, 3, 3723500, 2},
        {LIST4, 3, 9999999999, 2},
        {LIST5, 2, -1, -1},
        {LIST5, 2, 0, 0},
        {LIST5, 2, 1, 0},
        {LIST5, 2, 999, 1},
        {LIST5, 2, 1000, 1},
        {LIST5, 2, 1499, 1},
        {LIST5, 2, 1500, 1},
        {LIST5, 2, 4999, 1},
        {LIST5, 2, 5000, 1},
        {LIST5, 2, 10000, 1},
        {LIST5, 2, 59999, 1},
        {LIST5, 2, 60000, 1},
        {LIST5, 2, 61000, 1},
        {LIST5, 2, 3599999, 1},
        {LIST5, 2, 3600000, 1},
        {LIST5, 2, 3723499, 1},
        {LIST5, 2, 3723500, 1},
        {LIST5, 2, 9999999999, 1},
        {LIST6, 4, -1, -1},
        {LIST6, 4, 0, 0},
        {LIST6, 4, 1, 0},
        {LIST6, 4, 999, 3},
        {LIST6, 4, 1000, 3},
        {LIST6, 4, 1499, 3},
        {LIST6, 4, 1500, 3},
        {LIST6, 4, 4999, 3},
        {LIST6, 4, 5000, 3},
        {LIST6, 4, 10000, 3},
        {LIST6, 4, 59999, 3},
        {LIST6, 4, 60000, 3},
        {LIST6, 4, 61000, 3},
        {LIST6, 4, 3599999, 3},
        {LIST6, 4, 3600000, 3},
        {LIST6, 4, 3723499, 3},
        {LIST6, 4, 3723500, 3},
        {LIST6, 4, 9999999999, 3},
        {LIST7, 2, -1, -1},
        {LIST7, 2, 0, 0},
        {LIST7, 2, 1, 0},
        {LIST7, 2, 999, 0},
        {LIST7, 2, 1000, 0},
        {LIST7, 2, 1499, 0},
        {LIST7, 2, 1500, 0},
        {LIST7, 2, 4999, 0},
        {LIST7, 2, 5000, 0},
        {LIST7, 2, 10000, 0},
        {LIST7, 2, 59999, 0},
        {LIST7, 2, 60000, 0},
        {LIST7, 2, 61000, 0},
        {LIST7, 2, 3599999, 0},
        {LIST7, 2, 3600000, 0},
        {LIST7, 2, 3723499, 0},
        {LIST7, 2, 3723500, 0},
        {LIST7, 2, 9999999999, 1},
        {LIST8, 0, -1, -1},
        {LIST8, 0, 0, -1},
        {LIST8, 0, 1, -1},
        {LIST8, 0, 999, -1},
        {LIST8, 0, 1000, -1},
        {LIST8, 0, 1499, -1},
        {LIST8, 0, 1500, -1},
        {LIST8, 0, 4999, -1},
        {LIST8, 0, 5000, -1},
        {LIST8, 0, 10000, -1},
        {LIST8, 0, 59999, -1},
        {LIST8, 0, 60000, -1},
        {LIST8, 0, 61000, -1},
        {LIST8, 0, 3599999, -1},
        {LIST8, 0, 3600000, -1},
        {LIST8, 0, 3723499, -1},
        {LIST8, 0, 3723500, -1},
        {LIST8, 0, 9999999999, -1},
    };

    static const InvCase INVALIDS[] = {
        {LIST79, 1},
        {LIST80, 1},
        {LIST81, 1},
        {LIST82, 1},
        {LIST83, 1},
        {LIST84, 1},
        {LIST85, 1},
        {LIST86, 1},
        {LIST87, 1},
        {LIST88, 1},
    };

    static std::vector<Chapter> to_list(const RawCh *r, int n) {
        std::vector<Chapter> out;
        for (int i = 0; i < n; i++) out.push_back(Chapter{r[i].ms, r[i].title, r[i].url});
        return out;
    }

    static std::string dump(const std::vector<Chapter> &c) {
        std::string s;
        for (size_t i = 0; i < c.size(); i++) s += (i ? "\n" : "") + std::to_string(c[i].start_ms) + "|" + c[i].title + "|" + c[i].url;
        return s;
    }

    static std::string show(const std::string &s) {
        std::string o;
        for (char ch : s) {
            if (ch == '\n') o += "\\n";
            else if (ch == '\r') o += "\\r";
            else if (ch == '\t') o += "\\t";
            else o += ch;
        }
        return o.size() > 90 ? o.substr(0, 90) + "..." : o;
    }

    static void test_parse_table() {
        for (size_t i = 0; i < sizeof PARSES / sizeof PARSES[0]; i++) {
            const ParseCase &c = PARSES[i];
            std::string ctx = "parse(\"" + show(c.text) + "\")";
            try {
                std::vector<Chapter> got = parse(c.text);
                if (c.err_line != 0) {
                    CHECK_EQ_CTX(ctx, std::string("no error"), std::string(c.err_msg));
                } else {
                    CHECK_EQ_CTX(ctx, got.size(), static_cast<size_t>(c.count));
                    CHECK_EQ_CTX(ctx, dump(got), std::string(c.dump));
                }
            } catch (const ParseError &e) {
                CHECK_EQ_CTX(ctx, e.line(), c.err_line);
                CHECK_EQ_CTX(ctx, e.message(), std::string(c.err_msg));
                CHECK_EQ_CTX(ctx, std::string(e.what()), "line " + std::to_string(c.err_line) + ": " + c.err_msg);
            }
        }
    }

    static void test_format_table() {
        for (size_t i = 0; i < sizeof FORMATS / sizeof FORMATS[0]; i++) {
            const FormatCase &c = FORMATS[i];
            std::string ctx = "format case " + std::to_string(i) + (c.short_times ? " (short)" : " (long)");
            std::string text = format(to_list(c.list, c.n), c.short_times);
            CHECK_EQ_CTX(ctx, text, std::string(c.text));
            std::vector<Chapter> back = parse(text);
            CHECK_EQ_CTX(ctx, dump(back), dump(to_list(c.list, c.n)));
        }
        /* the default is long times */
        std::vector<Chapter> one = {{3723500, "x", ""}};
        CHECK_EQ(format(one), format(one, false));
        CHECK_EQ(format(one, true), std::string("1:02:03.500 x\n"));
        for (size_t i = 0; i < sizeof INVALIDS / sizeof INVALIDS[0]; i++) {
            bool threw = false;
            try {
                format(to_list(INVALIDS[i].list, INVALIDS[i].n));
            } catch (const std::invalid_argument &) {
                threw = true;
            }
            CHECK_EQ_CTX("invalid format case " + std::to_string(i), threw, true);
        }
    }

    static void test_shift_table() {
        for (size_t i = 0; i < sizeof SHIFTS / sizeof SHIFTS[0]; i++) {
            const ShiftCase &c = SHIFTS[i];
            std::string ctx = "shift case " + std::to_string(i) + " by " + std::to_string(c.offset);
            std::vector<Chapter> got = shift(to_list(c.list, c.n), c.offset);
            CHECK_EQ_CTX(ctx, dump(got), dump(to_list(c.result, c.rn)));
        }
    }

    static void test_durations_table() {
        for (size_t i = 0; i < sizeof DURS / sizeof DURS[0]; i++) {
            const DurCase &c = DURS[i];
            std::string ctx = "durations case " + std::to_string(i) + " total " + std::to_string(c.total);
            if (c.invalid) {
                bool threw = false;
                try {
                    durations(to_list(c.list, c.n), c.total);
                } catch (const std::invalid_argument &) {
                    threw = true;
                }
                CHECK_EQ_CTX(ctx, threw, true);
            } else {
                std::vector<long> got = durations(to_list(c.list, c.n), c.total);
                CHECK_EQ_CTX(ctx, got.size(), static_cast<size_t>(c.n));
                for (size_t k = 0; k < got.size() && k < static_cast<size_t>(c.n); k++) CHECK_EQ_CTX(ctx + " #" + std::to_string(k), got[k], c.result[k]);
            }
        }
    }

    static void test_at_table() {
        for (size_t i = 0; i < sizeof ATS / sizeof ATS[0]; i++) {
            const AtCase &c = ATS[i];
            CHECK_EQ_CTX("chapter_at case " + std::to_string(i) + " ms " + std::to_string(c.ms), chapter_at(to_list(c.list, c.n), c.ms), c.index);
        }
    }

    int main() {
        h_init();
        test_parse_table();
        test_format_table();
        test_shift_table();
        test_durations_table();
        test_at_table();
        return h_report();
    }
''')

LIB = Lib(
    name="chapterfmt", lang="cpp", title="the chapterfmt chapter-list library",
    blurb="The podcast host's publishing tool reads and writes chapter lists in a small text format with chapterfmt, so that players can show named chapters with links.",
    files={"README.md": README1, "include/chapterfmt.hpp": F2, "src/chapterfmt.cpp": F3},
    visible_tests={"tests/test_main.cpp": V4, "tests/harness.hpp": _lang3.CPP_HARNESS},
    hidden_tests={"tests/test_main.cpp": H5},
    mutate=["src/chapterfmt.cpp"], difficulty=3, tags=["parsing", "formatting", "time"],
    verify=_lang3.CPP_VERIFY,
)

_lang3.add(LIB, n=8)

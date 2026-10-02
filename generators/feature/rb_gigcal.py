"""gigcal (ruby): a band's gig calendar extended with search, setlists, ICS, conflicts, fee split, hooks, series, locales."""
import random

from fx import dd
from generators.feature._slices import App, Slice, fmt, register_app

README = dd('''
    # gigcal

    A booking calendar for a touring band, as a small Ruby library (Ruby 3.3, standard library only). Run the tests with
    `ruby -Ilib -Itest -e 'Dir["test/test_*.rb"].sort.each { |f| require "./#{f}" }'`.

    ## Layout

    * `lib/gigcal.rb`: requires everything.
    * `lib/gigcal/gig.rb`: `Gigcal::Gig`.
    * `lib/gigcal/calendar.rb`: `Gigcal::Calendar` and the errors.

    ## Basics

    * `Gigcal::Calendar.new`.
    * `calendar.add(title:, venue:, date:, start:, minutes:, fee_cents: 0, **options)` stores a gig and returns a `Gigcal::Gig`
      with ids 1, 2, 3, ... `title` must not be blank, `date` a `Date`, `start` a 24-hour `"HH:MM"` string, `minutes` and
      `fee_cents` integers (`minutes` positive, `fee_cents` not negative); anything else raises `ArgumentError`, as does an
      unknown option. A failed `add` changes nothing. There are no options yet.
    * `Gig` has `id`, `title`, `venue` (may be empty), `date`, `start`, `minutes`, `fee_cents`, plus `start_minute` and
      `end_minute` (minutes after midnight; the end is not clipped at midnight).
    * `calendar.gigs` lists all gigs ordered by date, start time, id. `calendar.on_date(date)` the gigs of one day.
      `calendar.fetch(id)` and `calendar.remove(id)` (returns the gig) raise `KeyError` for an unknown id.
      `calendar.total_fees` sums the fees.
    * `calendar.agenda` is one line per gig, `YYYY-MM-DD HH:MM VENUE - TITLE (N min)`, each line ending in a newline.
''')

LIB = '''\
require "date"
require_relative "gigcal/gig"
require_relative "gigcal/calendar"
@@uniq requires
'''

GIG = '''\
module Gigcal
  # One booked performance.
  class Gig
    attr_reader :id, :title, :venue, :date, :start, :minutes, :fee_cents
    @@slot gig_attrs

    def initialize(id:, title:, venue:, date:, start:, minutes:, fee_cents: 0)
      @id = id
      @title = title
      @venue = venue
      @date = date
      @start = start
      @minutes = minutes
      @fee_cents = fee_cents
      @@slot gig_init
    end

    # Minutes after midnight at which the gig starts.
    def start_minute
      h, m = start.split(":").map(&:to_i)
      h * 60 + m
    end

    def end_minute
      start_minute + minutes
    end

    @@blocks gig_methods
  end
end
'''

CALENDAR = '''\
module Gigcal
  class Error < StandardError; end

  @@blocks module_items

  class Calendar
    def initialize
      @gigs = {}
      @next_id = 1
      @@slot calendar_init
    end

    def add(title:, venue:, date:, start:, minutes:, fee_cents: 0, **opts)
      raise ArgumentError, "title is required" if title.to_s.strip.empty?
      raise ArgumentError, "date must be a Date" unless date.is_a?(Date)
      raise ArgumentError, "start must look like HH:MM" unless start.to_s.match?(/\\A([01]\\d|2[0-3]):[0-5]\\d\\z/)
      raise ArgumentError, "minutes must be a positive integer" unless minutes.is_a?(Integer) && minutes.positive?
      raise ArgumentError, "fee_cents must be a non-negative integer" unless fee_cents.is_a?(Integer) && fee_cents >= 0
      @@slot add_pre
      raise ArgumentError, "unknown option(s): #{opts.keys.map(&:to_s).sort.join(', ')}" unless opts.empty?
      @@slot add_checks
      gig = Gig.new(id: @next_id, title: title.strip, venue: venue.to_s.strip, date: date, start: start,
                    minutes: minutes, fee_cents: fee_cents)
      @next_id += 1
      @gigs[gig.id] = gig
      @@slot on_add
      gig
    end

    def fetch(id)
      @gigs.fetch(id) { raise KeyError, "no gig with id #{id}" }
    end

    def remove(id)
      gig = fetch(id)
      @gigs.delete(id)
      @@slot on_remove
      gig
    end

    def gigs
      @gigs.values.sort_by { |g| [g.date, g.start_minute, g.id] }
    end

    def on_date(date)
      gigs.select { |g| g.date == date }
    end

    def total_fees
      @gigs.values.sum(&:fee_cents)
    end

    @@default agenda_sig
    def agenda
    @@end
      gigs.map do |g|
        @@default agenda_line
        "#{g.date.iso8601} #{g.start} #{g.venue} - #{g.title} (#{g.minutes} min)\\n"
        @@end
      end.join
    end

    @@blocks methods
  end
end
'''

TEST_HEAD = '''\
require "minitest/autorun"
require "gigcal"
@@uniq requires

D = Date.new(2025, 6, 14) unless defined?(D)
DEFAULT_STARTS = %w[20:00 08:00 10:00 12:00 14:00 16:00 18:00 22:00 06:00 04:00 02:00 00:00].freeze unless defined?(DEFAULT_STARTS)
'''

VISIBLE = TEST_HEAD + '''
class BasicTest < Minitest::Test
  def setup
    @cal = Gigcal::Calendar.new
  end

  # Gigs made without an explicit start get different, non-overlapping times of day.
  def add(title: "Midsummer Ball", venue: "Harbour Hall", date: D, start: nil, minutes: 90, **opts)
    if start.nil?
      start = DEFAULT_STARTS[(@auto ||= 0) % DEFAULT_STARTS.size]
      @auto += 1
    end
    @cal.add(title: title, venue: venue, date: date, start: start, minutes: minutes, **opts)
  end

  def test_add_and_fetch
    g = add(fee_cents: 25_000)
    assert_equal 1, g.id
    assert_equal "Midsummer Ball", g.title
    assert_equal 20 * 60, g.start_minute
    assert_equal 20 * 60 + 90, g.end_minute
    assert_same g, @cal.fetch(1)
    assert_equal 25_000, @cal.total_fees
  end

  def test_validation
    assert_raises(ArgumentError) { add(title: "  ") }
    assert_raises(ArgumentError) { add(start: "25:00") }
    assert_raises(ArgumentError) { add(minutes: 0) }
    assert_raises(ArgumentError) { add(date: "2025-06-14") }
    assert_empty @cal.gigs
  end

  def test_order_and_remove
    add(title: "B", date: D + 1)
    add(title: "A", start: "21:00")
    add(title: "C", start: "09:30")
    assert_equal %w[C A B], @cal.gigs.map(&:title)
    assert_equal "A", @cal.remove(2).title
    assert_raises(KeyError) { @cal.remove(2) }
  end

  def test_agenda
    add(title: "Ball", venue: "Hall")
    assert_equal "2025-06-14 20:00 Hall - Ball (90 min)\\n", @cal.agenda
  end
  @@blocks tests
end
'''

HIDDEN = TEST_HEAD + '''
class FeatureTest < Minitest::Test
  def setup
    @cal = Gigcal::Calendar.new
  end

  # Gigs made without an explicit start get different, non-overlapping times of day.
  def add(title: "Midsummer Ball", venue: "Harbour Hall", date: D, start: nil, minutes: 90, **opts)
    if start.nil?
      start = DEFAULT_STARTS[(@auto ||= 0) % DEFAULT_STARTS.size]
      @auto += 1
    end
    @cal.add(title: title, venue: venue, date: date, start: start, minutes: minutes, **opts)
  end

  def test_base_rules
    g = add(title: "  Jazz  ", venue: " The Cellar ")
    assert_equal ["Jazz", "The Cellar", 0], [g.title, g.venue, g.fee_cents]
    assert_equal "", add(venue: "", date: D + 1).venue
    assert_equal [2, 1], @cal.gigs.map(&:id).reverse
    [{ start: "9:00" }, { start: "24:00" }, { start: "12:60" }, { minutes: -5 }, { minutes: 1.5 }, { fee_cents: -1 }, { fee_cents: "5" }, { date: nil }].each do |bad|
      assert_raises(ArgumentError, bad.inspect) { add(**bad) }
    end
    assert_raises(ArgumentError) { add(colour: "red") }
    assert_equal 2, @cal.gigs.size
    assert_equal 3, add.id
    assert_equal [D, D + 1], @cal.gigs.map(&:date).uniq.sort
    assert_equal 2, @cal.on_date(D).size
    assert_equal [], @cal.on_date(D + 9)
    assert_raises(KeyError) { @cal.fetch(99) }
    assert_equal 0, @cal.total_fees
  end

  def test_base_agenda_order
    add(title: "Late", start: "23:00", minutes: 30)
    add(title: "Early", start: "08:15")
    add(title: "Next day", date: D + 1, venue: "")
    assert_equal "2025-06-14 08:15 Harbour Hall - Early (90 min)\\n2025-06-14 23:00 Harbour Hall - Late (30 min)\\n2025-06-15 20:00  - Next day (90 min)\\n", @cal.agenda
    assert_equal "", Gigcal::Calendar.new.agenda
  end
  @@blocks tests
end
'''


def make_slices(rng: random.Random):
    locs = rng.sample([
        ("de", ["So", "Mo", "Di", "Mi", "Do", "Fr", "Sa"], "%d.%m.%Y", "Min."),
        ("fr", ["di", "lu", "ma", "me", "je", "ve", "sa"], "%d/%m/%Y", "min"),
        ("es", ["do", "lu", "ma", "mi", "ju", "vi", "sa"], "%d-%m-%Y", "min"),
    ], 2)
    S = []

    S.append(Slice(
        id="search", title="Search", d=1,
        pitch=("The calendar has grown long and nobody can find the gig at the harbour.",
               "Band members want to look gigs up by a word of the title or the venue."),
        reqs=("`calendar.find(text)` returns the gigs whose title or venue contains `text` (a substring, ignoring case), in the usual `gigs` order.",
              "A blank or empty `text` returns an empty array; no match returns an empty array too."),
        code={
            "lib/gigcal/calendar.rb::methods": '''
                def find(text)
                  needle = text.to_s.strip.downcase
                  return [] if needle.empty?

                  gigs.select { |g| g.title.downcase.include?(needle) || g.venue.downcase.include?(needle) }
                end
            ''',
        },
        readme=dd('''
            ## Search

            `calendar.find(text)` returns the gigs whose title or venue contains `text` (case-insensitive substring), in `gigs` order;
            blank text finds nothing.
        '''),
        vtests='''
          def test_find_basic
            add(title: "Jazz Night", venue: "Cellar")
            assert_equal ["Jazz Night"], @cal.find("jazz").map(&:title)
          end
        ''',
        tests='''
          def test_find
            add(title: "Midsummer Ball", venue: "Harbour Hall")
            add(title: "Jazz Night", venue: "The Cellar", date: D - 3)
            add(title: "Hall of Fame Gala", venue: "Town Square", date: D + 2)
            assert_equal ["Midsummer Ball", "Hall of Fame Gala"], @cal.find("HALL").map(&:title)
            assert_equal ["Jazz Night"], @cal.find(" cellar ").map(&:title)
            assert_equal [], @cal.find("")
            assert_equal [], @cal.find("   ")
            assert_equal [], @cal.find("zzz")
            assert_equal [], Gigcal::Calendar.new.find("hall")
          end
        ''',
    ))

    S.append(Slice(
        id="setlist", title="Setlists", d=2,
        pitch=("Sound engineers keep asking for the set order and how long it runs.",
               "Each gig needs a setlist that has to fit the time slot."),
        reqs=("`calendar.set_setlist(id, songs)` stores a setlist on a gig: `songs` is an array of `[title, minutes]` pairs (non-blank title, positive integer minutes). The total must not exceed the gig's `minutes`. It replaces any earlier setlist. Unknown gig: `KeyError`; an invalid or too long setlist: `ArgumentError` and the old setlist stays.",
              "`gig.setlist` returns a copy of the pairs in order (empty array by default) and `gig.setlist_minutes` their total. An empty `songs` array is valid and clears the setlist."),
        code={
            "lib/gigcal/gig.rb::gig_init": "@setlist = []",
            "lib/gigcal/gig.rb::gig_methods": '''
                def setlist
                  @setlist.map(&:dup)
                end

                def setlist_minutes
                  @setlist.sum { |_, m| m }
                end

                def assign_setlist(songs)
                  @setlist = songs
                end
            ''',
            "lib/gigcal/calendar.rb::methods": '''
                def set_setlist(id, songs)
                  gig = fetch(id)
                  list = songs.map do |song|
                    title, minutes = song
                    raise ArgumentError, "song title is required" if title.to_s.strip.empty?
                    raise ArgumentError, "song minutes must be a positive integer" unless minutes.is_a?(Integer) && minutes.positive?

                    [title.to_s.strip, minutes]
                  end
                  raise ArgumentError, "setlist is longer than the gig" if list.sum { |_, m| m } > gig.minutes

                  gig.assign_setlist(list)
                  list.map(&:dup)
                end
            ''',
        },
        readme=dd('''
            ## Setlists

            `calendar.set_setlist(id, songs)` with `songs` as `[title, minutes]` pairs whose total fits the gig; `gig.setlist` and
            `gig.setlist_minutes` read it back. Invalid setlists raise `ArgumentError` and leave the old one.
        '''),
        vtests='''
          def test_setlist_basic
            g = add(minutes: 60)
            @cal.set_setlist(g.id, [["Opener", 20]])
            assert_equal 20, g.setlist_minutes
          end
        ''',
        tests='''
          def test_setlist_roundtrip
            g = add(minutes: 60)
            assert_equal [], g.setlist
            assert_equal 0, g.setlist_minutes
            @cal.set_setlist(g.id, [["Opener", 20], [" Hit ", 25], ["Encore", 15]])
            assert_equal [["Opener", 20], ["Hit", 25], ["Encore", 15]], g.setlist
            assert_equal 60, g.setlist_minutes
            g.setlist << ["tampered", 1]
            g.setlist.first[1] = 99
            assert_equal 3, g.setlist.size
            assert_equal "Opener", g.setlist.first[0]
            @cal.set_setlist(g.id, [["Only", 5]])
            assert_equal [["Only", 5]], g.setlist
            @cal.set_setlist(g.id, [])
            assert_equal [], g.setlist
          end

          def test_setlist_errors
            g = add(minutes: 30)
            @cal.set_setlist(g.id, [["Keep", 10]])
            assert_raises(KeyError) { @cal.set_setlist(99, []) }
            [[["Long", 31]], [["A", 20], ["B", 11]], [["", 5]], [["  ", 5]], [["X", 0]], [["X", -3]], [["X", 2.5]], [["X", "5"]]].each do |bad|
              assert_raises(ArgumentError, bad.inspect) { @cal.set_setlist(g.id, bad) }
            end
            assert_equal [["Keep", 10]], g.setlist
            @cal.set_setlist(g.id, [["Exact", 30]])
            assert_equal 30, g.setlist_minutes
          end
        ''',
    ))

    S.append(Slice(
        id="ics", title="Calendar export", d=3,
        pitch=("Everyone in the band wants the gigs in their phone calendar.",
               "The booking agent wants to send an iCalendar file instead of retyping dates."),
        reqs=("`calendar.to_ics(stamp: \"20250101T000000Z\")` returns the calendar as iCalendar text. Lines are separated by `\\r\\n` and the text ends with a final `\\r\\n`; lines are never folded.",
              "The text starts with `BEGIN:VCALENDAR`, `VERSION:2.0`, `PRODID:-//gigcal//EN` and ends with `END:VCALENDAR`. In between, every gig in `gigs` order is a block: `BEGIN:VEVENT`, `UID:gig-ID@gigcal`, `DTSTAMP:` followed by the `stamp` argument as given, `DTSTART:YYYYMMDDTHHMM00` (local time, no zone), `DTEND:` in the same format for start plus `minutes` (rolling over to the next day when needed), `SUMMARY:` the title, `LOCATION:` the venue (the line is left out when the venue is empty), `END:VEVENT`.",
              "In SUMMARY and LOCATION a backslash is written `\\\\`, a comma `\\,`, a semicolon `\\;` and a newline `\\n` (backslash and the letter n)."),
        code={
            "lib/gigcal/calendar.rb::methods": '''
                def to_ics(stamp: "20250101T000000Z")
                  esc = ->(s) { s.to_s.gsub(/[\\\\,;\\n]/) { |c| c == "\\n" ? "\\\\n" : "\\\\" + c } }
                  stamp_of = ->(date, minute) { Time.utc(date.year, date.month, date.day, 0, 0) + minute * 60 }
                  lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//gigcal//EN"]
                  gigs.each do |g|
                    lines << "BEGIN:VEVENT"
                    lines << "UID:gig-#{g.id}@gigcal"
                    lines << "DTSTAMP:#{stamp}"
                    lines << "DTSTART:#{stamp_of.call(g.date, g.start_minute).strftime('%Y%m%dT%H%M00')}"
                    lines << "DTEND:#{stamp_of.call(g.date, g.end_minute).strftime('%Y%m%dT%H%M00')}"
                    lines << "SUMMARY:#{esc.call(g.title)}"
                    lines << "LOCATION:#{esc.call(g.venue)}" unless g.venue.empty?
                    lines << "END:VEVENT"
                  end
                  lines << "END:VCALENDAR"
                  lines.map { |l| "#{l}\\r\\n" }.join
                end
            ''',
        },
        readme=dd('''
            ## Calendar export

            `calendar.to_ics(stamp: "20250101T000000Z")` renders the calendar as iCalendar (`\\r\\n` line ends, no folding): a
            VCALENDAR wrapper and one VEVENT per gig with UID, DTSTAMP, DTSTART, DTEND (local floating times), SUMMARY and (when
            not empty) LOCATION; `\\`, `,`, `;` and newlines are escaped in text values.
        '''),
        vtests='''
          def test_ics_wrapper
            assert_equal "BEGIN:VCALENDAR\\r\\nVERSION:2.0\\r\\nPRODID:-//gigcal//EN\\r\\nEND:VCALENDAR\\r\\n", @cal.to_ics
          end
        ''',
        tests='''
          def test_ics_blocks
            add(title: "Ball, with; extras", venue: "Hall\\\\Annex", start: "20:30", minutes: 90)
            add(title: "Late show", venue: "", date: D + 1, start: "23:30", minutes: 120)
            expected = [
              "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//gigcal//EN",
              "BEGIN:VEVENT", "UID:gig-1@gigcal", "DTSTAMP:20250102T030405Z", "DTSTART:20250614T203000", "DTEND:20250614T220000",
              "SUMMARY:Ball\\\\, with\\\\; extras", "LOCATION:Hall\\\\\\\\Annex", "END:VEVENT",
              "BEGIN:VEVENT", "UID:gig-2@gigcal", "DTSTAMP:20250102T030405Z", "DTSTART:20250615T233000", "DTEND:20250616T013000",
              "SUMMARY:Late show", "END:VEVENT",
              "END:VCALENDAR"
            ]
            assert_equal expected.map { |l| "#{l}\\r\\n" }.join, @cal.to_ics(stamp: "20250102T030405Z")
          end

          def test_ics_default_stamp_and_order
            add(title: "B", date: D + 5)
            add(title: "A")
            text = @cal.to_ics
            assert_includes text, "DTSTAMP:20250101T000000Z\\r\\n"
            assert_equal %w[SUMMARY:A SUMMARY:B], text.split("\\r\\n").grep(/\\ASUMMARY/)
            assert text.end_with?("END:VCALENDAR\\r\\n")
            refute_includes text.delete("\\r"), "\\n\\n"
          end

          def test_ics_escapes_newlines
            add(title: "Line", venue: "North\\nWing")
            assert_includes @cal.to_ics, "LOCATION:North\\\\nWing\\r\\n"
          end
        ''',
    ))

    S.append(Slice(
        id="conflicts", title="Clash detection", d=3,
        pitch=("The band was double-booked twice this summer and nobody noticed until the van was loaded.",
               "Adding a gig that overlaps another one should be caught immediately."),
        reqs=("`add` raises the new error `Gigcal::Conflict` (a subclass of `Gigcal::Error`) when the new gig overlaps a gig on the **same date**. Two gigs overlap when each starts before the other ends: a gig that starts exactly when another ends is fine. Gigs on different dates never conflict (a gig's end is not clipped at midnight).",
              "`Conflict#gig` is the existing gig it collides with (the first one in `calendar.gigs` order if there are several) and the message is `overlaps gig #ID`.",
              "`add(..., force: true)` skips the check. The check runs after the argument validation and the unknown-option check, and a rejected `add` changes nothing (it does not use up an id)."),
        code={
            "lib/gigcal/calendar.rb::module_items": '''
                # Raised by Calendar#add when a gig overlaps another one on the same date.
                class Conflict < Error
                  attr_reader :gig

                  def initialize(gig)
                    @gig = gig
                    super("overlaps gig ##{gig.id}")
                  end
                end
            ''',
            "lib/gigcal/calendar.rb::add_pre": "force = opts.delete(:force)",
            "lib/gigcal/calendar.rb::add_checks": '''
                unless force
                  h, m = start.split(":").map(&:to_i)
                  from = h * 60 + m
                  clash = gigs.find { |g| g.date == date && from < g.end_minute && g.start_minute < from + minutes }
                  if clash
                    err = Conflict.new(clash)
                    @@slot on_conflict
                    raise err
                  end
                end
            ''',
        },
        readme=dd('''
            ## Clash detection

            `add` raises `Gigcal::Conflict` (`#gig` is the gig in the way, message `overlaps gig #ID`) when the new gig overlaps one
            on the same date; touching gigs are fine. `add(..., force: true)` skips the check.
        '''),
        vtests='''
          def test_conflict_basic
            add(start: "20:00", minutes: 60)
            assert_raises(Gigcal::Conflict) { add(title: "Clash", start: "20:30") }
          end
        ''',
        tests='''
          def test_conflict_detection
            a = add(start: "20:00", minutes: 90)
            err = assert_raises(Gigcal::Conflict) { add(title: "Clash", start: "21:00", minutes: 30) }
            assert_same a, err.gig
            assert_equal "overlaps gig #1", err.message
            assert_kind_of Gigcal::Error, err
            assert_equal 1, @cal.gigs.size
            assert_equal 2, add(title: "After", start: "21:30", minutes: 30).id
            assert_equal 3, add(title: "Before", start: "19:00", minutes: 60).id
            assert_equal 4, add(title: "Other day", date: D + 1, start: "20:00").id
            assert_raises(Gigcal::Conflict) { add(title: "Inside", start: "20:10", minutes: 10) }
            assert_raises(Gigcal::Conflict) { add(title: "Around", start: "18:00", minutes: 300) }
          end

          def test_force_and_check_order
            a = add(start: "20:00", minutes: 60)
            add(title: "Forced", start: "20:30", minutes: 60, force: true)
            assert_equal [1, 2], @cal.gigs.map(&:id)
            err = assert_raises(Gigcal::Conflict) { add(title: "Third", start: "20:45", minutes: 10) }
            assert_same a, err.gig
            assert_raises(ArgumentError) { add(title: "", start: "20:10") }
            assert_raises(ArgumentError) { add(start: "20:10", colour: 1) }
            assert_equal 3, add(title: "Free", start: "22:00").id
          end
        ''',
    ))

    S.append(Slice(
        id="fee-split", title="Fee split", d=3,
        pitch=("After every gig the treasurer divides the fee by hand and the cents never add up.",
               "The band splits fees by agreed shares and needs the rounding done fairly."),
        reqs=("`calendar.split_fee(id, shares)` divides the gig's `fee_cents` between the members in `shares`, a hash of name to a positive integer weight, and returns a hash of name to cents with the same keys in the same order. The amounts always add up to the fee exactly.",
              "Method: each member first gets `fee * weight / total_weight` rounded down; the cents that are left over are handed out one each to the members with the largest fractional remainders, ties going to the name that sorts first (`to_s` order).",
              "Unknown gig: `KeyError`. An empty hash, or a weight that is not a positive integer: `ArgumentError`. A fee of 0 gives everybody 0."),
        code={
            "lib/gigcal/calendar.rb::methods": '''
                def split_fee(id, shares)
                  gig = fetch(id)
                  raise ArgumentError, "shares must not be empty" if shares.empty?
                  unless shares.values.all? { |w| w.is_a?(Integer) && w.positive? }
                    raise ArgumentError, "weights must be positive integers"
                  end

                  total = shares.values.sum
                  parts = shares.map do |name, w|
                    q, r = (gig.fee_cents * w).divmod(total)
                    [name, q, r]
                  end
                  left = gig.fee_cents - parts.sum { |_, q, _| q }
                  winners = parts.sort_by { |name, _, r| [-r, name.to_s] }.first(left).map(&:first)
                  parts.to_h { |name, q, _| [name, q + (winners.include?(name) ? 1 : 0)] }
                end
            ''',
        },
        readme=dd('''
            ## Fee split

            `calendar.split_fee(id, shares)` splits the fee by integer weights: everyone gets the rounded-down share, leftover cents
            go to the largest fractional remainders (ties: name order). The result keeps the input order and sums to the fee.
        '''),
        vtests='''
          def test_split_fee_basic
            g = add(fee_cents: 1000)
            assert_equal 1000, @cal.split_fee(g.id, { "ana" => 1, "ben" => 1 }).values.sum
          end
        ''',
        tests='''
          def test_split_fee_leftover_cents
            g = add(fee_cents: 10_000)
            assert_equal({ "ana" => 3334, "ben" => 3333, "cy" => 3333 }, @cal.split_fee(g.id, { "ana" => 1, "ben" => 1, "cy" => 1 }))
            reordered = @cal.split_fee(g.id, { "cy" => 1, "ben" => 1, "ana" => 1 })
            assert_equal({ "cy" => 3333, "ben" => 3333, "ana" => 3334 }, reordered)
            assert_equal %w[cy ben ana], reordered.keys
            h = add(fee_cents: 1000)
            split = @cal.split_fee(h.id, { "a" => 3, "b" => 2, "c" => 2 })
            assert_equal({ "a" => 428, "b" => 286, "c" => 286 }, split)
            assert_equal %w[a b c], split.keys
            assert_equal 1000, split.values.sum
          end

          def test_split_fee_odd_cases
            g = add(fee_cents: 7)
            assert_equal({ solo: 7 }, @cal.split_fee(g.id, { solo: 5 }))
            assert_equal({ "x" => 4, "y" => 3 }, @cal.split_fee(g.id, { "x" => 1, "y" => 1 }))
            assert_equal({ "x" => 2, "y" => 5 }, @cal.split_fee(g.id, { "x" => 2, "y" => 5 }))
            z = add(title: "Free", date: D + 1)
            assert_equal({ "a" => 0, "b" => 0 }, @cal.split_fee(z.id, { "a" => 1, "b" => 2 }))
            big = add(title: "Big", date: D + 2, fee_cents: 99_999)
            assert_equal 99_999, @cal.split_fee(big.id, { "a" => 7, "b" => 11, "c" => 13, "d" => 17 }).values.sum
          end

          def test_split_fee_errors
            g = add(fee_cents: 100)
            assert_raises(KeyError) { @cal.split_fee(99, { "a" => 1 }) }
            assert_raises(ArgumentError) { @cal.split_fee(g.id, {}) }
            [{ "a" => 0 }, { "a" => -1 }, { "a" => 1.5 }, { "a" => "2" }, { "a" => 1, "b" => 0 }].each do |bad|
              assert_raises(ArgumentError, bad.inspect) { @cal.split_fee(g.id, bad) }
            end
          end
        ''',
    ))

    S.append(Slice(
        id="hooks", title="Calendar hooks", d=3,
        pitch=("The tour-manager bot and the website both have to hear about every change to the calendar.",
               "Other tools want to react when gigs are added or removed."),
        reqs=("`calendar.on(event, &block)` registers a handler and returns the block; `event` is `:added` or `:removed`, anything else (or no block) is an `ArgumentError`. `calendar.off(event, block)` removes one registration of that block (`ArgumentError` if it is not registered or the event is unknown).",
              "Handlers are called synchronously, in registration order, with the gig, after the change has been made (`add` after the gig is stored, `remove` after it is gone). Registering the same block twice calls it twice. A call that raises (`ArgumentError`, `KeyError`) fires nothing."),
        code={
            "lib/gigcal/calendar.rb::calendar_init": "@handlers = { added: [], removed: [] }",
            "lib/gigcal/calendar.rb::on_add": "_emit(:added, gig)",
            "lib/gigcal/calendar.rb::on_remove": "_emit(:removed, gig)",
            "lib/gigcal/calendar.rb::methods": '''
                def on(event, &block)
                  raise ArgumentError, "unknown event: #{event.inspect}" unless @handlers.key?(event)
                  raise ArgumentError, "a block is required" unless block

                  @handlers[event] << block
                  block
                end

                def off(event, block)
                  raise ArgumentError, "unknown event: #{event.inspect}" unless @handlers.key?(event)

                  idx = @handlers[event].index { |h| h.equal?(block) }
                  raise ArgumentError, "handler is not registered" unless idx

                  @handlers[event].delete_at(idx)
                  block
                end

                def _emit(event, payload)
                  @@slot emit_hold
                  @handlers[event].dup.each { |h| h.call(payload) }
                end
            ''',
        },
        readme=dd('''
            ## Hooks

            `calendar.on(:added | :removed) { |gig| ... }` and `calendar.off(event, block)`. Handlers run synchronously in
            registration order after the change; failed calls fire nothing.
        '''),
        vtests='''
          def test_hook_basic
            seen = []
            @cal.on(:added) { |g| seen << g.id }
            add
            assert_equal [1], seen
          end
        ''',
        tests='''
          def test_hooks_fire_in_order
            log = []
            h1 = @cal.on(:added) { |g| log << [:one, g.id] }
            @cal.on(:added) { |g| log << [:two, g.id] }
            @cal.on(:removed) { |g| log << [:gone, g.id, @cal.gigs.size] }
            g = add
            assert_equal [[:one, 1], [:two, 1]], log
            assert_kind_of Proc, h1
            @cal.remove(g.id)
            assert_equal [:gone, 1, 0], log.last
            @cal.off(:added, h1)
            add(title: "Again")
            assert_equal [[:one, 1], [:two, 1], [:gone, 1, 0], [:two, 2]], log
          end

          def test_hook_registration_rules
            assert_raises(ArgumentError) { @cal.on(:exploded) { nil } }
            assert_raises(ArgumentError) { @cal.on(:added) }
            assert_raises(ArgumentError) { @cal.off(:added, proc { nil }) }
            assert_raises(ArgumentError) { @cal.off(:exploded, proc { nil }) }
            calls = []
            twice = proc { |g| calls << g.id }
            @cal.on(:added, &twice)
            @cal.on(:added, &twice)
            add
            assert_equal [1, 1], calls
            @cal.off(:added, twice)
            add(title: "Two")
            assert_equal [1, 1, 2], calls
          end

          def test_failed_calls_fire_nothing
            fired = []
            @cal.on(:added) { |g| fired << g.id }
            @cal.on(:removed) { |g| fired << -g.id }
            assert_raises(ArgumentError) { add(title: "") }
            assert_raises(KeyError) { @cal.remove(42) }
            assert_empty fired
          end
        ''',
        cross={
            "conflicts": {
                "reqs": ("With clash detection there is a third event, `:rejected`: when `add` is refused with a `Conflict`, the handlers are called with that error just before it is raised.",),
                "code": {
                    "lib/gigcal/calendar.rb::calendar_init": "@handlers[:rejected] = []",
                    "lib/gigcal/calendar.rb::on_conflict": "_emit(:rejected, err)",
                },
                "tests": '''
                  def test_rejected_hook
                    add(start: "20:00")
                    seen = []
                    @cal.on(:rejected) { |err| seen << [err.class, err.gig.id] }
                    assert_raises(Gigcal::Conflict) { add(title: "Clash", start: "20:30") }
                    assert_equal [[Gigcal::Conflict, 1]], seen
                    add(title: "Forced", start: "20:30", force: true)
                    assert_equal 1, seen.size
                  end
                '''},
        },
    ))

    S.append(Slice(
        id="recurring", title="Weekly series", d=4,
        pitch=("Residencies run for weeks and entering every date by hand invites mistakes.",
               "Weekly residencies should be created in one step and managed as a group."),
        reqs=("`calendar.add_weekly(count:, **gig)` creates `count` gigs (an integer from 2 to 52, else `ArgumentError`), the first on `gig[:date]` and each next one seven days later; the other keywords are those of `add` and are passed to every `add` (so `fee_cents:` or `force:` apply to each). It returns the new gigs in date order.",
              "All or nothing: if any of the `add` calls fails, the error is re-raised and the calendar is exactly as it was, including the id counter and the series counter.",
              "Every gig of a series has `gig.series`, a positive integer that counts successful series from 1 (`nil` for ordinary gigs). `calendar.series(series_id)` lists the gigs of a series in date order (empty array if there are none). `calendar.remove_series(series_id)` removes them all and returns them in date order; it raises `KeyError` when the series has no gigs left. Removing a single gig with `remove` leaves the rest of its series."),
        code={
            "lib/gigcal/gig.rb::gig_attrs": "attr_accessor :series",
            "lib/gigcal/gig.rb::gig_init": "@series = nil",
            "lib/gigcal/calendar.rb::calendar_init": "@series_seq = 0",
            "lib/gigcal/calendar.rb::methods": '''
                def add_weekly(count:, **gig)
                  raise ArgumentError, "count must be an integer from 2 to 52" unless count.is_a?(Integer) && (2..52).cover?(count)
                  raise ArgumentError, "date must be a Date" unless gig[:date].is_a?(Date)

                  saved = [@gigs.dup, @next_id, @series_seq]
                  @@slot series_begin
                  created = []
                  begin
                    count.times { |i| created << add(**gig.merge(date: gig[:date] + 7 * i)) }
                  rescue StandardError
                    @gigs, @next_id, @series_seq = saved
                    @@slot series_rollback
                    raise
                  end
                  @series_seq += 1
                  created.each { |g| g.series = @series_seq }
                  @@slot series_commit
                  created
                end

                def series(series_id)
                  gigs.select { |g| g.series == series_id }
                end

                def remove_series(series_id)
                  members = series(series_id)
                  raise KeyError, "no series with id #{series_id}" if members.empty?

                  members.each { |g| remove(g.id) }
                  members
                end
            ''',
        },
        readme=dd('''
            ## Weekly series

            `calendar.add_weekly(count:, **gig)` creates `count` (2..52) gigs a week apart, all or nothing. `gig.series` numbers the
            successful series from 1; `calendar.series(id)` lists one; `calendar.remove_series(id)` removes it (`KeyError` when empty).
        '''),
        vtests='''
          def test_weekly_basic
            made = @cal.add_weekly(count: 2, title: "R", venue: "", date: D, start: "20:00", minutes: 60)
            assert_equal [D, D + 7], made.map(&:date)
          end
        ''',
        tests='''
          def test_weekly_series
            made = @cal.add_weekly(count: 3, title: "Residency", venue: "Hall", date: D, start: "20:00", minutes: 60, fee_cents: 1000)
            assert_equal [D, D + 7, D + 14], made.map(&:date)
            assert_equal [1, 2, 3], made.map(&:id)
            assert_equal [1, 1, 1], made.map(&:series)
            assert_equal 3000, @cal.total_fees
            other = @cal.add_weekly(count: 2, title: "Other", venue: "", date: D + 1, start: "10:00", minutes: 30)
            assert_equal [2, 2], other.map(&:series)
            assert_nil add(title: "Single", date: D + 3).series
            assert_equal %w[Residency] * 3, @cal.series(1).map(&:title)
            assert_equal [], @cal.series(99)
          end

          def test_weekly_validation_changes_nothing
            [1, 0, 53, "3", nil].each do |bad|
              assert_raises(ArgumentError, bad.inspect) { @cal.add_weekly(count: bad, title: "R", venue: "", date: D, start: "20:00", minutes: 60) }
            end
            assert_raises(ArgumentError) { @cal.add_weekly(count: 3, title: "R", venue: "", date: "soon", start: "20:00", minutes: 60) }
            assert_raises(ArgumentError) { @cal.add_weekly(count: 3, title: "", venue: "", date: D, start: "20:00", minutes: 60) }
            assert_raises(ArgumentError) { @cal.add_weekly(count: 3, title: "R", venue: "", date: D, start: "20:00", minutes: 60, colour: 1) }
            assert_empty @cal.gigs
            made = @cal.add_weekly(count: 52, title: "Year", venue: "", date: D, start: "20:00", minutes: 60)
            assert_equal [1, 52], [made.first.id, made.last.id]
            assert_equal [1], made.map(&:series).uniq
            assert_equal D + 51 * 7, made.last.date
          end

          def test_series_removal
            @cal.add_weekly(count: 3, title: "R", venue: "", date: D, start: "20:00", minutes: 60)
            single = add(title: "Solo", date: D + 1)
            gone = @cal.remove_series(1)
            assert_equal [1, 2, 3], gone.map(&:id)
            assert_equal [single.id], @cal.gigs.map(&:id)
            assert_raises(KeyError) { @cal.remove_series(1) }
            assert_raises(KeyError) { @cal.remove_series(7) }
            again = @cal.add_weekly(count: 2, title: "Again", venue: "", date: D + 40, start: "20:00", minutes: 60)
            assert_equal [2, 2], again.map(&:series)
            @cal.remove(again.first.id)
            assert_equal [again.last.id], @cal.series(2).map(&:id)
            assert_equal [again.last.id], @cal.remove_series(2).map(&:id)
          end
        ''',
        cross={
            "conflicts": {
                "reqs": ("A series that runs into an existing gig fails with `Conflict` and leaves the calendar untouched; `force: true` is passed on to every gig.",),
                "tests": '''
                  def test_series_with_conflict_rolls_back
                    add(title: "Blocker", date: D + 14, start: "20:30", minutes: 60)
                    before = @cal.gigs.map(&:id)
                    err = assert_raises(Gigcal::Conflict) { @cal.add_weekly(count: 4, title: "Series", venue: "", date: D, start: "20:00", minutes: 60) }
                    assert_equal 1, err.gig.id
                    assert_equal before, @cal.gigs.map(&:id)
                    made = @cal.add_weekly(count: 4, title: "Series", venue: "", date: D, start: "20:00", minutes: 60, force: true)
                    assert_equal [2, 3, 4, 5], made.map(&:id)
                    assert_equal [1, 1, 1, 1], made.map(&:series)
                  end
                '''},
            "hooks": {
                "reqs": ("With hooks: `:added` handlers are called once per created gig, in date order, only after the whole series exists (every gig already has its `series`); a series that fails delivers no `:added` events. `remove_series` delivers `:removed` once per gig in date order.",),
                "code": {
                    "lib/gigcal/calendar.rb::calendar_init": "@held = nil",
                    "lib/gigcal/calendar.rb::emit_hold": '''
                        if @held && event == :added
                          @held << [event, payload]
                          return
                        end
                    ''',
                    "lib/gigcal/calendar.rb::series_begin": "@held = []",
                    "lib/gigcal/calendar.rb::series_rollback": "@held = nil",
                    "lib/gigcal/calendar.rb::series_commit": '''
                        held = @held
                        @held = nil
                        held.each { |ev, g| _emit(ev, g) }
                    ''',
                },
                "tests": '''
                  def test_series_events_after_success
                    log = []
                    @cal.on(:added) { |g| log << [g.id, g.series, @cal.gigs.size] }
                    @cal.add_weekly(count: 3, title: "R", venue: "", date: D, start: "20:00", minutes: 60)
                    assert_equal [[1, 1, 3], [2, 1, 3], [3, 1, 3]], log
                    add(title: "Single", date: D + 1)
                    assert_equal [4, nil, 4], log.last
                  end

                  def test_series_removal_events
                    @cal.add_weekly(count: 3, title: "R", venue: "", date: D, start: "20:00", minutes: 60)
                    log = []
                    @cal.on(:removed) { |g| log << g.id }
                    @cal.remove_series(1)
                    assert_equal [1, 2, 3], log
                  end
                '''},
        },
    ))

    S.append(Slice(
        id="agenda-locale", title="Localised agenda", d=2,
        pitch=("The German and French support acts cannot read ISO dates on the printed schedule.",
               "The printed agenda should be readable for our crew in their own conventions."),
        reqs=("`calendar.agenda(locale: :iso)` takes a locale; `:iso` is today's output. An unknown locale is an `ArgumentError` (also for an empty calendar).",
              *(f"`:{l[0]}`: each line is `WD DATE START VENUE - TITLE (N UNIT)` where WD is the weekday abbreviation (Sunday to Saturday: {', '.join(l[1])}), DATE is written `{l[2].replace('%d', 'dd').replace('%m', 'mm').replace('%Y', 'yyyy')}` and UNIT is `{l[3]}`." for l in locs),
              "Lines still end with a newline and appear in the usual order."),
        code={
            "lib/gigcal/calendar.rb::module_items": "LOCALES = {\n  iso: nil,\n" + "".join(f"  {l[0]}: [{l[1]!r}, {l[2]!r}, {l[3]!r}],\n" for l in locs).replace("'", '"') + "}.freeze",
            "lib/gigcal/calendar.rb::agenda_sig": '''
                def agenda(locale: :iso)
                  raise ArgumentError, "unknown locale: #{locale.inspect}" unless LOCALES.key?(locale)

            ''',
            "lib/gigcal/calendar.rb::agenda_line": '''
                if locale == :iso
                  "#{g.date.iso8601} #{g.start} #{g.venue} - #{g.title} (#{g.minutes} min)\\n"
                else
                  days, pattern, unit = LOCALES[locale]
                  "#{days[g.date.wday]} #{g.date.strftime(pattern)} #{g.start} #{g.venue} - #{g.title} (#{g.minutes} #{unit})\\n"
                end
            ''',
        },
        readme=dd('''
            ## Localised agenda

            `calendar.agenda(locale: :iso)` also speaks ''' + ", ".join(f"`:{l[0]}`" for l in locs) + '''; a locale changes the weekday prefix, the date
            format and the minutes label. Unknown locales raise `ArgumentError`.
        '''),
        vtests='''
          def test_agenda_iso_locale
            add(title: "Ball", venue: "Hall")
            assert_equal "2025-06-14 20:00 Hall - Ball (90 min)\\n", @cal.agenda
          end
        ''',
        tests=fmt('''
          def test_agenda_locales
            add(title: "Ball", venue: "Hall")
            add(title: "Brunch", venue: "", date: D + 1, start: "11:00", minutes: 45)
            assert_equal @cal.agenda, @cal.agenda(locale: :iso)
            __CHECKS__
          end

          def test_agenda_locale_errors
            [:xx, "de", nil].each do |bad|
              assert_raises(ArgumentError, bad.inspect) { @cal.agenda(locale: bad) }
              assert_raises(ArgumentError) { Gigcal::Calendar.new.agenda(locale: bad) }
            end
            assert_equal "", Gigcal::Calendar.new.agenda(locale: :__L1__)
          end
        ''', L1=locs[0][0], CHECKS="\n            ".join(
            f'assert_equal "{l[1][6]} {__import__("datetime").date(2025, 6, 14).strftime(l[2])} 20:00 Hall - Ball (90 {l[3]})\\n{l[1][0]} {__import__("datetime").date(2025, 6, 15).strftime(l[2])} 11:00  - Brunch (45 {l[3]})\\n", @cal.agenda(locale: :{l[0]})'
            for l in locs)),
    ))

    return S


APP = App(
    name="gigcal", lang="ruby", title="the gig calendar library", role="the band's booking agent", key="GIG",
    base={
        "README.md": README + "\n@@blocks features\n",
        "lib/gigcal.rb": LIB,
        "lib/gigcal/gig.rb": GIG,
        "lib/gigcal/calendar.rb": CALENDAR,
        ".gitignore": "*.gem\n",
    },
    visible={"test/test_basic.rb": VISIBLE},
    hidden={"test/test_features.rb": HIDDEN},
)

register_app("feature-rb-gigcal", APP, make_slices, n=18, summary="band gig calendar: search, setlists, ICS, clashes, fee split, hooks, series, locales")

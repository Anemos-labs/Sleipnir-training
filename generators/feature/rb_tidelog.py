"""tidelog (ruby): a harbour tide table extended with statistics, ranges, datum, interpolation, corrections, CSV, alarms, windows, merging."""
import random

from fx import dd
from generators.feature._slices import App, Slice, fmt, register_app

README = dd('''
    # tidelog

    A tide table for a harbour office, as a small Ruby library (Ruby 3.3, standard library only). Run the tests with
    `ruby -Ilib -Itest -e 'Dir["test/test_*.rb"].sort.each { |f| require "./#{f}" }'`.

    ## Layout

    * `lib/tidelog.rb`: requires everything and has `Tidelog.label`.
    * `lib/tidelog/reading.rb`: `Tidelog::Reading`.
    * `lib/tidelog/table.rb`: `Tidelog::Table` and the errors.

    ## Basics

    Time is a whole number of minutes counted from midnight of day 0 of the log; heights are whole centimetres (they may
    be negative).

    * `Tidelog::Table.new(port)`; the port name must not be blank and is stripped (`ArgumentError`), and `table.port` returns
      it. Unknown options raise `ArgumentError` (there are no options yet).
    * `table.add(minute, height_cm)` stores a reading and returns the `Tidelog::Reading` (`minute`, `height_cm`). The minute
      must be a non-negative integer and the height an integer (`ArgumentError`); a second reading for the same minute
      raises `Tidelog::DuplicateReading`. A failed `add` changes nothing.
    * `table.readings` is a new array of the readings ordered by minute, `table.count` their number. `table.highest` and
      `table.lowest` return the reading with the largest / smallest height (the earliest one on a tie) or `nil` when the
      table is empty.
    * `Tidelog.label(minute)` formats a minute as `D<day> HH:MM` (`D1 01:15` for 1515). `reading.to_s` is
      `<label> <height> cm`, and `table.report` has one such line per reading, each ending in a newline.
''')

LIB = '''\
require_relative "tidelog/reading"
require_relative "tidelog/table"
@@uniq requires

module Tidelog
  # "D1 01:15" for minute 1515.
  def self.label(minute)
    format("D%d %02d:%02d", minute / 1440, minute % 1440 / 60, minute % 60)
  end
end
'''

READING = '''\
module Tidelog
  # One measured water height.
  class Reading
    attr_reader :minute, :height_cm

    def initialize(minute, height_cm)
      @minute = minute
      @height_cm = height_cm
    end

    def to_s
      "#{Tidelog.label(minute)} #{height_cm} cm"
    end

    @@blocks reading_methods
  end
end
'''

TABLE = '''\
module Tidelog
  class Error < StandardError; end

  class DuplicateReading < Error; end

  @@blocks module_items

  class Table
    attr_reader :port

    def initialize(port, **opts)
      raise ArgumentError, "port is required" if port.to_s.strip.empty?

      @@slot init_opts
      raise ArgumentError, "unknown option(s): #{opts.keys.map(&:to_s).sort.join(', ')}" unless opts.empty?

      @port = port.to_s.strip
      @readings = []
      @@slot table_init
    end

    def add(minute, height_cm)
      raise ArgumentError, "minute must be a non-negative integer" unless minute.is_a?(Integer) && minute >= 0
      raise ArgumentError, "height must be an integer" unless height_cm.is_a?(Integer)
      raise DuplicateReading, "there is already a reading at minute #{minute}" if @readings.any? { |r| r.minute == minute }

      @@slot height_adjust
      reading = Reading.new(minute, height_cm)
      @readings << reading
      @readings.sort_by!(&:minute)
      @@slot on_add
      reading
    end

    def readings
      @readings.dup
    end

    def count
      @readings.size
    end

    def highest
      @readings.reduce(nil) { |best, r| best.nil? || r.height_cm > best.height_cm ? r : best }
    end

    def lowest
      @readings.reduce(nil) { |best, r| best.nil? || r.height_cm < best.height_cm ? r : best }
    end

    def report
      @readings.map { |r| "#{r}\\n" }.join
    end

    @@blocks methods
  end
end
'''

TEST_HEAD = '''\
require "minitest/autorun"
require "tidelog"
@@uniq requires

# A day and a half of a semi-diurnal tide: high at 03:00 and 09:00, low at 06:00, falling to the end.
DATA = [[0, 120], [180, 340], [360, 90], [540, 310], [720, 60]].freeze unless defined?(DATA)
'''

VISIBLE = TEST_HEAD + '''
class BasicTest < Minitest::Test
  def setup
    @t = Tidelog::Table.new("Port Marrow")
  end

  def fill(table = @t, data = DATA)
    data.each { |m, h| table.add(m, h) }
    table
  end

  def test_add_and_order
    fill(@t, DATA.reverse)
    assert_equal 5, @t.count
    assert_equal [0, 180, 360, 540, 720], @t.readings.map(&:minute)
    assert_equal 340, @t.highest.height_cm
    assert_equal 60, @t.lowest.height_cm
    assert_raises(Tidelog::DuplicateReading) { @t.add(180, 1) }
    assert_equal 5, @t.count
  end

  def test_validation
    assert_raises(ArgumentError) { @t.add(-1, 10) }
    assert_raises(ArgumentError) { @t.add(1.5, 10) }
    assert_raises(ArgumentError) { @t.add(5, "10") }
    assert_raises(ArgumentError) { Tidelog::Table.new("  ") }
    assert_equal 0, @t.count
  end

  def test_report
    @t.add(75, 312)
    @t.add(1515, -8)
    assert_equal "D0 01:15 312 cm\\nD1 01:15 -8 cm\\n", @t.report
    assert_equal "D1 01:15", Tidelog.label(1515)
  end
  @@blocks tests
end
'''

HIDDEN = TEST_HEAD + '''
class FeatureTest < Minitest::Test
  def setup
    @t = Tidelog::Table.new("Port Marrow")
  end

  def fill(table = @t, data = DATA)
    data.each { |m, h| table.add(m, h) }
    table
  end

  def test_base_rules
    assert_equal "Harbour", Tidelog::Table.new("  Harbour ").port
    assert_raises(ArgumentError) { Tidelog::Table.new("") }
    assert_raises(ArgumentError) { Tidelog::Table.new(nil) }
    assert_raises(ArgumentError) { Tidelog::Table.new("Harbour", colour: "blue") }
    r = @t.add(0, 100)
    assert_equal [0, 100], [r.minute, r.height_cm]
    @t.add(10, 100)
    assert_equal 0, @t.highest.minute
    assert_equal 0, @t.lowest.minute
    @t.add(5, 100)
    assert_equal 0, @t.highest.minute
    [[nil, 5], ["3", 5], [3, nil], [3, 2.5], [-10, 5]].each do |m, h|
      assert_raises(ArgumentError, [m, h].inspect) { @t.add(m, h) }
    end
    assert_raises(Tidelog::DuplicateReading) { @t.add(5, 7) }
    assert_equal [0, 5, 10], @t.readings.map(&:minute)
    assert_equal [100, 100, 100], @t.readings.map(&:height_cm)
    @t.readings.clear
    assert_equal 3, @t.count
    assert_kind_of Tidelog::Error, Tidelog::DuplicateReading.new
    empty = Tidelog::Table.new("Nowhere")
    assert_nil empty.highest
    assert_nil empty.lowest
    assert_equal "", empty.report
  end

  def test_base_labels_and_report
    assert_equal "D0 00:00", Tidelog.label(0)
    assert_equal "D0 23:59", Tidelog.label(1439)
    assert_equal "D2 10:07", Tidelog.label(2 * 1440 + 607)
    @t.add(2 * 1440 + 607, -250)
    @t.add(59, 0)
    assert_equal "D0 00:59 0 cm", @t.readings.first.to_s
    assert_equal "D0 00:59 0 cm\\nD2 10:07 -250 cm\\n", @t.report
    assert_equal 0, @t.highest.height_cm
    assert_equal(-250, @t.lowest.height_cm)
  end
  @@blocks tests
end
'''


def make_slices(rng: random.Random):
    sep = rng.choice([",", ";"])
    kinds = rng.choice([("high", "low"), ("peak", "trough")])
    S = []

    S.append(Slice(
        id="mean", title="Mean height and range", d=1,
        pitch=("The harbour master quotes the mean tide level in every morning briefing and works it out on paper.",
               "The office wants two summary numbers for the weekly bulletin."),
        reqs=("`table.mean_height` returns the mean of all heights as an integer, rounded half up (towards positive infinity, so `-2.5` becomes `-2` and `100.5` becomes `101`), and `nil` for an empty table.",
              "`table.tidal_range` returns the highest height minus the lowest height (0 for a single reading, `nil` for an empty table)."),
        code={
            "lib/tidelog/table.rb::methods": '''
                def mean_height
                  return nil if @readings.empty?

                  (Rational(@readings.sum(&:height_cm), @readings.size) + Rational(1, 2)).floor
                end

                def tidal_range
                  return nil if @readings.empty?

                  highest.height_cm - lowest.height_cm
                end
            ''',
        },
        readme=dd('''
            ## Mean height and range

            `table.mean_height` is the mean height rounded half up (towards +infinity); `table.tidal_range` is highest minus
            lowest. Both are `nil` for an empty table.
        '''),
        vtests='''
          def test_mean_basic
            fill
            assert_equal 184, @t.mean_height
            assert_equal 280, @t.tidal_range
          end
        ''',
        tests='''
          def test_mean_and_range
            assert_nil @t.mean_height
            assert_nil @t.tidal_range
            fill
            assert_equal 184, @t.mean_height
            assert_equal 280, @t.tidal_range
            one = Tidelog::Table.new("One")
            one.add(5, -30)
            assert_equal(-30, one.mean_height)
            assert_equal 0, one.tidal_range
          end

          def test_mean_rounds_half_up
            a = fill(Tidelog::Table.new("A"), [[0, 100], [10, 101]])
            assert_equal 101, a.mean_height
            b = fill(Tidelog::Table.new("B"), [[0, -3], [10, -2]])
            assert_equal(-2, b.mean_height)
            c = fill(Tidelog::Table.new("C"), [[0, -4], [10, -2], [20, -2]])
            assert_equal(-3, c.mean_height)
            d = fill(Tidelog::Table.new("D"), [[0, 1], [10, 1], [20, 2]])
            assert_equal 1, d.mean_height
          end
        ''',
    ))

    S.append(Slice(
        id="between", title="Readings in a time range", d=1,
        pitch=("Pilots ask what the gauge showed during the night shift and the office scrolls through the whole report.",
               "People want the readings of a stretch of time instead of the whole table."),
        reqs=("`table.between(from, to)` returns the readings with `from <= minute <= to` (both ends included), ordered by minute. Both arguments must be integers and `from` must not be after `to` (`ArgumentError`). A range without readings gives an empty array.",),
        code={
            "lib/tidelog/table.rb::methods": '''
                def between(from, to)
                  raise ArgumentError, "from and to must be integers" unless from.is_a?(Integer) && to.is_a?(Integer)
                  raise ArgumentError, "from must not be after to" if from > to

                  @readings.select { |r| r.minute >= from && r.minute <= to }
                end
            ''',
        },
        readme="## Readings in a time range\n\n`table.between(from, to)` returns the readings with `from <= minute <= to` in order; invalid or reversed ranges raise `ArgumentError`.\n",
        vtests='''
          def test_between_basic
            fill
            assert_equal [180, 360], @t.between(100, 400).map(&:minute)
          end
        ''',
        tests='''
          def test_between
            fill
            assert_equal [180, 360, 540], @t.between(180, 540).map(&:minute)
            assert_equal [360], @t.between(360, 360).map(&:minute)
            assert_equal [0], @t.between(0, 179).map(&:minute)
            assert_equal [], @t.between(181, 359)
            assert_equal [], @t.between(1000, 2000)
            assert_equal 5, @t.between(0, 720).size
            assert_equal [], Tidelog::Table.new("E").between(0, 10)
          end

          def test_between_validation
            fill
            assert_raises(ArgumentError) { @t.between(10, 5) }
            assert_raises(ArgumentError) { @t.between(1.5, 5) }
            assert_raises(ArgumentError) { @t.between(nil, 5) }
            assert_raises(ArgumentError) { @t.between(0, "9") }
          end
        ''',
    ))

    S.append(Slice(
        id="datum", title="Chart datum offset", d=2,
        pitch=("The gauge at the quay was re-levelled and its zero no longer matches the chart datum.",
               "Readings from the quay gauge are off by a fixed offset."),
        reqs=("`Tidelog::Table.new(port, datum_cm: 0)` takes an integer option `datum_cm` (default 0; anything else is an `ArgumentError`) and `table.datum_cm` returns it. `add` takes the raw gauge height and stores gauge height plus datum; every height the table reports (`Reading#height_cm`, `highest`, `report`, ...) is that chart height.",),
        code={
            "lib/tidelog/table.rb::init_opts": '''
                datum = opts.delete(:datum_cm) { 0 }
                raise ArgumentError, "datum_cm must be an integer" unless datum.is_a?(Integer)

                @datum_cm = datum
            ''',
            "lib/tidelog/table.rb::methods": '''
                attr_reader :datum_cm
            ''',
            "lib/tidelog/table.rb::height_adjust": "height_cm += @datum_cm",
        },
        readme="## Chart datum offset\n\n`Tidelog::Table.new(port, datum_cm: 0)`: `add` stores the gauge height plus the datum, so all reported heights are chart heights. `table.datum_cm` returns the offset.\n",
        vtests='''
          def test_datum_basic
            t = Tidelog::Table.new("Quay", datum_cm: 20)
            assert_equal 120, t.add(0, 100).height_cm
          end
        ''',
        tests='''
          def test_datum
            t = Tidelog::Table.new("Port Marrow", datum_cm: 25)
            assert_equal 25, t.datum_cm
            assert_equal 125, t.add(0, 100).height_cm
            t.add(60, -30)
            assert_equal [125, -5], t.readings.map(&:height_cm)
            assert_equal 125, t.highest.height_cm
            assert_equal(-5, t.lowest.height_cm)
            assert_equal "D0 00:00 125 cm\\nD0 01:00 -5 cm\\n", t.report
            assert_equal 0, Tidelog::Table.new("X").datum_cm
            assert_equal(-40, Tidelog::Table.new("X", datum_cm: -40).add(0, 0).height_cm)
          end

          def test_datum_validation
            assert_raises(ArgumentError) { Tidelog::Table.new("X", datum_cm: 1.5) }
            assert_raises(ArgumentError) { Tidelog::Table.new("X", datum_cm: "5") }
            assert_raises(ArgumentError) { Tidelog::Table.new("X", datum_cm: nil) }
            assert_raises(ArgumentError) { Tidelog::Table.new("X", datum_cm: 5, bogus: 1) }
            assert_raises(ArgumentError) { Tidelog::Table.new("", datum_cm: 5) }
          end
        ''',
        cross={
            "interpolate": {"tests": '''
              def test_datum_applies_before_interpolation
                t = Tidelog::Table.new("Q", datum_cm: 10)
                t.add(0, 0)
                t.add(10, 10)
                assert_equal 10, t.height_at(0)
                assert_equal 15, t.height_at(5)
              end
            '''},
            "alarm": {
                "reqs": ("Alarm thresholds are compared with the chart height (the gauge height plus the datum).",),
                "tests": '''
                  def test_alarm_sees_chart_heights
                    t = Tidelog::Table.new("Q", datum_cm: 50)
                    seen = []
                    t.alarm(300) { |r| seen << r.height_cm }
                    t.add(0, 240)
                    t.add(10, 250)
                    t.add(20, 251)
                    assert_equal [300, 301], seen
                  end
                '''},
            "csv": {
                "reqs": ("`to_csv` writes the heights as `readings` reports them (chart heights, datum included); `Table.from_csv` always builds a table without a datum, so the numbers in the file are taken as they are.",),
                "tests": '''
                  def test_csv_uses_chart_heights
                    t = Tidelog::Table.new("Q", datum_cm: 10)
                    t.add(0, 90)
                    assert_equal "minute__SEP__height_cm\\n0__SEP__100\\n", t.to_csv
                    back = Tidelog::Table.from_csv("Q", t.to_csv)
                    assert_equal 100, back.readings.first.height_cm
                    assert_equal 0, back.datum_cm
                  end
                '''.replace("__SEP__", sep)},
            "merge": {
                "reqs": ("`merge` copies the heights of the other table as they are, without applying this table's datum again.",),
                "tests": '''
                  def test_merge_does_not_reapply_datum
                    a = Tidelog::Table.new("A", datum_cm: 10)
                    a.add(0, 0)
                    b = Tidelog::Table.new("B")
                    b.add(60, 100)
                    a.merge(b)
                    assert_equal [10, 100], a.readings.map(&:height_cm)
                  end
                '''},
        },
    ))

    S.append(Slice(
        id="interpolate", title="Height at any minute", d=2,
        pitch=("Skippers ask for the water level at 14:20, and the gauge was only read every three hours.",
               "The pilot office wants to know the height between two readings."),
        reqs=("`table.height_at(minute)` returns the height at any minute between the first and the last reading, interpolating linearly between the two neighbouring readings. At a reading it returns that reading's height. The result is an integer, rounded half up (towards positive infinity, so `-3.5` becomes `-3`).",
              "A minute that is not a non-negative integer is an `ArgumentError`; a minute before the first or after the last reading (or any minute of an empty table) raises `Tidelog::OutOfRange`, a subclass of `Tidelog::Error`."),
        code={
            "lib/tidelog/table.rb::module_items": "class OutOfRange < Error; end",
            "lib/tidelog/table.rb::methods": '''
                def height_at(minute)
                  raise ArgumentError, "minute must be a non-negative integer" unless minute.is_a?(Integer) && minute >= 0
                  if @readings.empty? || minute < @readings.first.minute || minute > @readings.last.minute
                    raise OutOfRange, "no readings around minute #{minute}"
                  end

                  lo = @readings.select { |r| r.minute <= minute }.last
                  return lo.height_cm if lo.minute == minute

                  hi = @readings.find { |r| r.minute > minute }
                  exact = Rational(lo.height_cm * (hi.minute - minute) + hi.height_cm * (minute - lo.minute), hi.minute - lo.minute)
                  (exact + Rational(1, 2)).floor
                end
            ''',
        },
        readme="## Height at any minute\n\n`table.height_at(minute)` interpolates linearly between neighbouring readings and rounds half up; outside the readings it raises `Tidelog::OutOfRange`.\n",
        vtests='''
          def test_height_at_basic
            fill
            assert_equal 230, @t.height_at(90)
            assert_equal 340, @t.height_at(180)
          end
        ''',
        tests='''
          def test_height_at
            fill
            assert_equal [120, 121, 122, 124, 230, 339, 340], [0, 1, 2, 3, 90, 179, 180].map { |m| @t.height_at(m) }
            assert_equal [328, 215, 91, 90], [189, 270, 359, 360].map { |m| @t.height_at(m) }
            assert_equal [200, 309, 310, 61, 60], [450, 539, 540, 719, 720].map { |m| @t.height_at(m) }
          end

          def test_height_at_rounds_half_up
            t = fill(Tidelog::Table.new("Neg"), [[0, -5], [2, -2]])
            assert_equal(-3, t.height_at(1))
            u = fill(Tidelog::Table.new("Pos"), [[0, 1], [2, 2]])
            assert_equal 2, u.height_at(1)
            v = fill(Tidelog::Table.new("Down"), [[0, 2], [2, 1]])
            assert_equal 2, v.height_at(1)
          end

          def test_height_at_errors
            fill
            assert_raises(ArgumentError) { @t.height_at(-1) }
            assert_raises(ArgumentError) { @t.height_at(1.5) }
            assert_raises(ArgumentError) { @t.height_at("5") }
            assert_raises(Tidelog::OutOfRange) { @t.height_at(721) }
            assert_raises(Tidelog::Error) { @t.height_at(5000) }
            assert_raises(Tidelog::OutOfRange) { Tidelog::Table.new("E").height_at(0) }
            late = fill(Tidelog::Table.new("Late"), [[100, 5], [200, 9]])
            assert_raises(Tidelog::OutOfRange) { late.height_at(99) }
            assert_equal 5, late.height_at(100)
          end
        ''',
    ))

    S.append(Slice(
        id="corrections", title="Gauge corrections", d=2,
        pitch=("The gauge reader fat-fingered a reading last week and the table has been wrong ever since.",
               "Readings need to be corrected after the fact, with a trail."),
        reqs=("`table.correct(minute, delta_cm)` adds `delta_cm` to the height of the reading at exactly that minute and returns the reading. `delta_cm` must be a non-zero integer (`ArgumentError`, checked first); a minute without a reading raises `KeyError`.",
              "`table.corrections` returns a new array of `[minute, delta_cm]` pairs, one per successful correction, in the order they were made."),
        code={
            "lib/tidelog/reading.rb::reading_methods": '''
                # Used by the table; not meant to be called from outside.
                def apply_delta(delta)
                  @height_cm += delta
                end
            ''',
            "lib/tidelog/table.rb::table_init": "@corrections = []",
            "lib/tidelog/table.rb::methods": '''
                def correct(minute, delta_cm)
                  raise ArgumentError, "delta must be a non-zero integer" unless delta_cm.is_a?(Integer) && !delta_cm.zero?

                  reading = @readings.find { |r| r.minute == minute }
                  raise KeyError, "no reading at minute #{minute}" if reading.nil?

                  reading.apply_delta(delta_cm)
                  @corrections << [minute, delta_cm]
                  reading
                end

                def corrections
                  @corrections.map(&:dup)
                end
            ''',
        },
        readme="## Gauge corrections\n\n`table.correct(minute, delta_cm)` adjusts one reading (non-zero integer delta; `KeyError` for a minute without a reading) and `table.corrections` lists the `[minute, delta]` pairs made so far.\n",
        vtests='''
          def test_correct_basic
            fill
            assert_equal 350, @t.correct(180, 10).height_cm
          end
        ''',
        tests='''
          def test_correct
            fill
            assert_equal [], @t.corrections
            r = @t.correct(180, -40)
            assert_equal 300, r.height_cm
            assert_equal 300, @t.readings[1].height_cm
            @t.correct(180, 5)
            @t.correct(0, -120)
            assert_equal 0, @t.readings.first.height_cm
            assert_equal [[180, -40], [180, 5], [0, -120]], @t.corrections
            assert_equal 310, @t.highest.height_cm
            @t.corrections.clear
            assert_equal 3, @t.corrections.size
          end

          def test_correct_errors
            fill
            assert_raises(ArgumentError) { @t.correct(180, 0) }
            assert_raises(ArgumentError) { @t.correct(180, 1.5) }
            assert_raises(ArgumentError) { @t.correct(180, "5") }
            assert_raises(ArgumentError) { @t.correct(999, 0) }
            assert_raises(KeyError) { @t.correct(181, 5) }
            assert_equal 340, @t.readings[1].height_cm
            assert_equal [], @t.corrections
          end
        ''',
    ))

    k_hi, k_lo = kinds
    S.append(Slice(
        id="turning", title="High and low water", d=3,
        pitch=("The harbour bulletin lists the times of high and low water, and somebody has to pick them out of the readings by eye.",
               "The office wants the turning points of the tide found automatically."),
        reqs=(f"`table.turning_points` returns the turning points of the tide as an array of `[kind, reading]` pairs ordered by minute, where `kind` is `:{k_hi}` or `:{k_lo}`.",
              f"Consecutive readings with the same height count as one level (represented by the earliest reading of that run). A level is a `:{k_hi}` when the levels on both sides are lower and a `:{k_lo}` when both are higher. The first and the last level are never turning points; fewer than three levels give an empty array."),
        code={
            "lib/tidelog/table.rb::methods": f'''
                def turning_points
                  levels = []
                  @readings.each do |r|
                    if levels.last && levels.last.height_cm == r.height_cm
                      next
                    end
                    levels << r
                  end
                  found = []
                  (1...(levels.size - 1)).each do |i|
                    before = levels[i - 1].height_cm
                    here = levels[i].height_cm
                    after = levels[i + 1].height_cm
                    if here > before && here > after
                      found << [:{k_hi}, levels[i]]
                    elsif here < before && here < after
                      found << [:{k_lo}, levels[i]]
                    end
                  end
                  found
                end
            ''',
        },
        readme=f"## High and low water\n\n`table.turning_points` returns `[kind, reading]` pairs (`:{k_hi}` / `:{k_lo}`); equal consecutive heights form one level, represented by its earliest reading, and the first and last level never count.\n",
        vtests=f'''
          def test_turning_basic
            fill
            assert_equal [:{k_hi}, :{k_lo}, :{k_hi}], @t.turning_points.map(&:first)
          end
        ''',
        tests=fmt('''
          def test_turning_points
            fill
            tp = @t.turning_points
            assert_equal [[:__HI__, 180], [:__LO__, 360], [:__HI__, 540]], tp.map { |k, r| [k, r.minute] }
            assert_equal [340, 90, 310], tp.map { |_, r| r.height_cm }
            assert_equal [], Tidelog::Table.new("E").turning_points
            assert_equal [], fill(Tidelog::Table.new("Two"), [[0, 1], [5, 9]]).turning_points
            assert_equal [], fill(Tidelog::Table.new("Ramp"), [[0, 1], [5, 2], [9, 3]]).turning_points
          end

          def test_turning_points_with_plateaus
            plateau = [[0, 10], [10, 30], [20, 30], [30, 30], [40, 5], [50, 5], [60, 20]]
            tp = fill(Tidelog::Table.new("Flat"), plateau).turning_points
            assert_equal [[:__HI__, 10], [:__LO__, 40]], tp.map { |k, r| [k, r.minute] }
            lead = fill(Tidelog::Table.new("Lead"), [[0, 5], [10, 5], [20, 9], [30, 2]]).turning_points
            assert_equal [[:__HI__, 20]], lead.map { |k, r| [k, r.minute] }
            tail = fill(Tidelog::Table.new("Tail"), [[0, 1], [10, 8], [20, 3], [30, 3], [40, 3]]).turning_points
            assert_equal [[:__HI__, 10]], tail.map { |k, r| [k, r.minute] }
            same = fill(Tidelog::Table.new("Same"), [[0, 4], [10, 4], [20, 4]]).turning_points
            assert_equal [], same
          end
        ''', HI=k_hi, LO=k_lo),
    ))

    S.append(Slice(
        id="csv", title="CSV export and import", d=3,
        pitch=("The harbour board wants the tide table in a spreadsheet, and the neighbouring port sends theirs as a text file.",
               "Tables need to leave and enter the library as plain CSV text."),
        reqs=(f"`table.to_csv` returns the text `minute{sep}height_cm` followed by one line `MINUTE{sep}HEIGHT` per reading ordered by minute, every line (the header too) ending in a newline.",
              f"`Tidelog::Table.from_csv(port, text)` builds a new table from such text. The first line must be exactly the header (surrounding whitespace is tolerated), otherwise `ArgumentError`; blank lines are skipped; each other line must be a non-negative minute and an integer height separated by `{sep}` (spaces around the numbers are fine), otherwise `ArgumentError`. Errors mention the 1-based line number as `line N` (blank lines count); a repeated minute raises `Tidelog::DuplicateReading` with the same `line N` prefix. Line endings may be `\\n` or `\\r\\n`."),
        code={
            "lib/tidelog/table.rb::methods": fmt('''
                def to_csv
                  "minute__SEP__height_cm\\n" + @readings.map { |r| "#{r.minute}__SEP__#{r.height_cm}\\n" }.join
                end

                def self.from_csv(port, text)
                  lines = text.to_s.lines.map(&:chomp)
                  unless lines.first.to_s.strip == "minute__SEP__height_cm"
                    raise ArgumentError, "line 1: the header must be minute__SEP__height_cm"
                  end

                  table = new(port)
                  lines.each_with_index do |line, i|
                    next if i.zero? || line.strip.empty?

                    m = line.match(/\\A\\s*(\\d+)\\s*__SEP__\\s*(-?\\d+)\\s*\\z/)
                    raise ArgumentError, "line #{i + 1}: expected minute__SEP__height" unless m

                    begin
                      table.add(m[1].to_i, m[2].to_i)
                    rescue DuplicateReading => e
                      raise DuplicateReading, "line #{i + 1}: #{e.message}"
                    end
                  end
                  table
                end
            ''', SEP=sep),
        },
        readme=f"## CSV export and import\n\n`table.to_csv` writes `minute{sep}height_cm` and a line per reading; `Tidelog::Table.from_csv(port, text)` reads it back (blank lines skipped, errors name the `line N`).\n",
        vtests=fmt('''
          def test_csv_basic
            fill
            assert_equal "minute__SEP__height_cm\\n0__SEP__120\\n", @t.to_csv.lines.first(2).join
          end
        ''', SEP=sep),
        tests=fmt('''
          def test_to_csv
            assert_equal "minute__SEP__height_cm\\n", Tidelog::Table.new("E").to_csv
            fill(@t, DATA.reverse)
            @t.add(900, -15)
            assert_equal "minute__SEP__height_cm\\n0__SEP__120\\n180__SEP__340\\n360__SEP__90\\n540__SEP__310\\n720__SEP__60\\n900__SEP__-15\\n", @t.to_csv
          end

          def test_from_csv_round_trip
            fill
            back = Tidelog::Table.from_csv("Copy", @t.to_csv)
            assert_equal "Copy", back.port
            assert_equal DATA, back.readings.map { |r| [r.minute, r.height_cm] }
            assert_equal @t.to_csv, back.to_csv
            assert_equal 0, Tidelog::Table.from_csv("Empty", "minute__SEP__height_cm\\n").count
          end

          def test_from_csv_tolerance
            text = "  minute__SEP__height_cm  \\r\\n\\r\\n 10 __SEP__ -4 \\r\\n\\n20__SEP__7\\n\\n"
            t = Tidelog::Table.from_csv("Odd", text)
            assert_equal [[10, -4], [20, 7]], t.readings.map { |r| [r.minute, r.height_cm] }
            assert_equal 1, Tidelog::Table.from_csv("NoEol", "minute__SEP__height_cm\\n5__SEP__5").count
          end

          def test_from_csv_errors
            assert_raises(ArgumentError) { Tidelog::Table.from_csv("X", "") }
            e = assert_raises(ArgumentError) { Tidelog::Table.from_csv("X", "time__SEP__height\\n1__SEP__2\\n") }
            assert_match(/line 1/, e.message)
            e = assert_raises(ArgumentError) { Tidelog::Table.from_csv("X", "minute__SEP__height_cm\\n1__SEP__2\\n\\nfoo__SEP__3\\n") }
            assert_match(/line 4/, e.message)
            e = assert_raises(ArgumentError) { Tidelog::Table.from_csv("X", "minute__SEP__height_cm\\n1__SEP__2__SEP__3\\n") }
            assert_match(/line 2/, e.message)
            assert_raises(ArgumentError) { Tidelog::Table.from_csv("X", "minute__SEP__height_cm\\n-1__SEP__2\\n") }
            assert_raises(ArgumentError) { Tidelog::Table.from_csv("X", "minute__SEP__height_cm\\n1__SEP__2.5\\n") }
            assert_raises(ArgumentError) { Tidelog::Table.from_csv("X", "minute__SEP__height_cm\\n1\\n") }
            e = assert_raises(Tidelog::DuplicateReading) { Tidelog::Table.from_csv("X", "minute__SEP__height_cm\\n1__SEP__2\\n3__SEP__4\\n1__SEP__9\\n") }
            assert_match(/line 4/, e.message)
            assert_raises(ArgumentError) { Tidelog::Table.from_csv(" ", "minute__SEP__height_cm\\n") }
          end
        ''', SEP=sep),
    ))

    S.append(Slice(
        id="alarm", title="High-water alarms", d=3,
        pitch=("The harbour office wants a warning the moment a gauge reading comes in above the flood mark.",
               "Something has to ring when the water reaches a dangerous level."),
        reqs=("`table.alarm(threshold_cm) { |reading| ... }` registers a callback. The threshold must be an integer and a block is required (`ArgumentError`). Every successful `add` whose height is at or above the threshold calls the block with the new reading, after the reading has been stored.",
              "Alarms run in the order they were registered. A failed `add` runs nothing. If a block raises, the exception propagates to the caller of `add` and the reading stays in the table."),
        code={
            "lib/tidelog/table.rb::table_init": "@alarms = []",
            "lib/tidelog/table.rb::on_add": "@alarms.each { |limit, block| block.call(reading) if reading.height_cm >= limit }",
            "lib/tidelog/table.rb::methods": '''
                def alarm(threshold_cm, &block)
                  raise ArgumentError, "threshold must be an integer" unless threshold_cm.is_a?(Integer)
                  raise ArgumentError, "a block is required" if block.nil?

                  @alarms << [threshold_cm, block]
                  nil
                end
            ''',
        },
        readme="## High-water alarms\n\n`table.alarm(threshold_cm) { |reading| ... }` calls the block (after the reading is stored) for every `add` at or above the threshold, in registration order. A raising block propagates but the reading stays.\n",
        vtests='''
          def test_alarm_basic
            seen = []
            @t.alarm(300) { |r| seen << r.minute }
            fill
            assert_equal [180, 540], seen
          end
        ''',
        tests='''
          def test_alarm
            log = []
            @t.alarm(300) { |r| log << [:flood, r.minute] }
            @t.alarm(100) { |r| log << [:watch, r.minute] }
            fill
            assert_equal [[:watch, 0], [:flood, 180], [:watch, 180], [:flood, 540], [:watch, 540]], log
            @t.add(900, 300)
            assert_equal [:flood, 900], log[-2]
            assert_equal [:watch, 900], log[-1]
          end

          def test_alarm_edge_cases
            seen = []
            @t.alarm(50) { |r| seen << r.height_cm }
            assert_raises(Tidelog::DuplicateReading) { @t.add(0, 60) && @t.add(0, 70) }
            assert_raises(ArgumentError) { @t.add(-1, 99) }
            assert_equal [60], seen
            @t.add(5, 49)
            @t.add(6, 50)
            assert_equal [60, 50], seen
            assert_raises(ArgumentError) { @t.alarm(1.5) { |_| } }
            assert_raises(ArgumentError) { @t.alarm("5") { |_| } }
            assert_raises(ArgumentError) { @t.alarm(5) }
          end

          def test_alarm_exception_keeps_reading
            @t.alarm(10) { |_| raise "siren broke" }
            err = assert_raises(RuntimeError) { @t.add(0, 20) }
            assert_equal "siren broke", err.message
            assert_equal 1, @t.count
            @t.add(1, 5)
            assert_equal 2, @t.count
          end
        ''',
        cross={
            "merge": {
                "reqs": ("`merge` does not trigger alarms.",),
                "tests": '''
                  def test_merge_does_not_ring_alarms
                    a = Tidelog::Table.new("A")
                    rang = []
                    a.alarm(0) { |r| rang << r.minute }
                    b = Tidelog::Table.new("B")
                    b.add(5, 500)
                    a.merge(b)
                    assert_equal [], rang
                    assert_equal 1, a.count
                  end
                '''},
            "corrections": {
                "reqs": ("`correct` does not trigger alarms.",),
                "tests": '''
                  def test_correct_does_not_ring_alarms
                    rang = []
                    @t.alarm(100) { |r| rang << r.minute }
                    @t.add(0, 10)
                    @t.correct(0, 500)
                    assert_equal [], rang
                  end
                '''},
        },
    ))

    S.append(Slice(
        id="windows", title="Navigable windows", d=4, needs=("interpolate",),
        pitch=("Deep-draught ships can only enter the harbour while the water is high enough, and the pilots plan around it by hand.",
               "The pilot office wants the time windows in which a given depth is available."),
        reqs=("`table.windows(min_cm)` returns the maximal stretches of whole minutes, between the first and the last reading (both included), in which `height_at(minute)` is at least `min_cm`. The argument must be an integer (`ArgumentError`). An empty table and a table without such minutes give an empty array.",
              "Each stretch is a `Tidelog::Window` (new file `lib/tidelog/window.rb`) with `from` and `to` (both ends included), `minutes` (their count), `cover?(minute)` and `to_s`, which is `<label of from>-<label of to>`, for example `D0 01:06-D0 04:41`. Two windows are equal when `from` and `to` are equal."),
        files={
            "lib/tidelog/window.rb": '''\
module Tidelog
  # A stretch of whole minutes, both ends included.
  Window = Struct.new(:from, :to) do
    def minutes
      to - from + 1
    end

    def cover?(minute)
      minute >= from && minute <= to
    end

    def to_s
      "#{Tidelog.label(from)}-#{Tidelog.label(to)}"
    end
  end
end
''',
        },
        code={
            "lib/tidelog.rb::requires": 'require_relative "tidelog/window"',
            "lib/tidelog/table.rb::methods": '''
                def windows(min_cm)
                  raise ArgumentError, "min_cm must be an integer" unless min_cm.is_a?(Integer)
                  return [] if @readings.empty?

                  found = []
                  start = nil
                  (@readings.first.minute..@readings.last.minute).each do |m|
                    if height_at(m) >= min_cm
                      start ||= m
                    elsif start
                      found << Window.new(start, m - 1)
                      start = nil
                    end
                  end
                  found << Window.new(start, @readings.last.minute) if start
                  found
                end
            ''',
        },
        readme="## Navigable windows\n\n`table.windows(min_cm)` returns `Tidelog::Window`s (`from`, `to`, `minutes`, `cover?`, `to_s`): the maximal runs of whole minutes in which the interpolated height is at least `min_cm`.\n",
        vtests='''
          def test_windows_basic
            fill
            assert_equal [[66, 281], [450, 619]], @t.windows(200).map { |w| [w.from, w.to] }
          end
        ''',
        tests='''
          def test_windows
            fill
            w = @t.windows(200)
            assert_equal [[66, 281], [450, 619]], w.map { |x| [x.from, x.to] }
            assert_equal [216, 170], w.map(&:minutes)
            assert_equal "D0 01:06-D0 04:41", w[0].to_s
            assert w[0].cover?(66)
            assert w[0].cover?(281)
            refute w[0].cover?(65)
            refute w[0].cover?(282)
            assert_equal Tidelog::Window.new(450, 619), w[1]
            assert_equal [[147, 209], [532, 547]], @t.windows(300).map { |x| [x.from, x.to] }
          end

          def test_windows_edges
            fill
            assert_equal [], @t.windows(350)
            assert_equal [[0, 720]], @t.windows(50).map { |x| [x.from, x.to] }
            assert_equal [[0, 720]], @t.windows(-1000).map { |x| [x.from, x.to] }
            assert_equal [], Tidelog::Table.new("E").windows(0)
            one = fill(Tidelog::Table.new("One"), [[30, 100]])
            assert_equal [[30, 30]], one.windows(100).map { |x| [x.from, x.to] }
            assert_equal [], one.windows(101)
            tri = fill(Tidelog::Table.new("Tri"), [[0, 10], [10, 20], [20, 10]])
            assert_equal [[5, 15]], tri.windows(15).map { |x| [x.from, x.to] }
            assert_equal [[0, 20]], tri.windows(10).map { |x| [x.from, x.to] }
            assert_raises(ArgumentError) { @t.windows(1.5) }
            assert_raises(ArgumentError) { @t.windows("200") }
            assert_equal "D1 00:00-D1 00:01", Tidelog::Window.new(1440, 1441).to_s
          end
        ''',
    ))

    S.append(Slice(
        id="merge", title="Merging tables", d=4,
        pitch=("The harbour got a second gauge on the far quay, and the two tide tables have to be combined into one.",
               "Readings from two tables need to be merged, including the minutes where they disagree."),
        reqs=("`table.merge(other, on_conflict: :error)` adds the readings of another `Tidelog::Table` to this one (anything else is an `ArgumentError`) and returns a `Tidelog::MergeReport` (new file `lib/tidelog/merge_report.rb`) with `added` (the number of minutes that were new to this table) and `conflicts` (the minutes, ascending, that both tables have with different heights); `to_s` of the report is `N added, M conflicting`.",
              "A minute that both tables have with the same height is ignored: it is neither added nor a conflict. For conflicts `on_conflict` decides: `:error` raises `Tidelog::DuplicateReading` and changes nothing, `:keep` keeps this table's height, `:replace` takes the other's, `:average` takes the mean of the two rounded half up (towards positive infinity). Any other value is an `ArgumentError` and changes nothing. The other table is never modified."),
        files={
            "lib/tidelog/merge_report.rb": '''\
module Tidelog
  # What a merge did.
  MergeReport = Struct.new(:added, :conflicts) do
    def to_s
      "#{added} added, #{conflicts.size} conflicting"
    end
  end
end
''',
        },
        code={
            "lib/tidelog.rb::requires": 'require_relative "tidelog/merge_report"',
            "lib/tidelog/reading.rb::reading_methods": '''
                # Used by the table; not meant to be called from outside.
                def set_height(height)
                  @height_cm = height
                end
            ''',
            "lib/tidelog/table.rb::methods": '''
                def merge(other, on_conflict: :error)
                  raise ArgumentError, "other must be a Tidelog::Table" unless other.is_a?(Table)
                  raise ArgumentError, "unknown policy: #{on_conflict.inspect}" unless %i[error keep replace average].include?(on_conflict)

                  mine = @readings.to_h { |r| [r.minute, r] }
                  added = []
                  conflicts = []
                  other.readings.each do |r|
                    own = mine[r.minute]
                    if own.nil?
                      added << r
                    elsif own.height_cm != r.height_cm
                      conflicts << [own, r]
                    end
                  end
                  if on_conflict == :error && !conflicts.empty?
                    raise DuplicateReading, "the tables disagree at minute #{conflicts.first[0].minute}"
                  end

                  added.each { |r| @readings << Reading.new(r.minute, r.height_cm) }
                  conflicts.each do |own, theirs|
                    case on_conflict
                    when :replace then own.set_height(theirs.height_cm)
                    when :average then own.set_height((Rational(own.height_cm + theirs.height_cm, 2) + Rational(1, 2)).floor)
                    end
                  end
                  @readings.sort_by!(&:minute)
                  MergeReport.new(added.size, conflicts.map { |own, _| own.minute })
                end
            ''',
        },
        readme="## Merging tables\n\n`table.merge(other, on_conflict: :error)` adds the other table's readings and returns a `Tidelog::MergeReport` (`added`, `conflicts`). Equal readings are ignored; for differing heights `:error` raises, `:keep`, `:replace` and `:average` (half up) resolve them.\n",
        vtests='''
          def test_merge_basic
            a = fill(Tidelog::Table.new("A"), [[0, 1]])
            b = fill(Tidelog::Table.new("B"), [[10, 2]])
            assert_equal 1, a.merge(b).added
            assert_equal 2, a.count
          end
        ''',
        tests='''
          def merge_pair
            a = fill(Tidelog::Table.new("A"), [[0, 100], [60, 150], [120, 90]])
            b = fill(Tidelog::Table.new("B"), [[60, 150], [120, 110], [180, 70]])
            [a, b]
          end

          def heights(t)
            t.readings.map { |r| [r.minute, r.height_cm] }
          end

          def test_merge_error_policy
            a, b = merge_pair
            assert_raises(Tidelog::DuplicateReading) { a.merge(b) }
            assert_raises(Tidelog::DuplicateReading) { a.merge(b, on_conflict: :error) }
            assert_equal [[0, 100], [60, 150], [120, 90]], heights(a)
            assert_equal [[60, 150], [120, 110], [180, 70]], heights(b)
          end

          def test_merge_policies
            a, b = merge_pair
            rep = a.merge(b, on_conflict: :keep)
            assert_equal [1, [120]], [rep.added, rep.conflicts]
            assert_equal "1 added, 1 conflicting", rep.to_s
            assert_equal [[0, 100], [60, 150], [120, 90], [180, 70]], heights(a)
            a, b = merge_pair
            a.merge(b, on_conflict: :replace)
            assert_equal [[0, 100], [60, 150], [120, 110], [180, 70]], heights(a)
            a, b = merge_pair
            a.merge(b, on_conflict: :average)
            assert_equal [[0, 100], [60, 150], [120, 100], [180, 70]], heights(a)
            assert_equal [[60, 150], [120, 110], [180, 70]], heights(b)
          end

          def test_merge_average_rounds_half_up
            a = fill(Tidelog::Table.new("A"), [[0, 90], [10, -3], [20, 4]])
            b = fill(Tidelog::Table.new("B"), [[0, 111], [10, -2], [20, 6]])
            rep = a.merge(b, on_conflict: :average)
            assert_equal [0, 10, 20], rep.conflicts
            assert_equal [[0, 101], [10, -2], [20, 5]], heights(a)
          end

          def test_merge_without_conflicts_and_errors
            a = fill(Tidelog::Table.new("A"), [[0, 5]])
            b = fill(Tidelog::Table.new("B"), [[10, 6], [20, 7]])
            rep = a.merge(b)
            assert_equal [2, []], [rep.added, rep.conflicts]
            assert_equal "2 added, 0 conflicting", rep.to_s
            assert_equal 0, a.merge(a).added
            assert_equal 0, a.merge(b).added
            assert_equal 3, a.count
            assert_raises(ArgumentError) { a.merge([[1, 2]]) }
            assert_raises(ArgumentError) { a.merge(nil) }
            c = fill(Tidelog::Table.new("C"), [[0, 99], [50, 1]])
            assert_raises(ArgumentError) { a.merge(c, on_conflict: :nope) }
            assert_raises(ArgumentError) { a.merge(c, on_conflict: "keep") }
            assert_equal [[0, 5], [10, 6], [20, 7]], heights(a)
            e = Tidelog::Table.new("E")
            assert_equal 0, e.merge(Tidelog::Table.new("E2")).added
            assert_equal 3, e.merge(a).added
            assert_equal [[0, 5], [10, 6], [20, 7]], heights(e)
          end
        ''',
    ))

    return S


APP = App(
    name="tidelog", lang="ruby", title="the tide table library", role="the harbour master", key="TIDE",
    base={
        "README.md": README + "\n@@blocks features\n",
        "lib/tidelog.rb": LIB,
        "lib/tidelog/reading.rb": READING,
        "lib/tidelog/table.rb": TABLE,
        ".gitignore": "*.gem\n",
    },
    visible={"test/test_basic.rb": VISIBLE},
    hidden={"test/test_features.rb": HIDDEN},
)

register_app("feature-rb-tidelog", APP, make_slices, n=18, summary="harbour tide table: statistics, ranges, datum, interpolation, corrections, CSV, alarms, windows, merging")

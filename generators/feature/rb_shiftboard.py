"""shiftboard (ruby): a volunteer shift roster extended with agendas, fill rates, skills, reminders, overlap and hour limits, waitlists, swaps."""
import random

from fx import dd
from generators.feature._slices import App, Slice, fmt, register_app

README = dd('''
    # shiftboard

    A volunteer roster for a community festival, as a small Ruby library (Ruby 3.3, standard library only). Run the tests with
    `ruby -Ilib -Itest -e 'Dir["test/test_*.rb"].sort.each { |f| require "./#{f}" }'`.

    ## Layout

    * `lib/shiftboard.rb`: requires everything.
    * `lib/shiftboard/shift.rb`: `Shiftboard::Shift`.
    * `lib/shiftboard/roster.rb`: `Shiftboard::Roster` and the errors.

    ## Basics

    * `Shiftboard::Roster.new(**options)`; there are no options yet and unknown ones raise `ArgumentError`.
    * `roster.add_shift(name:, day:, start:, hours:, slots:, **options)` stores a shift and returns a `Shiftboard::Shift` with ids
      1, 2, 3, ... `name` must not be blank (it is stripped), `day` a `Date`, `start` an integer hour from 0 to 23, `hours` an
      integer from 1 to 12 with `start + hours <= 24` (shifts end by midnight) and `slots` a positive integer; anything else raises
      `ArgumentError`, as does an unknown option. A failed call changes nothing.
    * `Shift` has `id`, `name`, `day`, `start`, `hours`, `slots`, `end_hour` (`start + hours`), `volunteers` (a copy of the
      confirmed volunteers in sign-up order) and `open_slots`.
    * `roster.shifts` lists the shifts ordered by day, start hour and id; `roster.fetch(id)` returns one (`KeyError` for an
      unknown id).
    * `roster.sign_up(volunteer, shift_id)` confirms a volunteer on a shift and returns `:confirmed`. The volunteer name must not be
      blank (`ArgumentError`, it is stripped). Checks in this order: unknown shift (`KeyError`); the volunteer is already on the
      shift (`Shiftboard::AlreadySignedUp`); the shift is full (`Shiftboard::ShiftFull`). A failed call changes nothing.
    * `roster.cancel(volunteer, shift_id)` removes a confirmed volunteer and returns the name (`KeyError` for an unknown shift or a
      volunteer who is not confirmed on it). `roster.hours_for(volunteer)` is the total of `hours` over the shifts the
      volunteer is confirmed on.
    * All errors raised by the roster itself inherit from `Shiftboard::Error`.
''')

LIB = '''\
require "date"
require_relative "shiftboard/shift"
require_relative "shiftboard/roster"
@@uniq requires
'''

SHIFT = '''\
module Shiftboard
  # One block of work on a day.
  class Shift
    attr_reader :id, :name, :day, :start, :hours, :slots
    @@slot shift_attrs

    def initialize(id:, name:, day:, start:, hours:, slots:)
      @id = id
      @name = name
      @day = day
      @start = start
      @hours = hours
      @slots = slots
      @volunteers = []
      @@slot shift_init
    end

    def end_hour
      start + hours
    end

    def volunteers
      @volunteers.dup
    end

    def open_slots
      slots - @volunteers.size
    end

    def full?
      open_slots <= 0
    end

    # Used by the roster; not meant to be called from outside.
    def confirmed
      @volunteers
    end

    @@blocks shift_methods
  end
end
'''

ROSTER = '''\
module Shiftboard
  class Error < StandardError; end

  class ShiftFull < Error; end

  class AlreadySignedUp < Error; end

  @@blocks module_items

  class Roster
    def initialize(**opts)
      @@slot init_opts
      raise ArgumentError, "unknown option(s): #{opts.keys.map(&:to_s).sort.join(', ')}" unless opts.empty?

      @shifts = {}
      @next_id = 1
      @@slot init
    end

    def add_shift(name:, day:, start:, hours:, slots:, **opts)
      raise ArgumentError, "name is required" if name.to_s.strip.empty?
      raise ArgumentError, "day must be a Date" unless day.is_a?(Date)
      raise ArgumentError, "start must be an hour from 0 to 23" unless start.is_a?(Integer) && (0..23).cover?(start)
      raise ArgumentError, "hours must be an integer from 1 to 12" unless hours.is_a?(Integer) && (1..12).cover?(hours)
      raise ArgumentError, "a shift must end by midnight" if start + hours > 24
      raise ArgumentError, "slots must be a positive integer" unless slots.is_a?(Integer) && slots.positive?

      @@slot add_pre
      raise ArgumentError, "unknown option(s): #{opts.keys.map(&:to_s).sort.join(', ')}" unless opts.empty?

      shift = Shift.new(id: @next_id, name: name.strip, day: day, start: start, hours: hours, slots: slots)
      @@slot shift_extra
      @next_id += 1
      @shifts[shift.id] = shift
      shift
    end

    def fetch(id)
      @shifts.fetch(id) { raise KeyError, "no shift with id #{id}" }
    end

    def shifts
      @shifts.values.sort_by { |s| [s.day, s.start, s.id] }
    end

    @@default assigned_shifts
    # The shifts a volunteer is committed to.
    def assigned_shifts(volunteer)
      @shifts.values.select { |s| s.confirmed.include?(volunteer) }
    end
    @@end

    # Raises when `volunteer` may not take `shift` (`ignore` lists shifts that are being given up at the same time).
    def check_assignment(volunteer, shift, ignore = [])
      @@slot assignment_pre
      raise AlreadySignedUp, "#{volunteer} is already on #{shift.name}" if shift.confirmed.include?(volunteer)

      @@slot assignment_checks
    end

    def sign_up(volunteer, shift_id)
      raise ArgumentError, "volunteer is required" if volunteer.to_s.strip.empty?

      volunteer = volunteer.to_s.strip
      shift = fetch(shift_id)
      check_assignment(volunteer, shift)
      @@default when_full
      raise ShiftFull, "#{shift.name} is full" if shift.full?
      @@end
      shift.confirmed << volunteer
      @@slot on_confirm
      :confirmed
    end

    def cancel(volunteer, shift_id)
      shift = fetch(shift_id)
      @@slot cancel_pre
      raise KeyError, "#{volunteer} is not on #{shift.name}" unless shift.confirmed.include?(volunteer)

      shift.confirmed.delete(volunteer)
      @@slot on_cancel
      volunteer
    end

    def hours_for(volunteer)
      @shifts.values.select { |s| s.confirmed.include?(volunteer) }.sum(&:hours)
    end

    @@blocks methods
  end
end
'''

TEST_HEAD = '''\
require "minitest/autorun"
require "shiftboard"
@@uniq requires

D = Date.new(2025, 6, 2) unless defined?(D) # a Monday
'''

SETUP = '''\
  def setup
    @r = Shiftboard::Roster.new
    @setup = @r.add_shift(name: "Setup", day: D, start: 8, hours: 3, slots: 2)        # 1: Mon 08-11
    @bar = @r.add_shift(name: "Bar", day: D, start: 18, hours: 4, slots: 1)           # 2: Mon 18-22
    @gate = @r.add_shift(name: "Gate", day: D + 1, start: 9, hours: 8, slots: 2)      # 3: Tue 09-17
    @clean = @r.add_shift(name: "Cleanup", day: D + 6, start: 20, hours: 2, slots: 3) # 4: Sun 20-22
    @next = @r.add_shift(name: "Next week", day: D + 7, start: 8, hours: 6, slots: 2) # 5: Mon 08-14, next week
  end
'''

VISIBLE = TEST_HEAD + '''
class BasicTest < Minitest::Test
''' + SETUP + '''
  def test_shifts
    assert_equal [1, 2, 3, 4, 5], @r.shifts.map(&:id)
    assert_equal 11, @setup.end_hour
    assert_equal 2, @setup.open_slots
    assert_equal "Gate", @r.fetch(3).name
    assert_raises(KeyError) { @r.fetch(99) }
  end

  def test_sign_up_and_cancel
    assert_equal :confirmed, @r.sign_up("ana", 1)
    @r.sign_up("bob", 1)
    assert_equal ["ana", "bob"], @r.fetch(1).volunteers
    assert_raises(Shiftboard::AlreadySignedUp) { @r.sign_up("ana", 1) }
    assert_equal "ana", @r.cancel("ana", 1)
    assert_equal 3, @r.hours_for("bob")
    assert_raises(KeyError) { @r.cancel("ana", 1) }
  end
  @@blocks tests
end
'''

HIDDEN = TEST_HEAD + '''
class FeatureTest < Minitest::Test
''' + SETUP + '''
  def test_base_add_shift_rules
    r = Shiftboard::Roster.new
    s = r.add_shift(name: "  Cooking ", day: D, start: 0, hours: 12, slots: 1)
    assert_equal ["Cooking", 0, 12, 12], [s.name, s.start, s.hours, s.end_hour]
    assert_equal 1, s.id
    bad = [{ name: " " }, { name: nil }, { day: "2025-06-02" }, { day: nil }, { start: 24 }, { start: -1 }, { start: 1.5 }, { start: "9" },
           { hours: 0 }, { hours: 13 }, { hours: 2.5 }, { start: 20, hours: 5 }, { slots: 0 }, { slots: -1 }, { slots: 1.5 }, { slots: "2" }]
    bad.each do |args|
      full = { name: "X", day: D, start: 9, hours: 2, slots: 1 }.merge(args)
      assert_raises(ArgumentError, args.inspect) { r.add_shift(**full) }
    end
    assert_raises(ArgumentError) { r.add_shift(name: "X", day: D, start: 9, hours: 2, slots: 1, colour: "red") }
    assert_raises(ArgumentError) { Shiftboard::Roster.new(colour: "red") }
    assert_equal 1, r.shifts.size
    assert_equal 2, r.add_shift(name: "Y", day: D, start: 20, hours: 4, slots: 1).id
  end

  def test_base_ordering
    assert_equal [1, 2, 3, 4, 5], @r.shifts.map(&:id)
    r = Shiftboard::Roster.new
    r.add_shift(name: "late", day: D, start: 20, hours: 1, slots: 1)
    r.add_shift(name: "early", day: D, start: 6, hours: 1, slots: 1)
    r.add_shift(name: "prev", day: D - 1, start: 23, hours: 1, slots: 1)
    r.add_shift(name: "twin", day: D, start: 6, hours: 2, slots: 1)
    assert_equal %w[prev early twin late], r.shifts.map(&:name)
    assert_same r.shifts.first, r.fetch(3)
  end

  def test_base_sign_up_rules
    assert_equal :confirmed, @r.sign_up("  ana ", 1)
    assert_equal ["ana"], @r.fetch(1).volunteers
    [nil, "", "  "].each { |v| assert_raises(ArgumentError, v.inspect) { @r.sign_up(v, 1) } }
    assert_raises(KeyError) { @r.sign_up("bob", 99) }
    assert_raises(ArgumentError) { @r.sign_up("", 99) }
    assert_raises(Shiftboard::AlreadySignedUp) { @r.sign_up("ana", 1) }
    @r.sign_up("bob", 1)
    @@default base_full
    assert_raises(Shiftboard::ShiftFull) { @r.sign_up("cy", 1) }
    @@end
    assert_raises(Shiftboard::AlreadySignedUp) { @r.sign_up("bob", 1) }
    assert_equal ["ana", "bob"], @r.fetch(1).volunteers
    assert_equal 0, @r.fetch(1).open_slots
    assert @r.fetch(1).full?
    assert_kind_of Shiftboard::Error, Shiftboard::ShiftFull.new
    assert_kind_of Shiftboard::Error, Shiftboard::AlreadySignedUp.new
    @r.fetch(1).volunteers << "intruder"
    assert_equal 2, @r.fetch(1).volunteers.size
  end

  def test_base_cancel_and_hours
    @r.sign_up("ana", 1)
    @r.sign_up("ana", 3)
    @r.sign_up("bob", 1)
    assert_equal 11, @r.hours_for("ana")
    assert_equal 3, @r.hours_for("bob")
    assert_equal 0, @r.hours_for("nobody")
    assert_equal "ana", @r.cancel("ana", 1)
    assert_equal 8, @r.hours_for("ana")
    assert_equal ["bob"], @r.fetch(1).volunteers
    assert_raises(KeyError) { @r.cancel("ana", 1) }
    assert_raises(KeyError) { @r.cancel("bob", 99) }
    assert_raises(KeyError) { @r.cancel("zed", 3) }
    assert_equal :confirmed, @r.sign_up("cy", 1)
    assert_equal ["bob", "cy"], @r.fetch(1).volunteers
    @r.cancel("bob", 1)
    assert_equal :confirmed, @r.sign_up("bob", 1)
    assert_equal ["cy", "bob"], @r.fetch(1).volunteers
  end
  @@blocks tests
end
'''


def make_slices(rng: random.Random):
    cap = rng.choice([10, 12, 14])
    S = []

    S.append(Slice(
        id="agenda", title="A volunteer's agenda", d=1,
        pitch=("Volunteers keep asking which of their shifts they have signed up for.",
               "Each volunteer should be able to see their own shifts."),
        reqs=("`roster.agenda(volunteer)` returns the shifts the volunteer is confirmed on, ordered like `roster.shifts` (day, start hour, id). A volunteer without shifts (or an unknown one) gets an empty array.",),
        code={
            "lib/shiftboard/roster.rb::methods": '''
                def agenda(volunteer)
                  shifts.select { |s| s.confirmed.include?(volunteer) }
                end
            ''',
        },
        readme="## A volunteer's agenda\n\n`roster.agenda(volunteer)` lists the shifts the volunteer is confirmed on, in `shifts` order.\n",
        vtests='''
          def test_agenda_basic
            @r.sign_up("ana", 3)
            @r.sign_up("ana", 1)
            assert_equal [1, 3], @r.agenda("ana").map(&:id)
          end
        ''',
        tests='''
          def test_agenda
            @r.sign_up("ana", 4)
            @r.sign_up("ana", 3)
            @r.sign_up("ana", 2)
            @r.sign_up("bob", 3)
            assert_equal [2, 3, 4], @r.agenda("ana").map(&:id)
            assert_equal [3], @r.agenda("bob").map(&:id)
            assert_equal [], @r.agenda("cy")
            @r.cancel("ana", 3)
            assert_equal [2, 4], @r.agenda("ana").map(&:id)
            assert_kind_of Shiftboard::Shift, @r.agenda("ana").first
          end
        ''',
    ))

    S.append(Slice(
        id="fill-rate", title="Fill rate", d=1,
        pitch=("The coordinator wants to see at a glance which shifts still need people.",
               "Each shift needs a fill rate figure for the dashboard."),
        reqs=("`roster.fill_rate(shift_id)` returns the share of confirmed volunteers in the slots of the shift as a whole percentage, rounded half up (`1` of `3` slots is `33`, `1` of `8` is `13`). An unknown shift is a `KeyError`.",),
        code={
            "lib/shiftboard/roster.rb::methods": '''
                def fill_rate(shift_id)
                  shift = fetch(shift_id)
                  (shift.confirmed.size * 100 + shift.slots / 2) / shift.slots
                end
            ''',
        },
        readme="## Fill rate\n\n`roster.fill_rate(shift_id)` is confirmed volunteers over slots as a whole percentage, rounded half up.\n",
        vtests='''
          def test_fill_rate_basic
            @r.sign_up("ana", 1)
            assert_equal 50, @r.fill_rate(1)
          end
        ''',
        tests='''
          def test_fill_rate
            assert_equal 0, @r.fill_rate(4)
            @r.sign_up("ana", 4)
            assert_equal 33, @r.fill_rate(4)
            @r.sign_up("bob", 4)
            assert_equal 67, @r.fill_rate(4)
            @r.sign_up("cy", 4)
            assert_equal 100, @r.fill_rate(4)
            big = @r.add_shift(name: "Big", day: D + 2, start: 8, hours: 1, slots: 8)
            @r.sign_up("ana", big.id)
            assert_equal 13, @r.fill_rate(big.id)
            @r.sign_up("bob", big.id)
            assert_equal 25, @r.fill_rate(big.id)
            @r.sign_up("cy", big.id)
            assert_equal 38, @r.fill_rate(big.id)
            @r.cancel("cy", big.id)
            assert_equal 25, @r.fill_rate(big.id)
            assert_raises(KeyError) { @r.fill_rate(99) }
          end
        ''',
    ))

    S.append(Slice(
        id="skills", title="Required skills", d=2,
        pitch=("Somebody without a food-handling certificate ended up on the grill.",
               "Some shifts may only be worked by volunteers with a certain skill."),
        reqs=("`add_shift(..., skill: nil)` takes an optional `skill`, a non-blank string that is stripped (anything else is an `ArgumentError`); `shift.skill` returns it (`nil` when there is none). `roster.grant(volunteer, skill)` gives a volunteer a skill (blank values are an `ArgumentError`; both are stripped; granting twice is fine) and `roster.skills_of(volunteer)` returns the volunteer's skills as a sorted array.",
              "`sign_up` for a shift with a skill fails with the new `Shiftboard::MissingSkill` (a `Shiftboard::Error`) when the volunteer does not have it. The check comes right after the \"already on the shift\" check and before the \"full\" check."),
        code={
            "lib/shiftboard/shift.rb::shift_attrs": "attr_reader :skill",
            "lib/shiftboard/shift.rb::shift_init": "@skill = nil",
            "lib/shiftboard/shift.rb::shift_methods": '''
                # Used by the roster; not meant to be called from outside.
                def require_skill(skill)
                  @skill = skill
                end
            ''',
            "lib/shiftboard/roster.rb::module_items": "class MissingSkill < Error; end",
            "lib/shiftboard/roster.rb::init": "@skills = Hash.new { |h, k| h[k] = [] }",
            "lib/shiftboard/roster.rb::add_pre": '''
                skill = opts.delete(:skill)
                unless skill.nil? || (skill.is_a?(String) && !skill.strip.empty?)
                  raise ArgumentError, "skill must be a non-blank string"
                end
            ''',
            "lib/shiftboard/roster.rb::shift_extra": "shift.require_skill(skill.strip) if skill",
            "lib/shiftboard/roster.rb::assignment_checks": '''
                if shift.skill && !@skills[volunteer].include?(shift.skill)
                  raise MissingSkill, "#{volunteer} lacks the skill #{shift.skill}"
                end
            ''',
            "lib/shiftboard/roster.rb::methods": '''
                def grant(volunteer, skill)
                  raise ArgumentError, "volunteer is required" if volunteer.to_s.strip.empty?
                  raise ArgumentError, "skill is required" if skill.to_s.strip.empty?

                  list = @skills[volunteer.to_s.strip]
                  list << skill.to_s.strip unless list.include?(skill.to_s.strip)
                  nil
                end

                def skills_of(volunteer)
                  @skills.key?(volunteer) ? @skills[volunteer].sort : []
                end
            ''',
        },
        readme="## Required skills\n\n`add_shift(..., skill: \"firstaid\")`, `roster.grant(volunteer, skill)` and `roster.skills_of(volunteer)`; `sign_up` raises `Shiftboard::MissingSkill` for a volunteer without the shift's skill (after the already-signed check, before the full check).\n",
        vtests='''
          def test_skill_basic
            g = @r.add_shift(name: "Grill", day: D, start: 12, hours: 2, slots: 1, skill: "food")
            assert_raises(Shiftboard::MissingSkill) { @r.sign_up("ana", g.id) }
            @r.grant("ana", "food")
            assert_equal :confirmed, @r.sign_up("ana", g.id)
          end
        ''',
        tests='''
          def test_skills
            g = @r.add_shift(name: "Grill", day: D, start: 12, hours: 2, slots: 1, skill: "  food ")
            assert_equal "food", g.skill
            assert_nil @r.fetch(1).skill
            assert_equal [], @r.skills_of("ana")
            @r.grant("ana", "food")
            @r.grant(" ana ", " first aid ")
            @r.grant("ana", "food")
            assert_equal ["first aid", "food"], @r.skills_of("ana")
            assert_equal :confirmed, @r.sign_up("ana", g.id)
            assert_equal :confirmed, @r.sign_up("bob", 1)
            assert_raises(Shiftboard::MissingSkill) { @r.sign_up("bob", g.id) }
            assert_kind_of Shiftboard::Error, Shiftboard::MissingSkill.new
            @r.skills_of("ana") << "hacked"
            assert_equal ["first aid", "food"], @r.skills_of("ana")
          end

          def test_skill_check_order_and_validation
            g = @r.add_shift(name: "Grill", day: D, start: 12, hours: 2, slots: 1, skill: "food")
            @r.grant("ana", "food")
            @r.sign_up("ana", g.id)
            assert_raises(Shiftboard::AlreadySignedUp) { @r.sign_up("ana", g.id) }
            assert_raises(Shiftboard::MissingSkill) { @r.sign_up("bob", g.id) }
            [" ", "", 5, :food].each do |bad|
              assert_raises(ArgumentError, bad.inspect) { @r.add_shift(name: "X", day: D, start: 1, hours: 1, slots: 1, skill: bad) }
            end
            assert_equal 6, @r.shifts.size
            assert_raises(ArgumentError) { @r.grant("", "food") }
            assert_raises(ArgumentError) { @r.grant("ana", " ") }
            assert_raises(ArgumentError) { @r.grant(nil, "x") }
            assert_raises(ArgumentError) { @r.add_shift(name: "X", day: D, start: 1, hours: 1, slots: 1, skill: "a", colour: "red") }
          end
        ''',
    ))

    S.append(Slice(
        id="reminders", title="Reminders for tomorrow", d=2,
        pitch=("Volunteers forget their shifts and the coordinator sends reminder texts by hand every evening.",
               "The roster should produce the reminder messages for the next day."),
        reqs=("`roster.reminders(today)` takes a `Date` (`ArgumentError` otherwise) and returns an array of messages, one for each confirmed volunteer of each shift whose day is `today + 1`: `NAME: SHIFT tomorrow at HH:00 for Nh` with a two-digit start hour (`ana: Setup tomorrow at 08:00 for 3h`). The messages are ordered by the start hour of the shift, then by shift id, and within a shift in sign-up order. Nothing tomorrow gives an empty array.",),
        code={
            "lib/shiftboard/roster.rb::methods": '''
                def reminders(today)
                  raise ArgumentError, "today must be a Date" unless today.is_a?(Date)

                  out = []
                  @shifts.values.select { |s| s.day == today + 1 }.sort_by { |s| [s.start, s.id] }.each do |s|
                    s.confirmed.each do |v|
                      out << format("%<v>s: %<n>s tomorrow at %<h>02d:00 for %<d>dh", v: v, n: s.name, h: s.start, d: s.hours)
                    end
                  end
                  out
                end
            ''',
        },
        readme="## Reminders for tomorrow\n\n`roster.reminders(today)` lists `NAME: SHIFT tomorrow at HH:00 for Nh` for every confirmed volunteer of the shifts on `today + 1`, by start hour, shift id and sign-up order.\n",
        vtests='''
          def test_reminders_basic
            @r.sign_up("ana", 1)
            assert_equal ["ana: Setup tomorrow at 08:00 for 3h"], @r.reminders(D - 1)
          end
        ''',
        tests='''
          def test_reminders
            @r.sign_up("bob", 2)
            @r.sign_up("ana", 1)
            @r.sign_up("cy", 1)
            @r.sign_up("dee", 3)
            assert_equal ["ana: Setup tomorrow at 08:00 for 3h", "cy: Setup tomorrow at 08:00 for 3h", "bob: Bar tomorrow at 18:00 for 4h"], @r.reminders(D - 1)
            assert_equal ["dee: Gate tomorrow at 09:00 for 8h"], @r.reminders(D)
            assert_equal [], @r.reminders(D + 1)
            assert_equal [], @r.reminders(D - 5)
            late = @r.add_shift(name: "Closing", day: D + 1, start: 7, hours: 2, slots: 1)
            @r.sign_up("eve", late.id)
            assert_equal ["eve: Closing tomorrow at 07:00 for 2h", "dee: Gate tomorrow at 09:00 for 8h"], @r.reminders(D)
            @r.cancel("dee", 3)
            assert_equal ["eve: Closing tomorrow at 07:00 for 2h"], @r.reminders(D)
          end

          def test_reminders_validation
            assert_raises(ArgumentError) { @r.reminders("2025-06-01") }
            assert_raises(ArgumentError) { @r.reminders(nil) }
            assert_raises(ArgumentError) { @r.reminders(20250601) }
          end
        ''',
    ))

    S.append(Slice(
        id="overlap", title="No double booking", d=3,
        pitch=("A volunteer was signed up for the bar and the box office at the same time.",
               "Nobody can work two shifts that overlap."),
        reqs=("`sign_up` fails with the new `Shiftboard::OverlapError` (a `Shiftboard::Error`) when the volunteer is already confirmed on a shift of the same day that overlaps in time: two shifts overlap when each starts before the other one ends (`08-11` and `10-12` overlap, `08-11` and `11-13` do not). The check comes after the \"already on the shift\" check and before the \"full\" check.",),
        code={
            "lib/shiftboard/roster.rb::module_items": "class OverlapError < Error; end",
            "lib/shiftboard/roster.rb::assignment_checks": '''
                clash = (assigned_shifts(volunteer) - ignore).find { |o| o.day == shift.day && o.start < shift.end_hour && shift.start < o.end_hour }
                raise OverlapError, "#{volunteer} is already on #{clash.name} at that time" if clash
            ''',
        },
        readme="## No double booking\n\n`sign_up` raises `Shiftboard::OverlapError` when the volunteer already has a confirmed shift on the same day that overlaps in time (touching ends do not overlap); checked after \"already signed up\", before \"full\".\n",
        vtests='''
          def test_overlap_basic
            b = @r.add_shift(name: "Box office", day: D, start: 9, hours: 2, slots: 2)
            @r.sign_up("ana", 1)
            assert_raises(Shiftboard::OverlapError) { @r.sign_up("ana", b.id) }
          end
        ''',
        tests='''
          def test_overlap
            a = @r.add_shift(name: "A", day: D, start: 10, hours: 2, slots: 2)
            touching = @r.add_shift(name: "Touching", day: D, start: 11, hours: 2, slots: 2)
            early = @r.add_shift(name: "Early", day: D, start: 6, hours: 2, slots: 2)
            enclosing = @r.add_shift(name: "Enclosing", day: D, start: 7, hours: 8, slots: 2)
            @r.sign_up("ana", 1)
            assert_raises(Shiftboard::OverlapError) { @r.sign_up("ana", a.id) }
            assert_equal :confirmed, @r.sign_up("ana", touching.id)
            assert_equal :confirmed, @r.sign_up("ana", early.id)
            assert_raises(Shiftboard::OverlapError) { @r.sign_up("ana", enclosing.id) }
            assert_equal :confirmed, @r.sign_up("bob", a.id)
            assert_equal :confirmed, @r.sign_up("ana", 2)
            assert_equal :confirmed, @r.sign_up("ana", 3)
            assert_equal 3 + 2 + 2 + 4 + 8, @r.hours_for("ana")
            assert_kind_of Shiftboard::Error, Shiftboard::OverlapError.new
          end

          def test_overlap_order_and_cancel
            b = @r.add_shift(name: "Box office", day: D, start: 9, hours: 2, slots: 1)
            @r.sign_up("bob", b.id)
            @r.sign_up("ana", 1)
            assert_raises(Shiftboard::OverlapError) { @r.sign_up("ana", b.id) }
            assert_raises(Shiftboard::AlreadySignedUp) { @r.sign_up("bob", b.id) }
            @r.cancel("ana", 1)
            @r.sign_up("ana", 3)
            assert_equal :confirmed, @r.sign_up("ana", 1)
            assert_equal ["ana"], @r.fetch(1).volunteers
          end
        ''',
    ))

    S.append(Slice(
        id="max-hours", title="Weekly hour limit", d=3,
        pitch=("A few eager volunteers signed up for sixty hours in one week and burned out.",
               "The festival wants to cap the hours a volunteer can work per week."),
        reqs=(f"`Roster.new(max_hours: nil)` takes an optional limit (an integer of at least 1, otherwise `ArgumentError`; `nil` means no limit) and `roster.max_hours` returns it. With a limit, `sign_up` fails with the new `Shiftboard::HoursLimit` (a `Shiftboard::Error`) when the volunteer's confirmed hours in the shift's week plus the hours of the shift would exceed it (exactly reaching the limit is fine). A week runs from Monday to Sunday. The check comes after the other checks of `sign_up` (the \"already on the shift\" check and, when they exist, skills and overlap) and before the \"full\" check.",),
        code={
            "lib/shiftboard/roster.rb::module_items": "class HoursLimit < Error; end",
            "lib/shiftboard/roster.rb::init_opts": '''
                max_hours = opts.delete(:max_hours)
                unless max_hours.nil? || (max_hours.is_a?(Integer) && max_hours >= 1)
                  raise ArgumentError, "max_hours must be an integer of at least 1"
                end
                @max_hours = max_hours
            ''',
            "lib/shiftboard/roster.rb::assignment_checks": '''
                if @max_hours
                  monday = ->(day) { day - (day.cwday - 1) }
                  week = monday.call(shift.day)
                  booked = (assigned_shifts(volunteer) - ignore).select { |o| monday.call(o.day) == week }.sum(&:hours)
                  if booked + shift.hours > @max_hours
                    raise HoursLimit, "#{volunteer} would work #{booked + shift.hours}h that week (limit #{@max_hours}h)"
                  end
                end
            ''',
            "lib/shiftboard/roster.rb::methods": "attr_reader :max_hours",
        },
        readme=f"## Weekly hour limit\n\n`Roster.new(max_hours: {cap})` caps the confirmed hours of a volunteer per Monday-to-Sunday week; `sign_up` raises `Shiftboard::HoursLimit` beyond it (reaching it exactly is fine). `roster.max_hours` returns the limit.\n",
        vtests=fmt('''
          def test_max_hours_basic
            r = Shiftboard::Roster.new(max_hours: __C__)
            r.add_shift(name: "Long", day: D, start: 6, hours: 8, slots: 1)
            r.add_shift(name: "Medium", day: D + 1, start: 6, hours: __C__ - 8, slots: 1)
            r.add_shift(name: "One more", day: D + 2, start: 6, hours: 1, slots: 1)
            r.sign_up("ana", 1)
            r.sign_up("ana", 2)
            assert_raises(Shiftboard::HoursLimit) { r.sign_up("ana", 3) }
          end
        ''', C=cap),
        tests=fmt('''
          def limited
            r = Shiftboard::Roster.new(max_hours: __C__)
            r.add_shift(name: "Mon", day: D, start: 8, hours: 8, slots: 2)
            r.add_shift(name: "Tue", day: D + 1, start: 8, hours: __C__ - 8, slots: 2)
            r.add_shift(name: "Sun", day: D + 6, start: 8, hours: 1, slots: 2)
            r.add_shift(name: "Next Mon", day: D + 7, start: 8, hours: 8, slots: 2)
            r.add_shift(name: "Prev Sun", day: D - 1, start: 8, hours: 8, slots: 2)
            r
          end

          def test_hours_limit
            r = limited
            assert_equal __C__, r.max_hours
            assert_nil Shiftboard::Roster.new.max_hours
            r.sign_up("ana", 1)
            assert_equal :confirmed, r.sign_up("ana", 2)
            assert_equal __C__, r.hours_for("ana")
            assert_raises(Shiftboard::HoursLimit) { r.sign_up("ana", 3) }
            assert_equal :confirmed, r.sign_up("ana", 4)
            assert_equal :confirmed, r.sign_up("ana", 5)
            assert_equal :confirmed, r.sign_up("bob", 3)
            assert_kind_of Shiftboard::Error, Shiftboard::HoursLimit.new
          end

          def test_hours_limit_follows_cancellations_and_order
            r = limited
            r.sign_up("ana", 1)
            r.sign_up("ana", 2)
            r.cancel("ana", 2)
            assert_equal :confirmed, r.sign_up("ana", 3)
            assert_raises(Shiftboard::AlreadySignedUp) { r.sign_up("ana", 1) }
            assert_raises(Shiftboard::HoursLimit) { r.sign_up("ana", 2) }
            assert_equal 9, r.hours_for("ana")
            r.sign_up("cy", 3)
            r.sign_up("dee", 1)
            r.sign_up("dee", 2)
            assert_raises(Shiftboard::HoursLimit) { r.sign_up("dee", 3) }
            assert_equal ["ana", "cy"], r.fetch(3).volunteers
          end

          def test_limit_validation
            [0, -1, 2.5, "10", :ten, true].each do |bad|
              assert_raises(ArgumentError, bad.inspect) { Shiftboard::Roster.new(max_hours: bad) }
            end
            assert_nil Shiftboard::Roster.new(max_hours: nil).max_hours
            assert_equal 1, Shiftboard::Roster.new(max_hours: 1).max_hours
            assert_raises(ArgumentError) { Shiftboard::Roster.new(max_hours: 5, colour: "red") }
          end
        ''', C=cap),
    ))

    S.append(Slice(
        id="waitlist", title="Waiting list", d=3,
        pitch=("When a shift fills up, the people who still want to help get a no and the coordinator loses track of them.",
               "Full shifts should keep a waiting list that fills gaps automatically."),
        reqs=("When a shift is full, `sign_up` no longer raises `ShiftFull` but puts the volunteer on the shift's waiting list and returns `:waitlisted`. `roster.waitlist(shift_id)` returns a copy of the waiting list (oldest first; `KeyError` for an unknown shift). A volunteer who is already on the waiting list gets `AlreadySignedUp` like a confirmed one.",
              "When a confirmed volunteer cancels, the first person on the waiting list becomes confirmed (at the end of the confirmed list). `cancel` also works for a volunteer on the waiting list: they are removed from it and the name is returned. A volunteer who is neither confirmed nor waiting is a `KeyError` as before. Waiting-list entries are not part of `shift.volunteers`, `hours_for`, `agenda` and the other readers: only confirmed volunteers count."),
        code={
            "lib/shiftboard/shift.rb::shift_init": "@waiting = []",
            "lib/shiftboard/shift.rb::shift_methods": '''
                def waiting
                  @waiting
                end
            ''',
            "lib/shiftboard/roster.rb::assignment_pre": '''
                raise AlreadySignedUp, "#{volunteer} is already waiting for #{shift.name}" if shift.waiting.include?(volunteer)
            ''',
            "lib/shiftboard/roster.rb::when_full": '''
                if shift.full?
                  shift.waiting << volunteer
                  return :waitlisted
                end
            ''',
            "lib/shiftboard/roster.rb::assigned_shifts": '''
                # The shifts a volunteer is committed to: confirmed or waiting.
                def assigned_shifts(volunteer)
                  @shifts.values.select { |s| s.confirmed.include?(volunteer) || s.waiting.include?(volunteer) }
                end
            ''',
            "lib/shiftboard/roster.rb::cancel_pre": '''
                if shift.waiting.include?(volunteer)
                  shift.waiting.delete(volunteer)
                  return volunteer
                end
            ''',
            "lib/shiftboard/roster.rb::on_cancel": '''
                shift.confirmed << shift.waiting.shift if !shift.full? && !shift.waiting.empty?
            ''',
            "T::base_full": "assert_equal :waitlisted, @r.sign_up(\"cy\", 1)",
            "lib/shiftboard/roster.rb::methods": '''
                def waitlist(shift_id)
                  fetch(shift_id).waiting.dup
                end
            ''',
        },
        readme="## Waiting list\n\nA full shift puts new volunteers on a waiting list (`sign_up` returns `:waitlisted`, `roster.waitlist(shift_id)` lists them). A cancellation promotes the first one; waiting volunteers can cancel too.\n",
        vtests='''
          def test_waitlist_basic
            @r.sign_up("ana", 2)
            assert_equal :waitlisted, @r.sign_up("bob", 2)
            assert_equal ["bob"], @r.waitlist(2)
          end
        ''',
        tests='''
          def test_waitlist
            assert_equal :confirmed, @r.sign_up("ana", 2)
            assert_equal :waitlisted, @r.sign_up("bob", 2)
            assert_equal :waitlisted, @r.sign_up("cy", 2)
            assert_equal ["bob", "cy"], @r.waitlist(2)
            assert_equal ["ana"], @r.fetch(2).volunteers
            assert_equal 0, @r.hours_for("bob")
            assert_raises(Shiftboard::AlreadySignedUp) { @r.sign_up("bob", 2) }
            assert_raises(Shiftboard::AlreadySignedUp) { @r.sign_up("ana", 2) }
            assert_raises(KeyError) { @r.waitlist(99) }
            @r.waitlist(2).clear
            assert_equal 2, @r.waitlist(2).size
          end

          def test_cancel_promotes_the_first_in_line
            @r.sign_up("ana", 2)
            @r.sign_up("bob", 2)
            @r.sign_up("cy", 2)
            assert_equal "ana", @r.cancel("ana", 2)
            assert_equal ["bob"], @r.fetch(2).volunteers
            assert_equal ["cy"], @r.waitlist(2)
            assert_equal 4, @r.hours_for("bob")
            assert_equal "cy", @r.cancel("cy", 2)
            assert_equal [], @r.waitlist(2)
            assert_equal ["bob"], @r.fetch(2).volunteers
            assert_raises(KeyError) { @r.cancel("cy", 2) }
            assert_equal :waitlisted, @r.sign_up("dee", 2)
            @r.sign_up("eve", 1)
            @r.sign_up("fay", 1)
            @r.sign_up("gus", 1)
            @r.cancel("eve", 1)
            assert_equal ["fay", "gus"], @r.fetch(1).volunteers
            assert_equal [], @r.waitlist(1)
          end
        ''',
        cross={
            "skills": {
                "reqs": ("A volunteer without the skill is refused with `MissingSkill` even when the shift is full (nobody is put on the waiting list without the skill).",),
                "tests": '''
                  def test_waitlist_needs_the_skill
                    g = @r.add_shift(name: "Grill", day: D + 2, start: 12, hours: 2, slots: 1, skill: "food")
                    @r.grant("ana", "food")
                    @r.grant("bob", "food")
                    @r.sign_up("ana", g.id)
                    assert_raises(Shiftboard::MissingSkill) { @r.sign_up("cy", g.id) }
                    assert_equal :waitlisted, @r.sign_up("bob", g.id)
                    assert_equal ["bob"], @r.waitlist(g.id)
                  end
                '''},
            "overlap": {
                "reqs": ("Shifts a volunteer is waiting for count like confirmed ones when the overlap is checked.",),
                "tests": '''
                  def test_waiting_counts_for_overlap
                    b = @r.add_shift(name: "Box office", day: D, start: 9, hours: 2, slots: 1)
                    @r.sign_up("bob", b.id)
                    assert_equal :waitlisted, @r.sign_up("ana", b.id)
                    assert_raises(Shiftboard::OverlapError) { @r.sign_up("ana", 1) }
                    @r.cancel("ana", b.id)
                    assert_equal :confirmed, @r.sign_up("ana", 1)
                  end
                '''},
            "max-hours": {
                "reqs": ("Shifts a volunteer is waiting for count like confirmed ones when the weekly limit is checked.",),
                "tests": '''
                  def test_waiting_counts_for_the_limit
                    r = Shiftboard::Roster.new(max_hours: 10)
                    a = r.add_shift(name: "A", day: D, start: 8, hours: 6, slots: 1)
                    b = r.add_shift(name: "B", day: D + 1, start: 8, hours: 6, slots: 1)
                    r.sign_up("bob", a.id)
                    assert_equal :waitlisted, r.sign_up("ana", a.id)
                    assert_raises(Shiftboard::HoursLimit) { r.sign_up("ana", b.id) }
                    assert_equal 0, r.hours_for("ana")
                    r.cancel("bob", a.id)
                    assert_equal 6, r.hours_for("ana")
                  end
                '''},
        },
    ))

    S.append(Slice(
        id="swap", title="Swapping shifts", d=4,
        pitch=("Volunteers trade shifts among themselves and the coordinator has to cancel and re-book both of them in the right order.",
               "Two volunteers should be able to swap shifts in one step."),
        reqs=("`roster.swap(a, shift_a_id, b, shift_b_id)` makes volunteer `a` (confirmed on shift A) and volunteer `b` (confirmed on shift B) trade places: afterwards `a` is on shift B and `b` on shift A, each taking the position in the confirmed list that the other one had. It returns `[shift_a, shift_b]`. Names are stripped; two equal (or blank) volunteers and two equal shift ids are an `ArgumentError`; an unknown shift is a `KeyError`; a volunteer who is not confirmed on the shift he is supposed to give up is the new `Shiftboard::NotSignedUp` (a `Shiftboard::Error`).",
              "After the trade each volunteer must be allowed to take the new shift: the checks of `sign_up` that apply before \"full\" are run for `a` on shift B and `b` on shift A (the \"already on the shift\" check, so `AlreadySignedUp` when `a` is already on shift B, and so on), counting the shift each of them gives up as given up. The swap is all or nothing: when anything fails nothing changes. Shift sizes never matter."),
        code={
            "lib/shiftboard/roster.rb::module_items": "class NotSignedUp < Error; end",
            "lib/shiftboard/roster.rb::methods": '''
                def swap(a, shift_a_id, b, shift_b_id)
                  a = a.to_s.strip
                  b = b.to_s.strip
                  raise ArgumentError, "swap needs two different volunteers" if a.empty? || b.empty? || a == b
                  raise ArgumentError, "swap needs two different shifts" if shift_a_id == shift_b_id

                  shift_a = fetch(shift_a_id)
                  shift_b = fetch(shift_b_id)
                  raise NotSignedUp, "#{a} is not on #{shift_a.name}" unless shift_a.confirmed.include?(a)
                  raise NotSignedUp, "#{b} is not on #{shift_b.name}" unless shift_b.confirmed.include?(b)

                  check_assignment(a, shift_b, [shift_a])
                  check_assignment(b, shift_a, [shift_b])
                  shift_a.confirmed[shift_a.confirmed.index(a)] = b
                  shift_b.confirmed[shift_b.confirmed.index(b)] = a
                  [shift_a, shift_b]
                end
            ''',
        },
        readme="## Swapping shifts\n\n`roster.swap(a, shift_a_id, b, shift_b_id)` trades the two volunteers' places (each takes the other's position) after checking that both may take the new shift; all or nothing; `NotSignedUp` when a volunteer is not on the shift he gives up.\n",
        vtests='''
          def test_swap_basic
            @r.sign_up("ana", 1)
            @r.sign_up("bob", 3)
            @r.swap("ana", 1, "bob", 3)
            assert_equal ["bob"], @r.fetch(1).volunteers
            assert_equal ["ana"], @r.fetch(3).volunteers
          end
        ''',
        tests='''
          def test_swap
            @r.sign_up("ana", 1)
            @r.sign_up("zed", 1)
            @r.sign_up("bob", 3)
            @r.sign_up("cy", 3)
            result = @r.swap(" zed ", 1, "cy", 3)
            assert_equal [1, 3], result.map(&:id)
            assert_equal ["ana", "cy"], @r.fetch(1).volunteers
            assert_equal ["bob", "zed"], @r.fetch(3).volunteers
            assert_equal 3, @r.hours_for("cy")
            assert_equal 8, @r.hours_for("zed")
            @r.swap("cy", 1, "zed", 3)
            assert_equal ["ana", "zed"], @r.fetch(1).volunteers
            assert_equal ["bob", "cy"], @r.fetch(3).volunteers
          end

          def test_swap_errors_change_nothing
            @r.sign_up("ana", 1)
            @r.sign_up("bob", 3)
            @r.sign_up("cy", 3)
            before = [@r.fetch(1).volunteers, @r.fetch(3).volunteers]
            assert_raises(ArgumentError) { @r.swap("ana", 1, "ana", 3) }
            assert_raises(ArgumentError) { @r.swap(" ", 1, "bob", 3) }
            assert_raises(ArgumentError) { @r.swap("ana", 1, "bob", 1) }
            assert_raises(KeyError) { @r.swap("ana", 1, "bob", 99) }
            assert_raises(KeyError) { @r.swap("ana", 99, "bob", 3) }
            assert_raises(Shiftboard::NotSignedUp) { @r.swap("bob", 1, "cy", 3) }
            assert_raises(Shiftboard::NotSignedUp) { @r.swap("ana", 1, "zed", 3) }
            assert_raises(Shiftboard::NotSignedUp) { @r.swap("ana", 3, "bob", 1) }
            @r.sign_up("bob", 1)
            assert_raises(Shiftboard::AlreadySignedUp) { @r.swap("ana", 1, "bob", 3) }
            assert_raises(Shiftboard::AlreadySignedUp) { @r.swap("bob", 3, "ana", 1) }
            assert_kind_of Shiftboard::Error, Shiftboard::NotSignedUp.new
            assert_equal before[1], @r.fetch(3).volunteers
            assert_equal ["ana", "bob"], @r.fetch(1).volunteers
          end
        ''',
        cross={
            "skills": {"tests": '''
                def test_swap_needs_the_skill
                  g = @r.add_shift(name: "Grill", day: D + 2, start: 12, hours: 2, slots: 1, skill: "food")
                  @r.grant("ana", "food")
                  @r.sign_up("ana", g.id)
                  @r.sign_up("bob", 1)
                  assert_raises(Shiftboard::MissingSkill) { @r.swap("ana", g.id, "bob", 1) }
                  assert_raises(Shiftboard::MissingSkill) { @r.swap("bob", 1, "ana", g.id) }
                  assert_equal ["ana"], @r.fetch(g.id).volunteers
                  assert_equal ["bob"], @r.fetch(1).volunteers
                  @r.grant("bob", "food")
                  @r.swap("bob", 1, "ana", g.id)
                  assert_equal ["bob"], @r.fetch(g.id).volunteers
                end
            '''},
            "overlap": {
                "reqs": ("The overlap check ignores the shift that is given up: swapping two overlapping shifts is fine, but a volunteer's other shifts are still checked.",),
                "tests": '''
                  def test_swap_checks_overlap
                    a = @r.add_shift(name: "A", day: D + 3, start: 8, hours: 4, slots: 1)
                    b = @r.add_shift(name: "B", day: D + 3, start: 10, hours: 4, slots: 1)
                    c = @r.add_shift(name: "C", day: D + 3, start: 13, hours: 2, slots: 1)
                    e = @r.add_shift(name: "E", day: D + 3, start: 11, hours: 1, slots: 1)
                    @r.sign_up("ana", a.id)
                    @r.sign_up("bob", b.id)
                    @r.swap("ana", a.id, "bob", b.id)
                    assert_equal ["bob"], @r.fetch(a.id).volunteers
                    assert_equal ["ana"], @r.fetch(b.id).volunteers
                    @r.sign_up("cy", c.id)
                    @r.sign_up("cy", e.id)
                    assert_raises(Shiftboard::OverlapError) { @r.swap("cy", c.id, "ana", b.id) }
                    assert_equal ["cy"], @r.fetch(c.id).volunteers
                    assert_equal ["ana"], @r.fetch(b.id).volunteers
                  end
                '''},
            "max-hours": {
                "reqs": ("The weekly limit is checked with the shift that is given up taken out of the week.",),
                "tests": '''
                  def test_swap_checks_the_hour_limit
                    r = Shiftboard::Roster.new(max_hours: 10)
                    a = r.add_shift(name: "A", day: D, start: 8, hours: 4, slots: 1)
                    b = r.add_shift(name: "B", day: D + 1, start: 8, hours: 8, slots: 1)
                    c = r.add_shift(name: "C", day: D + 2, start: 8, hours: 6, slots: 1)
                    d = r.add_shift(name: "D", day: D + 8, start: 8, hours: 8, slots: 1)
                    r.sign_up("ana", a.id)
                    r.sign_up("ana", c.id)
                    r.sign_up("bob", b.id)
                    assert_raises(Shiftboard::HoursLimit) { r.swap("ana", a.id, "bob", b.id) }
                    assert_equal ["ana"], r.fetch(a.id).volunteers
                    assert_equal ["bob"], r.fetch(b.id).volunteers
                    r.sign_up("eve", d.id)
                    r.swap("ana", c.id, "eve", d.id)
                    assert_equal ["eve"], r.fetch(c.id).volunteers
                    assert_equal ["ana"], r.fetch(d.id).volunteers
                  end
                '''},
            "waitlist": {
                "reqs": ("A volunteer who is on the waiting list of the shift he would receive counts as already being on it (`AlreadySignedUp`).",),
                "tests": '''
                  def test_swap_with_waiting_volunteers
                    @r.sign_up("bob", 2)
                    assert_equal :waitlisted, @r.sign_up("ana", 2)
                    @r.sign_up("ana", 1)
                    assert_raises(Shiftboard::AlreadySignedUp) { @r.swap("ana", 1, "bob", 2) }
                    assert_equal ["ana"], @r.fetch(1).volunteers
                    assert_equal ["bob"], @r.fetch(2).volunteers
                    assert_equal ["ana"], @r.waitlist(2)
                  end
                '''},
        },
    ))
    order = ["agenda", "fill-rate", "skills", "reminders", "overlap", "max-hours", "waitlist", "swap"]
    S.sort(key=lambda x: order.index(x.id))
    return S


APP = App(
    name="shiftboard", lang="ruby", title="the volunteer roster library", role="the festival volunteer coordinator", key="SHIFT",
    base={
        "README.md": README + "\n@@blocks features\n",
        "lib/shiftboard.rb": LIB,
        "lib/shiftboard/shift.rb": SHIFT,
        "lib/shiftboard/roster.rb": ROSTER,
        ".gitignore": "*.gem\n",
    },
    visible={"test/test_basic.rb": VISIBLE},
    hidden={"test/test_features.rb": HIDDEN},
)

register_app("feature-rb-shiftboard", APP, make_slices, n=18, summary="volunteer roster: agenda, fill rate, skills, reminders, overlaps, hour limits, waiting list, swaps")

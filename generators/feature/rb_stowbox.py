"""stowbox (ruby): left-luggage lockers extended with occupancy, lookup, receipt text, grace period, day cap, PINs, service, revenue, members, upgrades and reservations."""
import random

from fx import dd
from generators.feature._slices import App, Slice, fmt, register_app

README = dd('''
    # stowbox

    The locker bank of a railway station left-luggage room, as a small Ruby library (Ruby 3.3, standard library only). Run the
    tests with `ruby -Ilib -Itest -e 'Dir["test/test_*.rb"].sort.each { |f| require "./#{f}" }'`.

    ## Layout

    * `lib/stowbox.rb`: requires everything, the error classes and `Stowbox.clock`.
    * `lib/stowbox/bank.rb`: `Stowbox::Bank`.
    * `lib/stowbox/rental.rb`: `Stowbox::Rental` (an active rental).
    * `lib/stowbox/receipt.rb`: `Stowbox::Receipt` (what `release` returns).

    ## Basics

    Time is a whole number of minutes counted from midnight of day 0. Money is a whole number of cents. Lockers come in three
    sizes, the symbols `:small`, `:medium` and `:large`.

    * `Stowbox::Bank.new(name, sizes)`: the name must not be blank and is stripped; `sizes` is a non-empty hash from size to a
      positive integer count, for example `{ small: 2, medium: 1 }` (anything else is an `ArgumentError`, and so is an unknown
      option; there are no options yet). Lockers are numbered from 1: all the small ones first, then the medium ones, then the
      large ones. `bank.name` returns the name and `bank.lockers` returns a new array of `[number, size]` pairs.
    * `bank.rent(size, minute)` rents the free locker of that size with the lowest number and returns a `Stowbox::Rental` with
      `token`, `locker`, `size` and `start`. The tokens are `K001`, `K002`, ... in the order of the successful rentals. An
      unknown size or a minute that is not a non-negative integer is an `ArgumentError`; when every locker of that size is
      taken the call raises `Stowbox::Full`. A failed call changes nothing (no token is used up).
    * `bank.release(token, minute)` frees the locker and returns a `Stowbox::Receipt` with `token`, `locker`, `size`, `start`,
      `finish` (the minute given) and `fee`. An unknown or already released token raises `Stowbox::UnknownToken`; a minute that
      is not an integer, or lies before the start of the rental, is an `ArgumentError`. A failed call changes nothing.
    * The fee is counted in blocks of one started hour: a rental that lasted `d` minutes costs `max(1, ceil(d / 60))` blocks,
      and a block costs 100 cents for a small locker, 200 for a medium one and 350 for a large one.
    * `bank.free_count(size)` is the number of free lockers of that size, `bank.active` the active rentals ordered by locker
      number and `bank.receipts` a new array of all receipts in the order of release.
    * `Stowbox.clock(minute)` formats a minute as `d<day> HH:MM` (`d1 01:15` for 1515).
''')

LIB = '''\
require_relative "stowbox/rental"
require_relative "stowbox/receipt"
require_relative "stowbox/bank"
@@uniq requires

module Stowbox
  class Error < StandardError; end

  class Full < Error; end

  class UnknownToken < Error; end

  @@blocks module_items

  # "d1 01:15" for minute 1515.
  def self.clock(minute)
    format("d%d %02d:%02d", minute / 1440, minute % 1440 / 60, minute % 60)
  end
end
'''

RENTAL = '''\
module Stowbox
  # An active rental of one locker.
  class Rental
    attr_reader :token, :locker, :size, :start
    @@blocks rental_attrs

    def initialize(token, locker, size, start)
      @token = token
      @locker = locker
      @size = size
      @start = start
      @@slot rental_init
    end

    @@blocks rental_methods
  end
end
'''

RECEIPT = '''\
module Stowbox
  # What the renter gets back when a locker is released.
  class Receipt
    attr_reader :token, :locker, :size, :start, :finish, :fee

    def initialize(token, locker, size, start, finish, fee)
      @token = token
      @locker = locker
      @size = size
      @start = start
      @finish = finish
      @fee = fee
    end

    @@blocks receipt_methods
  end
end
'''

BANK = '''\
module Stowbox
  # Cents per started hour.
  RATES = { small: 100, medium: 200, large: 350 }.freeze
  SIZES = RATES.keys.freeze

  class Bank
    attr_reader :name

    def initialize(name, sizes, **opts)
      raise ArgumentError, "name is required" if name.to_s.strip.empty?
      raise ArgumentError, "sizes must be a non-empty hash" unless sizes.is_a?(Hash) && !sizes.empty?

      sizes.each do |size, count|
        raise ArgumentError, "unknown size #{size.inspect}" unless SIZES.include?(size)
        raise ArgumentError, "the count of #{size} must be a positive integer" unless count.is_a?(Integer) && count.positive?
      end
      @@slot init_opts
      raise ArgumentError, "unknown option(s): #{opts.keys.map(&:to_s).sort.join(', ')}" unless opts.empty?

      @name = name.to_s.strip
      @lockers = []
      SIZES.each { |size| sizes.fetch(size, 0).times { @lockers << [@lockers.size + 1, size] } }
      @rented = {}
      @receipts = []
      @token_seq = 0
      @@slot bank_init
    end

    def lockers
      @lockers.map(&:dup)
    end

    def rent(size, minute, **opts)
      check_size!(size)
      check_minute!(minute)
      @@slot pre_op
      number = free_numbers(size).first
      raise Full, "no free #{size} locker" if number.nil?

      start_rental(number, size, minute, opts)
    end

    def release(token, minute, **opts)
      check_minute!(minute)
      @@slot release_opts
      raise ArgumentError, "unknown option(s): #{opts.keys.map(&:to_s).sort.join(', ')}" unless opts.empty?

      @@slot pre_op
      rental = @rented.values.find { |r| r.token == token }
      raise UnknownToken, "no active rental #{token.inspect}" if rental.nil?
      raise ArgumentError, "the minute is before the start of the rental" if minute < rental.start

      @@slot release_checks
      amount = fee_for(rental, minute)
      @rented.delete(rental.locker)
      receipt = Receipt.new(rental.token, rental.locker, rental.size, rental.start, minute, amount)
      @receipts << receipt
      @@slot on_release
      receipt
    end

    def free_count(size)
      check_size!(size)
      free_numbers(size).size
    end

    def active
      @rented.sort.map { |_, rental| rental }
    end

    def receipts
      @receipts.dup
    end

    @@blocks methods

    private

    def check_size!(size)
      raise ArgumentError, "unknown size #{size.inspect}" unless SIZES.include?(size)
    end

    def check_minute!(minute)
      raise ArgumentError, "minute must be a non-negative integer" unless minute.is_a?(Integer) && minute >= 0
    end

    def free_numbers(size)
      numbers = @lockers.select { |_, s| s == size }.map(&:first)
      numbers -= @rented.keys
      @@slot free_filter
      numbers
    end

    def start_rental(number, size, minute, opts)
      @@slot rent_opts
      raise ArgumentError, "unknown option(s): #{opts.keys.map(&:to_s).sort.join(', ')}" unless opts.empty?

      @token_seq += 1
      rental = Rental.new(format("K%03d", @token_seq), number, size, minute)
      @@slot rental_init
      @rented[number] = rental
      rental
    end

    def fee_for(rental, minute)
      duration = minute - rental.start
      @@slot fee_pre
      total = charge(block_rates(rental, duration))
      @@slot fee_post
      total
    end

    @@default block_rates
    def block_rates(rental, duration)
      Array.new([(duration + 59) / 60, 1].max, RATES.fetch(rental.size))
    end
    @@end

    @@default charge
    def charge(rates)
      rates.sum
    end
    @@end

    @@blocks private_methods
  end
end
'''

TEST_HEAD = '''\
require "minitest/autorun"
require "stowbox"
@@uniq requires
'''

VISIBLE = TEST_HEAD + '''
class BasicTest < Minitest::Test
  def setup
    @b = Stowbox::Bank.new("Hut 7", { small: 2, medium: 1, large: 1 })
  end

  def test_layout
    assert_equal "Hut 7", @b.name
    assert_equal [[1, :small], [2, :small], [3, :medium], [4, :large]], @b.lockers
    assert_raises(ArgumentError) { Stowbox::Bank.new(" ", { small: 1 }) }
    assert_raises(ArgumentError) { Stowbox::Bank.new("x", { small: 0 }) }
  end

  def test_rent_and_release
    a = @b.rent(:small, 10)
    assert_equal ["K001", 1, :small, 10], [a.token, a.locker, a.size, a.start]
    b = @b.rent(:small, 12)
    assert_equal 2, b.locker
    assert_raises(Stowbox::Full) { @b.rent(:small, 13) }
    assert_equal 0, @b.free_count(:small)
    rc = @b.release(a.token, 70)
    assert_equal [a.token, 1, 10, 70, 100], [rc.token, rc.locker, rc.start, rc.finish, rc.fee]
    assert_equal 1, @b.free_count(:small)
    assert_equal 200, @b.release(b.token, 90 + 12).fee
    assert_equal [100, 200], @b.receipts.map(&:fee)
  end

  def test_errors
    assert_raises(ArgumentError) { @b.rent(:tiny, 1) }
    assert_raises(ArgumentError) { @b.rent(:small, -3) }
    assert_raises(Stowbox::UnknownToken) { @b.release("K404", 5) }
    r = @b.rent(:large, 100)
    assert_raises(ArgumentError) { @b.release(r.token, 99) }
    assert_equal 700, @b.release(r.token, 190).fee
    assert_equal "d1 01:15", Stowbox.clock(1515)
  end
  @@blocks tests
end
'''

HIDDEN = TEST_HEAD + '''
class FeatureTest < Minitest::Test
  @@default zero_fee
  ZERO_FEE = 100
  @@end

  def setup
    @b = Stowbox::Bank.new("Hut 7", { small: 2, medium: 1, large: 1 })
  end

  def fee_of(size, from, to)
    r = @b.rent(size, from)
    @b.release(r.token, to).fee
  end

  def test_base_construction
    assert_equal "Hut 7", @b.name
    assert_equal [[1, :small], [2, :small], [3, :medium], [4, :large]], @b.lockers
    assert_equal "Station", Stowbox::Bank.new("  Station ", { large: 1 }).name
    odd = Stowbox::Bank.new("Odd", { large: 1, small: 1 })
    assert_equal [[1, :small], [2, :large]], odd.lockers
    bad = [["", { small: 1 }], [nil, { small: 1 }], ["x", {}], ["x", nil], ["x", { tiny: 1 }], ["x", { small: 0 }],
           ["x", { small: 1.5 }], ["x", { small: -1 }], ["x", { "small" => 1 }]]
    bad.each do |n, s|
      assert_raises(ArgumentError, [n, s].inspect) { Stowbox::Bank.new(n, s) }
    end
    assert_raises(ArgumentError) { Stowbox::Bank.new("x", { small: 1 }, colour: "red") }
    @b.lockers.clear
    assert_equal 4, @b.lockers.size
    assert_kind_of Stowbox::Error, Stowbox::Full.new
    assert_kind_of Stowbox::Error, Stowbox::UnknownToken.new
  end

  def test_base_rent_and_free_count
    assert_raises(ArgumentError) { @b.rent(:small, 1, colour: "red") }
    r = @b.rent(:small, 10)
    assert_equal ["K001", 1, :small, 10], [r.token, r.locker, r.size, r.start]
    assert_equal 2, @b.rent(:small, 11).locker
    assert_equal 3, @b.rent(:medium, 12).locker
    assert_equal [0, 0, 1], [@b.free_count(:small), @b.free_count(:medium), @b.free_count(:large)]
    assert_raises(Stowbox::Full) { @b.rent(:small, 13) }
    assert_raises(Stowbox::Full) { @b.rent(:medium, 13) }
    assert_equal "K004", @b.rent(:large, 14).token
    assert_equal [1, 2, 3, 4], @b.active.map(&:locker)
    assert_equal %w[K001 K002 K003 K004], @b.active.map(&:token)
    assert_raises(Stowbox::Full) { @b.rent(:large, 15) }
    [[:tiny, 1], ["small", 1], [nil, 1], [:small, -1], [:small, 1.5], [:small, "1"], [:small, nil]].each do |s, m|
      assert_raises(ArgumentError, [s, m].inspect) { @b.rent(s, m) }
    end
    assert_raises(ArgumentError) { @b.free_count(:tiny) }
    assert_equal 4, @b.active.size
    only_large = Stowbox::Bank.new("L", { large: 2 })
    assert_equal 0, only_large.free_count(:small)
    assert_raises(Stowbox::Full) { only_large.rent(:small, 0) }
    assert_equal 1, only_large.rent(:large, 0).locker
  end

  def test_base_release_and_receipts
    a = @b.rent(:small, 100)
    m = @b.rent(:medium, 110)
    rc = @b.release(a.token, 130)
    assert_equal [a.token, 1, :small, 100, 130, 100], [rc.token, rc.locker, rc.size, rc.start, rc.finish, rc.fee]
    assert_raises(Stowbox::UnknownToken) { @b.release(a.token, 140) }
    assert_raises(Stowbox::UnknownToken) { @b.release("K999", 140) }
    assert_raises(ArgumentError) { @b.release(m.token, 109) }
    assert_raises(ArgumentError) { @b.release(m.token, -5) }
    assert_raises(ArgumentError) { @b.release(m.token, 150.0) }
    assert_raises(ArgumentError) { @b.release(m.token, 150, colour: "red") }
    assert_equal [m.token], @b.active.map(&:token)
    assert_equal 400, @b.release(m.token, 171).fee
    assert_equal [], @b.active
    assert_equal [100, 400], @b.receipts.map(&:fee)
    assert_equal [:small, :medium], @b.receipts.map(&:size)
    @b.receipts.clear
    assert_equal 2, @b.receipts.size
    assert_equal 1, @b.rent(:small, 200).locker
    assert_equal "K003", @b.active.first.token
  end

  def test_base_fees
    assert_equal ZERO_FEE, fee_of(:small, 0, 0)
    assert_equal 100, fee_of(:small, 5, 35)
    assert_equal 100, fee_of(:small, 5, 65)
    assert_equal 200, fee_of(:small, 5, 66)
    assert_equal 200, fee_of(:small, 0, 120)
    assert_equal 300, fee_of(:small, 0, 121)
    assert_equal 200, fee_of(:medium, 1000, 1060)
    assert_equal 400, fee_of(:medium, 1000, 1061)
    assert_equal 350, fee_of(:large, 30, 90)
    assert_equal 700, fee_of(:large, 30, 91)
  end

  def test_base_clock
    assert_equal "d0 00:00", Stowbox.clock(0)
    assert_equal "d0 23:59", Stowbox.clock(1439)
    assert_equal "d2 10:07", Stowbox.clock(2 * 1440 + 607)
  end
  @@blocks tests
end
'''


def ref_fee(size, start, finish, moves=(), cap=None, grace=None, pct=None):
    rates = {"small": 100, "medium": 200, "large": 350}
    dur = finish - start
    if grace is not None and dur <= grace:
        return 0
    n = max(1, -(-dur // 60))
    chain = [(start, size)] + list(moves)

    def rate_at(t):
        cur = chain[0][1]
        for m, sz in chain:
            if m <= t:
                cur = sz
        return rates[cur]

    rs = [rate_at(start + 60 * k) for k in range(n)]
    total = sum(min(sum(rs[i:i + 24]), cap) if cap else sum(rs[i:i + 24]) for i in range(0, n, 24))
    if pct is not None:
        total = (total * (100 - pct) + 50) // 100
    return total


def make_slices(rng: random.Random):
    G = rng.choice([10, 15, 20])
    C = rng.choice([800, 1000, 1200])
    P = rng.choice([15, 25, 35])
    H = rng.choice([30, 45, 60])
    S = []

    S.append(Slice(
        id="occupancy", title="Occupancy per size", d=1,
        pitch=("The station manager wants to know at a glance how full the room is.",
               "The display above the counter needs numbers: how many lockers of each size are in use."),
        reqs=("`bank.occupancy` returns a hash from size to `[used, total]`, with one entry for each size the bank has lockers of, in the order small, medium, large. `used` is the number of lockers with an active rental, `total` the number of lockers of that size.",),
        code={
            "lib/stowbox/bank.rb::methods": '''
                def occupancy
                  SIZES.each_with_object({}) do |size, out|
                    total = @lockers.count { |_, s| s == size }
                    out[size] = [@rented.values.count { |r| r.size == size }, total] if total.positive?
                  end
                end
            ''',
        },
        readme="## Occupancy per size\n\n`bank.occupancy` returns `{ small: [used, total], ... }` for the sizes the bank has, in the order small, medium, large.\n",
        vtests='''
          def test_occupancy_basic
            @b.rent(:medium, 5)
            assert_equal({ small: [0, 2], medium: [1, 1], large: [0, 1] }, @b.occupancy)
          end
        ''',
        tests='''
          def test_occupancy
            assert_equal [:small, :medium, :large], @b.occupancy.keys
            assert_equal({ small: [0, 2], medium: [0, 1], large: [0, 1] }, @b.occupancy)
            a = @b.rent(:small, 1)
            @b.rent(:small, 2)
            @b.rent(:large, 3)
            assert_equal({ small: [2, 2], medium: [0, 1], large: [1, 1] }, @b.occupancy)
            @b.release(a.token, 100)
            assert_equal [1, 2], @b.occupancy[:small]
            only = Stowbox::Bank.new("Odd", { large: 3, small: 1 })
            assert_equal [:small, :large], only.occupancy.keys
            assert_equal({ small: [0, 1], large: [0, 3] }, only.occupancy)
          end
        ''',
        cross={
            "reserve": {
                "reqs": ("A locker that is held for a reservation does not count as used in `occupancy`; it still counts in the total.",),
                "tests": '''
                  def test_occupancy_ignores_holds
                    @b.reserve(:small, 0)
                    assert_equal [0, 2], @b.occupancy[:small]
                    @b.rent(:small, 1)
                    assert_equal [1, 2], @b.occupancy[:small]
                  end
                '''},
            "upgrade": {"tests": '''
                def test_occupancy_follows_upgrades
                  r = @b.rent(:small, 0)
                  @b.upgrade(r.token, :large, 30)
                  assert_equal({ small: [0, 2], medium: [0, 1], large: [1, 1] }, @b.occupancy)
                end
            '''},
        },
    ))

    S.append(Slice(
        id="lookup", title="Finding a rental by token", d=1,
        pitch=("The counter staff get a token across the desk and have to scroll the list for the matching locker.",
               "Staff need to find the locker that belongs to a token."),
        reqs=("`bank.rental(token)` returns the active `Stowbox::Rental` with that token, or `nil` when there is none (unknown, or already released). `bank.locker_of(token)` returns its locker number, or `nil`.",),
        code={
            "lib/stowbox/bank.rb::methods": '''
                def rental(token)
                  @rented.values.find { |r| r.token == token }
                end

                def locker_of(token)
                  rental(token)&.locker
                end
            ''',
        },
        readme="## Finding a rental by token\n\n`bank.rental(token)` returns the active rental or `nil`; `bank.locker_of(token)` its locker number or `nil`.\n",
        vtests='''
          def test_lookup_basic
            r = @b.rent(:medium, 5)
            assert_equal r.token, @b.rental(r.token).token
            assert_equal 3, @b.locker_of(r.token)
          end
        ''',
        tests='''
          def test_lookup
            assert_nil @b.rental("K001")
            assert_nil @b.locker_of("K001")
            a = @b.rent(:small, 1)
            b = @b.rent(:large, 2)
            assert_equal [a.token, 1], [@b.rental(a.token).token, @b.locker_of(a.token)]
            assert_equal [b.token, 4], [@b.rental(b.token).token, @b.locker_of(b.token)]
            assert_nil @b.rental(nil)
            assert_nil @b.rental("k001")
            @b.release(a.token, 100)
            assert_nil @b.rental(a.token)
            assert_nil @b.locker_of(a.token)
            assert_equal 4, @b.locker_of(b.token)
          end
        ''',
        cross={
            "upgrade": {"tests": '''
                def test_lookup_follows_upgrades
                  r = @b.rent(:small, 0)
                  @b.upgrade(r.token, :medium, 10)
                  assert_equal 3, @b.locker_of(r.token)
                  assert_equal :medium, @b.rental(r.token).size
                end
            '''},
        },
    ))

    S.append(Slice(
        id="receipt_text", title="Printed receipts", d=1,
        pitch=("The receipt printer prints raw numbers and customers cannot tell what they paid for.",
               "Receipts need a readable text for the printer and for the end-of-day statement."),
        reqs=("`receipt.to_s` is `<token> locker <locker> (<size>) <start> - <finish>, fee <money>` where the two times are `Stowbox.clock` of the start and the finish, and the money is the fee in whole units with two decimals (`7.50` for 750 cents, `0.05` for 5), for example `K003 locker 3 (medium) d0 10:05 - d0 12:40, fee 8.00`.",
              "`bank.statement` returns the `to_s` of all receipts in the order of release, each followed by a newline (an empty string when nothing has been released)."),
        code={
            "lib/stowbox.rb::module_items": '''
                # 750 -> "7.50"
                def self.money(cents)
                  format("%d.%02d", cents / 100, cents % 100)
                end
            ''',
            "lib/stowbox/receipt.rb::receipt_methods": '''
                def to_s
                  "#{token} locker #{locker} (#{size}) #{Stowbox.clock(start)} - #{Stowbox.clock(finish)}, fee #{Stowbox.money(fee)}"
                end
            ''',
            "lib/stowbox/bank.rb::methods": '''
                def statement
                  @receipts.map { |r| "#{r}\\n" }.join
                end
            ''',
        },
        readme="## Printed receipts\n\n`receipt.to_s` is `<token> locker <n> (<size>) <start> - <finish>, fee <money>`; `bank.statement` has one such line per receipt.\n",
        vtests='''
          def test_receipt_text_basic
            r = @b.rent(:medium, 605)
            assert_equal "K001 locker 3 (medium) d0 10:05 - d0 12:40, fee 6.00", @b.release(r.token, 760).to_s
          end
        ''',
        tests='''
          def test_receipt_text
            assert_equal "", @b.statement
            a = @b.rent(:medium, 605)
            b = @b.rent(:large, 1500)
            assert_equal "K001 locker 3 (medium) d0 10:05 - d0 12:40, fee 6.00", @b.release(a.token, 760).to_s
            assert_equal "K002 locker 4 (large) d1 01:00 - d1 02:01, fee 7.00", @b.release(b.token, 1561).to_s
            assert_equal "K001 locker 3 (medium) d0 10:05 - d0 12:40, fee 6.00\\nK002 locker 4 (large) d1 01:00 - d1 02:01, fee 7.00\\n", @b.statement
            @b.statement
            assert_equal 2, @b.receipts.size
          end

          def test_receipt_money_format
            r = @b.rent(:small, 0)
            line = @b.release(r.token, 30).to_s
            assert line.end_with?("fee 1.00"), line
            assert_equal "0.05", Stowbox.money(5)
            assert_equal "0.00", Stowbox.money(0)
            assert_equal "12.30", Stowbox.money(1230)
            assert_equal "1234.56", Stowbox.money(123_456)
          end
        ''',
        cross={
            "upgrade": {"tests": '''
                def test_receipt_text_after_an_upgrade
                  r = @b.rent(:small, 0)
                  @b.upgrade(r.token, :medium, 60)
                  assert_equal "K001 locker 3 (medium) d0 00:00 - d0 03:20, fee 7.00", @b.release(r.token, 200).to_s
                end
            '''},
        },
    ))

    S.append(Slice(
        id="grace", title="Grace period", d=2,
        pitch=("People who change their mind at the counter and take their bag straight back are charged a whole hour.",
               "A very short rental should not cost anything."),
        reqs=(f"A rental that is released at most {G} minutes after its start (`finish - start <= {G}`, which includes 0) costs nothing: the receipt's `fee` is 0. From minute {G + 1} on it is charged as before.",),
        code={
            "T::zero_fee": "ZERO_FEE = 0",
            "lib/stowbox/bank.rb::fee_pre": fmt("return 0 if duration <= __G__", G=G),
        },
        readme=f"## Grace period\n\nA rental released within {G} minutes of its start (inclusive) is free.\n",
        vtests=fmt('''
          def test_grace_basic
            r = @b.rent(:small, 100)
            assert_equal 0, @b.release(r.token, 100 + __G__).fee
          end
        ''', G=G),
        tests=fmt('''
          def test_grace
            assert_equal 0, fee_of(:small, 100, 100)
            assert_equal 0, fee_of(:small, 100, 100 + __G__)
            assert_equal 100, fee_of(:small, 100, 100 + __G__ + 1)
            assert_equal 0, fee_of(:medium, 0, __G__)
            assert_equal 200, fee_of(:medium, 0, __G__ + 1)
            assert_equal 350, fee_of(:large, 7, 7 + 60)
            assert_equal 700, fee_of(:large, 7, 7 + 61)
            assert_equal [0, 0, 100, 0, 200, 350, 700], @b.receipts.map(&:fee)
            assert_equal [], @b.active
          end
        ''', G=G),
        cross={
            "daycap": {"tests": fmt('''
                def test_grace_and_cap
                  assert_equal 0, fee_of(:small, 0, __G__)
                  assert_equal __C__, fee_of(:small, 0, 13 * 60)
                end
            ''', G=G, C=C)},
            "members": {"tests": fmt('''
                def test_grace_is_free_for_members_too
                  @b.add_member("M-1")
                  r = @b.rent(:large, 0, member: "M-1")
                  assert_equal 0, @b.release(r.token, __G__).fee
                  r = @b.rent(:large, 100, member: "M-1")
                  assert_equal __F__, @b.release(r.token, 100 + __G__ + 1).fee
                end
            ''', G=G, F=ref_fee("large", 100, 100 + G + 1, pct=P))},
            "upgrade": {"tests": fmt('''
                def test_grace_after_an_upgrade
                  r = @b.rent(:small, 0)
                  @b.upgrade(r.token, :large, 3)
                  assert_equal 0, @b.release(r.token, __G__).fee
                  r = @b.rent(:small, 50)
                  @b.upgrade(r.token, :large, 50)
                  assert_equal 350, @b.release(r.token, 50 + __G__ + 1).fee
                end
            ''', G=G)},
        },
    ))

    S.append(Slice(
        id="daycap", title="Daily maximum", d=2,
        pitch=("A traveller left a bag for a week and paid more than the bag was worth, and then complained on the radio.",
               "Long rentals need a daily ceiling."),
        reqs=(f"A rental is charged per day: its blocks are split into days of 24 consecutive blocks counted from the start of the rental, and the cost of each day (the sum of its blocks) is at most {C} cents. The fee is the sum of the days. Short rentals are not affected (a rental of two hours or less costs what it cost before, whatever the size).",),
        code={
            "lib/stowbox/bank.rb::charge": '''
                def charge(rates)
                  rates.each_slice(24).sum { |day| [day.sum, __C__].min }
                end
            '''.replace("__C__", str(C)),
        },
        readme=f"## Daily maximum\n\nBlocks are grouped into days of 24 from the start of the rental; each day costs at most {C} cents.\n",
        vtests=fmt('''
          def test_daycap_basic
            r = @b.rent(:small, 0)
            assert_equal __C__, @b.release(r.token, 20 * 60).fee
          end
        ''', C=C),
        tests=fmt('''
          def test_daycap
            assert_equal 700, fee_of(:small, 0, 7 * 60)
            assert_equal 300, fee_of(:small, 0, 121)
            assert_equal __A__, fee_of(:small, 0, 13 * 60)
            assert_equal __B__, fee_of(:small, 0, 24 * 60)
            assert_equal __C1__, fee_of(:small, 0, 24 * 60 + 1)
            assert_equal __D__, fee_of(:small, 500, 500 + 48 * 60)
            assert_equal __E__, fee_of(:medium, 0, 25 * 60)
            assert_equal __F__, fee_of(:medium, 0, 30 * 60)
            assert_equal __G__, fee_of(:large, 0, 3 * 60)
            assert_equal __H__, fee_of(:large, 100, 100 + 73 * 60 + 1)
          end
        ''', A=ref_fee("small", 0, 780, cap=C), B=ref_fee("small", 0, 1440, cap=C), C1=ref_fee("small", 0, 1441, cap=C),
             D=ref_fee("small", 500, 500 + 2880, cap=C), E=ref_fee("medium", 0, 1500, cap=C),
             F=ref_fee("medium", 0, 1800, cap=C), G=ref_fee("large", 0, 180, cap=C),
             H=ref_fee("large", 100, 100 + 73 * 60 + 1, cap=C)),
        cross={
            "members": {"tests": fmt('''
                def test_cap_then_discount
                  @b.add_member("M-1")
                  r = @b.rent(:small, 0, member: "M-1")
                  assert_equal __F__, @b.release(r.token, 25 * 60 + 5).fee
                end
            ''', F=ref_fee("small", 0, 25 * 60 + 5, cap=C, pct=P))},
            "upgrade": {"reqs": ("The day cost is the sum of the block prices of that day, whatever the size of the locker was in each block.",),
                        "tests": fmt('''
                def test_cap_with_upgrades
                  r = @b.rent(:small, 0)
                  @b.upgrade(r.token, :medium, 300)
                  assert_equal __F__, @b.release(r.token, 1500).fee
                  r = @b.rent(:small, 0)
                  @b.upgrade(r.token, :medium, 60)
                  @b.upgrade(r.token, :large, 120)
                  assert_equal __G__, @b.release(r.token, 4 * 60).fee
                end
            ''', F=ref_fee("small", 0, 1500, moves=[(300, "medium")], cap=C),
                   G=ref_fee("small", 0, 240, moves=[(60, "medium"), (120, "large")], cap=C))},
        },
    ))

    S.append(Slice(
        id="pin", title="PIN-protected lockers", d=2,
        pitch=("Somebody walked off with the wrong suitcase because the token had been lost and found.",
               "Renters should be able to protect a locker with a code."),
        reqs=("`bank.rent(size, minute, pin: \"1234\")` takes an optional `pin:` that must be a string of exactly four digits (`ArgumentError` otherwise; the call changes nothing). `rental.pin_protected?` says whether the rental has one.",
              "`bank.release(token, minute, pin: nil)` takes an optional `pin:`. For a protected rental a missing or different pin raises the new `Stowbox::BadPin` (a `Stowbox::Error`) and the rental stays active; a rental without a pin can be released with or without a `pin:`."),
        code={
            "lib/stowbox.rb::module_items": "class BadPin < Error; end",
            "lib/stowbox/rental.rb::rental_methods": '''
                def pin=(pin)
                  @pin = pin
                end

                def pin_protected?
                  !@pin.nil?
                end

                def pin_ok?(given)
                  @pin.nil? || @pin == given
                end
            ''',
            "lib/stowbox/bank.rb::rent_opts": '''
                pin = opts.delete(:pin)
                raise ArgumentError, "pin must be four digits" unless pin.nil? || (pin.is_a?(String) && pin.match?(/\\A\\d{4}\\z/))
            ''',
            "lib/stowbox/bank.rb::rental_init": "rental.pin = pin",
            "lib/stowbox/bank.rb::release_opts": "pin = opts.delete(:pin)",
            "lib/stowbox/bank.rb::release_checks": 'raise BadPin, "wrong pin for #{token}" unless rental.pin_ok?(pin)',
        },
        readme="## PIN-protected lockers\n\n`rent(size, minute, pin: \"1234\")` protects a rental with a four-digit pin; `release(token, minute, pin: ...)` raises `Stowbox::BadPin` for a missing or wrong pin and leaves the rental active.\n",
        vtests='''
          def test_pin_basic
            r = @b.rent(:small, 0, pin: "0042")
            assert r.pin_protected?
            assert_raises(Stowbox::BadPin) { @b.release(r.token, 60) }
            assert_equal 100, @b.release(r.token, 60, pin: "0042").fee
          end
        ''',
        tests='''
          def test_pin
            plain = @b.rent(:small, 0)
            refute plain.pin_protected?
            r = @b.rent(:small, 1, pin: "0042")
            assert r.pin_protected?
            assert_raises(Stowbox::BadPin) { @b.release(r.token, 100) }
            assert_raises(Stowbox::BadPin) { @b.release(r.token, 100, pin: "0043") }
            assert_raises(Stowbox::BadPin) { @b.release(r.token, 100, pin: 42) }
            assert_raises(Stowbox::BadPin) { @b.release(r.token, 100, pin: nil) }
            assert_equal [plain.token, r.token], @b.active.map(&:token)
            assert_equal 200, @b.release(r.token, 100, pin: "0042").fee
            assert_equal 100, @b.release(plain.token, 30, pin: "9999").fee
            assert_raises(Stowbox::UnknownToken) { @b.release(r.token, 100, pin: "0042") }
            assert_kind_of Stowbox::Error, Stowbox::BadPin.new
          end

          def test_pin_validation
            ["123", "12345", "12a4", "", " 123", 1234, :"1234", ["1234"]].each do |bad|
              assert_raises(ArgumentError, bad.inspect) { @b.rent(:small, 0, pin: bad) }
            end
            assert_equal 2, @b.free_count(:small)
            assert_equal "K001", @b.rent(:small, 0, pin: "0000").token
            assert_raises(ArgumentError) { @b.rent(:small, 0, pin: "1234", colour: "red") }
            assert_equal 1, @b.free_count(:small)
            assert_raises(ArgumentError) { @b.release("K001", 10, pen: "0000") }
          end
        ''',
        cross={
            "reserve": {
                "reqs": ("`claim(code, minute, pin: nil)` takes the same `pin:` option as `rent`; an invalid pin is an `ArgumentError` and the reservation stays.",),
                "tests": '''
                  def test_claim_with_a_pin
                    h = @b.reserve(:medium, 0)
                    assert_raises(ArgumentError) { @b.claim(h.code, 5, pin: "12") }
                    r = @b.claim(h.code, 5, pin: "1234")
                    assert r.pin_protected?
                    assert_raises(Stowbox::BadPin) { @b.release(r.token, 100) }
                    assert_equal 400, @b.release(r.token, 100, pin: "1234").fee
                  end
                '''},
            "upgrade": {"tests": '''
                def test_pin_survives_an_upgrade
                  r = @b.rent(:small, 0, pin: "5555")
                  @b.upgrade(r.token, :medium, 10)
                  assert_raises(Stowbox::BadPin) { @b.release(r.token, 100) }
                  assert_equal 100, @b.release(r.token, 50, pin: "5555").fee
                end
            '''},
        },
    ))

    S.append(Slice(
        id="service", title="Lockers out of service", d=2,
        pitch=("A locker door was kicked in on Saturday and the system kept renting it out.",
               "Broken lockers must be taken out of circulation."),
        reqs=("`bank.take_out(number)` marks a locker as out of service and `bank.put_back(number)` brings it back (both are harmless when repeated; an unknown locker number is an `ArgumentError`). `bank.out_of_service` returns the numbers of the lockers that are out of service, ascending.",
              "A locker that is out of service is never rented and is not counted by `free_count`. A rental that is active on a locker when it is taken out stays valid until it is released; the locker is not free afterwards either, until it is put back."),
        code={
            "lib/stowbox/bank.rb::bank_init": "@out = []",
            "lib/stowbox/bank.rb::free_filter": "numbers -= @out",
            "lib/stowbox/bank.rb::methods": '''
                def take_out(number)
                  check_locker!(number)
                  @out << number unless @out.include?(number)
                  nil
                end

                def put_back(number)
                  check_locker!(number)
                  @out.delete(number)
                  nil
                end

                def out_of_service
                  @out.sort
                end
            ''',
            "lib/stowbox/bank.rb::private_methods": '''
                def check_locker!(number)
                  raise ArgumentError, "unknown locker #{number.inspect}" unless number.is_a?(Integer) && @lockers.any? { |n, _| n == number }
                end
            ''',
        },
        readme="## Lockers out of service\n\n`bank.take_out(n)`, `bank.put_back(n)` and `bank.out_of_service`: a locker that is out of service is never rented and not counted as free (an active rental keeps its locker until it is released).\n",
        vtests='''
          def test_service_basic
            @b.take_out(1)
            assert_equal 2, @b.rent(:small, 0).locker
            assert_equal [1], @b.out_of_service
          end
        ''',
        tests='''
          def test_service
            assert_equal [], @b.out_of_service
            @b.take_out(2)
            @b.take_out(1)
            @b.take_out(1)
            assert_equal [1, 2], @b.out_of_service
            assert_equal 0, @b.free_count(:small)
            assert_raises(Stowbox::Full) { @b.rent(:small, 0) }
            @b.put_back(1)
            @b.put_back(1)
            assert_equal [2], @b.out_of_service
            assert_equal 1, @b.free_count(:small)
            assert_equal 1, @b.rent(:small, 0).locker
            assert_raises(Stowbox::Full) { @b.rent(:small, 1) }
            assert_equal [3, 4], [@b.rent(:medium, 2).locker, @b.rent(:large, 3).locker]
          end

          def test_service_while_rented
            a = @b.rent(:small, 0)
            @b.take_out(a.locker)
            assert_equal [a.token], @b.active.map(&:token)
            assert_equal 2, @b.rent(:small, 5).locker
            @b.release(a.token, 70)
            assert_equal 0, @b.free_count(:small)
            assert_raises(Stowbox::Full) { @b.rent(:small, 80) }
            @b.put_back(1)
            assert_equal 1, @b.rent(:small, 90).locker
          end

          def test_service_validation
            [0, 5, -1, nil, "1", 1.0].each do |bad|
              assert_raises(ArgumentError, bad.inspect) { @b.take_out(bad) }
              assert_raises(ArgumentError, bad.inspect) { @b.put_back(bad) }
            end
            assert_equal [], @b.out_of_service
            @b.out_of_service << 3
            assert_equal [], @b.out_of_service
          end
        ''',
        cross={
            "reserve": {
                "reqs": ("A locker that is out of service is never reserved.",),
                "tests": '''
                  def test_reserve_skips_lockers_out_of_service
                    @b.take_out(1)
                    h = @b.reserve(:small, 0)
                    assert_equal 2, h.locker
                    assert_raises(Stowbox::Full) { @b.reserve(:small, 1) }
                  end
                '''},
            "upgrade": {"tests": '''
                def test_upgrade_skips_lockers_out_of_service
                  r = @b.rent(:small, 0)
                  @b.take_out(3)
                  assert_raises(Stowbox::Full) { @b.upgrade(r.token, :medium, 10) }
                  assert_equal 1, r.locker
                  assert_equal 4, @b.upgrade(r.token, :large, 10).locker
                end
            '''},
        },
    ))

    S.append(Slice(
        id="revenue", title="Revenue report", d=2,
        pitch=("The cashier adds up the day's receipts on a calculator and is never sure about the cut-off.",
               "The office wants the takings for a period."),
        reqs=("`bank.revenue(from, to)` returns the sum of the fees of all receipts with `from <= finish <= to` (both ends included), 0 when there are none. Both arguments must be non-negative integers and `from` must not be after `to` (`ArgumentError`).",),
        code={
            "lib/stowbox/bank.rb::methods": '''
                def revenue(from, to)
                  raise ArgumentError, "from and to must be non-negative integers" unless [from, to].all? { |m| m.is_a?(Integer) && m >= 0 }
                  raise ArgumentError, "from must not be after to" if from > to

                  @receipts.select { |r| r.finish >= from && r.finish <= to }.sum(&:fee)
                end
            ''',
        },
        readme="## Revenue report\n\n`bank.revenue(from, to)` sums the fees of the receipts released between `from` and `to` (inclusive).\n",
        vtests='''
          def test_revenue_basic
            r = @b.rent(:small, 0)
            @b.release(r.token, 60)
            assert_equal 100, @b.revenue(0, 1000)
          end
        ''',
        tests='''
          def test_revenue
            assert_equal 0, @b.revenue(0, 10_000)
            a = @b.rent(:small, 0)
            b = @b.rent(:medium, 0)
            c = @b.rent(:large, 0)
            @b.release(a.token, 30)
            @b.release(b.token, 60)
            @b.release(c.token, 90)
            assert_equal [100, 200, 700], @b.receipts.map(&:fee)
            assert_equal 1000, @b.revenue(0, 90)
            assert_equal 1000, @b.revenue(30, 90)
            assert_equal 900, @b.revenue(31, 90)
            assert_equal 300, @b.revenue(30, 60)
            assert_equal 200, @b.revenue(60, 60)
            assert_equal 0, @b.revenue(61, 89)
            assert_equal 0, @b.revenue(0, 29)
            assert_equal 0, @b.revenue(5000, 6000)
          end

          def test_revenue_validation
            assert_raises(ArgumentError) { @b.revenue(10, 5) }
            assert_raises(ArgumentError) { @b.revenue(-1, 5) }
            assert_raises(ArgumentError) { @b.revenue(1.5, 5) }
            assert_raises(ArgumentError) { @b.revenue(0, nil) }
            assert_raises(ArgumentError) { @b.revenue("0", 5) }
            assert_equal 0, @b.revenue(5, 5)
          end
        ''',
        cross={
            "members": {"tests": fmt('''
                def test_revenue_counts_discounted_fees
                  @b.add_member("M-1")
                  r = @b.rent(:large, 0, member: "M-1")
                  @b.release(r.token, 60)
                  assert_equal __F__, @b.revenue(0, 60)
                  r = @b.rent(:large, 100)
                  @b.release(r.token, 160)
                  assert_equal __F__ + 350, @b.revenue(0, 160)
                end
            ''', F=ref_fee("large", 0, 60, pct=P))},
            "grace": {"tests": fmt('''
                def test_revenue_of_free_rentals
                  r = @b.rent(:large, 0)
                  @b.release(r.token, __G__)
                  assert_equal 0, @b.revenue(0, 100)
                end
            ''', G=G)},
        },
    ))

    S.append(Slice(
        id="members", title="Member discount", d=3,
        pitch=("Season-ticket holders were promised a discount at the left-luggage room and the cashier does it by hand.",
               "Registered members should pay less."),
        reqs=(f"`bank.add_member(code)` registers a member: the code must be a non-blank string (`ArgumentError`), it is stripped, registering twice is harmless and the stripped code is returned. `bank.member?(code)` says whether a code (compared exactly as given) is registered.",
              f"`bank.rent(size, minute, member: code)` takes an optional `member:`; a code that is not registered raises the new `Stowbox::UnknownMember` (a `Stowbox::Error`) and changes nothing. `rental.member` returns the code or `nil`.",
              f"A member's fee is reduced by {P} percent: the fee that is computed as before is multiplied by {100 - P} / 100 and rounded half up to whole cents (a fee of 0 stays 0). Other rentals pay the normal fee."),
        code={
            "lib/stowbox.rb::module_items": "class UnknownMember < Error; end",
            "lib/stowbox/rental.rb::rental_attrs": "attr_accessor :member",
            "lib/stowbox/bank.rb::bank_init": "@members = []",
            "lib/stowbox/bank.rb::rent_opts": '''
                member = opts.delete(:member)
                raise UnknownMember, "unknown member #{member.inspect}" unless member.nil? || @members.include?(member)
            ''',
            "lib/stowbox/bank.rb::rental_init": "rental.member = member",
            "lib/stowbox/bank.rb::fee_post": fmt("total = (total * (100 - __P__) + 50) / 100 if rental.member", P=P),
            "lib/stowbox/bank.rb::methods": '''
                def add_member(code)
                  raise ArgumentError, "a member code must be a non-blank string" unless code.is_a?(String) && !code.strip.empty?

                  @members << code.strip unless @members.include?(code.strip)
                  code.strip
                end

                def member?(code)
                  @members.include?(code)
                end
            ''',
        },
        readme=f"## Member discount\n\n`bank.add_member(code)`, `bank.member?(code)` and `rent(..., member: code)`; members pay {100 - P} percent of the fee (rounded half up), unknown codes raise `Stowbox::UnknownMember`.\n",
        vtests=fmt('''
          def test_members_basic
            @b.add_member("M-1")
            r = @b.rent(:large, 0, member: "M-1")
            assert_equal "M-1", r.member
            assert_equal __F__, @b.release(r.token, 60).fee
            assert_raises(Stowbox::UnknownMember) { @b.rent(:small, 0, member: "M-2") }
          end
        ''', F=ref_fee("large", 0, 60, pct=P)),
        tests=fmt('''
          def test_members
            assert_equal "M-7", @b.add_member("  M-7 ")
            assert_equal "M-7", @b.add_member("M-7")
            assert @b.member?("M-7")
            refute @b.member?("m-7")
            refute @b.member?(" M-7")
            refute @b.member?(nil)
            plain = @b.rent(:small, 0)
            assert_nil plain.member
            assert_equal 300, @b.release(plain.token, 121).fee
            r = @b.rent(:large, 0, member: "M-7")
            assert_equal "M-7", r.member
            assert_equal __L1__, @b.release(r.token, 60).fee
            assert_equal 350, @b.release(@b.rent(:large, 100).token, 160).fee
            r = @b.rent(:small, 200, member: "M-7")
            assert_equal __S3__, @b.release(r.token, 200 + 121).fee
            r = @b.rent(:medium, 400, member: "M-7")
            assert_equal __M2__, @b.release(r.token, 400 + 61).fee
            r = @b.rent(:large, 500, member: "M-7")
            assert_equal __L2__, @b.release(r.token, 500 + 61).fee
          end

          def test_member_validation
            ["", "  ", nil, 7, :m, ["M"]].each do |bad|
              assert_raises(ArgumentError, bad.inspect) { @b.add_member(bad) }
            end
            refute @b.member?("")
            assert_raises(Stowbox::UnknownMember) { @b.rent(:small, 0, member: "M-1") }
            assert_raises(Stowbox::UnknownMember) { @b.rent(:small, 0, member: "") }
            @b.add_member("M-1")
            assert_raises(Stowbox::UnknownMember) { @b.rent(:small, 0, member: "M-1 ") }
            assert_equal 2, @b.free_count(:small)
            assert_equal "K001", @b.rent(:small, 0, member: "M-1").token
            assert_raises(ArgumentError) { @b.rent(:small, 0, member: "M-1", colour: "red") }
            assert_equal 1, @b.free_count(:small)
            assert_kind_of Stowbox::Error, Stowbox::UnknownMember.new
          end
        ''', L1=ref_fee("large", 0, 60, pct=P), S3=ref_fee("small", 0, 121, pct=P), M2=ref_fee("medium", 0, 61, pct=P),
             L2=ref_fee("large", 0, 61, pct=P)),
        cross={
            "upgrade": {"tests": fmt('''
                def test_member_discount_after_an_upgrade
                  @b.add_member("M-1")
                  r = @b.rent(:small, 0, member: "M-1")
                  @b.upgrade(r.token, :medium, 60)
                  assert_equal __F__, @b.release(r.token, 180).fee
                  assert_equal "M-1", r.member
                end
            ''', F=ref_fee("small", 0, 180, moves=[(60, "medium")], pct=P))},
            "reserve": {
                "reqs": ("`claim(code, minute, member: nil)` takes the same `member:` option as `rent`; an unknown code raises `Stowbox::UnknownMember` and the reservation stays.",),
                "tests": '''
                  def test_claim_as_a_member
                    @b.add_member("M-1")
                    h = @b.reserve(:small, 0)
                    assert_raises(Stowbox::UnknownMember) { @b.claim(h.code, 5, member: "M-9") }
                    r = @b.claim(h.code, 5, member: "M-1")
                    assert_equal "M-1", r.member
                  end
                '''},
        },
    ))

    S.append(Slice(
        id="upgrade", title="Upgrading to a bigger locker", d=4,
        pitch=("A traveller's second suitcase does not fit the small locker and the counter staff have to release and rent again, charging twice.",
               "Renters need to be able to move into a bigger locker without starting a new rental."),
        reqs=("`bank.upgrade(token, size, minute)` moves an active rental to the free locker with the lowest number of the new `size`, which must be larger than the rental's current size (small < medium < large; anything else is an `ArgumentError`). It returns the same rental object, whose `locker` and `size` now describe the new locker; the old locker is free again. The `start` and the token do not change.",
              "Errors, each leaving everything unchanged: an unknown size or a minute that is not a non-negative integer is an `ArgumentError`; an unknown token raises `Stowbox::UnknownToken`; a minute before the start of the rental or before its previous upgrade is an `ArgumentError`; no free locker of the new size raises `Stowbox::Full`.",
              "`rental.moves` returns a new array of `[minute, size]` pairs: first `[start, original size]`, then one pair for each upgrade, in order.",
              "The fee counts blocks as before, but a block is priced by the size the rental had when that block started: block `k` (counting from 0) starts at `start + 60 * k` and costs the rate of the size after all upgrades made at a minute up to and including that moment. The receipt shows the final locker and size."),
        code={
            "lib/stowbox/rental.rb::rental_init": "@moves = [[start, size]]",
            "lib/stowbox/rental.rb::rental_methods": '''
                def moves
                  @moves.map(&:dup)
                end

                def move_to(locker, size, minute)
                  @locker = locker
                  @size = size
                  @moves << [minute, size]
                end

                # The size the rental had at a given minute (not before the start).
                def size_at(minute)
                  @moves.select { |m, _| m <= minute }.last.last
                end
            ''',
            "lib/stowbox/bank.rb::methods": '''
                def upgrade(token, size, minute)
                  check_size!(size)
                  check_minute!(minute)
                  @@slot pre_op
                  rental = @rented.values.find { |r| r.token == token }
                  raise UnknownToken, "no active rental #{token.inspect}" if rental.nil?
                  raise ArgumentError, "the new size must be larger than #{rental.size}" unless SIZES.index(size) > SIZES.index(rental.size)
                  raise ArgumentError, "the minute is before the last change of the rental" if minute < rental.moves.last.first

                  number = free_numbers(size).first
                  raise Full, "no free #{size} locker" if number.nil?

                  @rented.delete(rental.locker)
                  rental.move_to(number, size, minute)
                  @rented[number] = rental
                  rental
                end
            ''',
            "lib/stowbox/bank.rb::block_rates": '''
                def block_rates(rental, duration)
                  Array.new([(duration + 59) / 60, 1].max) { |k| RATES.fetch(rental.size_at(rental.start + 60 * k)) }
                end
            ''',
        },
        readme="## Upgrading to a bigger locker\n\n`bank.upgrade(token, size, minute)` moves a rental to the lowest free locker of a larger size; `rental.moves` lists `[minute, size]` pairs. Each block of the fee is priced by the size the rental had when the block started.\n",
        vtests='''
          def test_upgrade_basic
            r = @b.rent(:small, 0)
            same = @b.upgrade(r.token, :medium, 90)
            assert_equal [3, :medium], [same.locker, same.size]
            assert_equal 2, @b.free_count(:small)
            assert_equal 600, @b.release(r.token, 200).fee
          end
        ''',
        tests='''
          def test_upgrade
            r = @b.rent(:small, 0)
            assert_equal [[0, :small]], r.moves
            u = @b.upgrade(r.token, :medium, 90)
            assert_same r, u
            assert_equal [3, :medium, 0, r.token], [u.locker, u.size, u.start, u.token]
            assert_equal [[0, :small], [90, :medium]], u.moves
            assert_equal [2, 0, 1], [@b.free_count(:small), @b.free_count(:medium), @b.free_count(:large)]
            assert_equal [3], @b.active.map(&:locker)
            rc = @b.release(r.token, 200)
            assert_equal [3, :medium, 0, 200, 600], [rc.locker, rc.size, rc.start, rc.finish, rc.fee]
            assert_equal [1, 1], [@b.free_count(:medium), @b.rent(:small, 300).locker]
          end

          def test_upgrade_block_boundaries
            r = @b.rent(:small, 0)
            @b.upgrade(r.token, :medium, 120)
            assert_equal 600, @b.release(r.token, 200).fee
            r = @b.rent(:small, 1000)
            @b.upgrade(r.token, :medium, 1121)
            assert_equal 500, @b.release(r.token, 1200).fee
            r = @b.rent(:small, 2000)
            @b.upgrade(r.token, :medium, 2000)
            assert_equal 200, @b.release(r.token, 2060).fee
            r = @b.rent(:small, 3000)
            @b.upgrade(r.token, :medium, 3030)
            @b.upgrade(r.token, :large, 3100)
            assert_equal [[3000, :small], [3030, :medium], [3100, :large]], r.moves
            assert_equal 650, @b.release(r.token, 3170).fee
            r = @b.rent(:small, 4000)
            @b.upgrade(r.token, :large, 4010)
            assert_equal 450, @b.release(r.token, 4070).fee
          end

          def test_upgrade_errors
            r = @b.rent(:medium, 10)
            before = [r.locker, r.size, r.moves]
            [[:medium, 20], [:small, 20], [:tiny, 20], ["large", 20], [:large, 9], [:large, -1], [:large, 1.5], [:large, nil]].each do |size, minute|
              assert_raises(ArgumentError, [size, minute].inspect) { @b.upgrade(r.token, size, minute) }
            end
            assert_raises(Stowbox::UnknownToken) { @b.upgrade("K404", :large, 20) }
            assert_equal before, [r.locker, r.size, r.moves]
            other = @b.rent(:large, 11)
            assert_raises(Stowbox::Full) { @b.upgrade(r.token, :large, 20) }
            assert_equal before, [r.locker, r.size, r.moves]
            assert_equal [3, 4], @b.active.map(&:locker)
            @b.release(other.token, 30)
            assert_equal 4, @b.upgrade(r.token, :large, 40).locker
            assert_equal [[10, :medium], [40, :large]], r.moves
            @b.release(r.token, 100)
            small = @b.rent(:small, 200)
            @b.upgrade(small.token, :medium, 210)
            assert_raises(ArgumentError) { @b.upgrade(small.token, :large, 209) }
            assert_equal [[200, :small], [210, :medium]], small.moves
            assert_equal 4, @b.upgrade(small.token, :large, 210).locker
            assert_equal [[200, :small], [210, :medium], [210, :large]], small.moves
            assert_raises(Stowbox::UnknownToken) { @b.upgrade(r.token, :large, 300) }
          end

          def test_upgrade_takes_the_lowest_free_locker
            b = Stowbox::Bank.new("Wide", { small: 1, medium: 3 })
            a = b.rent(:small, 0)
            b.rent(:medium, 1)
            assert_equal 3, b.upgrade(a.token, :medium, 5).locker
            assert_equal 1, b.rent(:small, 6).locker
            assert_equal 1, b.free_count(:medium)
          end
        ''',
    ))

    S.append(Slice(
        id="reserve", title="Reservations", d=4,
        pitch=("A school group phones ahead from the train and finds every large locker taken when it arrives.",
               "Lockers need to be held for people who are on the way."),
        reqs=(f"The bank has a clock: `bank.now` is the largest minute that was passed to `rent`, `release`, `reserve`, `claim` or `upgrade` so far (0 at the start).",
              f"`bank.reserve(size, minute)` holds the free locker of that size with the lowest number for {H} minutes and returns a `Stowbox::Reservation` (new class) with `code` (`R001`, `R002`, ... in the order of the successful reservations, a separate sequence from the tokens), `size`, `locker`, `made` (the minute given) and `expires` (`made + {H}`). A reservation is active while `expires > bank.now`. A held locker cannot be rented or reserved by anyone else and is not counted by `free_count`. When no locker of the size is free the call raises `Stowbox::Full`; argument errors are the same as for `rent`.",
              "`bank.claim(code, minute)` turns an active reservation into a rental of the held locker: it returns a `Stowbox::Rental` that starts at `minute` and gets the next token. A code that is unknown, already claimed, cancelled or no longer active raises the new `Stowbox::NoSuchReservation` (a `Stowbox::Error`). `bank.cancel(code)` drops an active reservation and returns it (same error). `bank.reservations` returns the active reservations ordered by code."),
        code={
            "lib/stowbox.rb::requires": 'require_relative "stowbox/reservation"',
            "lib/stowbox.rb::module_items": "class NoSuchReservation < Error; end",
            "lib/stowbox/bank.rb::bank_init": '''
                @holds = {}
                @hold_seq = 0
                @now = 0
            ''',
            "lib/stowbox/bank.rb::pre_op": "tick(minute)",
            "lib/stowbox/bank.rb::free_filter": "numbers -= active_holds.map(&:locker)",
            "lib/stowbox/bank.rb::methods": '''
                attr_reader :now

                def reserve(size, minute)
                  check_size!(size)
                  check_minute!(minute)
                  tick(minute)
                  number = free_numbers(size).first
                  raise Full, "no free #{size} locker" if number.nil?

                  @hold_seq += 1
                  hold = Reservation.new(format("R%03d", @hold_seq), size, number, minute, minute + __H__)
                  @holds[hold.code] = hold
                  hold
                end

                def claim(code, minute, **opts)
                  check_minute!(minute)
                  tick(minute)
                  hold = active_holds.find { |h| h.code == code }
                  raise NoSuchReservation, "no active reservation #{code.inspect}" if hold.nil?

                  rental = start_rental(hold.locker, hold.size, minute, opts)
                  @holds.delete(hold.code)
                  rental
                end

                def cancel(code)
                  hold = active_holds.find { |h| h.code == code }
                  raise NoSuchReservation, "no active reservation #{code.inspect}" if hold.nil?

                  @holds.delete(hold.code)
                  hold
                end

                def reservations
                  active_holds
                end
            '''.replace("__H__", str(H)),
            "lib/stowbox/bank.rb::private_methods": '''
                def tick(minute)
                  @now = minute if minute > @now
                end

                def active_holds
                  @holds.values.select { |h| h.expires > @now }.sort_by(&:code)
                end
            ''',
        },
        files={
            "lib/stowbox/reservation.rb": '''\
module Stowbox
  # A locker that is held for somebody who is on the way.
  class Reservation
    attr_reader :code, :size, :locker, :made, :expires

    def initialize(code, size, locker, made, expires)
      @code = code
      @size = size
      @locker = locker
      @made = made
      @expires = expires
    end
  end
end
''',
        },
        readme=f"## Reservations\n\n`bank.reserve(size, minute)` holds a locker for {H} minutes (`Stowbox::Reservation` with `code`, `size`, `locker`, `made`, `expires`); `bank.claim(code, minute)` turns it into a rental, `bank.cancel(code)` drops it, `bank.reservations` lists the active ones. `bank.now` is the largest minute the bank has been given.\n",
        vtests=fmt('''
          def test_reserve_basic
            h = @b.reserve(:small, 100)
            assert_equal ["R001", 1, 100 + __H__], [h.code, h.locker, h.expires]
            assert_equal 2, @b.rent(:small, 101).locker
            assert_equal 1, @b.claim(h.code, 110).locker
          end
        ''', H=H),
        tests=fmt('''
          def test_reserve
            assert_equal 0, @b.now
            h = @b.reserve(:small, 100)
            assert_equal ["R001", :small, 1, 100, 100 + __H__], [h.code, h.size, h.locker, h.made, h.expires]
            assert_equal 100, @b.now
            assert_equal 1, @b.free_count(:small)
            assert_equal [h.code], @b.reservations.map(&:code)
            r = @b.rent(:small, 101)
            assert_equal [2, "K001"], [r.locker, r.token]
            assert_raises(Stowbox::Full) { @b.rent(:small, 102) }
            assert_raises(Stowbox::Full) { @b.reserve(:small, 103) }
            assert_equal 103, @b.now
            h2 = @b.reserve(:medium, 104)
            assert_equal ["R002", 3], [h2.code, h2.locker]
            assert_raises(Stowbox::Full) { @b.reserve(:medium, 105) }
            assert_raises(Stowbox::Full) { @b.rent(:medium, 105) }
            assert_equal %w[R001 R002], @b.reservations.map(&:code)
            assert_equal "K002", @b.rent(:large, 106).token
          end

          def test_reservations_expire
            h = @b.reserve(:small, 100)
            @b.rent(:small, 101)
            assert_raises(Stowbox::Full) { @b.rent(:small, 99 + __H__) }
            assert_equal 99 + __H__, @b.now
            assert_equal [h.code], @b.reservations.map(&:code)
            r = @b.rent(:small, 100 + __H__)
            assert_equal 1, r.locker
            assert_equal [], @b.reservations
            assert_raises(Stowbox::NoSuchReservation) { @b.claim(h.code, 100 + __H__) }
            assert_raises(Stowbox::NoSuchReservation) { @b.cancel(h.code) }
            h2 = @b.reserve(:medium, 500)
            @b.release(r.token, 100 + __H__ + 5)
            assert_equal 500, @b.now
            assert_equal 1, @b.free_count(:small)
            assert_equal 0, @b.free_count(:medium)
            @b.release("K001", 500 + __H__ - 1)
            assert_equal 0, @b.free_count(:medium)
            assert_equal [h2.code], @b.reservations.map(&:code)
            @b.rent(:small, 500 + __H__)
            assert_equal 1, @b.free_count(:medium)
          end

          def test_claim_and_cancel
            h = @b.reserve(:small, 10)
            g = @b.reserve(:small, 11)
            assert_equal [1, 2], [h.locker, g.locker]
            r = @b.claim(g.code, 10 + __H__ - 1)
            assert_equal [2, :small, 10 + __H__ - 1, "K001"], [r.locker, r.size, r.start, r.token]
            assert_equal [h.code], @b.reservations.map(&:code)
            assert_raises(Stowbox::NoSuchReservation) { @b.claim(g.code, 20) }
            assert_raises(Stowbox::NoSuchReservation) { @b.claim("R999", 20) }
            assert_raises(Stowbox::NoSuchReservation) { @b.claim(nil, 20) }
            assert_equal h.code, @b.cancel(h.code).code
            assert_equal [], @b.reservations
            assert_equal 1, @b.free_count(:small)
            assert_raises(Stowbox::NoSuchReservation) { @b.cancel(h.code) }
            assert_raises(Stowbox::NoSuchReservation) { @b.claim(h.code, 30) }
            assert_equal 1, @b.rent(:small, 31).locker
            assert_equal "K002", @b.active.first.token
            assert_equal 200, @b.release(r.token, 10 + __H__ - 1 + 61).fee
          end

          def test_reserve_validation
            [[:tiny, 1], [nil, 1], [:small, -1], [:small, 1.5], [:small, nil]].each do |size, minute|
              assert_raises(ArgumentError, [size, minute].inspect) { @b.reserve(size, minute) }
            end
            assert_raises(ArgumentError) { @b.claim("R001", -1) }
            assert_equal [], @b.reservations
            assert_equal "R001", @b.reserve(:small, 0).code
            assert_equal "K001", @b.rent(:small, 1).token
            assert_equal "R002", @b.reserve(:large, 2).code
            assert_raises(ArgumentError) { @b.claim("R001", 1.5) }
          end
        ''', H=H),
    ))

    order = ["occupancy", "lookup", "receipt_text", "grace", "daycap", "pin", "service", "revenue", "members", "upgrade", "reserve"]
    S.sort(key=lambda x: order.index(x.id))
    return S


APP = App(
    name="stowbox", lang="ruby", title="the locker bank library", role="the station left-luggage manager", key="STOW",
    base={
        "README.md": README + "\n@@blocks features\n",
        "lib/stowbox.rb": LIB,
        "lib/stowbox/rental.rb": RENTAL,
        "lib/stowbox/receipt.rb": RECEIPT,
        "lib/stowbox/bank.rb": BANK,
        ".gitignore": "*.gem\n",
    },
    visible={"test/test_basic.rb": VISIBLE},
    hidden={"test/test_features.rb": HIDDEN},
)

register_app("feature-rb-stowbox", APP, make_slices, n=18, summary="left-luggage lockers: occupancy, lookup, receipts, grace period, day cap, PINs, service, revenue, members, upgrades, reservations")

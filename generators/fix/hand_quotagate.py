"""A layered ruby quota gateway (windows, plans and overrides, meter, gate). Several defects show up in a different
layer than the one that holds the cause, and the incident tickets combine causes."""
from fx import dd, family
from generators.fix._hand_kit import Base, Bug, tasks_from

README = dd('''
    # quotagate

    Request quotas for a small API (Ruby, `lib/quotagate/*.rb`, loaded with `require "quotagate"`). Time comes from a
    clock object with `now` (integer seconds); tests use `ManualClock`.

    * **Windows.** There are two fixed windows: `:minute` (60 s, aligned to the clock) and `:day` (86 400 s, aligned to
      the account's *local* midnight: an account has `utc_offset` in seconds, east of UTC positive, local time is UTC time
      plus the offset). A window is the half-open interval `[start, start + size)`: at `start + size` the count starts again
      from zero. The reset time of a window is `start + size`.
    * **Limits.** A plan has a `limits` hash such as `{ minute: 60, day: 5000 }`; a window that is missing, or `nil`, is
      unlimited. An account may carry `overrides`, merged over its plan's limits: an override replaces the plan's value for
      that window, and an override of `nil` means *unlimited* (it does not fall back to the plan).
    * **Cost.** A request has a cost in units (default 1). It is allowed only if `used + cost <= limit` holds in every
      limited window.
    * **Counting.** An allowed request adds its cost to every limited window; a denied request changes nothing anywhere.
      Counters belong to the account and the window. A plan change takes effect at once but never resets usage.
    * **Decisions.** `Meter#check_and_count(account, limits, cost = 1)` returns a `Decision`: `allowed`; `denied_by`, the
      windows that denied (minute before day); `resets`, a hash window => reset time (epoch seconds) of the *denying*
      windows only, empty for an allowed request; and `remaining`, a hash window => units left *after* this request for
      every limited window (after a denial nothing was consumed, so it is what is left).
    * **Gate.** `Gate#call(api_key, cost: 1)` returns `{ status:, headers:, body: }`.
      * unknown key: 401. An account whose plan is not in the plan table: 403 with body `"unknown plan"`.
      * allowed: 200. Denied: 429.
      * headers (none when the account has no limited window at all): `X-RateLimit-Limit` and `X-RateLimit-Remaining`
        describe the *tightest* window, the one with the fewest units remaining (ties: minute first). A 429 also carries
        `Retry-After`: the seconds until every denying window has reset, as a string (the largest of the waits).
    * `Gate#usage(api_key)` returns `{ window => { used:, limit: } }` for the limited windows (the dashboard).
''')

MAIN = dd('''
    require "quotagate/clock"
    require "quotagate/window"
    require "quotagate/plan"
    require "quotagate/meter"
    require "quotagate/gate"
''')

CLOCK = dd('''
    module Quotagate
      # A clock that only moves when told to.
      class ManualClock
        attr_reader :now

        def initialize(start = 0)
          @now = start
        end

        def advance(seconds)
          @now += seconds
          self
        end
      end
    end
''')

WINDOW = dd('''
    module Quotagate
      WINDOW_SIZES = { minute: 60, day: 86_400 }.freeze

      # Start of the window that contains +now+. Minute windows follow the clock; day windows start at the account's
      # local midnight (+utc_offset+ seconds east of UTC).
      def self.window_start(window, now, utc_offset)
        size = WINDOW_SIZES.fetch(window)
        offset = window == :day ? utc_offset : 0
        ((now + offset) / size) * size - offset
      end

      # The first second after the window: when the count starts again from zero.
      def self.window_reset(window, now, utc_offset)
        window_start(window, now, utc_offset) + WINDOW_SIZES.fetch(window)
      end
    end
''')

PLAN = dd('''
    module Quotagate
      class UnknownPlan < StandardError; end

      Plan = Struct.new(:name, :limits)

      class Plans
        def initialize(list)
          @by_name = list.each_with_object({}) { |plan, h| h[plan.name] = plan }
        end

        def fetch(name)
          @by_name.fetch(name) { raise UnknownPlan, "unknown plan #{name.inspect}" }
        end
      end

      class Account
        attr_accessor :id, :plan, :overrides, :utc_offset

        def initialize(id, plan, overrides: {}, utc_offset: 0)
          @id = id
          @plan = plan
          @overrides = overrides
          @utc_offset = utc_offset
        end
      end

      # The limits that apply to an account: its plan's limits with the account's overrides on top.
      def self.effective_limits(plans, account)
        plans.fetch(account.plan).limits.merge(account.overrides)
      end
    end
''')

METER = dd('''
    module Quotagate
      Decision = Struct.new(:allowed, :denied_by, :resets, :remaining, keyword_init: true)

      # Counts units per account and window and decides requests.
      class Meter
        def initialize(clock)
          @clock = clock
          @used = Hash.new(0)
        end

        # Units used so far in the account's current window.
        def used(account, window)
          @used[key(account, window)]
        end

        # Decide a request of +cost+ units against +limits+ ({window => limit or nil}); it is counted only if allowed.
        def check_and_count(account, limits, cost = 1)
          now = @clock.now
          denied_by = []
          resets = {}
          remaining = {}
          WINDOW_SIZES.each_key do |window|
            limit = limits[window]
            next if limit.nil?

            left = limit - used(account, window)
            if cost > left
              denied_by << window
              resets[window] = Quotagate.window_reset(window, now, account.utc_offset)
            end
            remaining[window] = left
          end
          if denied_by.empty?
            remaining.each_key do |window|
              @used[key(account, window)] += cost
              remaining[window] -= cost
            end
          end
          Decision.new(allowed: denied_by.empty?, denied_by: denied_by, resets: resets, remaining: remaining)
        end

        private

        def key(account, window)
          [account.id, window, Quotagate.window_start(window, @clock.now, account.utc_offset)]
        end
      end
    end
''')

GATE = dd('''
    module Quotagate
      # The front door: turns a request into a response hash.
      class Gate
        def initialize(plans:, accounts:, meter:, clock:)
          @plans = plans
          @accounts = accounts
          @meter = meter
          @clock = clock
        end

        def call(api_key, cost: 1)
          account = @accounts[api_key]
          return response(401, {}, "unknown key") unless account

          limits = begin
            Quotagate.effective_limits(@plans, account)
          rescue UnknownPlan
            return response(403, {}, "unknown plan")
          end
          decision = @meter.check_and_count(account, limits, cost)
          headers = {}
          unless decision.remaining.empty?
            window, left = decision.remaining.min_by { |_window, units| units }
            headers["X-RateLimit-Limit"] = limits[window].to_s
            headers["X-RateLimit-Remaining"] = left.to_s
          end
          return response(200, headers, "ok") if decision.allowed

          headers["Retry-After"] = (decision.resets.values.max - @clock.now).to_s
          response(429, headers, "rate limited")
        end

        # What the dashboard shows: usage and limit of every limited window.
        def usage(api_key)
          account = @accounts[api_key]
          return nil unless account

          limits = Quotagate.effective_limits(@plans, account)
          out = {}
          WINDOW_SIZES.each_key do |window|
            limit = limits[window]
            next if limit.nil?

            out[window] = { used: @meter.used(account, window), limit: limit }
          end
          out
        end

        private

        def response(status, headers, body)
          { status: status, headers: headers, body: body }
        end
      end
    end
''')

VISIBLE = {
    "test/test_basic.rb": dd('''
        require "minitest/autorun"
        require "quotagate"

        class TestBasic < Minitest::Test
          include Quotagate

          def setup
            @clock = ManualClock.new(1_699_920_000 + 36_000)
            plans = Plans.new([Plan.new("free", { minute: 5, day: 12 })])
            @accounts = { "k1" => Account.new("a1", "free") }
            @gate = Gate.new(plans: plans, accounts: @accounts, meter: Meter.new(@clock), clock: @clock)
          end

          def test_five_per_minute
            5.times { assert_equal 200, @gate.call("k1")[:status] }
            r = @gate.call("k1")
            assert_equal 429, r[:status]
            assert_equal "rate limited", r[:body]
          end

          def test_a_new_minute_starts_again
            5.times { @gate.call("k1") }
            @clock.advance(60)
            assert_equal 200, @gate.call("k1")[:status]
          end

          def test_unknown_key
            assert_equal 401, @gate.call("nope")[:status]
          end
        end
    '''),
}

HIDDEN = {
    "test/test_hidden_quotagate.rb": dd('''
        require "minitest/autorun"
        require "quotagate"

        class TestHiddenQuotagate < Minitest::Test
          include Quotagate

          DAY0 = 1_699_920_000 # a UTC midnight
          PLANS = Plans.new([
            Plan.new("free", { minute: 5, day: 12 }),
            Plan.new("pro", { minute: 60, day: 1000 }),
            Plan.new("tight", { minute: 5, day: 7 }),
            Plan.new("daily", { day: 3 }),
            Plan.new("minutely", { minute: 3 }),
            Plan.new("both3", { minute: 3, day: 3 }),
            Plan.new("open", {})
          ])

          def build(*accounts, at: DAY0 + 36_000)
            @clock = ManualClock.new(at)
            @meter = Meter.new(@clock)
            @accounts = accounts.each_with_object({}) { |a, h| h["key-#{a.id}"] = a }
            @gate = Gate.new(plans: PLANS, accounts: @accounts, meter: @meter, clock: @clock)
            accounts.first
          end

          def call(account, cost = 1)
            @gate.call("key-#{account.id}", cost: cost)
          end

          # ---- cost -------------------------------------------------------------------------------------------

          def test_cost_counts_against_the_limit
            a = build(Account.new("a", "free"))
            assert_equal 200, call(a, 3)[:status]
            assert_equal 429, call(a, 3)[:status]
            assert_equal 200, call(a, 2)[:status]
            assert_equal 429, call(a, 1)[:status]
            assert_equal({ minute: { used: 5, limit: 5 }, day: { used: 5, limit: 12 } }, @gate.usage("key-a"))
          end

          def test_a_cost_larger_than_the_whole_limit_is_never_allowed
            a = build(Account.new("a", "free"))
            assert_equal 429, call(a, 6)[:status]
            assert_equal 0, @meter.used(a, :minute)
          end

          def test_decision_remaining_is_after_the_request
            a = build(Account.new("a", "free"))
            d = @meter.check_and_count(a, { minute: 5, day: 12 }, 2)
            assert d.allowed
            assert_equal({ minute: 3, day: 10 }, d.remaining)
            assert_equal [], d.denied_by
            assert_equal({}, d.resets)
            d = @meter.check_and_count(a, { minute: 5, day: 12 }, 4)
            refute d.allowed
            assert_equal({ minute: 3, day: 10 }, d.remaining)
          end

          # ---- windows ----------------------------------------------------------------------------------------

          def test_minute_window_is_half_open
            a = build(Account.new("a", "free"), at: DAY0 + 36_000 + 59)
            5.times { assert_equal 200, call(a)[:status] }
            r = call(a)
            assert_equal 429, r[:status]
            assert_equal "1", r[:headers]["Retry-After"]
            @clock.advance(1)
            assert_equal 200, call(a)[:status]
          end

          def test_retry_after_is_the_wait_until_the_reset
            a = build(Account.new("a", "free"), at: DAY0 + 36_000 + 17)
            5.times { call(a) }
            r = call(a)
            assert_equal "43", r[:headers]["Retry-After"]
            @clock.advance(43)
            assert_equal 200, call(a)[:status]
          end

          def test_window_functions
            assert_equal DAY0 + 600, Quotagate.window_start(:minute, DAY0 + 659, 12_345)
            assert_equal DAY0 + 660, Quotagate.window_reset(:minute, DAY0 + 659, 12_345)
            assert_equal DAY0, Quotagate.window_start(:day, DAY0 + 86_399, 0)
            assert_equal DAY0 + 86_400, Quotagate.window_reset(:day, DAY0 + 5, 0)
          end

          def test_day_window_starts_at_local_midnight_east_of_utc
            # +09:00: local midnight is 15:00 UTC
            a = build(Account.new("tokyo", "daily", utc_offset: 32_400), at: DAY0 + 15 * 3600 - 3600)
            3.times { assert_equal 200, call(a)[:status] }
            @clock.advance(3599) # 14:59:59 UTC = 23:59:59 local
            r = call(a)
            assert_equal 429, r[:status]
            assert_equal "1", r[:headers]["Retry-After"]
            @clock.advance(1)
            assert_equal 200, call(a)[:status]
            assert_equal({ day: { used: 1, limit: 3 } }, @gate.usage("key-tokyo"))
          end

          def test_day_window_starts_at_local_midnight_west_of_utc
            # -05:00: local midnight is 05:00 UTC
            a = build(Account.new("ny", "daily", utc_offset: -18_000), at: DAY0 + 29 * 3600 - 3600)
            3.times { assert_equal 200, call(a)[:status] }
            r = call(a)
            assert_equal 429, r[:status]
            assert_equal "3600", r[:headers]["Retry-After"]
            @clock.advance(3599)
            assert_equal 429, call(a)[:status]
            @clock.advance(1)
            assert_equal 200, call(a)[:status]
          end

          def test_half_hour_offsets
            a = build(Account.new("delhi", "daily", utc_offset: 19_800), at: DAY0 + 18 * 3600 + 30 * 60 - 1)
            3.times { call(a) }
            assert_equal 429, call(a)[:status]
            @clock.advance(1)
            assert_equal 200, call(a)[:status]
          end

          # ---- counting ---------------------------------------------------------------------------------------

          def test_a_denial_by_the_day_window_consumes_no_minute_quota
            a = build(Account.new("a", "tight"))
            5.times { call(a) }
            @clock.advance(60)
            2.times { call(a) }
            assert_equal({ minute: { used: 2, limit: 5 }, day: { used: 7, limit: 7 } }, @gate.usage("key-a"))
            @clock.advance(60)
            4.times { assert_equal 429, call(a)[:status] }
            assert_equal({ minute: { used: 0, limit: 5 }, day: { used: 7, limit: 7 } }, @gate.usage("key-a"))
          end

          def test_a_denial_by_the_minute_window_consumes_no_day_quota
            a = build(Account.new("a", "tight"))
            5.times { call(a) }
            3.times { assert_equal 429, call(a)[:status] }
            assert_equal({ minute: { used: 5, limit: 5 }, day: { used: 5, limit: 7 } }, @gate.usage("key-a"))
          end

          def test_retry_after_waits_only_for_the_windows_that_denied
            a = build(Account.new("a", "free"), at: DAY0 + 36_000 + 10)
            5.times { call(a) }
            d = @meter.check_and_count(a, { minute: 5, day: 12 }, 1)
            assert_equal [:minute], d.denied_by
            assert_equal [DAY0 + 36_000 + 60], d.resets.values
            r = call(a)
            assert_equal "50", r[:headers]["Retry-After"]
          end

          def test_retry_after_is_the_largest_wait_when_both_windows_deny
            a = build(Account.new("a", "both3"), at: DAY0 + 36_000 + 10)
            3.times { call(a) }
            r = call(a)
            assert_equal 429, r[:status]
            assert_equal (DAY0 + 86_400 - (DAY0 + 36_000 + 10)).to_s, r[:headers]["Retry-After"]
            d = @meter.check_and_count(a, { minute: 3, day: 3 }, 1)
            assert_equal %i[minute day], d.denied_by
            assert_equal %i[minute day], d.resets.keys
          end

          def test_day_denial_alone_reports_the_day_reset
            a = build(Account.new("a", "tight"), at: DAY0 + 36_000)
            5.times { call(a) }
            @clock.advance(60)
            2.times { call(a) }
            @clock.advance(120)
            r = call(a)
            assert_equal 429, r[:status]
            assert_equal (86_400 - 36_000 - 180).to_s, r[:headers]["Retry-After"]
          end

          def test_a_plan_change_keeps_the_usage
            a = build(Account.new("a", "free"))
            4.times { call(a) }
            a.plan = "pro"
            assert_equal({ minute: { used: 4, limit: 60 }, day: { used: 4, limit: 1000 } }, @gate.usage("key-a"))
            a.plan = "free"
            assert_equal({ minute: { used: 4, limit: 5 }, day: { used: 4, limit: 12 } }, @gate.usage("key-a"))
            assert_equal 200, call(a)[:status]
            assert_equal 429, call(a)[:status]
          end

          def test_counters_are_per_account
            a = Account.new("a", "free")
            b = Account.new("b", "free")
            build(a, b)
            5.times { call(a) }
            assert_equal 429, call(a)[:status]
            assert_equal 200, call(b)[:status]
          end

          # ---- limits and overrides -----------------------------------------------------------------------------

          def test_nil_override_means_unlimited
            a = build(Account.new("a", "free", overrides: { minute: nil }))
            9.times { assert_equal 200, call(a)[:status] }
            assert_equal({ day: { used: 9, limit: 12 } }, @gate.usage("key-a"))
            3.times { call(a) }
            d = @meter.check_and_count(a, Quotagate.effective_limits(PLANS, a), 1)
            assert_equal [:day], d.denied_by
          end

          def test_overrides_replace_plan_values
            a = build(Account.new("a", "free", overrides: { minute: 2, day: 50 }))
            assert_equal({ minute: 2, day: 50 }, Quotagate.effective_limits(PLANS, a))
            2.times { assert_equal 200, call(a)[:status] }
            assert_equal 429, call(a)[:status]
          end

          def test_override_can_add_a_window_the_plan_lacks
            a = build(Account.new("a", "minutely", overrides: { day: 4 }))
            assert_equal({ minute: 3, day: 4 }, Quotagate.effective_limits(PLANS, a))
          end

          def test_fully_unlimited_accounts_get_no_rate_headers
            a = build(Account.new("a", "free", overrides: { minute: nil, day: nil }), Account.new("b", "open"))
            r = call(a)
            assert_equal 200, r[:status]
            assert_equal({}, r[:headers])
            assert_equal({}, @gate.usage("key-a"))
            assert_equal({}, call(@accounts["key-b"])[:headers])
          end

          # ---- headers -------------------------------------------------------------------------------------------

          def test_headers_describe_the_tightest_window
            a = build(Account.new("a", "free"))
            h = call(a)[:headers]
            assert_equal "5", h["X-RateLimit-Limit"]
            assert_equal "4", h["X-RateLimit-Remaining"]
            # use up the day: minute 5, minute 5, then 2 more in the third minute
            4.times { call(a) }
            @clock.advance(60)
            5.times { call(a) }
            @clock.advance(60)
            h = call(a)[:headers] # day used 11 of 12: one left; minute used 1 of 5
            assert_equal "12", h["X-RateLimit-Limit"]
            assert_equal "1", h["X-RateLimit-Remaining"]
          end

          def test_headers_of_a_denial_and_ties
            a = build(Account.new("a", "both3"))
            h = call(a)[:headers]
            assert_equal %w[3 2], [h["X-RateLimit-Limit"], h["X-RateLimit-Remaining"]]
            2.times { call(a) }
            r = call(a)
            assert_equal 429, r[:status]
            assert_equal %w[3 0], [r[:headers]["X-RateLimit-Limit"], r[:headers]["X-RateLimit-Remaining"]]
            assert r[:headers].key?("Retry-After")
          end

          def test_allowed_responses_have_no_retry_after
            a = build(Account.new("a", "free"))
            refute call(a)[:headers].key?("Retry-After")
          end

          # ---- gate errors -----------------------------------------------------------------------------------------

          def test_unknown_plan_is_forbidden
            a = build(Account.new("a", "legacy-pro"))
            r = call(a)
            assert_equal 403, r[:status]
            assert_equal "unknown plan", r[:body]
            assert_equal({}, r[:headers])
          end

          def test_unknown_key_is_unauthorized
            build(Account.new("a", "free"))
            assert_equal 401, @gate.call("nope")[:status]
            assert_nil @gate.usage("nope")
          end

          # ---- a model -------------------------------------------------------------------------------------------

          def test_random_traffic_matches_a_model
            rng = Random.new(2024)
            accounts = [
              Account.new("a", "free"),
              Account.new("b", "pro", utc_offset: 19_800),
              Account.new("c", "free", overrides: { minute: 9 }, utc_offset: -10_800),
              Account.new("d", "both3", utc_offset: 3_600)
            ]
            build(*accounts)
            limits = {
              "a" => { minute: 5, day: 12 }, "b" => { minute: 60, day: 1000 },
              "c" => { minute: 9, day: 12 }, "d" => { minute: 3, day: 3 }
            }
            used = Hash.new(0)
            400.times do |i|
              @clock.advance(rng.rand(10) == 0 ? rng.rand(40_000..90_000) : rng.rand(0..70))
              acct = accounts[rng.rand(accounts.size)]
              cost = rng.rand(1..3)
              now = @clock.now
              keys = {}
              waits = []
              limits[acct.id].each do |window, limit|
                size = Quotagate::WINDOW_SIZES[window]
                off = window == :day ? acct.utc_offset : 0
                idx = (now + off).div(size)
                keys[window] = [acct.id, window, idx]
                waits << (idx + 1) * size - off - now if used[keys[window]] + cost > limit
              end
              r = call(acct, cost)
              if waits.empty?
                assert_equal 200, r[:status], "step #{i}"
                keys.each_value { |k| used[k] += cost }
              else
                assert_equal 429, r[:status], "step #{i}"
                assert_equal waits.max.to_s, r[:headers]["Retry-After"], "step #{i}"
              end
            end
          end
        end
    '''),
}

REPORTED_RETRY = {
    "test/test_reported.rb": dd('''
        require "minitest/autorun"
        require "quotagate"

        class TestReported < Minitest::Test
          include Quotagate

          def test_retry_after_matches_the_next_window
            clock = ManualClock.new(1_699_920_000 + 36_000 + 17)
            plans = Plans.new([Plan.new("free", { minute: 5, day: 12 })])
            gate = Gate.new(plans: plans, accounts: { "k" => Account.new("a", "free") }, meter: Meter.new(clock), clock: clock)
            5.times { gate.call("k") }
            r = gate.call("k")
            assert_equal 43, r[:headers]["Retry-After"].to_i
            clock.advance(43)
            assert_equal 200, gate.call("k")[:status]
          end
        end
    '''),
}


def _prompts() -> dict:
    p = {}
    p["cost"] = (
        "Our batch endpoint charges 5 units per call (`cost: 5`). A client with 60 requests per minute still got 62 units "
        "through in one minute: a call is accepted as long as *some* quota is left, even when it costs more than what is left."
    )

    def retry_ci(c):
        return (
            "Clients that honour `Retry-After` come back one second too early and are rejected a second time (two 429s in a row "
            "in the access log). Reduced to a test, this is what our CI prints:\n\n```\n" + c.visible_out(14) + "\n```\n"
        )

    p["retry-ci"] = retry_ci
    p["unknown-plan"] = (
        "A customer whose billing plan was retired (their account still says `legacy-pro`, which is no longer in the plan table) "
        "gets a server error from the gateway instead of the documented 403 answer."
    )
    p["day-sign"] = (
        "Our Tokyo customers (UTC+9) say their daily quota resets at 18:00 their time, not at midnight. Customers in UTC are fine, and "
        "so are minute limits."
    )
    p["denied-consumes"] = (
        "Dashboard oddity: an account locked out by its *daily* limit shows its per-minute usage at 5 of 5 as well, and the minute "
        "counter climbs with every refused request. Tester's note: refused requests must not consume anything, in any window."
    )
    p["nil-override"] = (
        "Enterprise customer Hartmann was promised unlimited requests per minute (we set `minute: nil` in their overrides, only the "
        "daily limit applies), but they are throttled at the plan's 60 per minute."
    )
    p["retry-too-long"] = (
        "A short burst over the per-minute limit comes back with `Retry-After: 49000`, about 13 hours; well-behaved clients go "
        "silent for the rest of the day. A refusal because of the minute window should say when *the minute window* resets."
    )
    p["plan-key"] = (
        "Support case: a customer upgraded from free to pro at 14:00 and the dashboard instantly showed 0 used, so they got a whole new "
        "day's worth of quota; downgrading does the same. Usage is supposed to survive plan changes."
    )
    p["loosest"] = (
        "Clients that pace themselves by the `X-RateLimit-*` headers keep running into 429s the headers never warned about: the "
        "headers show the daily window (limit 12, remaining 11) while the account is two requests away from its per-minute limit. "
        "The README says which window the headers describe."
    )
    p["enterprise-pair"] = (
        "Two complaints from the same customer, Hartmann (enterprise, unlimited requests per minute by override `minute: nil`, "
        "daily limit 12 in this test plan): (1) they are throttled at the plan's per-minute value anyway, and (2) their pacing client, "
        "which reads `X-RateLimit-Remaining`, says it still has lots of room (it shows the daily window) while it is about to hit another "
        "limit. Please fix both."
    )
    p["burn-and-wait"] = (
        "Incident review for the Friday lockout. Timeline: a client bursts over its per-minute limit, receives `Retry-After` of "
        "several hours (the wait for a window that did not even deny), goes quiet - and the account's daily usage on the dashboard "
        "is far higher than the successful calls (refused calls were counted). Both effects trace back to how a refusal is handled. Please fix the gateway."
    )
    p["onboarding"] = (
        "Onboarding incident, customer Sakura (Tokyo, UTC+9, enterprise). Three things went wrong in their first week: (1) their daily "
        "quota did not reset at local midnight but at 18:00 local; (2) the unlimited per-minute option we set up for them (`minute: nil` "
        "override) never took effect, they were throttled at the plan's per-minute value; (3) when they were moved from the trial plan "
        "to the enterprise plan mid-day, the dashboard went back to zero used and they got a second day's worth. Please fix all of it."
    )
    return p


def _base() -> Base:
    P = _prompts()
    good = {
        "README.md": README, "lib/quotagate.rb": MAIN, "lib/quotagate/clock.rb": CLOCK, "lib/quotagate/window.rb": WINDOW,
        "lib/quotagate/plan.rb": PLAN, "lib/quotagate/meter.rb": METER, "lib/quotagate/gate.rb": GATE,
    }
    wi, pl, me, ga = "lib/quotagate/window.rb", "lib/quotagate/plan.rb", "lib/quotagate/meter.rb", "lib/quotagate/gate.rb"

    deny_ok = ("        if cost > left\n          denied_by << window\n          resets[window] = Quotagate.window_reset(window, now, account.utc_offset)\n        end\n        remaining[window] = left\n      end\n      if denied_by.empty?\n        remaining.each_key do |window|\n          @used[key(account, window)] += cost\n          remaining[window] -= cost\n        end\n      end\n")
    consume_as_you_go = (deny_ok,
                         "        if cost > left\n          denied_by << window\n          resets[window] = Quotagate.window_reset(window, now, account.utc_offset)\n        else\n          @used[key(account, window)] += cost\n          left -= cost\n        end\n        remaining[window] = left\n      end\n")
    resets_always = ("        if cost > left\n          denied_by << window\n          resets[window] = Quotagate.window_reset(window, now, account.utc_offset)\n        end\n        remaining[window] = left\n",
                     "        denied_by << window if cost > left\n        resets[window] = Quotagate.window_reset(window, now, account.utc_offset)\n        remaining[window] = left\n")
    both = (deny_ok,
            "        if cost > left\n          denied_by << window\n        else\n          @used[key(account, window)] += cost\n          left -= cost\n        end\n        resets[window] = Quotagate.window_reset(window, now, account.utc_offset)\n        remaining[window] = left\n      end\n")
    sign = ("    ((now + offset) / size) * size - offset\n", "    ((now - offset) / size) * size + offset\n")
    nil_over = ("    plans.fetch(account.plan).limits.merge(account.overrides)\n", "    plans.fetch(account.plan).limits.merge(account.overrides.compact)\n")
    plan_key = ("      [account.id, window, Quotagate.window_start(window, @clock.now, account.utc_offset)]\n",
                "      [account.id, account.plan, window, Quotagate.window_start(window, @clock.now, account.utc_offset)]\n")
    loosest = ("        window, left = decision.remaining.min_by { |_window, units| units }\n", "        window, left = decision.remaining.max_by { |_window, units| units }\n")
    bugs = [
        Bug("cost-is-not-part-of-the-check", 2, {me: [("        if cost > left\n          denied_by << window\n", "        if left <= 0\n          denied_by << window\n")]}, P["cost"]),
        Bug("reset-is-one-second-early", 2, {wi: [("    window_start(window, now, utc_offset) + WINDOW_SIZES.fetch(window)\n", "    window_start(window, now, utc_offset) + WINDOW_SIZES.fetch(window) - 1\n")]}, P["retry-ci"], reported=REPORTED_RETRY),
        Bug("unknown-plan-is-a-server-error", 2, {ga: [("      rescue UnknownPlan\n", "      rescue KeyError\n")]}, P["unknown-plan"]),
        Bug("day-offset-has-the-wrong-sign", 3, {wi: [sign]}, P["day-sign"]),
        Bug("refused-requests-are-counted", 3, {me: [consume_as_you_go]}, P["denied-consumes"]),
        Bug("nil-override-falls-back-to-the-plan", 4, {pl: [nil_over]}, P["nil-override"]),
        Bug("retry-after-includes-windows-that-allowed", 4, {me: [resets_always]}, P["retry-too-long"]),
        Bug("plan-name-in-the-counter-key", 4, {me: [plan_key]}, P["plan-key"]),
        Bug("headers-describe-the-loosest-window", 3, {ga: [loosest]}, P["loosest"]),
        Bug("unlimited-override-and-header-window", 4, {pl: [nil_over], ga: [loosest]}, P["enterprise-pair"]),
        Bug("refusal-burns-quota-and-waits-too-long", 4, {me: [both]}, P["burn-and-wait"]),
        Bug("onboarding-incident", 5, {wi: [sign], pl: [nil_over], me: [plan_key]}, P["onboarding"]),
    ]
    return Base("quotagate", "ruby", good, VISIBLE, HIDDEN, bugs)


@family("fix-hand-quota-gate", category="fix", lang="ruby", kind="fix", n=12,
        summary="a layered ruby quota gateway (windows, plan overrides, meter, gate) with cross-layer defects and incident tickets")
def gen(rng, n):
    return tasks_from([_base()])

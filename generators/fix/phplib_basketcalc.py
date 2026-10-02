"""Shopping-basket pricing across three modules (php): line promotions, a coupon shared over the lines, free-shipping threshold and VAT extraction; bugs injected into the library."""
from fx import Lib, dd

from generators.fix import _lang3

README1 = dd(r'''
    # basketcalc

    Prices a shopping basket. Three classes in `src/`: `Basket` (the pricing steps), `Promo` (line promotions) and `Allocator` (sharing an amount). All amounts are integer **cents**, all prices **include VAT**.
    `InvalidArgumentException` is thrown for invalid input.

    ## `Basket::price(array $lines, array $opts = []): array`

    **Lines**: each is `['sku' => string, 'price' => int, 'qty' => int, 'tax' => 'std'|'red'|'zero', 'promo' => ...]`; `price` is the unit price, `qty` at least 0, `price` at least 0 and `tax` one of
    the three classes (default `'std'` when missing); `promo` is optional (see `Promo`). Anything else is `InvalidArgumentException`. VAT rates are per mille: `std` 190, `red` 70, `zero` 0.

    **Options** (all optional): `'coupon' => ['pct' => int, 'cap' => int]` or `['fixed' => int]`; `'shipping' => ['flat' => int, 'free_over' => int]`.

    Steps, in this order:

    1. **Line price**: `gross = price * qty`. The line's promotion discount (see `Promo`, never more than `gross`) gives `net1 = gross - promo`.
    2. **Subtotal** = the sum of the `net1`.
    3. **Coupon**: with `pct` the discount is `subtotal * pct / 100` rounded to the nearest cent with halves up, then limited by `cap` when there is one; with `fixed` it is `fixed`; in both cases never more than the subtotal. `pct` must be in `0..100`, `cap` and `fixed` at
       least 0. The coupon amount is shared over the lines **in proportion to their `net1`** with `Allocator::share`; `net2 = net1 - share`. With no coupon, or a subtotal of 0, nothing is shared.
    4. **Shipping**: with the `shipping` option: `0` when the sum of the `net2` is **at least** `free_over` (when `free_over` is given), otherwise `flat`; also `0` when the basket has no items at all (sum of `qty` is 0). Without the option, 0.
    5. **VAT** (contained in the prices): for each line `vat = net2 * rate / (1000 + rate)` rounded to the nearest cent, halves up; the shipping is taxed at the `std` rate the same way.

    Result:

        [
          'lines'    => [ ['sku' => ..., 'gross' => ..., 'promo' => ..., 'coupon' => ..., 'net' => net2, 'vat' => ...], ... ],   // same order as the input
          'subtotal' => ...,   // step 2
          'coupon'   => ...,   // the coupon amount
          'shipping' => ...,
          'total'    => ...,   // sum of the net2 plus shipping
          'vat'      => ...,   // sum of the line VAT plus the shipping VAT
        ]

    ## `Promo::discount(array $line): int`

    The discount of one line's `promo` (0 when there is none), at most `price * qty`:

    * `['type' => 'bundle', 'buy' => B, 'free' => F]` ("buy B get F free"): units are taken in groups of `B + F`; in every complete group the last `F` units are free, and in the final incomplete group the units beyond the first `B` are free
      (`qty % (B + F) - B`, when positive). The discount is the number of free units times the unit price. `B >= 1` and `F >= 1` are required.
    * `['type' => 'tier', 'tiers' => [[minQty, pct], ...]]`: the tier with the **largest** `minQty` that is `<= qty` applies (tiers in any order); the discount is `price * qty * pct / 100` rounded to the nearest cent, halves up. No tier reached: 0.
      `minQty >= 1` and `pct` in `1..100` are required.
    * any other `type` is invalid.

    ## `Allocator::share(int $amount, array $weights): array`

    Splits `$amount` (at least 0) into one integer share per weight, proportionally: each share first gets `floor(amount * weight / sum)`, the leftover cents go one each to the shares with the largest remainder `amount * weight mod sum`, ties to the
    earlier one. The shares add up to `$amount`. A weight of 0 never gets a share. Weights must be non-negative ints; when their sum is 0 every share is 0 (and `$amount` is then ignored).
''')

F2 = dd(r'''
    <?php
    declare(strict_types=1);

    class Allocator
    {
        public static function share(int $amount, array $weights): array
        {
            if ($amount < 0) {
                throw new InvalidArgumentException('negative amount');
            }
            $sum = 0;
            foreach ($weights as $w) {
                if (!is_int($w) || $w < 0) {
                    throw new InvalidArgumentException('bad weight');
                }
                $sum += $w;
            }
            $n = count($weights);
            if ($sum === 0) {
                return array_fill(0, $n, 0);
            }
            $shares = [];
            $rem = [];
            $given = 0;
            $i = 0;
            foreach ($weights as $w) {
                $shares[$i] = intdiv($amount * $w, $sum);
                $rem[$i] = ($amount * $w) % $sum;
                $given += $shares[$i];
                $i++;
            }
            for ($left = $amount - $given; $left > 0; $left--) {
                $best = -1;
                for ($j = 0; $j < $n; $j++) {
                    if ($weights[$j] > 0 && ($best < 0 || $rem[$j] > $rem[$best])) {
                        $best = $j;
                    }
                }
                $shares[$best]++;
                $rem[$best] = -1;
            }
            return $shares;
        }
    }
''')

F3 = dd(r'''
    <?php
    declare(strict_types=1);

    require_once __DIR__ . '/Allocator.php';
    require_once __DIR__ . '/Promo.php';

    class Basket
    {
        private const RATES = ['std' => 190, 'red' => 70, 'zero' => 0];

        private static function vat(int $gross, int $rate): int
        {
            $den = 1000 + $rate;
            return intdiv(2 * $gross * $rate + $den, 2 * $den);
        }

        public static function price(array $lines, array $opts = []): array
        {
            $rows = [];
            $items = 0;
            foreach ($lines as $line) {
                $tax = $line['tax'] ?? 'std';
                if (!isset($line['sku'], $line['price'], $line['qty']) || !is_int($line['price']) || !is_int($line['qty'])
                    || $line['price'] < 0 || $line['qty'] < 0 || !isset(self::RATES[$tax])) {
                    throw new InvalidArgumentException('bad basket line');
                }
                $line['tax'] = $tax;
                $gross = $line['price'] * $line['qty'];
                $promo = Promo::discount($line);
                $rows[] = ['sku' => $line['sku'], 'gross' => $gross, 'promo' => $promo, 'net1' => $gross - $promo, 'tax' => $tax];
                $items += $line['qty'];
            }
            $subtotal = array_sum(array_column($rows, 'net1'));

            $coupon = 0;
            if (isset($opts['coupon'])) {
                $c = $opts['coupon'];
                if (isset($c['pct'])) {
                    if ($c['pct'] < 0 || $c['pct'] > 100 || (isset($c['cap']) && $c['cap'] < 0)) {
                        throw new InvalidArgumentException('bad coupon');
                    }
                    $coupon = intdiv($subtotal * $c['pct'] * 2 + 100, 200);
                    if (isset($c['cap'])) {
                        $coupon = min($coupon, $c['cap']);
                    }
                } elseif (isset($c['fixed'])) {
                    if ($c['fixed'] < 0) {
                        throw new InvalidArgumentException('bad coupon');
                    }
                    $coupon = $c['fixed'];
                } else {
                    throw new InvalidArgumentException('bad coupon');
                }
                $coupon = min($coupon, $subtotal);
            }
            $shares = $coupon > 0 ? Allocator::share($coupon, array_column($rows, 'net1')) : array_fill(0, count($rows), 0);

            $out = [];
            $total = 0;
            $vat = 0;
            foreach ($rows as $i => $r) {
                $net = $r['net1'] - $shares[$i];
                $lineVat = self::vat($net, self::RATES[$r['tax']]);
                $out[] = ['sku' => $r['sku'], 'gross' => $r['gross'], 'promo' => $r['promo'], 'coupon' => $shares[$i], 'net' => $net, 'vat' => $lineVat];
                $total += $net;
                $vat += $lineVat;
            }

            $shipping = 0;
            if (isset($opts['shipping']) && $items > 0) {
                $s = $opts['shipping'];
                $free = isset($s['free_over']) && $total >= $s['free_over'];
                $shipping = $free ? 0 : ($s['flat'] ?? 0);
            }
            $vat += self::vat($shipping, self::RATES['std']);
            return ['lines' => $out, 'subtotal' => $subtotal, 'coupon' => $coupon, 'shipping' => $shipping, 'total' => $total + $shipping, 'vat' => $vat];
        }
    }
''')

F4 = dd(r'''
    <?php
    declare(strict_types=1);

    class Promo
    {
        public static function discount(array $line): int
        {
            if (!isset($line['promo'])) {
                return 0;
            }
            $promo = $line['promo'];
            $gross = $line['price'] * $line['qty'];
            $qty = $line['qty'];
            switch ($promo['type'] ?? null) {
                case 'bundle':
                    $buy = $promo['buy'] ?? 0;
                    $free = $promo['free'] ?? 0;
                    if (!is_int($buy) || !is_int($free) || $buy < 1 || $free < 1) {
                        throw new InvalidArgumentException('bad bundle promotion');
                    }
                    $group = $buy + $free;
                    $freeUnits = intdiv($qty, $group) * $free + max(0, $qty % $group - $buy);
                    return min($gross, $freeUnits * $line['price']);
                case 'tier':
                    $best = null;
                    foreach ($promo['tiers'] ?? [] as $tier) {
                        [$min, $pct] = $tier;
                        if (!is_int($min) || !is_int($pct) || $min < 1 || $pct < 1 || $pct > 100) {
                            throw new InvalidArgumentException('bad tier');
                        }
                        if ($min <= $qty && ($best === null || $min > $best[0])) {
                            $best = [$min, $pct];
                        }
                    }
                    if ($best === null) {
                        return 0;
                    }
                    return min($gross, intdiv($gross * $best[1] * 2 + 100, 200));
                default:
                    throw new InvalidArgumentException('unknown promotion type');
            }
        }
    }
''')

V5 = dd(r'''
    require __DIR__ . '/../src/Basket.php';

    test('basics', function () {
        $r = Basket::price([['sku' => 'A', 'price' => 1000, 'qty' => 3, 'tax' => 'std', 'promo' => ['type' => 'bundle', 'buy' => 2, 'free' => 1]]]);
        eq($r['subtotal'], 2000);
        eq($r['lines'][0]['promo'], 1000);
        eq($r['total'], 2000);
        eq(Allocator::share(100, [1, 1, 1]), [34, 33, 33]);
    });

    t_done();
''')

H6 = dd(r'''
    require __DIR__ . '/../src/Basket.php';

    $CASES = [
        [[], [], ['lines' => [], 'subtotal' => 0, 'coupon' => 0, 'shipping' => 0, 'total' => 0, 'vat' => 0]],
        [[['sku' => 'A', 'price' => 1000, 'qty' => 0, 'tax' => 'std']], [], ['lines' => [['sku' => 'A', 'gross' => 0, 'promo' => 0, 'coupon' => 0, 'net' => 0, 'vat' => 0]], 'subtotal' => 0, 'coupon' => 0, 'shipping' => 0, 'total' => 0, 'vat' => 0]],
        [[['sku' => 'A', 'price' => 1000, 'qty' => 1, 'tax' => 'std']], [], ['lines' => [['sku' => 'A', 'gross' => 1000, 'promo' => 0, 'coupon' => 0, 'net' => 1000, 'vat' => 160]], 'subtotal' => 1000, 'coupon' => 0, 'shipping' => 0, 'total' => 1000, 'vat' => 160]],
        [[['sku' => 'A', 'price' => 999, 'qty' => 3, 'tax' => 'red']], [], ['lines' => [['sku' => 'A', 'gross' => 2997, 'promo' => 0, 'coupon' => 0, 'net' => 2997, 'vat' => 196]], 'subtotal' => 2997, 'coupon' => 0, 'shipping' => 0, 'total' => 2997, 'vat' => 196]],
        [[['sku' => 'A', 'price' => 999, 'qty' => 3, 'tax' => 'zero']], [], ['lines' => [['sku' => 'A', 'gross' => 2997, 'promo' => 0, 'coupon' => 0, 'net' => 2997, 'vat' => 0]], 'subtotal' => 2997, 'coupon' => 0, 'shipping' => 0, 'total' => 2997, 'vat' => 0]],
        [[['sku' => 'A', 'price' => 1999, 'qty' => 2, 'tax' => 'std'], ['sku' => 'B', 'price' => 500, 'qty' => 1, 'tax' => 'red']], [], ['lines' => [['sku' => 'A', 'gross' => 3998, 'promo' => 0, 'coupon' => 0, 'net' => 3998, 'vat' => 638], ['sku' => 'B', 'gross' => 500, 'promo' => 0, 'coupon' => 0, 'net' => 500, 'vat' => 33]], 'subtotal' => 4498, 'coupon' => 0, 'shipping' => 0, 'total' => 4498, 'vat' => 671]],
        [[['sku' => 'A', 'price' => 1000, 'qty' => 2]], [], ['lines' => [['sku' => 'A', 'gross' => 2000, 'promo' => 0, 'coupon' => 0, 'net' => 2000, 'vat' => 319]], 'subtotal' => 2000, 'coupon' => 0, 'shipping' => 0, 'total' => 2000, 'vat' => 319]],
        [[['sku' => 'A', 'price' => 1000, 'qty' => 3, 'tax' => 'std', 'promo' => ['type' => 'bundle', 'buy' => 2, 'free' => 1]]], [], ['lines' => [['sku' => 'A', 'gross' => 3000, 'promo' => 1000, 'coupon' => 0, 'net' => 2000, 'vat' => 319]], 'subtotal' => 2000, 'coupon' => 0, 'shipping' => 0, 'total' => 2000, 'vat' => 319]],
        [[['sku' => 'A', 'price' => 1000, 'qty' => 2, 'tax' => 'std', 'promo' => ['type' => 'bundle', 'buy' => 2, 'free' => 1]]], [], ['lines' => [['sku' => 'A', 'gross' => 2000, 'promo' => 0, 'coupon' => 0, 'net' => 2000, 'vat' => 319]], 'subtotal' => 2000, 'coupon' => 0, 'shipping' => 0, 'total' => 2000, 'vat' => 319]],
        [[['sku' => 'A', 'price' => 1000, 'qty' => 6, 'tax' => 'std', 'promo' => ['type' => 'bundle', 'buy' => 2, 'free' => 1]]], [], ['lines' => [['sku' => 'A', 'gross' => 6000, 'promo' => 2000, 'coupon' => 0, 'net' => 4000, 'vat' => 639]], 'subtotal' => 4000, 'coupon' => 0, 'shipping' => 0, 'total' => 4000, 'vat' => 639]],
        [[['sku' => 'A', 'price' => 1000, 'qty' => 7, 'tax' => 'std', 'promo' => ['type' => 'bundle', 'buy' => 2, 'free' => 1]]], [], ['lines' => [['sku' => 'A', 'gross' => 7000, 'promo' => 2000, 'coupon' => 0, 'net' => 5000, 'vat' => 798]], 'subtotal' => 5000, 'coupon' => 0, 'shipping' => 0, 'total' => 5000, 'vat' => 798]],
        [[['sku' => 'A', 'price' => 1000, 'qty' => 8, 'tax' => 'std', 'promo' => ['type' => 'bundle', 'buy' => 2, 'free' => 1]]], [], ['lines' => [['sku' => 'A', 'gross' => 8000, 'promo' => 2000, 'coupon' => 0, 'net' => 6000, 'vat' => 958]], 'subtotal' => 6000, 'coupon' => 0, 'shipping' => 0, 'total' => 6000, 'vat' => 958]],
        [[['sku' => 'A', 'price' => 1000, 'qty' => 9, 'tax' => 'std', 'promo' => ['type' => 'bundle', 'buy' => 2, 'free' => 1]]], [], ['lines' => [['sku' => 'A', 'gross' => 9000, 'promo' => 3000, 'coupon' => 0, 'net' => 6000, 'vat' => 958]], 'subtotal' => 6000, 'coupon' => 0, 'shipping' => 0, 'total' => 6000, 'vat' => 958]],
        [[['sku' => 'A', 'price' => 1000, 'qty' => 1, 'tax' => 'std', 'promo' => ['type' => 'bundle', 'buy' => 1, 'free' => 1]]], [], ['lines' => [['sku' => 'A', 'gross' => 1000, 'promo' => 0, 'coupon' => 0, 'net' => 1000, 'vat' => 160]], 'subtotal' => 1000, 'coupon' => 0, 'shipping' => 0, 'total' => 1000, 'vat' => 160]],
        [[['sku' => 'A', 'price' => 1000, 'qty' => 2, 'tax' => 'std', 'promo' => ['type' => 'bundle', 'buy' => 1, 'free' => 1]]], [], ['lines' => [['sku' => 'A', 'gross' => 2000, 'promo' => 1000, 'coupon' => 0, 'net' => 1000, 'vat' => 160]], 'subtotal' => 1000, 'coupon' => 0, 'shipping' => 0, 'total' => 1000, 'vat' => 160]],
        [[['sku' => 'A', 'price' => 1000, 'qty' => 5, 'tax' => 'std', 'promo' => ['type' => 'bundle', 'buy' => 1, 'free' => 1]]], [], ['lines' => [['sku' => 'A', 'gross' => 5000, 'promo' => 2000, 'coupon' => 0, 'net' => 3000, 'vat' => 479]], 'subtotal' => 3000, 'coupon' => 0, 'shipping' => 0, 'total' => 3000, 'vat' => 479]],
        [[['sku' => 'A', 'price' => 1000, 'qty' => 5, 'tax' => 'std', 'promo' => ['type' => 'bundle', 'buy' => 3, 'free' => 2]]], [], ['lines' => [['sku' => 'A', 'gross' => 5000, 'promo' => 2000, 'coupon' => 0, 'net' => 3000, 'vat' => 479]], 'subtotal' => 3000, 'coupon' => 0, 'shipping' => 0, 'total' => 3000, 'vat' => 479]],
        [[['sku' => 'A', 'price' => 1000, 'qty' => 4, 'tax' => 'std', 'promo' => ['type' => 'bundle', 'buy' => 3, 'free' => 2]]], [], ['lines' => [['sku' => 'A', 'gross' => 4000, 'promo' => 1000, 'coupon' => 0, 'net' => 3000, 'vat' => 479]], 'subtotal' => 3000, 'coupon' => 0, 'shipping' => 0, 'total' => 3000, 'vat' => 479]],
        [[['sku' => 'A', 'price' => 1000, 'qty' => 3, 'tax' => 'std', 'promo' => ['type' => 'bundle', 'buy' => 3, 'free' => 2]]], [], ['lines' => [['sku' => 'A', 'gross' => 3000, 'promo' => 0, 'coupon' => 0, 'net' => 3000, 'vat' => 479]], 'subtotal' => 3000, 'coupon' => 0, 'shipping' => 0, 'total' => 3000, 'vat' => 479]],
        [[['sku' => 'A', 'price' => 1000, 'qty' => 10, 'tax' => 'std', 'promo' => ['type' => 'bundle', 'buy' => 3, 'free' => 2]]], [], ['lines' => [['sku' => 'A', 'gross' => 10000, 'promo' => 4000, 'coupon' => 0, 'net' => 6000, 'vat' => 958]], 'subtotal' => 6000, 'coupon' => 0, 'shipping' => 0, 'total' => 6000, 'vat' => 958]],
        [[['sku' => 'A', 'price' => 1000, 'qty' => 11, 'tax' => 'std', 'promo' => ['type' => 'bundle', 'buy' => 3, 'free' => 2]]], [], ['lines' => [['sku' => 'A', 'gross' => 11000, 'promo' => 4000, 'coupon' => 0, 'net' => 7000, 'vat' => 1118]], 'subtotal' => 7000, 'coupon' => 0, 'shipping' => 0, 'total' => 7000, 'vat' => 1118]],
        [[['sku' => 'A', 'price' => 333, 'qty' => 10, 'tax' => 'std', 'promo' => ['type' => 'bundle', 'buy' => 1, 'free' => 3]]], [], ['lines' => [['sku' => 'A', 'gross' => 3330, 'promo' => 2331, 'coupon' => 0, 'net' => 999, 'vat' => 160]], 'subtotal' => 999, 'coupon' => 0, 'shipping' => 0, 'total' => 999, 'vat' => 160]],
        [[['sku' => 'A', 'price' => 333, 'qty' => 4, 'tax' => 'std', 'promo' => ['type' => 'bundle', 'buy' => 1, 'free' => 3]]], [], ['lines' => [['sku' => 'A', 'gross' => 1332, 'promo' => 999, 'coupon' => 0, 'net' => 333, 'vat' => 53]], 'subtotal' => 333, 'coupon' => 0, 'shipping' => 0, 'total' => 333, 'vat' => 53]],
        [[['sku' => 'A', 'price' => 333, 'qty' => 3, 'tax' => 'std', 'promo' => ['type' => 'bundle', 'buy' => 1, 'free' => 3]]], [], ['lines' => [['sku' => 'A', 'gross' => 999, 'promo' => 666, 'coupon' => 0, 'net' => 333, 'vat' => 53]], 'subtotal' => 333, 'coupon' => 0, 'shipping' => 0, 'total' => 333, 'vat' => 53]],
        [[['sku' => 'A', 'price' => 1000, 'qty' => 3, 'tax' => 'std', 'promo' => ['type' => 'bundle', 'buy' => 0, 'free' => 1]]], [], null],
        [[['sku' => 'A', 'price' => 1000, 'qty' => 3, 'tax' => 'std', 'promo' => ['type' => 'bundle', 'buy' => 1, 'free' => 0]]], [], null],
        [[['sku' => 'A', 'price' => 1000, 'qty' => 3, 'tax' => 'std', 'promo' => ['type' => 'bundle', 'buy' => -1, 'free' => 1]]], [], null],
        [[['sku' => 'A', 'price' => 1000, 'qty' => 3, 'tax' => 'std', 'promo' => ['type' => 'bogus']]], [], null],
        [[['sku' => 'A', 'price' => 1000, 'qty' => 3, 'tax' => 'std', 'promo' => ['type' => 'tier']]], [], ['lines' => [['sku' => 'A', 'gross' => 3000, 'promo' => 0, 'coupon' => 0, 'net' => 3000, 'vat' => 479]], 'subtotal' => 3000, 'coupon' => 0, 'shipping' => 0, 'total' => 3000, 'vat' => 479]],
        [[['sku' => 'A', 'price' => 1000, 'qty' => 3, 'tax' => 'std', 'promo' => ['type' => 'tier', 'tiers' => [[0, 10]]]]], [], null],
        [[['sku' => 'A', 'price' => 1000, 'qty' => 3, 'tax' => 'std', 'promo' => ['type' => 'tier', 'tiers' => [[1, 0]]]]], [], null],
        [[['sku' => 'A', 'price' => 1000, 'qty' => 3, 'tax' => 'std', 'promo' => ['type' => 'tier', 'tiers' => [[1, 101]]]]], [], null],
        [[['sku' => 'A', 'price' => 1000, 'qty' => 3, 'tax' => 'std', 'promo' => ['type' => 'bundle']]], [], null],
        [[['sku' => 'A', 'price' => 1000, 'qty' => 9, 'tax' => 'std', 'promo' => ['type' => 'tier', 'tiers' => [[10, 10], [50, 20]]]]], [], ['lines' => [['sku' => 'A', 'gross' => 9000, 'promo' => 0, 'coupon' => 0, 'net' => 9000, 'vat' => 1437]], 'subtotal' => 9000, 'coupon' => 0, 'shipping' => 0, 'total' => 9000, 'vat' => 1437]],
        [[['sku' => 'A', 'price' => 1000, 'qty' => 10, 'tax' => 'std', 'promo' => ['type' => 'tier', 'tiers' => [[10, 10], [50, 20]]]]], [], ['lines' => [['sku' => 'A', 'gross' => 10000, 'promo' => 1000, 'coupon' => 0, 'net' => 9000, 'vat' => 1437]], 'subtotal' => 9000, 'coupon' => 0, 'shipping' => 0, 'total' => 9000, 'vat' => 1437]],
        [[['sku' => 'A', 'price' => 1000, 'qty' => 49, 'tax' => 'std', 'promo' => ['type' => 'tier', 'tiers' => [[10, 10], [50, 20]]]]], [], ['lines' => [['sku' => 'A', 'gross' => 49000, 'promo' => 4900, 'coupon' => 0, 'net' => 44100, 'vat' => 7041]], 'subtotal' => 44100, 'coupon' => 0, 'shipping' => 0, 'total' => 44100, 'vat' => 7041]],
        [[['sku' => 'A', 'price' => 1000, 'qty' => 50, 'tax' => 'std', 'promo' => ['type' => 'tier', 'tiers' => [[10, 10], [50, 20]]]]], [], ['lines' => [['sku' => 'A', 'gross' => 50000, 'promo' => 10000, 'coupon' => 0, 'net' => 40000, 'vat' => 6387]], 'subtotal' => 40000, 'coupon' => 0, 'shipping' => 0, 'total' => 40000, 'vat' => 6387]],
        [[['sku' => 'A', 'price' => 1000, 'qty' => 100, 'tax' => 'std', 'promo' => ['type' => 'tier', 'tiers' => [[50, 20], [10, 10]]]]], [], ['lines' => [['sku' => 'A', 'gross' => 100000, 'promo' => 20000, 'coupon' => 0, 'net' => 80000, 'vat' => 12773]], 'subtotal' => 80000, 'coupon' => 0, 'shipping' => 0, 'total' => 80000, 'vat' => 12773]],
        [[['sku' => 'A', 'price' => 333, 'qty' => 10, 'tax' => 'std', 'promo' => ['type' => 'tier', 'tiers' => [[10, 15]]]]], [], ['lines' => [['sku' => 'A', 'gross' => 3330, 'promo' => 500, 'coupon' => 0, 'net' => 2830, 'vat' => 452]], 'subtotal' => 2830, 'coupon' => 0, 'shipping' => 0, 'total' => 2830, 'vat' => 452]],
        [[['sku' => 'A', 'price' => 5, 'qty' => 10, 'tax' => 'std', 'promo' => ['type' => 'tier', 'tiers' => [[1, 50]]]]], [], ['lines' => [['sku' => 'A', 'gross' => 50, 'promo' => 25, 'coupon' => 0, 'net' => 25, 'vat' => 4]], 'subtotal' => 25, 'coupon' => 0, 'shipping' => 0, 'total' => 25, 'vat' => 4]],
        [[['sku' => 'A', 'price' => 5, 'qty' => 1, 'tax' => 'std', 'promo' => ['type' => 'tier', 'tiers' => [[1, 50]]]]], [], ['lines' => [['sku' => 'A', 'gross' => 5, 'promo' => 3, 'coupon' => 0, 'net' => 2, 'vat' => 0]], 'subtotal' => 2, 'coupon' => 0, 'shipping' => 0, 'total' => 2, 'vat' => 0]],
        [[['sku' => 'A', 'price' => 1, 'qty' => 1, 'tax' => 'std', 'promo' => ['type' => 'tier', 'tiers' => [[1, 50]]]]], [], ['lines' => [['sku' => 'A', 'gross' => 1, 'promo' => 1, 'coupon' => 0, 'net' => 0, 'vat' => 0]], 'subtotal' => 0, 'coupon' => 0, 'shipping' => 0, 'total' => 0, 'vat' => 0]],
        [[['sku' => 'A', 'price' => 3, 'qty' => 1, 'tax' => 'std', 'promo' => ['type' => 'tier', 'tiers' => [[1, 50]]]]], [], ['lines' => [['sku' => 'A', 'gross' => 3, 'promo' => 2, 'coupon' => 0, 'net' => 1, 'vat' => 0]], 'subtotal' => 1, 'coupon' => 0, 'shipping' => 0, 'total' => 1, 'vat' => 0]],
        [[['sku' => 'A', 'price' => 999, 'qty' => 7, 'tax' => 'red', 'promo' => ['type' => 'tier', 'tiers' => [[5, 33], [7, 34]]]]], [], ['lines' => [['sku' => 'A', 'gross' => 6993, 'promo' => 2378, 'coupon' => 0, 'net' => 4615, 'vat' => 302]], 'subtotal' => 4615, 'coupon' => 0, 'shipping' => 0, 'total' => 4615, 'vat' => 302]],
        [[['sku' => 'A', 'price' => 100, 'qty' => 3, 'tax' => 'std', 'promo' => ['type' => 'tier', 'tiers' => [[1, 100]]]]], [], ['lines' => [['sku' => 'A', 'gross' => 300, 'promo' => 300, 'coupon' => 0, 'net' => 0, 'vat' => 0]], 'subtotal' => 0, 'coupon' => 0, 'shipping' => 0, 'total' => 0, 'vat' => 0]],
        [[['sku' => 'A', 'price' => 100, 'qty' => 3, 'tax' => 'std', 'promo' => ['type' => 'tier', 'tiers' => [[2, 10], [2, 20]]]]], [], ['lines' => [['sku' => 'A', 'gross' => 300, 'promo' => 30, 'coupon' => 0, 'net' => 270, 'vat' => 43]], 'subtotal' => 270, 'coupon' => 0, 'shipping' => 0, 'total' => 270, 'vat' => 43]],
        [[['sku' => 'A', 'price' => 1000, 'qty' => 2, 'tax' => 'std'], ['sku' => 'B', 'price' => 1000, 'qty' => 1, 'tax' => 'std']], ['coupon' => ['pct' => 10]], ['lines' => [['sku' => 'A', 'gross' => 2000, 'promo' => 0, 'coupon' => 200, 'net' => 1800, 'vat' => 287], ['sku' => 'B', 'gross' => 1000, 'promo' => 0, 'coupon' => 100, 'net' => 900, 'vat' => 144]], 'subtotal' => 3000, 'coupon' => 300, 'shipping' => 0, 'total' => 2700, 'vat' => 431]],
        [[['sku' => 'A', 'price' => 1000, 'qty' => 2, 'tax' => 'std'], ['sku' => 'B', 'price' => 1000, 'qty' => 1, 'tax' => 'std']], ['coupon' => ['pct' => 10, 'cap' => 100]], ['lines' => [['sku' => 'A', 'gross' => 2000, 'promo' => 0, 'coupon' => 67, 'net' => 1933, 'vat' => 309], ['sku' => 'B', 'gross' => 1000, 'promo' => 0, 'coupon' => 33, 'net' => 967, 'vat' => 154]], 'subtotal' => 3000, 'coupon' => 100, 'shipping' => 0, 'total' => 2900, 'vat' => 463]],
        [[['sku' => 'A', 'price' => 1000, 'qty' => 2, 'tax' => 'std'], ['sku' => 'B', 'price' => 1000, 'qty' => 1, 'tax' => 'std']], ['coupon' => ['pct' => 10, 'cap' => 300]], ['lines' => [['sku' => 'A', 'gross' => 2000, 'promo' => 0, 'coupon' => 200, 'net' => 1800, 'vat' => 287], ['sku' => 'B', 'gross' => 1000, 'promo' => 0, 'coupon' => 100, 'net' => 900, 'vat' => 144]], 'subtotal' => 3000, 'coupon' => 300, 'shipping' => 0, 'total' => 2700, 'vat' => 431]],
        [[['sku' => 'A', 'price' => 1000, 'qty' => 2, 'tax' => 'std'], ['sku' => 'B', 'price' => 1000, 'qty' => 1, 'tax' => 'std']], ['coupon' => ['pct' => 10, 'cap' => 301]], ['lines' => [['sku' => 'A', 'gross' => 2000, 'promo' => 0, 'coupon' => 200, 'net' => 1800, 'vat' => 287], ['sku' => 'B', 'gross' => 1000, 'promo' => 0, 'coupon' => 100, 'net' => 900, 'vat' => 144]], 'subtotal' => 3000, 'coupon' => 300, 'shipping' => 0, 'total' => 2700, 'vat' => 431]],
        [[['sku' => 'A', 'price' => 1000, 'qty' => 2, 'tax' => 'std'], ['sku' => 'B', 'price' => 1000, 'qty' => 1, 'tax' => 'std']], ['coupon' => ['pct' => 100]], ['lines' => [['sku' => 'A', 'gross' => 2000, 'promo' => 0, 'coupon' => 2000, 'net' => 0, 'vat' => 0], ['sku' => 'B', 'gross' => 1000, 'promo' => 0, 'coupon' => 1000, 'net' => 0, 'vat' => 0]], 'subtotal' => 3000, 'coupon' => 3000, 'shipping' => 0, 'total' => 0, 'vat' => 0]],
        [[['sku' => 'A', 'price' => 1000, 'qty' => 2, 'tax' => 'std'], ['sku' => 'B', 'price' => 1000, 'qty' => 1, 'tax' => 'std']], ['coupon' => ['pct' => 0]], ['lines' => [['sku' => 'A', 'gross' => 2000, 'promo' => 0, 'coupon' => 0, 'net' => 2000, 'vat' => 319], ['sku' => 'B', 'gross' => 1000, 'promo' => 0, 'coupon' => 0, 'net' => 1000, 'vat' => 160]], 'subtotal' => 3000, 'coupon' => 0, 'shipping' => 0, 'total' => 3000, 'vat' => 479]],
        [[['sku' => 'A', 'price' => 1000, 'qty' => 2, 'tax' => 'std'], ['sku' => 'B', 'price' => 1000, 'qty' => 1, 'tax' => 'std']], ['coupon' => ['pct' => 101]], null],
        [[['sku' => 'A', 'price' => 1000, 'qty' => 2, 'tax' => 'std'], ['sku' => 'B', 'price' => 1000, 'qty' => 1, 'tax' => 'std']], ['coupon' => ['pct' => -1]], null],
        [[['sku' => 'A', 'price' => 1000, 'qty' => 2, 'tax' => 'std']], ['coupon' => ['pct' => 10, 'cap' => -5]], null],
        [[['sku' => 'A', 'price' => 1000, 'qty' => 2, 'tax' => 'std'], ['sku' => 'B', 'price' => 1000, 'qty' => 1, 'tax' => 'std']], ['coupon' => ['fixed' => 500]], ['lines' => [['sku' => 'A', 'gross' => 2000, 'promo' => 0, 'coupon' => 333, 'net' => 1667, 'vat' => 266], ['sku' => 'B', 'gross' => 1000, 'promo' => 0, 'coupon' => 167, 'net' => 833, 'vat' => 133]], 'subtotal' => 3000, 'coupon' => 500, 'shipping' => 0, 'total' => 2500, 'vat' => 399]],
        [[['sku' => 'A', 'price' => 1000, 'qty' => 2, 'tax' => 'std'], ['sku' => 'B', 'price' => 1000, 'qty' => 1, 'tax' => 'std']], ['coupon' => ['fixed' => 3000]], ['lines' => [['sku' => 'A', 'gross' => 2000, 'promo' => 0, 'coupon' => 2000, 'net' => 0, 'vat' => 0], ['sku' => 'B', 'gross' => 1000, 'promo' => 0, 'coupon' => 1000, 'net' => 0, 'vat' => 0]], 'subtotal' => 3000, 'coupon' => 3000, 'shipping' => 0, 'total' => 0, 'vat' => 0]],
        [[['sku' => 'A', 'price' => 1000, 'qty' => 2, 'tax' => 'std'], ['sku' => 'B', 'price' => 1000, 'qty' => 1, 'tax' => 'std']], ['coupon' => ['fixed' => 3001]], ['lines' => [['sku' => 'A', 'gross' => 2000, 'promo' => 0, 'coupon' => 2000, 'net' => 0, 'vat' => 0], ['sku' => 'B', 'gross' => 1000, 'promo' => 0, 'coupon' => 1000, 'net' => 0, 'vat' => 0]], 'subtotal' => 3000, 'coupon' => 3000, 'shipping' => 0, 'total' => 0, 'vat' => 0]],
        [[['sku' => 'A', 'price' => 1000, 'qty' => 2, 'tax' => 'std'], ['sku' => 'B', 'price' => 1000, 'qty' => 1, 'tax' => 'std']], ['coupon' => ['fixed' => 0]], ['lines' => [['sku' => 'A', 'gross' => 2000, 'promo' => 0, 'coupon' => 0, 'net' => 2000, 'vat' => 319], ['sku' => 'B', 'gross' => 1000, 'promo' => 0, 'coupon' => 0, 'net' => 1000, 'vat' => 160]], 'subtotal' => 3000, 'coupon' => 0, 'shipping' => 0, 'total' => 3000, 'vat' => 479]],
        [[['sku' => 'A', 'price' => 1000, 'qty' => 2, 'tax' => 'std']], ['coupon' => ['fixed' => -1]], null],
        [[['sku' => 'A', 'price' => 1000, 'qty' => 2, 'tax' => 'std']], ['coupon' => []], null],
        [[['sku' => 'A', 'price' => 1000, 'qty' => 2, 'tax' => 'std']], ['coupon' => ['cap' => 5]], null],
        [[['sku' => 'A', 'price' => 100, 'qty' => 1, 'tax' => 'std'], ['sku' => 'B', 'price' => 100, 'qty' => 1, 'tax' => 'std'], ['sku' => 'C', 'price' => 100, 'qty' => 1, 'tax' => 'std']], ['coupon' => ['fixed' => 100]], ['lines' => [['sku' => 'A', 'gross' => 100, 'promo' => 0, 'coupon' => 34, 'net' => 66, 'vat' => 11], ['sku' => 'B', 'gross' => 100, 'promo' => 0, 'coupon' => 33, 'net' => 67, 'vat' => 11], ['sku' => 'C', 'gross' => 100, 'promo' => 0, 'coupon' => 33, 'net' => 67, 'vat' => 11]], 'subtotal' => 300, 'coupon' => 100, 'shipping' => 0, 'total' => 200, 'vat' => 33]],
        [[['sku' => 'A', 'price' => 100, 'qty' => 1, 'tax' => 'std'], ['sku' => 'B', 'price' => 100, 'qty' => 1, 'tax' => 'std'], ['sku' => 'C', 'price' => 100, 'qty' => 1, 'tax' => 'std']], ['coupon' => ['fixed' => 101]], ['lines' => [['sku' => 'A', 'gross' => 100, 'promo' => 0, 'coupon' => 34, 'net' => 66, 'vat' => 11], ['sku' => 'B', 'gross' => 100, 'promo' => 0, 'coupon' => 34, 'net' => 66, 'vat' => 11], ['sku' => 'C', 'gross' => 100, 'promo' => 0, 'coupon' => 33, 'net' => 67, 'vat' => 11]], 'subtotal' => 300, 'coupon' => 101, 'shipping' => 0, 'total' => 199, 'vat' => 33]],
        [[['sku' => 'A', 'price' => 100, 'qty' => 1, 'tax' => 'std'], ['sku' => 'B', 'price' => 100, 'qty' => 1, 'tax' => 'std'], ['sku' => 'C', 'price' => 100, 'qty' => 1, 'tax' => 'std']], ['coupon' => ['fixed' => 1]], ['lines' => [['sku' => 'A', 'gross' => 100, 'promo' => 0, 'coupon' => 1, 'net' => 99, 'vat' => 16], ['sku' => 'B', 'gross' => 100, 'promo' => 0, 'coupon' => 0, 'net' => 100, 'vat' => 16], ['sku' => 'C', 'gross' => 100, 'promo' => 0, 'coupon' => 0, 'net' => 100, 'vat' => 16]], 'subtotal' => 300, 'coupon' => 1, 'shipping' => 0, 'total' => 299, 'vat' => 48]],
        [[['sku' => 'A', 'price' => 100, 'qty' => 1, 'tax' => 'std'], ['sku' => 'B', 'price' => 300, 'qty' => 1, 'tax' => 'std']], ['coupon' => ['fixed' => 1]], ['lines' => [['sku' => 'A', 'gross' => 100, 'promo' => 0, 'coupon' => 0, 'net' => 100, 'vat' => 16], ['sku' => 'B', 'gross' => 300, 'promo' => 0, 'coupon' => 1, 'net' => 299, 'vat' => 48]], 'subtotal' => 400, 'coupon' => 1, 'shipping' => 0, 'total' => 399, 'vat' => 64]],
        [[['sku' => 'A', 'price' => 100, 'qty' => 1, 'tax' => 'std'], ['sku' => 'B', 'price' => 300, 'qty' => 1, 'tax' => 'std']], ['coupon' => ['fixed' => 2]], ['lines' => [['sku' => 'A', 'gross' => 100, 'promo' => 0, 'coupon' => 1, 'net' => 99, 'vat' => 16], ['sku' => 'B', 'gross' => 300, 'promo' => 0, 'coupon' => 1, 'net' => 299, 'vat' => 48]], 'subtotal' => 400, 'coupon' => 2, 'shipping' => 0, 'total' => 398, 'vat' => 64]],
        [[['sku' => 'A', 'price' => 100, 'qty' => 1, 'tax' => 'std'], ['sku' => 'B', 'price' => 300, 'qty' => 1, 'tax' => 'std']], ['coupon' => ['fixed' => 3]], ['lines' => [['sku' => 'A', 'gross' => 100, 'promo' => 0, 'coupon' => 1, 'net' => 99, 'vat' => 16], ['sku' => 'B', 'gross' => 300, 'promo' => 0, 'coupon' => 2, 'net' => 298, 'vat' => 48]], 'subtotal' => 400, 'coupon' => 3, 'shipping' => 0, 'total' => 397, 'vat' => 64]],
        [[['sku' => 'A', 'price' => 0, 'qty' => 5, 'tax' => 'std'], ['sku' => 'B', 'price' => 300, 'qty' => 1, 'tax' => 'std']], ['coupon' => ['fixed' => 3]], ['lines' => [['sku' => 'A', 'gross' => 0, 'promo' => 0, 'coupon' => 0, 'net' => 0, 'vat' => 0], ['sku' => 'B', 'gross' => 300, 'promo' => 0, 'coupon' => 3, 'net' => 297, 'vat' => 47]], 'subtotal' => 300, 'coupon' => 3, 'shipping' => 0, 'total' => 297, 'vat' => 47]],
        [[['sku' => 'A', 'price' => 0, 'qty' => 5, 'tax' => 'std']], ['coupon' => ['fixed' => 3]], ['lines' => [['sku' => 'A', 'gross' => 0, 'promo' => 0, 'coupon' => 0, 'net' => 0, 'vat' => 0]], 'subtotal' => 0, 'coupon' => 0, 'shipping' => 0, 'total' => 0, 'vat' => 0]],
        [[['sku' => 'A', 'price' => 500, 'qty' => 0, 'tax' => 'std'], ['sku' => 'B', 'price' => 700, 'qty' => 1, 'tax' => 'std']], ['coupon' => ['fixed' => 3]], ['lines' => [['sku' => 'A', 'gross' => 0, 'promo' => 0, 'coupon' => 0, 'net' => 0, 'vat' => 0], ['sku' => 'B', 'gross' => 700, 'promo' => 0, 'coupon' => 3, 'net' => 697, 'vat' => 111]], 'subtotal' => 700, 'coupon' => 3, 'shipping' => 0, 'total' => 697, 'vat' => 111]],
        [[['sku' => 'A', 'price' => 1000, 'qty' => 1, 'tax' => 'std']], ['shipping' => ['flat' => 499]], ['lines' => [['sku' => 'A', 'gross' => 1000, 'promo' => 0, 'coupon' => 0, 'net' => 1000, 'vat' => 160]], 'subtotal' => 1000, 'coupon' => 0, 'shipping' => 499, 'total' => 1499, 'vat' => 240]],
        [[['sku' => 'A', 'price' => 1000, 'qty' => 1, 'tax' => 'std']], ['shipping' => ['flat' => 499, 'free_over' => 1000]], ['lines' => [['sku' => 'A', 'gross' => 1000, 'promo' => 0, 'coupon' => 0, 'net' => 1000, 'vat' => 160]], 'subtotal' => 1000, 'coupon' => 0, 'shipping' => 0, 'total' => 1000, 'vat' => 160]],
        [[['sku' => 'A', 'price' => 999, 'qty' => 1, 'tax' => 'std']], ['shipping' => ['flat' => 499, 'free_over' => 1000]], ['lines' => [['sku' => 'A', 'gross' => 999, 'promo' => 0, 'coupon' => 0, 'net' => 999, 'vat' => 160]], 'subtotal' => 999, 'coupon' => 0, 'shipping' => 499, 'total' => 1498, 'vat' => 240]],
        [[['sku' => 'A', 'price' => 1001, 'qty' => 1, 'tax' => 'std']], ['shipping' => ['flat' => 499, 'free_over' => 1000]], ['lines' => [['sku' => 'A', 'gross' => 1001, 'promo' => 0, 'coupon' => 0, 'net' => 1001, 'vat' => 160]], 'subtotal' => 1001, 'coupon' => 0, 'shipping' => 0, 'total' => 1001, 'vat' => 160]],
        [[['sku' => 'A', 'price' => 1000, 'qty' => 1, 'tax' => 'std']], ['shipping' => ['flat' => 499, 'free_over' => 0]], ['lines' => [['sku' => 'A', 'gross' => 1000, 'promo' => 0, 'coupon' => 0, 'net' => 1000, 'vat' => 160]], 'subtotal' => 1000, 'coupon' => 0, 'shipping' => 0, 'total' => 1000, 'vat' => 160]],
        [[], ['shipping' => ['flat' => 499]], ['lines' => [], 'subtotal' => 0, 'coupon' => 0, 'shipping' => 0, 'total' => 0, 'vat' => 0]],
        [[], ['shipping' => ['flat' => 499, 'free_over' => 0]], ['lines' => [], 'subtotal' => 0, 'coupon' => 0, 'shipping' => 0, 'total' => 0, 'vat' => 0]],
        [[['sku' => 'A', 'price' => 1000, 'qty' => 0, 'tax' => 'std']], ['shipping' => ['flat' => 499]], ['lines' => [['sku' => 'A', 'gross' => 0, 'promo' => 0, 'coupon' => 0, 'net' => 0, 'vat' => 0]], 'subtotal' => 0, 'coupon' => 0, 'shipping' => 0, 'total' => 0, 'vat' => 0]],
        [[['sku' => 'A', 'price' => 1000, 'qty' => 1, 'tax' => 'std']], ['shipping' => ['free_over' => 5000]], ['lines' => [['sku' => 'A', 'gross' => 1000, 'promo' => 0, 'coupon' => 0, 'net' => 1000, 'vat' => 160]], 'subtotal' => 1000, 'coupon' => 0, 'shipping' => 0, 'total' => 1000, 'vat' => 160]],
        [[['sku' => 'A', 'price' => 1000, 'qty' => 1, 'tax' => 'std']], ['shipping' => []], ['lines' => [['sku' => 'A', 'gross' => 1000, 'promo' => 0, 'coupon' => 0, 'net' => 1000, 'vat' => 160]], 'subtotal' => 1000, 'coupon' => 0, 'shipping' => 0, 'total' => 1000, 'vat' => 160]],
        [[['sku' => 'A', 'price' => 0, 'qty' => 2, 'tax' => 'std']], ['shipping' => ['flat' => 250, 'free_over' => 1]], ['lines' => [['sku' => 'A', 'gross' => 0, 'promo' => 0, 'coupon' => 0, 'net' => 0, 'vat' => 0]], 'subtotal' => 0, 'coupon' => 0, 'shipping' => 250, 'total' => 250, 'vat' => 40]],
        [[['sku' => 'A', 'price' => 1000, 'qty' => 1, 'tax' => 'std']], ['shipping' => ['flat' => 499, 'free_over' => 1000], 'coupon' => ['pct' => 10]], ['lines' => [['sku' => 'A', 'gross' => 1000, 'promo' => 0, 'coupon' => 100, 'net' => 900, 'vat' => 144]], 'subtotal' => 1000, 'coupon' => 100, 'shipping' => 499, 'total' => 1399, 'vat' => 224]],
        [[['sku' => 'A', 'price' => 1000, 'qty' => 2, 'tax' => 'std']], ['shipping' => ['flat' => 499, 'free_over' => 1800], 'coupon' => ['pct' => 10]], ['lines' => [['sku' => 'A', 'gross' => 2000, 'promo' => 0, 'coupon' => 200, 'net' => 1800, 'vat' => 287]], 'subtotal' => 2000, 'coupon' => 200, 'shipping' => 0, 'total' => 1800, 'vat' => 287]],
        [[['sku' => 'A', 'price' => 1000, 'qty' => 2, 'tax' => 'std']], ['shipping' => ['flat' => 499, 'free_over' => 1801], 'coupon' => ['pct' => 10]], ['lines' => [['sku' => 'A', 'gross' => 2000, 'promo' => 0, 'coupon' => 200, 'net' => 1800, 'vat' => 287]], 'subtotal' => 2000, 'coupon' => 200, 'shipping' => 499, 'total' => 2299, 'vat' => 367]],
        [[['sku' => 'A', 'price' => 1000, 'qty' => 3, 'tax' => 'std', 'promo' => ['type' => 'bundle', 'buy' => 2, 'free' => 1]]], ['shipping' => ['flat' => 499, 'free_over' => 2000]], ['lines' => [['sku' => 'A', 'gross' => 3000, 'promo' => 1000, 'coupon' => 0, 'net' => 2000, 'vat' => 319]], 'subtotal' => 2000, 'coupon' => 0, 'shipping' => 0, 'total' => 2000, 'vat' => 319]],
        [[['sku' => 'A', 'price' => 1000, 'qty' => 3, 'tax' => 'std', 'promo' => ['type' => 'bundle', 'buy' => 2, 'free' => 1]]], ['shipping' => ['flat' => 499, 'free_over' => 2001]], ['lines' => [['sku' => 'A', 'gross' => 3000, 'promo' => 1000, 'coupon' => 0, 'net' => 2000, 'vat' => 319]], 'subtotal' => 2000, 'coupon' => 0, 'shipping' => 499, 'total' => 2499, 'vat' => 399]],
        [[['sku' => 'A', 'price' => 1, 'qty' => 1, 'tax' => 'std']], [], ['lines' => [['sku' => 'A', 'gross' => 1, 'promo' => 0, 'coupon' => 0, 'net' => 1, 'vat' => 0]], 'subtotal' => 1, 'coupon' => 0, 'shipping' => 0, 'total' => 1, 'vat' => 0]],
        [[['sku' => 'A', 'price' => 5, 'qty' => 1, 'tax' => 'std']], [], ['lines' => [['sku' => 'A', 'gross' => 5, 'promo' => 0, 'coupon' => 0, 'net' => 5, 'vat' => 1]], 'subtotal' => 5, 'coupon' => 0, 'shipping' => 0, 'total' => 5, 'vat' => 1]],
        [[['sku' => 'A', 'price' => 6, 'qty' => 1, 'tax' => 'std']], [], ['lines' => [['sku' => 'A', 'gross' => 6, 'promo' => 0, 'coupon' => 0, 'net' => 6, 'vat' => 1]], 'subtotal' => 6, 'coupon' => 0, 'shipping' => 0, 'total' => 6, 'vat' => 1]],
        [[['sku' => 'A', 'price' => 3, 'qty' => 1, 'tax' => 'red']], [], ['lines' => [['sku' => 'A', 'gross' => 3, 'promo' => 0, 'coupon' => 0, 'net' => 3, 'vat' => 0]], 'subtotal' => 3, 'coupon' => 0, 'shipping' => 0, 'total' => 3, 'vat' => 0]],
        [[['sku' => 'A', 'price' => 8, 'qty' => 1, 'tax' => 'red']], [], ['lines' => [['sku' => 'A', 'gross' => 8, 'promo' => 0, 'coupon' => 0, 'net' => 8, 'vat' => 1]], 'subtotal' => 8, 'coupon' => 0, 'shipping' => 0, 'total' => 8, 'vat' => 1]],
        [[['sku' => 'A', 'price' => 15, 'qty' => 1, 'tax' => 'red']], [], ['lines' => [['sku' => 'A', 'gross' => 15, 'promo' => 0, 'coupon' => 0, 'net' => 15, 'vat' => 1]], 'subtotal' => 15, 'coupon' => 0, 'shipping' => 0, 'total' => 15, 'vat' => 1]],
        [[['sku' => 'A', 'price' => 10, 'qty' => 1, 'tax' => 'std']], [], ['lines' => [['sku' => 'A', 'gross' => 10, 'promo' => 0, 'coupon' => 0, 'net' => 10, 'vat' => 2]], 'subtotal' => 10, 'coupon' => 0, 'shipping' => 0, 'total' => 10, 'vat' => 2]],
        [[['sku' => 'A', 'price' => 100, 'qty' => 1, 'tax' => 'std']], [], ['lines' => [['sku' => 'A', 'gross' => 100, 'promo' => 0, 'coupon' => 0, 'net' => 100, 'vat' => 16]], 'subtotal' => 100, 'coupon' => 0, 'shipping' => 0, 'total' => 100, 'vat' => 16]],
        [[['sku' => 'A', 'price' => 84, 'qty' => 1, 'tax' => 'std']], [], ['lines' => [['sku' => 'A', 'gross' => 84, 'promo' => 0, 'coupon' => 0, 'net' => 84, 'vat' => 13]], 'subtotal' => 84, 'coupon' => 0, 'shipping' => 0, 'total' => 84, 'vat' => 13]],
        [[['sku' => 'A', 'price' => 85, 'qty' => 1, 'tax' => 'std']], [], ['lines' => [['sku' => 'A', 'gross' => 85, 'promo' => 0, 'coupon' => 0, 'net' => 85, 'vat' => 14]], 'subtotal' => 85, 'coupon' => 0, 'shipping' => 0, 'total' => 85, 'vat' => 14]],
        [[['sku' => 'A', 'price' => 86, 'qty' => 1, 'tax' => 'std']], [], ['lines' => [['sku' => 'A', 'gross' => 86, 'promo' => 0, 'coupon' => 0, 'net' => 86, 'vat' => 14]], 'subtotal' => 86, 'coupon' => 0, 'shipping' => 0, 'total' => 86, 'vat' => 14]],
        [[['sku' => 'A', 'price' => 1190, 'qty' => 1, 'tax' => 'std']], [], ['lines' => [['sku' => 'A', 'gross' => 1190, 'promo' => 0, 'coupon' => 0, 'net' => 1190, 'vat' => 190]], 'subtotal' => 1190, 'coupon' => 0, 'shipping' => 0, 'total' => 1190, 'vat' => 190]],
        [[['sku' => 'A', 'price' => 595, 'qty' => 1, 'tax' => 'std']], [], ['lines' => [['sku' => 'A', 'gross' => 595, 'promo' => 0, 'coupon' => 0, 'net' => 595, 'vat' => 95]], 'subtotal' => 595, 'coupon' => 0, 'shipping' => 0, 'total' => 595, 'vat' => 95]],
        [[['sku' => 'A', 'price' => 1070, 'qty' => 1, 'tax' => 'red']], [], ['lines' => [['sku' => 'A', 'gross' => 1070, 'promo' => 0, 'coupon' => 0, 'net' => 1070, 'vat' => 70]], 'subtotal' => 1070, 'coupon' => 0, 'shipping' => 0, 'total' => 1070, 'vat' => 70]],
        [[['sku' => 'A', 'price' => 536, 'qty' => 1, 'tax' => 'red']], [], ['lines' => [['sku' => 'A', 'gross' => 536, 'promo' => 0, 'coupon' => 0, 'net' => 536, 'vat' => 35]], 'subtotal' => 536, 'coupon' => 0, 'shipping' => 0, 'total' => 536, 'vat' => 35]],
        [[['sku' => 'A', 'price' => 535, 'qty' => 1, 'tax' => 'red']], [], ['lines' => [['sku' => 'A', 'gross' => 535, 'promo' => 0, 'coupon' => 0, 'net' => 535, 'vat' => 35]], 'subtotal' => 535, 'coupon' => 0, 'shipping' => 0, 'total' => 535, 'vat' => 35]],
        [[['sku' => 'A', 'price' => 1000000000, 'qty' => 3, 'tax' => 'std']], [], ['lines' => [['sku' => 'A', 'gross' => 3000000000, 'promo' => 0, 'coupon' => 0, 'net' => 3000000000, 'vat' => 478991597]], 'subtotal' => 3000000000, 'coupon' => 0, 'shipping' => 0, 'total' => 3000000000, 'vat' => 478991597]],
        [[['sku' => 'A', 'price' => -1, 'qty' => 1, 'tax' => 'std']], [], null],
        [[['sku' => 'A', 'price' => 1, 'qty' => -1, 'tax' => 'std']], [], null],
        [[['sku' => 'A', 'price' => 1, 'qty' => 1, 'tax' => 'luxury']], [], null],
        [[['price' => 1, 'qty' => 1]], [], null],
        [[['sku' => 'A', 'qty' => 1]], [], null],
        [[['sku' => 'A', 'price' => 1]], [], null],
        [[['sku' => 'A', 'price' => 1.5, 'qty' => 1]], [], null],
        [[['sku' => 'A', 'price' => '1', 'qty' => 1]], [], null],
        [[['sku' => 'S0', 'price' => 99, 'qty' => 3, 'tax' => 'std'], ['sku' => 'S1', 'price' => 0, 'qty' => 10, 'tax' => 'std']], ['shipping' => ['flat' => 990, 'free_over' => 1]], ['lines' => [['sku' => 'S0', 'gross' => 297, 'promo' => 0, 'coupon' => 0, 'net' => 297, 'vat' => 47], ['sku' => 'S1', 'gross' => 0, 'promo' => 0, 'coupon' => 0, 'net' => 0, 'vat' => 0]], 'subtotal' => 297, 'coupon' => 0, 'shipping' => 0, 'total' => 297, 'vat' => 47]],
        [[], ['coupon' => ['pct' => 5]], ['lines' => [], 'subtotal' => 0, 'coupon' => 0, 'shipping' => 0, 'total' => 0, 'vat' => 0]],
        [[['sku' => 'S0', 'price' => 1, 'qty' => 3, 'tax' => 'red'], ['sku' => 'S1', 'price' => 1000, 'qty' => 12, 'tax' => 'std'], ['sku' => 'S2', 'price' => 2500, 'qty' => 7, 'tax' => 'std'], ['sku' => 'S3', 'price' => 999, 'qty' => 4, 'tax' => 'zero']], ['coupon' => ['pct' => 15]], ['lines' => [['sku' => 'S0', 'gross' => 3, 'promo' => 0, 'coupon' => 1, 'net' => 2, 'vat' => 0], ['sku' => 'S1', 'gross' => 12000, 'promo' => 0, 'coupon' => 1800, 'net' => 10200, 'vat' => 1629], ['sku' => 'S2', 'gross' => 17500, 'promo' => 0, 'coupon' => 2625, 'net' => 14875, 'vat' => 2375], ['sku' => 'S3', 'gross' => 3996, 'promo' => 0, 'coupon' => 599, 'net' => 3397, 'vat' => 0]], 'subtotal' => 33499, 'coupon' => 5025, 'shipping' => 0, 'total' => 28474, 'vat' => 4004]],
        [[['sku' => 'S0', 'price' => 0, 'qty' => 10, 'tax' => 'std', 'promo' => ['type' => 'tier', 'tiers' => [[2, 3], [13, 34]]]], ['sku' => 'S1', 'price' => 1, 'qty' => 2, 'tax' => 'std'], ['sku' => 'S2', 'price' => 99, 'qty' => 12, 'tax' => 'zero']], ['coupon' => ['fixed' => 100], 'shipping' => ['flat' => 499, 'free_over' => 1]], ['lines' => [['sku' => 'S0', 'gross' => 0, 'promo' => 0, 'coupon' => 0, 'net' => 0, 'vat' => 0], ['sku' => 'S1', 'gross' => 2, 'promo' => 0, 'coupon' => 0, 'net' => 2, 'vat' => 0], ['sku' => 'S2', 'gross' => 1188, 'promo' => 0, 'coupon' => 100, 'net' => 1088, 'vat' => 0]], 'subtotal' => 1190, 'coupon' => 100, 'shipping' => 0, 'total' => 1090, 'vat' => 0]],
        [[], ['shipping' => ['flat' => 0]], ['lines' => [], 'subtotal' => 0, 'coupon' => 0, 'shipping' => 0, 'total' => 0, 'vat' => 0]],
        [[], ['coupon' => ['pct' => 0]], ['lines' => [], 'subtotal' => 0, 'coupon' => 0, 'shipping' => 0, 'total' => 0, 'vat' => 0]],
        [[['sku' => 'S0', 'price' => 1, 'qty' => 7, 'tax' => 'red', 'promo' => ['type' => 'tier', 'tiers' => [[5, 23], [12, 37]]]], ['sku' => 'S1', 'price' => 100, 'qty' => 1, 'tax' => 'red', 'promo' => ['type' => 'tier', 'tiers' => [[3, 12], [13, 54]]]], ['sku' => 'S2', 'price' => 1999, 'qty' => 4, 'tax' => 'zero']], ['coupon' => ['fixed' => 5000], 'shipping' => ['flat' => 0, 'free_over' => 9999]], ['lines' => [['sku' => 'S0', 'gross' => 7, 'promo' => 2, 'coupon' => 3, 'net' => 2, 'vat' => 0], ['sku' => 'S1', 'gross' => 100, 'promo' => 0, 'coupon' => 62, 'net' => 38, 'vat' => 2], ['sku' => 'S2', 'gross' => 7996, 'promo' => 0, 'coupon' => 4935, 'net' => 3061, 'vat' => 0]], 'subtotal' => 8101, 'coupon' => 5000, 'shipping' => 0, 'total' => 3101, 'vat' => 2]],
        [[], [], ['lines' => [], 'subtotal' => 0, 'coupon' => 0, 'shipping' => 0, 'total' => 0, 'vat' => 0]],
        [[['sku' => 'S0', 'price' => 1319, 'qty' => 0, 'tax' => 'zero'], ['sku' => 'S1', 'price' => 1000, 'qty' => 2, 'tax' => 'zero', 'promo' => ['type' => 'tier', 'tiers' => [[4, 1], [7, 32]]]]], ['shipping' => ['flat' => 499]], ['lines' => [['sku' => 'S0', 'gross' => 0, 'promo' => 0, 'coupon' => 0, 'net' => 0, 'vat' => 0], ['sku' => 'S1', 'gross' => 2000, 'promo' => 0, 'coupon' => 0, 'net' => 2000, 'vat' => 0]], 'subtotal' => 2000, 'coupon' => 0, 'shipping' => 499, 'total' => 2499, 'vat' => 80]],
        [[['sku' => 'S0', 'price' => 1999, 'qty' => 29, 'tax' => 'std'], ['sku' => 'S1', 'price' => 1000, 'qty' => 12, 'tax' => 'red', 'promo' => ['type' => 'tier', 'tiers' => [[2, 7], [13, 49]]]]], ['shipping' => ['flat' => 199, 'free_over' => 0]], ['lines' => [['sku' => 'S0', 'gross' => 57971, 'promo' => 0, 'coupon' => 0, 'net' => 57971, 'vat' => 9256], ['sku' => 'S1', 'gross' => 12000, 'promo' => 840, 'coupon' => 0, 'net' => 11160, 'vat' => 730]], 'subtotal' => 69131, 'coupon' => 0, 'shipping' => 0, 'total' => 69131, 'vat' => 9986]],
        [[['sku' => 'S0', 'price' => 2513, 'qty' => 5, 'tax' => 'red']], ['coupon' => ['pct' => 100, 'cap' => 50], 'shipping' => ['flat' => 199]], ['lines' => [['sku' => 'S0', 'gross' => 12565, 'promo' => 0, 'coupon' => 50, 'net' => 12515, 'vat' => 819]], 'subtotal' => 12565, 'coupon' => 50, 'shipping' => 199, 'total' => 12714, 'vat' => 851]],
        [[['sku' => 'S0', 'price' => 100, 'qty' => 10, 'tax' => 'std', 'promo' => ['type' => 'bundle', 'buy' => 3, 'free' => 1]], ['sku' => 'S1', 'price' => 0, 'qty' => 4, 'tax' => 'zero', 'promo' => ['type' => 'tier', 'tiers' => [[4, 29], [7, 52]]]], ['sku' => 'S2', 'price' => 333, 'qty' => 10, 'tax' => 'zero', 'promo' => ['type' => 'bundle', 'buy' => 1, 'free' => 2]], ['sku' => 'S3', 'price' => 2500, 'qty' => 4, 'tax' => 'zero', 'promo' => ['type' => 'tier', 'tiers' => [[5, 1], [15, 33]]]]], ['coupon' => ['fixed' => 7]], ['lines' => [['sku' => 'S0', 'gross' => 1000, 'promo' => 200, 'coupon' => 0, 'net' => 800, 'vat' => 128], ['sku' => 'S1', 'gross' => 0, 'promo' => 0, 'coupon' => 0, 'net' => 0, 'vat' => 0], ['sku' => 'S2', 'gross' => 3330, 'promo' => 1998, 'coupon' => 1, 'net' => 1331, 'vat' => 0], ['sku' => 'S3', 'gross' => 10000, 'promo' => 0, 'coupon' => 6, 'net' => 9994, 'vat' => 0]], 'subtotal' => 12132, 'coupon' => 7, 'shipping' => 0, 'total' => 12125, 'vat' => 128]],
        [[['sku' => 'S0', 'price' => 333, 'qty' => 2, 'tax' => 'std', 'promo' => ['type' => 'bundle', 'buy' => 2, 'free' => 1]], ['sku' => 'S1', 'price' => 333, 'qty' => 3, 'tax' => 'red'], ['sku' => 'S2', 'price' => 4176, 'qty' => 3, 'tax' => 'std'], ['sku' => 'S3', 'price' => 0, 'qty' => 5, 'tax' => 'zero']], [], ['lines' => [['sku' => 'S0', 'gross' => 666, 'promo' => 0, 'coupon' => 0, 'net' => 666, 'vat' => 106], ['sku' => 'S1', 'gross' => 999, 'promo' => 0, 'coupon' => 0, 'net' => 999, 'vat' => 65], ['sku' => 'S2', 'gross' => 12528, 'promo' => 0, 'coupon' => 0, 'net' => 12528, 'vat' => 2000], ['sku' => 'S3', 'gross' => 0, 'promo' => 0, 'coupon' => 0, 'net' => 0, 'vat' => 0]], 'subtotal' => 14193, 'coupon' => 0, 'shipping' => 0, 'total' => 14193, 'vat' => 2171]],
        [[['sku' => 'S0', 'price' => 259, 'qty' => 50, 'tax' => 'std'], ['sku' => 'S1', 'price' => 99, 'qty' => 12, 'tax' => 'zero', 'promo' => ['type' => 'tier', 'tiers' => [[2, 4], [14, 46]]]], ['sku' => 'S2', 'price' => 999, 'qty' => 10, 'tax' => 'std', 'promo' => ['type' => 'bundle', 'buy' => 2, 'free' => 1]], ['sku' => 'S3', 'price' => 333, 'qty' => 4, 'tax' => 'red']], [], ['lines' => [['sku' => 'S0', 'gross' => 12950, 'promo' => 0, 'coupon' => 0, 'net' => 12950, 'vat' => 2068], ['sku' => 'S1', 'gross' => 1188, 'promo' => 48, 'coupon' => 0, 'net' => 1140, 'vat' => 0], ['sku' => 'S2', 'gross' => 9990, 'promo' => 2997, 'coupon' => 0, 'net' => 6993, 'vat' => 1117], ['sku' => 'S3', 'gross' => 1332, 'promo' => 0, 'coupon' => 0, 'net' => 1332, 'vat' => 87]], 'subtotal' => 22415, 'coupon' => 0, 'shipping' => 0, 'total' => 22415, 'vat' => 3272]],
        [[['sku' => 'S0', 'price' => 999, 'qty' => 1, 'tax' => 'std'], ['sku' => 'S1', 'price' => 333, 'qty' => 1, 'tax' => 'red'], ['sku' => 'S2', 'price' => 0, 'qty' => 0, 'tax' => 'std', 'promo' => ['type' => 'tier', 'tiers' => [[3, 26], [13, 39]]]], ['sku' => 'S3', 'price' => 1, 'qty' => 4, 'tax' => 'zero']], ['shipping' => ['flat' => 199, 'free_over' => 1]], ['lines' => [['sku' => 'S0', 'gross' => 999, 'promo' => 0, 'coupon' => 0, 'net' => 999, 'vat' => 160], ['sku' => 'S1', 'gross' => 333, 'promo' => 0, 'coupon' => 0, 'net' => 333, 'vat' => 22], ['sku' => 'S2', 'gross' => 0, 'promo' => 0, 'coupon' => 0, 'net' => 0, 'vat' => 0], ['sku' => 'S3', 'gross' => 4, 'promo' => 0, 'coupon' => 0, 'net' => 4, 'vat' => 0]], 'subtotal' => 1336, 'coupon' => 0, 'shipping' => 0, 'total' => 1336, 'vat' => 182]],
        [[['sku' => 'S0', 'price' => 100, 'qty' => 1, 'tax' => 'red', 'promo' => ['type' => 'tier', 'tiers' => [[1, 6], [10, 39]]]], ['sku' => 'S1', 'price' => 999, 'qty' => 5, 'tax' => 'std'], ['sku' => 'S2', 'price' => 0, 'qty' => 7, 'tax' => 'zero'], ['sku' => 'S3', 'price' => 100, 'qty' => 7, 'tax' => 'zero']], ['coupon' => ['pct' => 25, 'cap' => 300], 'shipping' => ['flat' => 990, 'free_over' => 1]], ['lines' => [['sku' => 'S0', 'gross' => 100, 'promo' => 6, 'coupon' => 5, 'net' => 89, 'vat' => 6], ['sku' => 'S1', 'gross' => 4995, 'promo' => 0, 'coupon' => 259, 'net' => 4736, 'vat' => 756], ['sku' => 'S2', 'gross' => 0, 'promo' => 0, 'coupon' => 0, 'net' => 0, 'vat' => 0], ['sku' => 'S3', 'gross' => 700, 'promo' => 0, 'coupon' => 36, 'net' => 664, 'vat' => 0]], 'subtotal' => 5789, 'coupon' => 300, 'shipping' => 0, 'total' => 5489, 'vat' => 762]],
        [[['sku' => 'S0', 'price' => 5, 'qty' => 10, 'tax' => 'std', 'promo' => ['type' => 'tier', 'tiers' => [[5, 24], [14, 38]]]]], ['coupon' => ['fixed' => 5000], 'shipping' => ['flat' => 0, 'free_over' => 0]], ['lines' => [['sku' => 'S0', 'gross' => 50, 'promo' => 12, 'coupon' => 38, 'net' => 0, 'vat' => 0]], 'subtotal' => 38, 'coupon' => 38, 'shipping' => 0, 'total' => 0, 'vat' => 0]],
        [[['sku' => 'S0', 'price' => 999, 'qty' => 7, 'tax' => 'std', 'promo' => ['type' => 'bundle', 'buy' => 1, 'free' => 1]], ['sku' => 'S1', 'price' => 1999, 'qty' => 12, 'tax' => 'std'], ['sku' => 'S2', 'price' => 1, 'qty' => 0, 'tax' => 'zero', 'promo' => ['type' => 'tier', 'tiers' => [[3, 5], [14, 38]]]], ['sku' => 'S3', 'price' => 999, 'qty' => 10, 'tax' => 'zero']], ['coupon' => ['pct' => 0]], ['lines' => [['sku' => 'S0', 'gross' => 6993, 'promo' => 2997, 'coupon' => 0, 'net' => 3996, 'vat' => 638], ['sku' => 'S1', 'gross' => 23988, 'promo' => 0, 'coupon' => 0, 'net' => 23988, 'vat' => 3830], ['sku' => 'S2', 'gross' => 0, 'promo' => 0, 'coupon' => 0, 'net' => 0, 'vat' => 0], ['sku' => 'S3', 'gross' => 9990, 'promo' => 0, 'coupon' => 0, 'net' => 9990, 'vat' => 0]], 'subtotal' => 37974, 'coupon' => 0, 'shipping' => 0, 'total' => 37974, 'vat' => 4468]],
        [[['sku' => 'S0', 'price' => 1, 'qty' => 7, 'tax' => 'std', 'promo' => ['type' => 'tier', 'tiers' => [[1, 30], [6, 40]]]], ['sku' => 'S1', 'price' => 2596, 'qty' => 4, 'tax' => 'std']], ['coupon' => ['fixed' => 100], 'shipping' => ['flat' => 499]], ['lines' => [['sku' => 'S0', 'gross' => 7, 'promo' => 3, 'coupon' => 0, 'net' => 4, 'vat' => 1], ['sku' => 'S1', 'gross' => 10384, 'promo' => 0, 'coupon' => 100, 'net' => 10284, 'vat' => 1642]], 'subtotal' => 10388, 'coupon' => 100, 'shipping' => 499, 'total' => 10787, 'vat' => 1723]],
        [[], [], ['lines' => [], 'subtotal' => 0, 'coupon' => 0, 'shipping' => 0, 'total' => 0, 'vat' => 0]],
        [[['sku' => 'S0', 'price' => 99, 'qty' => 22, 'tax' => 'std', 'promo' => ['type' => 'tier', 'tiers' => [[1, 13], [13, 32]]]], ['sku' => 'S1', 'price' => 333, 'qty' => 4, 'tax' => 'std', 'promo' => ['type' => 'bundle', 'buy' => 1, 'free' => 1]], ['sku' => 'S2', 'price' => 99, 'qty' => 5, 'tax' => 'zero']], ['coupon' => ['fixed' => 5000]], ['lines' => [['sku' => 'S0', 'gross' => 2178, 'promo' => 697, 'coupon' => 1481, 'net' => 0, 'vat' => 0], ['sku' => 'S1', 'gross' => 1332, 'promo' => 666, 'coupon' => 666, 'net' => 0, 'vat' => 0], ['sku' => 'S2', 'gross' => 495, 'promo' => 0, 'coupon' => 495, 'net' => 0, 'vat' => 0]], 'subtotal' => 2642, 'coupon' => 2642, 'shipping' => 0, 'total' => 0, 'vat' => 0]],
        [[['sku' => 'S0', 'price' => 999, 'qty' => 0, 'tax' => 'std', 'promo' => ['type' => 'bundle', 'buy' => 1, 'free' => 1]], ['sku' => 'S1', 'price' => 99, 'qty' => 12, 'tax' => 'std'], ['sku' => 'S2', 'price' => 999, 'qty' => 7, 'tax' => 'zero'], ['sku' => 'S3', 'price' => 2500, 'qty' => 7, 'tax' => 'std', 'promo' => ['type' => 'tier', 'tiers' => [[5, 18], [8, 35]]]]], ['coupon' => ['pct' => 5]], ['lines' => [['sku' => 'S0', 'gross' => 0, 'promo' => 0, 'coupon' => 0, 'net' => 0, 'vat' => 0], ['sku' => 'S1', 'gross' => 1188, 'promo' => 0, 'coupon' => 59, 'net' => 1129, 'vat' => 180], ['sku' => 'S2', 'gross' => 6993, 'promo' => 0, 'coupon' => 350, 'net' => 6643, 'vat' => 0], ['sku' => 'S3', 'gross' => 17500, 'promo' => 3150, 'coupon' => 718, 'net' => 13632, 'vat' => 2177]], 'subtotal' => 22531, 'coupon' => 1127, 'shipping' => 0, 'total' => 21404, 'vat' => 2357]],
        [[['sku' => 'S0', 'price' => 999, 'qty' => 1, 'tax' => 'std']], ['coupon' => ['pct' => 10, 'cap' => 300], 'shipping' => ['flat' => 0]], ['lines' => [['sku' => 'S0', 'gross' => 999, 'promo' => 0, 'coupon' => 100, 'net' => 899, 'vat' => 144]], 'subtotal' => 999, 'coupon' => 100, 'shipping' => 0, 'total' => 899, 'vat' => 144]],
        [[['sku' => 'S0', 'price' => 1, 'qty' => 4, 'tax' => 'std']], ['coupon' => ['pct' => 15, 'cap' => 0], 'shipping' => ['flat' => 990]], ['lines' => [['sku' => 'S0', 'gross' => 4, 'promo' => 0, 'coupon' => 0, 'net' => 4, 'vat' => 1]], 'subtotal' => 4, 'coupon' => 0, 'shipping' => 990, 'total' => 994, 'vat' => 159]],
        [[['sku' => 'S0', 'price' => 1, 'qty' => 22, 'tax' => 'zero'], ['sku' => 'S1', 'price' => 0, 'qty' => 10, 'tax' => 'zero', 'promo' => ['type' => 'tier', 'tiers' => [[2, 19], [9, 40]]]]], ['shipping' => ['flat' => 0]], ['lines' => [['sku' => 'S0', 'gross' => 22, 'promo' => 0, 'coupon' => 0, 'net' => 22, 'vat' => 0], ['sku' => 'S1', 'gross' => 0, 'promo' => 0, 'coupon' => 0, 'net' => 0, 'vat' => 0]], 'subtotal' => 22, 'coupon' => 0, 'shipping' => 0, 'total' => 22, 'vat' => 0]],
        [[['sku' => 'S0', 'price' => 5, 'qty' => 12, 'tax' => 'zero', 'promo' => ['type' => 'bundle', 'buy' => 3, 'free' => 1]]], ['coupon' => ['pct' => 10], 'shipping' => ['flat' => 990, 'free_over' => 2000]], ['lines' => [['sku' => 'S0', 'gross' => 60, 'promo' => 15, 'coupon' => 5, 'net' => 40, 'vat' => 0]], 'subtotal' => 45, 'coupon' => 5, 'shipping' => 990, 'total' => 1030, 'vat' => 158]],
        [[['sku' => 'S0', 'price' => 1, 'qty' => 50, 'tax' => 'std', 'promo' => ['type' => 'bundle', 'buy' => 3, 'free' => 1]], ['sku' => 'S1', 'price' => 333, 'qty' => 11, 'tax' => 'std', 'promo' => ['type' => 'bundle', 'buy' => 1, 'free' => 1]]], ['coupon' => ['pct' => 100]], ['lines' => [['sku' => 'S0', 'gross' => 50, 'promo' => 12, 'coupon' => 38, 'net' => 0, 'vat' => 0], ['sku' => 'S1', 'gross' => 3663, 'promo' => 1665, 'coupon' => 1998, 'net' => 0, 'vat' => 0]], 'subtotal' => 2036, 'coupon' => 2036, 'shipping' => 0, 'total' => 0, 'vat' => 0]],
        [[['sku' => 'S0', 'price' => 1, 'qty' => 10, 'tax' => 'std'], ['sku' => 'S1', 'price' => 999, 'qty' => 17, 'tax' => 'std', 'promo' => ['type' => 'tier', 'tiers' => [[1, 30], [13, 36]]]]], [], ['lines' => [['sku' => 'S0', 'gross' => 10, 'promo' => 0, 'coupon' => 0, 'net' => 10, 'vat' => 2], ['sku' => 'S1', 'gross' => 16983, 'promo' => 6114, 'coupon' => 0, 'net' => 10869, 'vat' => 1735]], 'subtotal' => 10879, 'coupon' => 0, 'shipping' => 0, 'total' => 10879, 'vat' => 1737]],
        [[['sku' => 'S0', 'price' => 2500, 'qty' => 7, 'tax' => 'zero'], ['sku' => 'S1', 'price' => 999, 'qty' => 4, 'tax' => 'std', 'promo' => ['type' => 'tier', 'tiers' => [[3, 8], [10, 59]]]]], ['coupon' => ['pct' => 25]], ['lines' => [['sku' => 'S0', 'gross' => 17500, 'promo' => 0, 'coupon' => 4375, 'net' => 13125, 'vat' => 0], ['sku' => 'S1', 'gross' => 3996, 'promo' => 320, 'coupon' => 919, 'net' => 2757, 'vat' => 440]], 'subtotal' => 21176, 'coupon' => 5294, 'shipping' => 0, 'total' => 15882, 'vat' => 440]],
        [[], ['coupon' => ['pct' => 50, 'cap' => 1000], 'shipping' => ['flat' => 199]], ['lines' => [], 'subtotal' => 0, 'coupon' => 0, 'shipping' => 0, 'total' => 0, 'vat' => 0]],
        [[['sku' => 'S0', 'price' => 2500, 'qty' => 10, 'tax' => 'std', 'promo' => ['type' => 'tier', 'tiers' => [[2, 1], [11, 38]]]], ['sku' => 'S1', 'price' => 999, 'qty' => 2, 'tax' => 'red', 'promo' => ['type' => 'tier', 'tiers' => [[4, 21], [13, 57]]]], ['sku' => 'S2', 'price' => 45, 'qty' => 5, 'tax' => 'std', 'promo' => ['type' => 'bundle', 'buy' => 3, 'free' => 2]], ['sku' => 'S3', 'price' => 333, 'qty' => 10, 'tax' => 'zero']], [], ['lines' => [['sku' => 'S0', 'gross' => 25000, 'promo' => 250, 'coupon' => 0, 'net' => 24750, 'vat' => 3952], ['sku' => 'S1', 'gross' => 1998, 'promo' => 0, 'coupon' => 0, 'net' => 1998, 'vat' => 131], ['sku' => 'S2', 'gross' => 225, 'promo' => 90, 'coupon' => 0, 'net' => 135, 'vat' => 22], ['sku' => 'S3', 'gross' => 3330, 'promo' => 0, 'coupon' => 0, 'net' => 3330, 'vat' => 0]], 'subtotal' => 30213, 'coupon' => 0, 'shipping' => 0, 'total' => 30213, 'vat' => 4105]],
        [[['sku' => 'S0', 'price' => 0, 'qty' => 3, 'tax' => 'std'], ['sku' => 'S1', 'price' => 0, 'qty' => 6, 'tax' => 'red', 'promo' => ['type' => 'tier', 'tiers' => [[1, 11], [11, 57]]]], ['sku' => 'S2', 'price' => 5, 'qty' => 5, 'tax' => 'red', 'promo' => ['type' => 'bundle', 'buy' => 1, 'free' => 2]], ['sku' => 'S3', 'price' => 1, 'qty' => 4, 'tax' => 'red']], ['coupon' => ['pct' => 0]], ['lines' => [['sku' => 'S0', 'gross' => 0, 'promo' => 0, 'coupon' => 0, 'net' => 0, 'vat' => 0], ['sku' => 'S1', 'gross' => 0, 'promo' => 0, 'coupon' => 0, 'net' => 0, 'vat' => 0], ['sku' => 'S2', 'gross' => 25, 'promo' => 15, 'coupon' => 0, 'net' => 10, 'vat' => 1], ['sku' => 'S3', 'gross' => 4, 'promo' => 0, 'coupon' => 0, 'net' => 4, 'vat' => 0]], 'subtotal' => 14, 'coupon' => 0, 'shipping' => 0, 'total' => 14, 'vat' => 1]],
        [[['sku' => 'S0', 'price' => 1999, 'qty' => 12, 'tax' => 'red', 'promo' => ['type' => 'tier', 'tiers' => [[4, 4], [10, 59]]]], ['sku' => 'S1', 'price' => 2500, 'qty' => 3, 'tax' => 'red'], ['sku' => 'S2', 'price' => 1, 'qty' => 5, 'tax' => 'zero']], [], ['lines' => [['sku' => 'S0', 'gross' => 23988, 'promo' => 14153, 'coupon' => 0, 'net' => 9835, 'vat' => 643], ['sku' => 'S1', 'gross' => 7500, 'promo' => 0, 'coupon' => 0, 'net' => 7500, 'vat' => 491], ['sku' => 'S2', 'gross' => 5, 'promo' => 0, 'coupon' => 0, 'net' => 5, 'vat' => 0]], 'subtotal' => 17340, 'coupon' => 0, 'shipping' => 0, 'total' => 17340, 'vat' => 1134]],
        [[['sku' => 'S0', 'price' => 1, 'qty' => 5, 'tax' => 'std', 'promo' => ['type' => 'tier', 'tiers' => [[1, 30], [6, 36]]]], ['sku' => 'S1', 'price' => 99, 'qty' => 2, 'tax' => 'std', 'promo' => ['type' => 'bundle', 'buy' => 3, 'free' => 1]], ['sku' => 'S2', 'price' => 999, 'qty' => 4, 'tax' => 'std', 'promo' => ['type' => 'bundle', 'buy' => 3, 'free' => 1]], ['sku' => 'S3', 'price' => 1839, 'qty' => 17, 'tax' => 'std']], ['shipping' => ['flat' => 990]], ['lines' => [['sku' => 'S0', 'gross' => 5, 'promo' => 2, 'coupon' => 0, 'net' => 3, 'vat' => 0], ['sku' => 'S1', 'gross' => 198, 'promo' => 0, 'coupon' => 0, 'net' => 198, 'vat' => 32], ['sku' => 'S2', 'gross' => 3996, 'promo' => 999, 'coupon' => 0, 'net' => 2997, 'vat' => 479], ['sku' => 'S3', 'gross' => 31263, 'promo' => 0, 'coupon' => 0, 'net' => 31263, 'vat' => 4992]], 'subtotal' => 34461, 'coupon' => 0, 'shipping' => 990, 'total' => 35451, 'vat' => 5661]],
        [[['sku' => 'S0', 'price' => 100, 'qty' => 5, 'tax' => 'std']], ['coupon' => ['pct' => 0, 'cap' => 300], 'shipping' => ['flat' => 499, 'free_over' => 5000]], ['lines' => [['sku' => 'S0', 'gross' => 500, 'promo' => 0, 'coupon' => 0, 'net' => 500, 'vat' => 80]], 'subtotal' => 500, 'coupon' => 0, 'shipping' => 499, 'total' => 999, 'vat' => 160]],
        [[], ['shipping' => ['flat' => 0]], ['lines' => [], 'subtotal' => 0, 'coupon' => 0, 'shipping' => 0, 'total' => 0, 'vat' => 0]],
        [[], ['coupon' => ['fixed' => 0], 'shipping' => ['flat' => 0]], ['lines' => [], 'subtotal' => 0, 'coupon' => 0, 'shipping' => 0, 'total' => 0, 'vat' => 0]],
        [[['sku' => 'S0', 'price' => 4276, 'qty' => 0, 'tax' => 'std'], ['sku' => 'S1', 'price' => 999, 'qty' => 10, 'tax' => 'std', 'promo' => ['type' => 'bundle', 'buy' => 1, 'free' => 1]], ['sku' => 'S2', 'price' => 1999, 'qty' => 2, 'tax' => 'std', 'promo' => ['type' => 'bundle', 'buy' => 1, 'free' => 1]]], ['coupon' => ['pct' => 10]], ['lines' => [['sku' => 'S0', 'gross' => 0, 'promo' => 0, 'coupon' => 0, 'net' => 0, 'vat' => 0], ['sku' => 'S1', 'gross' => 9990, 'promo' => 4995, 'coupon' => 499, 'net' => 4496, 'vat' => 718], ['sku' => 'S2', 'gross' => 3998, 'promo' => 1999, 'coupon' => 200, 'net' => 1799, 'vat' => 287]], 'subtotal' => 6994, 'coupon' => 699, 'shipping' => 0, 'total' => 6295, 'vat' => 1005]],
        [[['sku' => 'S0', 'price' => 1, 'qty' => 1, 'tax' => 'std', 'promo' => ['type' => 'bundle', 'buy' => 1, 'free' => 1]], ['sku' => 'S1', 'price' => 1999, 'qty' => 7, 'tax' => 'zero'], ['sku' => 'S2', 'price' => 2500, 'qty' => 7, 'tax' => 'red', 'promo' => ['type' => 'bundle', 'buy' => 2, 'free' => 1]], ['sku' => 'S3', 'price' => 999, 'qty' => 10, 'tax' => 'std', 'promo' => ['type' => 'bundle', 'buy' => 2, 'free' => 1]]], ['shipping' => ['flat' => 499, 'free_over' => 9999]], ['lines' => [['sku' => 'S0', 'gross' => 1, 'promo' => 0, 'coupon' => 0, 'net' => 1, 'vat' => 0], ['sku' => 'S1', 'gross' => 13993, 'promo' => 0, 'coupon' => 0, 'net' => 13993, 'vat' => 0], ['sku' => 'S2', 'gross' => 17500, 'promo' => 5000, 'coupon' => 0, 'net' => 12500, 'vat' => 818], ['sku' => 'S3', 'gross' => 9990, 'promo' => 2997, 'coupon' => 0, 'net' => 6993, 'vat' => 1117]], 'subtotal' => 33487, 'coupon' => 0, 'shipping' => 0, 'total' => 33487, 'vat' => 1935]],
        [[['sku' => 'S0', 'price' => 999, 'qty' => 0, 'tax' => 'std', 'promo' => ['type' => 'bundle', 'buy' => 2, 'free' => 1]], ['sku' => 'S1', 'price' => 333, 'qty' => 0, 'tax' => 'std'], ['sku' => 'S2', 'price' => 333, 'qty' => 2, 'tax' => 'zero', 'promo' => ['type' => 'bundle', 'buy' => 3, 'free' => 1]], ['sku' => 'S3', 'price' => 3146, 'qty' => 50, 'tax' => 'red']], ['shipping' => ['flat' => 499, 'free_over' => 2000]], ['lines' => [['sku' => 'S0', 'gross' => 0, 'promo' => 0, 'coupon' => 0, 'net' => 0, 'vat' => 0], ['sku' => 'S1', 'gross' => 0, 'promo' => 0, 'coupon' => 0, 'net' => 0, 'vat' => 0], ['sku' => 'S2', 'gross' => 666, 'promo' => 0, 'coupon' => 0, 'net' => 666, 'vat' => 0], ['sku' => 'S3', 'gross' => 157300, 'promo' => 0, 'coupon' => 0, 'net' => 157300, 'vat' => 10291]], 'subtotal' => 157966, 'coupon' => 0, 'shipping' => 0, 'total' => 157966, 'vat' => 10291]],
        [[['sku' => 'S0', 'price' => 1000, 'qty' => 3, 'tax' => 'std', 'promo' => ['type' => 'tier', 'tiers' => [[2, 30], [13, 53]]]], ['sku' => 'S1', 'price' => 1999, 'qty' => 5, 'tax' => 'std']], [], ['lines' => [['sku' => 'S0', 'gross' => 3000, 'promo' => 900, 'coupon' => 0, 'net' => 2100, 'vat' => 335], ['sku' => 'S1', 'gross' => 9995, 'promo' => 0, 'coupon' => 0, 'net' => 9995, 'vat' => 1596]], 'subtotal' => 12095, 'coupon' => 0, 'shipping' => 0, 'total' => 12095, 'vat' => 1931]],
        [[['sku' => 'S0', 'price' => 999, 'qty' => 2, 'tax' => 'red'], ['sku' => 'S1', 'price' => 99, 'qty' => 3, 'tax' => 'std', 'promo' => ['type' => 'bundle', 'buy' => 1, 'free' => 1]]], ['shipping' => ['flat' => 499, 'free_over' => 2000]], ['lines' => [['sku' => 'S0', 'gross' => 1998, 'promo' => 0, 'coupon' => 0, 'net' => 1998, 'vat' => 131], ['sku' => 'S1', 'gross' => 297, 'promo' => 99, 'coupon' => 0, 'net' => 198, 'vat' => 32]], 'subtotal' => 2196, 'coupon' => 0, 'shipping' => 0, 'total' => 2196, 'vat' => 163]],
        [[['sku' => 'S0', 'price' => 2500, 'qty' => 3, 'tax' => 'std', 'promo' => ['type' => 'tier', 'tiers' => [[3, 10], [10, 60]]]], ['sku' => 'S1', 'price' => 0, 'qty' => 2, 'tax' => 'std', 'promo' => ['type' => 'tier', 'tiers' => [[3, 7], [6, 34]]]]], ['coupon' => ['pct' => 0], 'shipping' => ['flat' => 199]], ['lines' => [['sku' => 'S0', 'gross' => 7500, 'promo' => 750, 'coupon' => 0, 'net' => 6750, 'vat' => 1078], ['sku' => 'S1', 'gross' => 0, 'promo' => 0, 'coupon' => 0, 'net' => 0, 'vat' => 0]], 'subtotal' => 6750, 'coupon' => 0, 'shipping' => 199, 'total' => 6949, 'vat' => 1110]],
        [[], ['shipping' => ['flat' => 199, 'free_over' => 1]], ['lines' => [], 'subtotal' => 0, 'coupon' => 0, 'shipping' => 0, 'total' => 0, 'vat' => 0]],
        [[['sku' => 'S0', 'price' => 1, 'qty' => 4, 'tax' => 'std'], ['sku' => 'S1', 'price' => 5, 'qty' => 12, 'tax' => 'std', 'promo' => ['type' => 'tier', 'tiers' => [[3, 21], [7, 39]]]], ['sku' => 'S2', 'price' => 614, 'qty' => 1, 'tax' => 'red', 'promo' => ['type' => 'tier', 'tiers' => [[1, 6], [9, 45]]]]], ['coupon' => ['fixed' => 499]], ['lines' => [['sku' => 'S0', 'gross' => 4, 'promo' => 0, 'coupon' => 3, 'net' => 1, 'vat' => 0], ['sku' => 'S1', 'gross' => 60, 'promo' => 23, 'coupon' => 30, 'net' => 7, 'vat' => 1], ['sku' => 'S2', 'gross' => 614, 'promo' => 37, 'coupon' => 466, 'net' => 111, 'vat' => 7]], 'subtotal' => 618, 'coupon' => 499, 'shipping' => 0, 'total' => 119, 'vat' => 8]],
        [[], ['coupon' => ['pct' => 0, 'cap' => 1000], 'shipping' => ['flat' => 990, 'free_over' => 1]], ['lines' => [], 'subtotal' => 0, 'coupon' => 0, 'shipping' => 0, 'total' => 0, 'vat' => 0]],
        [[['sku' => 'S0', 'price' => 5, 'qty' => 2, 'tax' => 'red', 'promo' => ['type' => 'bundle', 'buy' => 2, 'free' => 2]], ['sku' => 'S1', 'price' => 594, 'qty' => 0, 'tax' => 'std', 'promo' => ['type' => 'tier', 'tiers' => [[2, 2], [15, 35]]]], ['sku' => 'S2', 'price' => 333, 'qty' => 50, 'tax' => 'std'], ['sku' => 'S3', 'price' => 999, 'qty' => 4, 'tax' => 'std', 'promo' => ['type' => 'bundle', 'buy' => 3, 'free' => 1]]], [], ['lines' => [['sku' => 'S0', 'gross' => 10, 'promo' => 0, 'coupon' => 0, 'net' => 10, 'vat' => 1], ['sku' => 'S1', 'gross' => 0, 'promo' => 0, 'coupon' => 0, 'net' => 0, 'vat' => 0], ['sku' => 'S2', 'gross' => 16650, 'promo' => 0, 'coupon' => 0, 'net' => 16650, 'vat' => 2658], ['sku' => 'S3', 'gross' => 3996, 'promo' => 999, 'coupon' => 0, 'net' => 2997, 'vat' => 479]], 'subtotal' => 19657, 'coupon' => 0, 'shipping' => 0, 'total' => 19657, 'vat' => 3138]],
        [[['sku' => 'S0', 'price' => 100, 'qty' => 5, 'tax' => 'std', 'promo' => ['type' => 'tier', 'tiers' => [[5, 25], [11, 40]]]], ['sku' => 'S1', 'price' => 999, 'qty' => 5, 'tax' => 'red', 'promo' => ['type' => 'bundle', 'buy' => 1, 'free' => 1]], ['sku' => 'S2', 'price' => 991, 'qty' => 1, 'tax' => 'std', 'promo' => ['type' => 'tier', 'tiers' => [[1, 18], [14, 46]]]], ['sku' => 'S3', 'price' => 100, 'qty' => 12, 'tax' => 'std', 'promo' => ['type' => 'tier', 'tiers' => [[5, 15], [15, 34]]]]], [], ['lines' => [['sku' => 'S0', 'gross' => 500, 'promo' => 125, 'coupon' => 0, 'net' => 375, 'vat' => 60], ['sku' => 'S1', 'gross' => 4995, 'promo' => 1998, 'coupon' => 0, 'net' => 2997, 'vat' => 196], ['sku' => 'S2', 'gross' => 991, 'promo' => 178, 'coupon' => 0, 'net' => 813, 'vat' => 130], ['sku' => 'S3', 'gross' => 1200, 'promo' => 180, 'coupon' => 0, 'net' => 1020, 'vat' => 163]], 'subtotal' => 5205, 'coupon' => 0, 'shipping' => 0, 'total' => 5205, 'vat' => 549]],
        [[], ['coupon' => ['pct' => 15], 'shipping' => ['flat' => 0]], ['lines' => [], 'subtotal' => 0, 'coupon' => 0, 'shipping' => 0, 'total' => 0, 'vat' => 0]],
        [[['sku' => 'S0', 'price' => 0, 'qty' => 2, 'tax' => 'zero', 'promo' => ['type' => 'tier', 'tiers' => [[4, 4], [9, 39]]]]], ['coupon' => ['pct' => 50]], ['lines' => [['sku' => 'S0', 'gross' => 0, 'promo' => 0, 'coupon' => 0, 'net' => 0, 'vat' => 0]], 'subtotal' => 0, 'coupon' => 0, 'shipping' => 0, 'total' => 0, 'vat' => 0]],
        [[['sku' => 'S0', 'price' => 333, 'qty' => 1, 'tax' => 'zero', 'promo' => ['type' => 'tier', 'tiers' => [[3, 5], [13, 40]]]]], ['coupon' => ['fixed' => 0]], ['lines' => [['sku' => 'S0', 'gross' => 333, 'promo' => 0, 'coupon' => 0, 'net' => 333, 'vat' => 0]], 'subtotal' => 333, 'coupon' => 0, 'shipping' => 0, 'total' => 333, 'vat' => 0]],
        [[], ['shipping' => ['flat' => 199, 'free_over' => 0]], ['lines' => [], 'subtotal' => 0, 'coupon' => 0, 'shipping' => 0, 'total' => 0, 'vat' => 0]],
        [[['sku' => 'S0', 'price' => 99, 'qty' => 4, 'tax' => 'red'], ['sku' => 'S1', 'price' => 1000, 'qty' => 7, 'tax' => 'red'], ['sku' => 'S2', 'price' => 5, 'qty' => 1, 'tax' => 'std', 'promo' => ['type' => 'tier', 'tiers' => [[3, 27], [12, 48]]]]], ['coupon' => ['pct' => 10, 'cap' => 0], 'shipping' => ['flat' => 199]], ['lines' => [['sku' => 'S0', 'gross' => 396, 'promo' => 0, 'coupon' => 0, 'net' => 396, 'vat' => 26], ['sku' => 'S1', 'gross' => 7000, 'promo' => 0, 'coupon' => 0, 'net' => 7000, 'vat' => 458], ['sku' => 'S2', 'gross' => 5, 'promo' => 0, 'coupon' => 0, 'net' => 5, 'vat' => 1]], 'subtotal' => 7401, 'coupon' => 0, 'shipping' => 199, 'total' => 7600, 'vat' => 517]],
        [[], ['coupon' => ['pct' => 25], 'shipping' => ['flat' => 990, 'free_over' => 0]], ['lines' => [], 'subtotal' => 0, 'coupon' => 0, 'shipping' => 0, 'total' => 0, 'vat' => 0]],
        [[['sku' => 'S0', 'price' => 1793, 'qty' => 30, 'tax' => 'std'], ['sku' => 'S1', 'price' => 999, 'qty' => 3, 'tax' => 'std']], ['coupon' => ['pct' => 100, 'cap' => 0], 'shipping' => ['flat' => 0]], ['lines' => [['sku' => 'S0', 'gross' => 53790, 'promo' => 0, 'coupon' => 0, 'net' => 53790, 'vat' => 8588], ['sku' => 'S1', 'gross' => 2997, 'promo' => 0, 'coupon' => 0, 'net' => 2997, 'vat' => 479]], 'subtotal' => 56787, 'coupon' => 0, 'shipping' => 0, 'total' => 56787, 'vat' => 9067]],
        [[], [], ['lines' => [], 'subtotal' => 0, 'coupon' => 0, 'shipping' => 0, 'total' => 0, 'vat' => 0]],
        [[['sku' => 'S0', 'price' => 0, 'qty' => 3, 'tax' => 'zero', 'promo' => ['type' => 'tier', 'tiers' => [[2, 15], [10, 35]]]], ['sku' => 'S1', 'price' => 100, 'qty' => 3, 'tax' => 'red', 'promo' => ['type' => 'tier', 'tiers' => [[3, 29], [10, 55]]]]], [], ['lines' => [['sku' => 'S0', 'gross' => 0, 'promo' => 0, 'coupon' => 0, 'net' => 0, 'vat' => 0], ['sku' => 'S1', 'gross' => 300, 'promo' => 87, 'coupon' => 0, 'net' => 213, 'vat' => 14]], 'subtotal' => 213, 'coupon' => 0, 'shipping' => 0, 'total' => 213, 'vat' => 14]],
        [[['sku' => 'S0', 'price' => 99, 'qty' => 12, 'tax' => 'std', 'promo' => ['type' => 'tier', 'tiers' => [[5, 25], [10, 60]]]], ['sku' => 'S1', 'price' => 5, 'qty' => 10, 'tax' => 'red']], ['coupon' => ['pct' => 10]], ['lines' => [['sku' => 'S0', 'gross' => 1188, 'promo' => 713, 'coupon' => 48, 'net' => 427, 'vat' => 68], ['sku' => 'S1', 'gross' => 50, 'promo' => 0, 'coupon' => 5, 'net' => 45, 'vat' => 3]], 'subtotal' => 525, 'coupon' => 53, 'shipping' => 0, 'total' => 472, 'vat' => 71]],
        [[['sku' => 'S0', 'price' => 4393, 'qty' => 2, 'tax' => 'red', 'promo' => ['type' => 'bundle', 'buy' => 2, 'free' => 2]], ['sku' => 'S1', 'price' => 1, 'qty' => 0, 'tax' => 'zero', 'promo' => ['type' => 'tier', 'tiers' => [[3, 13], [11, 48]]]], ['sku' => 'S2', 'price' => 100, 'qty' => 10, 'tax' => 'zero'], ['sku' => 'S3', 'price' => 333, 'qty' => 12, 'tax' => 'red']], ['coupon' => ['fixed' => 7], 'shipping' => ['flat' => 499]], ['lines' => [['sku' => 'S0', 'gross' => 8786, 'promo' => 0, 'coupon' => 4, 'net' => 8782, 'vat' => 575], ['sku' => 'S1', 'gross' => 0, 'promo' => 0, 'coupon' => 0, 'net' => 0, 'vat' => 0], ['sku' => 'S2', 'gross' => 1000, 'promo' => 0, 'coupon' => 1, 'net' => 999, 'vat' => 0], ['sku' => 'S3', 'gross' => 3996, 'promo' => 0, 'coupon' => 2, 'net' => 3994, 'vat' => 261]], 'subtotal' => 13782, 'coupon' => 7, 'shipping' => 499, 'total' => 14274, 'vat' => 916]],
        [[['sku' => 'S0', 'price' => 999, 'qty' => 3, 'tax' => 'std', 'promo' => ['type' => 'bundle', 'buy' => 3, 'free' => 1]], ['sku' => 'S1', 'price' => 0, 'qty' => 50, 'tax' => 'zero'], ['sku' => 'S2', 'price' => 0, 'qty' => 1, 'tax' => 'std', 'promo' => ['type' => 'tier', 'tiers' => [[4, 30], [14, 39]]]], ['sku' => 'S3', 'price' => 100, 'qty' => 0, 'tax' => 'red']], ['shipping' => ['flat' => 990]], ['lines' => [['sku' => 'S0', 'gross' => 2997, 'promo' => 0, 'coupon' => 0, 'net' => 2997, 'vat' => 479], ['sku' => 'S1', 'gross' => 0, 'promo' => 0, 'coupon' => 0, 'net' => 0, 'vat' => 0], ['sku' => 'S2', 'gross' => 0, 'promo' => 0, 'coupon' => 0, 'net' => 0, 'vat' => 0], ['sku' => 'S3', 'gross' => 0, 'promo' => 0, 'coupon' => 0, 'net' => 0, 'vat' => 0]], 'subtotal' => 2997, 'coupon' => 0, 'shipping' => 990, 'total' => 3987, 'vat' => 637]],
        [[['sku' => 'S0', 'price' => 100, 'qty' => 50, 'tax' => 'red', 'promo' => ['type' => 'bundle', 'buy' => 3, 'free' => 1]], ['sku' => 'S1', 'price' => 100, 'qty' => 0, 'tax' => 'zero']], [], ['lines' => [['sku' => 'S0', 'gross' => 5000, 'promo' => 1200, 'coupon' => 0, 'net' => 3800, 'vat' => 249], ['sku' => 'S1', 'gross' => 0, 'promo' => 0, 'coupon' => 0, 'net' => 0, 'vat' => 0]], 'subtotal' => 3800, 'coupon' => 0, 'shipping' => 0, 'total' => 3800, 'vat' => 249]],
        [[['sku' => 'S0', 'price' => 0, 'qty' => 2, 'tax' => 'std']], [], ['lines' => [['sku' => 'S0', 'gross' => 0, 'promo' => 0, 'coupon' => 0, 'net' => 0, 'vat' => 0]], 'subtotal' => 0, 'coupon' => 0, 'shipping' => 0, 'total' => 0, 'vat' => 0]],
        [[['sku' => 'S0', 'price' => 1000, 'qty' => 5, 'tax' => 'zero', 'promo' => ['type' => 'bundle', 'buy' => 1, 'free' => 2]], ['sku' => 'S1', 'price' => 999, 'qty' => 7, 'tax' => 'std', 'promo' => ['type' => 'bundle', 'buy' => 2, 'free' => 2]], ['sku' => 'S2', 'price' => 1539, 'qty' => 10, 'tax' => 'zero']], [], ['lines' => [['sku' => 'S0', 'gross' => 5000, 'promo' => 3000, 'coupon' => 0, 'net' => 2000, 'vat' => 0], ['sku' => 'S1', 'gross' => 6993, 'promo' => 2997, 'coupon' => 0, 'net' => 3996, 'vat' => 638], ['sku' => 'S2', 'gross' => 15390, 'promo' => 0, 'coupon' => 0, 'net' => 15390, 'vat' => 0]], 'subtotal' => 21386, 'coupon' => 0, 'shipping' => 0, 'total' => 21386, 'vat' => 638]],
        [[['sku' => 'S0', 'price' => 100, 'qty' => 10, 'tax' => 'std', 'promo' => ['type' => 'tier', 'tiers' => [[1, 28], [11, 43]]]]], [], ['lines' => [['sku' => 'S0', 'gross' => 1000, 'promo' => 280, 'coupon' => 0, 'net' => 720, 'vat' => 115]], 'subtotal' => 720, 'coupon' => 0, 'shipping' => 0, 'total' => 720, 'vat' => 115]],
        [[['sku' => 'S0', 'price' => 1000, 'qty' => 2, 'tax' => 'zero', 'promo' => ['type' => 'tier', 'tiers' => [[3, 24], [10, 60]]]], ['sku' => 'S1', 'price' => 999, 'qty' => 7, 'tax' => 'red', 'promo' => ['type' => 'bundle', 'buy' => 2, 'free' => 2]]], ['coupon' => ['fixed' => 100], 'shipping' => ['flat' => 990]], ['lines' => [['sku' => 'S0', 'gross' => 2000, 'promo' => 0, 'coupon' => 33, 'net' => 1967, 'vat' => 0], ['sku' => 'S1', 'gross' => 6993, 'promo' => 2997, 'coupon' => 67, 'net' => 3929, 'vat' => 257]], 'subtotal' => 5996, 'coupon' => 100, 'shipping' => 990, 'total' => 6886, 'vat' => 415]],
        [[['sku' => 'S0', 'price' => 0, 'qty' => 10, 'tax' => 'std', 'promo' => ['type' => 'tier', 'tiers' => [[3, 25], [8, 35]]]], ['sku' => 'S1', 'price' => 99, 'qty' => 7, 'tax' => 'red'], ['sku' => 'S2', 'price' => 0, 'qty' => 7, 'tax' => 'std', 'promo' => ['type' => 'bundle', 'buy' => 2, 'free' => 2]]], ['shipping' => ['flat' => 0, 'free_over' => 0]], ['lines' => [['sku' => 'S0', 'gross' => 0, 'promo' => 0, 'coupon' => 0, 'net' => 0, 'vat' => 0], ['sku' => 'S1', 'gross' => 693, 'promo' => 0, 'coupon' => 0, 'net' => 693, 'vat' => 45], ['sku' => 'S2', 'gross' => 0, 'promo' => 0, 'coupon' => 0, 'net' => 0, 'vat' => 0]], 'subtotal' => 693, 'coupon' => 0, 'shipping' => 0, 'total' => 693, 'vat' => 45]],
        [[], [], ['lines' => [], 'subtotal' => 0, 'coupon' => 0, 'shipping' => 0, 'total' => 0, 'vat' => 0]],
        [[['sku' => 'S0', 'price' => 1000, 'qty' => 3, 'tax' => 'std', 'promo' => ['type' => 'bundle', 'buy' => 2, 'free' => 1]], ['sku' => 'S1', 'price' => 333, 'qty' => 5, 'tax' => 'std', 'promo' => ['type' => 'tier', 'tiers' => [[4, 30], [13, 40]]]], ['sku' => 'S2', 'price' => 0, 'qty' => 12, 'tax' => 'red'], ['sku' => 'S3', 'price' => 333, 'qty' => 11, 'tax' => 'zero', 'promo' => ['type' => 'bundle', 'buy' => 3, 'free' => 2]]], ['coupon' => ['pct' => 5, 'cap' => 0]], ['lines' => [['sku' => 'S0', 'gross' => 3000, 'promo' => 1000, 'coupon' => 0, 'net' => 2000, 'vat' => 319], ['sku' => 'S1', 'gross' => 1665, 'promo' => 500, 'coupon' => 0, 'net' => 1165, 'vat' => 186], ['sku' => 'S2', 'gross' => 0, 'promo' => 0, 'coupon' => 0, 'net' => 0, 'vat' => 0], ['sku' => 'S3', 'gross' => 3663, 'promo' => 1332, 'coupon' => 0, 'net' => 2331, 'vat' => 0]], 'subtotal' => 5496, 'coupon' => 0, 'shipping' => 0, 'total' => 5496, 'vat' => 505]],
        [[['sku' => 'S0', 'price' => 2139, 'qty' => 7, 'tax' => 'std', 'promo' => ['type' => 'tier', 'tiers' => [[1, 6], [15, 52]]]], ['sku' => 'S1', 'price' => 1000, 'qty' => 50, 'tax' => 'std'], ['sku' => 'S2', 'price' => 5, 'qty' => 7, 'tax' => 'std']], [], ['lines' => [['sku' => 'S0', 'gross' => 14973, 'promo' => 898, 'coupon' => 0, 'net' => 14075, 'vat' => 2247], ['sku' => 'S1', 'gross' => 50000, 'promo' => 0, 'coupon' => 0, 'net' => 50000, 'vat' => 7983], ['sku' => 'S2', 'gross' => 35, 'promo' => 0, 'coupon' => 0, 'net' => 35, 'vat' => 6]], 'subtotal' => 64110, 'coupon' => 0, 'shipping' => 0, 'total' => 64110, 'vat' => 10236]],
        [[['sku' => 'S0', 'price' => 100, 'qty' => 12, 'tax' => 'std']], ['shipping' => ['flat' => 199, 'free_over' => 2000]], ['lines' => [['sku' => 'S0', 'gross' => 1200, 'promo' => 0, 'coupon' => 0, 'net' => 1200, 'vat' => 192]], 'subtotal' => 1200, 'coupon' => 0, 'shipping' => 199, 'total' => 1399, 'vat' => 224]],
        [[['sku' => 'S0', 'price' => 5, 'qty' => 12, 'tax' => 'zero']], ['coupon' => ['fixed' => 0]], ['lines' => [['sku' => 'S0', 'gross' => 60, 'promo' => 0, 'coupon' => 0, 'net' => 60, 'vat' => 0]], 'subtotal' => 60, 'coupon' => 0, 'shipping' => 0, 'total' => 60, 'vat' => 0]],
        [[['sku' => 'S0', 'price' => 1, 'qty' => 3, 'tax' => 'zero', 'promo' => ['type' => 'tier', 'tiers' => [[2, 6], [6, 38]]]], ['sku' => 'S1', 'price' => 1, 'qty' => 3, 'tax' => 'std'], ['sku' => 'S2', 'price' => 0, 'qty' => 6, 'tax' => 'zero'], ['sku' => 'S3', 'price' => 2500, 'qty' => 7, 'tax' => 'zero']], ['coupon' => ['fixed' => 499]], ['lines' => [['sku' => 'S0', 'gross' => 3, 'promo' => 0, 'coupon' => 0, 'net' => 3, 'vat' => 0], ['sku' => 'S1', 'gross' => 3, 'promo' => 0, 'coupon' => 0, 'net' => 3, 'vat' => 0], ['sku' => 'S2', 'gross' => 0, 'promo' => 0, 'coupon' => 0, 'net' => 0, 'vat' => 0], ['sku' => 'S3', 'gross' => 17500, 'promo' => 0, 'coupon' => 499, 'net' => 17001, 'vat' => 0]], 'subtotal' => 17506, 'coupon' => 499, 'shipping' => 0, 'total' => 17007, 'vat' => 0]],
        [[['sku' => 'S0', 'price' => 2500, 'qty' => 50, 'tax' => 'std'], ['sku' => 'S1', 'price' => 1999, 'qty' => 4, 'tax' => 'zero', 'promo' => ['type' => 'tier', 'tiers' => [[3, 22], [13, 49]]]]], ['coupon' => ['pct' => 100]], ['lines' => [['sku' => 'S0', 'gross' => 125000, 'promo' => 0, 'coupon' => 125000, 'net' => 0, 'vat' => 0], ['sku' => 'S1', 'gross' => 7996, 'promo' => 1759, 'coupon' => 6237, 'net' => 0, 'vat' => 0]], 'subtotal' => 131237, 'coupon' => 131237, 'shipping' => 0, 'total' => 0, 'vat' => 0]],
        [[], ['coupon' => ['pct' => 50]], ['lines' => [], 'subtotal' => 0, 'coupon' => 0, 'shipping' => 0, 'total' => 0, 'vat' => 0]],
        [[['sku' => 'S0', 'price' => 0, 'qty' => 7, 'tax' => 'zero', 'promo' => ['type' => 'tier', 'tiers' => [[2, 18], [6, 58]]]], ['sku' => 'S1', 'price' => 4922, 'qty' => 22, 'tax' => 'red'], ['sku' => 'S2', 'price' => 1465, 'qty' => 7, 'tax' => 'std', 'promo' => ['type' => 'bundle', 'buy' => 1, 'free' => 1]]], ['coupon' => ['pct' => 50], 'shipping' => ['flat' => 199]], ['lines' => [['sku' => 'S0', 'gross' => 0, 'promo' => 0, 'coupon' => 0, 'net' => 0, 'vat' => 0], ['sku' => 'S1', 'gross' => 108284, 'promo' => 0, 'coupon' => 54142, 'net' => 54142, 'vat' => 3542], ['sku' => 'S2', 'gross' => 10255, 'promo' => 4395, 'coupon' => 2930, 'net' => 2930, 'vat' => 468]], 'subtotal' => 114144, 'coupon' => 57072, 'shipping' => 199, 'total' => 57271, 'vat' => 4042]],
        [[], [], ['lines' => [], 'subtotal' => 0, 'coupon' => 0, 'shipping' => 0, 'total' => 0, 'vat' => 0]],
        [[['sku' => 'S0', 'price' => 333, 'qty' => 12, 'tax' => 'zero', 'promo' => ['type' => 'tier', 'tiers' => [[3, 27], [12, 45]]]], ['sku' => 'S1', 'price' => 2500, 'qty' => 4, 'tax' => 'std', 'promo' => ['type' => 'tier', 'tiers' => [[2, 18], [8, 38]]]]], ['shipping' => ['flat' => 990]], ['lines' => [['sku' => 'S0', 'gross' => 3996, 'promo' => 1798, 'coupon' => 0, 'net' => 2198, 'vat' => 0], ['sku' => 'S1', 'gross' => 10000, 'promo' => 1800, 'coupon' => 0, 'net' => 8200, 'vat' => 1309]], 'subtotal' => 10398, 'coupon' => 0, 'shipping' => 990, 'total' => 11388, 'vat' => 1467]],
        [[['sku' => 'S0', 'price' => 100, 'qty' => 4, 'tax' => 'std'], ['sku' => 'S1', 'price' => 1999, 'qty' => 50, 'tax' => 'zero'], ['sku' => 'S2', 'price' => 1999, 'qty' => 2, 'tax' => 'zero'], ['sku' => 'S3', 'price' => 2500, 'qty' => 0, 'tax' => 'std']], [], ['lines' => [['sku' => 'S0', 'gross' => 400, 'promo' => 0, 'coupon' => 0, 'net' => 400, 'vat' => 64], ['sku' => 'S1', 'gross' => 99950, 'promo' => 0, 'coupon' => 0, 'net' => 99950, 'vat' => 0], ['sku' => 'S2', 'gross' => 3998, 'promo' => 0, 'coupon' => 0, 'net' => 3998, 'vat' => 0], ['sku' => 'S3', 'gross' => 0, 'promo' => 0, 'coupon' => 0, 'net' => 0, 'vat' => 0]], 'subtotal' => 104348, 'coupon' => 0, 'shipping' => 0, 'total' => 104348, 'vat' => 64]],
        [[['sku' => 'S0', 'price' => 0, 'qty' => 10, 'tax' => 'std', 'promo' => ['type' => 'tier', 'tiers' => [[5, 7], [13, 32]]]], ['sku' => 'S1', 'price' => 1999, 'qty' => 7, 'tax' => 'std'], ['sku' => 'S2', 'price' => 333, 'qty' => 5, 'tax' => 'zero', 'promo' => ['type' => 'bundle', 'buy' => 2, 'free' => 1]], ['sku' => 'S3', 'price' => 1, 'qty' => 2, 'tax' => 'zero']], ['coupon' => ['pct' => 50, 'cap' => 1000], 'shipping' => ['flat' => 990, 'free_over' => 2000]], ['lines' => [['sku' => 'S0', 'gross' => 0, 'promo' => 0, 'coupon' => 0, 'net' => 0, 'vat' => 0], ['sku' => 'S1', 'gross' => 13993, 'promo' => 0, 'coupon' => 913, 'net' => 13080, 'vat' => 2088], ['sku' => 'S2', 'gross' => 1665, 'promo' => 333, 'coupon' => 87, 'net' => 1245, 'vat' => 0], ['sku' => 'S3', 'gross' => 2, 'promo' => 0, 'coupon' => 0, 'net' => 2, 'vat' => 0]], 'subtotal' => 15327, 'coupon' => 1000, 'shipping' => 0, 'total' => 14327, 'vat' => 2088]],
        [[['sku' => 'S0', 'price' => 333, 'qty' => 4, 'tax' => 'std', 'promo' => ['type' => 'bundle', 'buy' => 3, 'free' => 1]], ['sku' => 'S1', 'price' => 5, 'qty' => 8, 'tax' => 'red'], ['sku' => 'S2', 'price' => 333, 'qty' => 3, 'tax' => 'std', 'promo' => ['type' => 'bundle', 'buy' => 1, 'free' => 1]]], ['coupon' => ['fixed' => 100]], ['lines' => [['sku' => 'S0', 'gross' => 1332, 'promo' => 333, 'coupon' => 59, 'net' => 940, 'vat' => 150], ['sku' => 'S1', 'gross' => 40, 'promo' => 0, 'coupon' => 2, 'net' => 38, 'vat' => 2], ['sku' => 'S2', 'gross' => 999, 'promo' => 333, 'coupon' => 39, 'net' => 627, 'vat' => 100]], 'subtotal' => 1705, 'coupon' => 100, 'shipping' => 0, 'total' => 1605, 'vat' => 252]],
        [[['sku' => 'S0', 'price' => 999, 'qty' => 12, 'tax' => 'std'], ['sku' => 'S1', 'price' => 2500, 'qty' => 3, 'tax' => 'std'], ['sku' => 'S2', 'price' => 5, 'qty' => 2, 'tax' => 'std']], ['shipping' => ['flat' => 499]], ['lines' => [['sku' => 'S0', 'gross' => 11988, 'promo' => 0, 'coupon' => 0, 'net' => 11988, 'vat' => 1914], ['sku' => 'S1', 'gross' => 7500, 'promo' => 0, 'coupon' => 0, 'net' => 7500, 'vat' => 1197], ['sku' => 'S2', 'gross' => 10, 'promo' => 0, 'coupon' => 0, 'net' => 10, 'vat' => 2]], 'subtotal' => 19498, 'coupon' => 0, 'shipping' => 499, 'total' => 19997, 'vat' => 3193]],
        [[], ['shipping' => ['flat' => 499, 'free_over' => 9999]], ['lines' => [], 'subtotal' => 0, 'coupon' => 0, 'shipping' => 0, 'total' => 0, 'vat' => 0]],
        [[['sku' => 'S0', 'price' => 2500, 'qty' => 3, 'tax' => 'std', 'promo' => ['type' => 'bundle', 'buy' => 3, 'free' => 2]], ['sku' => 'S1', 'price' => 99, 'qty' => 10, 'tax' => 'zero']], ['coupon' => ['pct' => 50]], ['lines' => [['sku' => 'S0', 'gross' => 7500, 'promo' => 0, 'coupon' => 3750, 'net' => 3750, 'vat' => 599], ['sku' => 'S1', 'gross' => 990, 'promo' => 0, 'coupon' => 495, 'net' => 495, 'vat' => 0]], 'subtotal' => 8490, 'coupon' => 4245, 'shipping' => 0, 'total' => 4245, 'vat' => 599]],
        [[['sku' => 'S0', 'price' => 2500, 'qty' => 4, 'tax' => 'zero']], [], ['lines' => [['sku' => 'S0', 'gross' => 10000, 'promo' => 0, 'coupon' => 0, 'net' => 10000, 'vat' => 0]], 'subtotal' => 10000, 'coupon' => 0, 'shipping' => 0, 'total' => 10000, 'vat' => 0]],
        [[['sku' => 'S0', 'price' => 1, 'qty' => 4, 'tax' => 'std']], ['coupon' => ['pct' => 5], 'shipping' => ['flat' => 199, 'free_over' => 1]], ['lines' => [['sku' => 'S0', 'gross' => 4, 'promo' => 0, 'coupon' => 0, 'net' => 4, 'vat' => 1]], 'subtotal' => 4, 'coupon' => 0, 'shipping' => 0, 'total' => 4, 'vat' => 1]],
        [[['sku' => 'S0', 'price' => 99, 'qty' => 4, 'tax' => 'red', 'promo' => ['type' => 'tier', 'tiers' => [[4, 9], [10, 39]]]], ['sku' => 'S1', 'price' => 333, 'qty' => 50, 'tax' => 'std'], ['sku' => 'S2', 'price' => 2500, 'qty' => 2, 'tax' => 'red', 'promo' => ['type' => 'bundle', 'buy' => 2, 'free' => 2]]], ['coupon' => ['pct' => 50]], ['lines' => [['sku' => 'S0', 'gross' => 396, 'promo' => 36, 'coupon' => 180, 'net' => 180, 'vat' => 12], ['sku' => 'S1', 'gross' => 16650, 'promo' => 0, 'coupon' => 8325, 'net' => 8325, 'vat' => 1329], ['sku' => 'S2', 'gross' => 5000, 'promo' => 0, 'coupon' => 2500, 'net' => 2500, 'vat' => 164]], 'subtotal' => 22010, 'coupon' => 11005, 'shipping' => 0, 'total' => 11005, 'vat' => 1505]],
        [[], ['coupon' => ['fixed' => 1]], ['lines' => [], 'subtotal' => 0, 'coupon' => 0, 'shipping' => 0, 'total' => 0, 'vat' => 0]],
        [[['sku' => 'S0', 'price' => 1000, 'qty' => 10, 'tax' => 'zero']], ['shipping' => ['flat' => 990]], ['lines' => [['sku' => 'S0', 'gross' => 10000, 'promo' => 0, 'coupon' => 0, 'net' => 10000, 'vat' => 0]], 'subtotal' => 10000, 'coupon' => 0, 'shipping' => 990, 'total' => 10990, 'vat' => 158]],
        [[], [], ['lines' => [], 'subtotal' => 0, 'coupon' => 0, 'shipping' => 0, 'total' => 0, 'vat' => 0]],
        [[['sku' => 'S0', 'price' => 5, 'qty' => 2, 'tax' => 'std', 'promo' => ['type' => 'bundle', 'buy' => 2, 'free' => 2]], ['sku' => 'S1', 'price' => 2500, 'qty' => 12, 'tax' => 'red', 'promo' => ['type' => 'tier', 'tiers' => [[3, 25], [12, 32]]]]], ['shipping' => ['flat' => 990, 'free_over' => 5000]], ['lines' => [['sku' => 'S0', 'gross' => 10, 'promo' => 0, 'coupon' => 0, 'net' => 10, 'vat' => 2], ['sku' => 'S1', 'gross' => 30000, 'promo' => 9600, 'coupon' => 0, 'net' => 20400, 'vat' => 1335]], 'subtotal' => 20410, 'coupon' => 0, 'shipping' => 0, 'total' => 20410, 'vat' => 1337]],
        [[['sku' => 'S0', 'price' => 99, 'qty' => 50, 'tax' => 'zero'], ['sku' => 'S1', 'price' => 1000, 'qty' => 12, 'tax' => 'red'], ['sku' => 'S2', 'price' => 1, 'qty' => 10, 'tax' => 'std', 'promo' => ['type' => 'bundle', 'buy' => 1, 'free' => 1]]], ['coupon' => ['fixed' => 499], 'shipping' => ['flat' => 499]], ['lines' => [['sku' => 'S0', 'gross' => 4950, 'promo' => 0, 'coupon' => 146, 'net' => 4804, 'vat' => 0], ['sku' => 'S1', 'gross' => 12000, 'promo' => 0, 'coupon' => 353, 'net' => 11647, 'vat' => 762], ['sku' => 'S2', 'gross' => 10, 'promo' => 5, 'coupon' => 0, 'net' => 5, 'vat' => 1]], 'subtotal' => 16955, 'coupon' => 499, 'shipping' => 499, 'total' => 16955, 'vat' => 843]],
        [[], ['coupon' => ['fixed' => 1], 'shipping' => ['flat' => 499]], ['lines' => [], 'subtotal' => 0, 'coupon' => 0, 'shipping' => 0, 'total' => 0, 'vat' => 0]],
        [[['sku' => 'S0', 'price' => 0, 'qty' => 3, 'tax' => 'std', 'promo' => ['type' => 'tier', 'tiers' => [[1, 22], [7, 38]]]], ['sku' => 'S1', 'price' => 1000, 'qty' => 4, 'tax' => 'zero']], ['coupon' => ['pct' => 100], 'shipping' => ['flat' => 499, 'free_over' => 1]], ['lines' => [['sku' => 'S0', 'gross' => 0, 'promo' => 0, 'coupon' => 0, 'net' => 0, 'vat' => 0], ['sku' => 'S1', 'gross' => 4000, 'promo' => 0, 'coupon' => 4000, 'net' => 0, 'vat' => 0]], 'subtotal' => 4000, 'coupon' => 4000, 'shipping' => 499, 'total' => 499, 'vat' => 80]],
        [[], ['shipping' => ['flat' => 0, 'free_over' => 0]], ['lines' => [], 'subtotal' => 0, 'coupon' => 0, 'shipping' => 0, 'total' => 0, 'vat' => 0]],
        [[['sku' => 'S0', 'price' => 333, 'qty' => 50, 'tax' => 'zero', 'promo' => ['type' => 'bundle', 'buy' => 3, 'free' => 2]]], ['shipping' => ['flat' => 199]], ['lines' => [['sku' => 'S0', 'gross' => 16650, 'promo' => 6660, 'coupon' => 0, 'net' => 9990, 'vat' => 0]], 'subtotal' => 9990, 'coupon' => 0, 'shipping' => 199, 'total' => 10189, 'vat' => 32]],
        [[], ['shipping' => ['flat' => 0, 'free_over' => 9999]], ['lines' => [], 'subtotal' => 0, 'coupon' => 0, 'shipping' => 0, 'total' => 0, 'vat' => 0]],
        [[['sku' => 'S0', 'price' => 1999, 'qty' => 5, 'tax' => 'std'], ['sku' => 'S1', 'price' => 0, 'qty' => 50, 'tax' => 'std'], ['sku' => 'S2', 'price' => 5, 'qty' => 50, 'tax' => 'zero']], ['coupon' => ['fixed' => 499], 'shipping' => ['flat' => 0, 'free_over' => 0]], ['lines' => [['sku' => 'S0', 'gross' => 9995, 'promo' => 0, 'coupon' => 487, 'net' => 9508, 'vat' => 1518], ['sku' => 'S1', 'gross' => 0, 'promo' => 0, 'coupon' => 0, 'net' => 0, 'vat' => 0], ['sku' => 'S2', 'gross' => 250, 'promo' => 0, 'coupon' => 12, 'net' => 238, 'vat' => 0]], 'subtotal' => 10245, 'coupon' => 499, 'shipping' => 0, 'total' => 9746, 'vat' => 1518]],
        [[['sku' => 'S0', 'price' => 0, 'qty' => 4, 'tax' => 'red', 'promo' => ['type' => 'tier', 'tiers' => [[1, 25], [13, 38]]]]], ['shipping' => ['flat' => 499, 'free_over' => 5000]], ['lines' => [['sku' => 'S0', 'gross' => 0, 'promo' => 0, 'coupon' => 0, 'net' => 0, 'vat' => 0]], 'subtotal' => 0, 'coupon' => 0, 'shipping' => 499, 'total' => 499, 'vat' => 80]],
        [[['sku' => 'S0', 'price' => 999, 'qty' => 7, 'tax' => 'zero'], ['sku' => 'S1', 'price' => 99, 'qty' => 2, 'tax' => 'std'], ['sku' => 'S2', 'price' => 99, 'qty' => 4, 'tax' => 'red', 'promo' => ['type' => 'bundle', 'buy' => 3, 'free' => 1]], ['sku' => 'S3', 'price' => 99, 'qty' => 5, 'tax' => 'red', 'promo' => ['type' => 'bundle', 'buy' => 2, 'free' => 1]]], ['shipping' => ['flat' => 199, 'free_over' => 9999]], ['lines' => [['sku' => 'S0', 'gross' => 6993, 'promo' => 0, 'coupon' => 0, 'net' => 6993, 'vat' => 0], ['sku' => 'S1', 'gross' => 198, 'promo' => 0, 'coupon' => 0, 'net' => 198, 'vat' => 32], ['sku' => 'S2', 'gross' => 396, 'promo' => 99, 'coupon' => 0, 'net' => 297, 'vat' => 19], ['sku' => 'S3', 'gross' => 495, 'promo' => 99, 'coupon' => 0, 'net' => 396, 'vat' => 26]], 'subtotal' => 7884, 'coupon' => 0, 'shipping' => 199, 'total' => 8083, 'vat' => 109]],
        [[['sku' => 'S0', 'price' => 99, 'qty' => 12, 'tax' => 'std']], [], ['lines' => [['sku' => 'S0', 'gross' => 1188, 'promo' => 0, 'coupon' => 0, 'net' => 1188, 'vat' => 190]], 'subtotal' => 1188, 'coupon' => 0, 'shipping' => 0, 'total' => 1188, 'vat' => 190]],
        [[['sku' => 'S0', 'price' => 1, 'qty' => 12, 'tax' => 'red'], ['sku' => 'S1', 'price' => 2029, 'qty' => 7, 'tax' => 'red', 'promo' => ['type' => 'bundle', 'buy' => 2, 'free' => 2]]], ['coupon' => ['fixed' => 5000], 'shipping' => ['flat' => 499, 'free_over' => 5000]], ['lines' => [['sku' => 'S0', 'gross' => 12, 'promo' => 0, 'coupon' => 7, 'net' => 5, 'vat' => 0], ['sku' => 'S1', 'gross' => 14203, 'promo' => 6087, 'coupon' => 4993, 'net' => 3123, 'vat' => 204]], 'subtotal' => 8128, 'coupon' => 5000, 'shipping' => 499, 'total' => 3627, 'vat' => 284]],
        [[['sku' => 'S0', 'price' => 1000, 'qty' => 5, 'tax' => 'std'], ['sku' => 'S1', 'price' => 99, 'qty' => 0, 'tax' => 'std'], ['sku' => 'S2', 'price' => 5, 'qty' => 10, 'tax' => 'zero', 'promo' => ['type' => 'tier', 'tiers' => [[4, 6], [11, 41]]]], ['sku' => 'S3', 'price' => 2500, 'qty' => 28, 'tax' => 'std']], ['coupon' => ['fixed' => 0]], ['lines' => [['sku' => 'S0', 'gross' => 5000, 'promo' => 0, 'coupon' => 0, 'net' => 5000, 'vat' => 798], ['sku' => 'S1', 'gross' => 0, 'promo' => 0, 'coupon' => 0, 'net' => 0, 'vat' => 0], ['sku' => 'S2', 'gross' => 50, 'promo' => 3, 'coupon' => 0, 'net' => 47, 'vat' => 0], ['sku' => 'S3', 'gross' => 70000, 'promo' => 0, 'coupon' => 0, 'net' => 70000, 'vat' => 11176]], 'subtotal' => 75047, 'coupon' => 0, 'shipping' => 0, 'total' => 75047, 'vat' => 11974]],
        [[['sku' => 'S0', 'price' => 1, 'qty' => 10, 'tax' => 'std', 'promo' => ['type' => 'bundle', 'buy' => 3, 'free' => 2]], ['sku' => 'S1', 'price' => 100, 'qty' => 0, 'tax' => 'std']], ['shipping' => ['flat' => 499]], ['lines' => [['sku' => 'S0', 'gross' => 10, 'promo' => 4, 'coupon' => 0, 'net' => 6, 'vat' => 1], ['sku' => 'S1', 'gross' => 0, 'promo' => 0, 'coupon' => 0, 'net' => 0, 'vat' => 0]], 'subtotal' => 6, 'coupon' => 0, 'shipping' => 499, 'total' => 505, 'vat' => 81]],
        [[['sku' => 'S0', 'price' => 1999, 'qty' => 2, 'tax' => 'std', 'promo' => ['type' => 'bundle', 'buy' => 3, 'free' => 1]], ['sku' => 'S1', 'price' => 2500, 'qty' => 12, 'tax' => 'zero', 'promo' => ['type' => 'bundle', 'buy' => 3, 'free' => 1]], ['sku' => 'S2', 'price' => 0, 'qty' => 5, 'tax' => 'red']], ['coupon' => ['pct' => 5]], ['lines' => [['sku' => 'S0', 'gross' => 3998, 'promo' => 0, 'coupon' => 200, 'net' => 3798, 'vat' => 606], ['sku' => 'S1', 'gross' => 30000, 'promo' => 7500, 'coupon' => 1125, 'net' => 21375, 'vat' => 0], ['sku' => 'S2', 'gross' => 0, 'promo' => 0, 'coupon' => 0, 'net' => 0, 'vat' => 0]], 'subtotal' => 26498, 'coupon' => 1325, 'shipping' => 0, 'total' => 25173, 'vat' => 606]],
        [[['sku' => 'S0', 'price' => 0, 'qty' => 3, 'tax' => 'zero'], ['sku' => 'S1', 'price' => 1749, 'qty' => 4, 'tax' => 'red', 'promo' => ['type' => 'bundle', 'buy' => 1, 'free' => 2]], ['sku' => 'S2', 'price' => 999, 'qty' => 7, 'tax' => 'std'], ['sku' => 'S3', 'price' => 99, 'qty' => 0, 'tax' => 'std']], [], ['lines' => [['sku' => 'S0', 'gross' => 0, 'promo' => 0, 'coupon' => 0, 'net' => 0, 'vat' => 0], ['sku' => 'S1', 'gross' => 6996, 'promo' => 3498, 'coupon' => 0, 'net' => 3498, 'vat' => 229], ['sku' => 'S2', 'gross' => 6993, 'promo' => 0, 'coupon' => 0, 'net' => 6993, 'vat' => 1117], ['sku' => 'S3', 'gross' => 0, 'promo' => 0, 'coupon' => 0, 'net' => 0, 'vat' => 0]], 'subtotal' => 10491, 'coupon' => 0, 'shipping' => 0, 'total' => 10491, 'vat' => 1346]],
        [[['sku' => 'S0', 'price' => 151, 'qty' => 0, 'tax' => 'std', 'promo' => ['type' => 'tier', 'tiers' => [[2, 18], [7, 57]]]], ['sku' => 'S1', 'price' => 1, 'qty' => 4, 'tax' => 'red', 'promo' => ['type' => 'tier', 'tiers' => [[3, 28], [7, 42]]]], ['sku' => 'S2', 'price' => 2500, 'qty' => 3, 'tax' => 'std'], ['sku' => 'S3', 'price' => 1000, 'qty' => 50, 'tax' => 'zero']], ['coupon' => ['pct' => 10]], ['lines' => [['sku' => 'S0', 'gross' => 0, 'promo' => 0, 'coupon' => 0, 'net' => 0, 'vat' => 0], ['sku' => 'S1', 'gross' => 4, 'promo' => 1, 'coupon' => 0, 'net' => 3, 'vat' => 0], ['sku' => 'S2', 'gross' => 7500, 'promo' => 0, 'coupon' => 750, 'net' => 6750, 'vat' => 1078], ['sku' => 'S3', 'gross' => 50000, 'promo' => 0, 'coupon' => 5000, 'net' => 45000, 'vat' => 0]], 'subtotal' => 57503, 'coupon' => 5750, 'shipping' => 0, 'total' => 51753, 'vat' => 1078]],
        [[['sku' => 'S0', 'price' => 100, 'qty' => 3, 'tax' => 'std', 'promo' => ['type' => 'bundle', 'buy' => 3, 'free' => 1]]], ['coupon' => ['pct' => 10]], ['lines' => [['sku' => 'S0', 'gross' => 300, 'promo' => 0, 'coupon' => 30, 'net' => 270, 'vat' => 43]], 'subtotal' => 300, 'coupon' => 30, 'shipping' => 0, 'total' => 270, 'vat' => 43]],
        [[['sku' => 'S0', 'price' => 458, 'qty' => 10, 'tax' => 'zero', 'promo' => ['type' => 'tier', 'tiers' => [[3, 15], [13, 40]]]]], ['coupon' => ['fixed' => 499]], ['lines' => [['sku' => 'S0', 'gross' => 4580, 'promo' => 687, 'coupon' => 499, 'net' => 3394, 'vat' => 0]], 'subtotal' => 3893, 'coupon' => 499, 'shipping' => 0, 'total' => 3394, 'vat' => 0]],
        [[['sku' => 'S0', 'price' => 1999, 'qty' => 7, 'tax' => 'std'], ['sku' => 'S1', 'price' => 999, 'qty' => 12, 'tax' => 'red'], ['sku' => 'S2', 'price' => 333, 'qty' => 1, 'tax' => 'red'], ['sku' => 'S3', 'price' => 333, 'qty' => 6, 'tax' => 'std']], ['coupon' => ['pct' => 5], 'shipping' => ['flat' => 199, 'free_over' => 0]], ['lines' => [['sku' => 'S0', 'gross' => 13993, 'promo' => 0, 'coupon' => 700, 'net' => 13293, 'vat' => 2122], ['sku' => 'S1', 'gross' => 11988, 'promo' => 0, 'coupon' => 599, 'net' => 11389, 'vat' => 745], ['sku' => 'S2', 'gross' => 333, 'promo' => 0, 'coupon' => 17, 'net' => 316, 'vat' => 21], ['sku' => 'S3', 'gross' => 1998, 'promo' => 0, 'coupon' => 100, 'net' => 1898, 'vat' => 303]], 'subtotal' => 28312, 'coupon' => 1416, 'shipping' => 0, 'total' => 26896, 'vat' => 3191]],
        [[], ['shipping' => ['flat' => 199, 'free_over' => 0]], ['lines' => [], 'subtotal' => 0, 'coupon' => 0, 'shipping' => 0, 'total' => 0, 'vat' => 0]],
        [[['sku' => 'S0', 'price' => 1999, 'qty' => 2, 'tax' => 'zero', 'promo' => ['type' => 'tier', 'tiers' => [[3, 1], [8, 53]]]], ['sku' => 'S1', 'price' => 333, 'qty' => 12, 'tax' => 'std', 'promo' => ['type' => 'bundle', 'buy' => 3, 'free' => 2]], ['sku' => 'S2', 'price' => 99, 'qty' => 4, 'tax' => 'red']], ['coupon' => ['fixed' => 499]], ['lines' => [['sku' => 'S0', 'gross' => 3998, 'promo' => 0, 'coupon' => 283, 'net' => 3715, 'vat' => 0], ['sku' => 'S1', 'gross' => 3996, 'promo' => 1332, 'coupon' => 188, 'net' => 2476, 'vat' => 395], ['sku' => 'S2', 'gross' => 396, 'promo' => 0, 'coupon' => 28, 'net' => 368, 'vat' => 24]], 'subtotal' => 7058, 'coupon' => 499, 'shipping' => 0, 'total' => 6559, 'vat' => 419]],
        [[['sku' => 'S0', 'price' => 999, 'qty' => 3, 'tax' => 'std', 'promo' => ['type' => 'tier', 'tiers' => [[3, 2], [9, 60]]]], ['sku' => 'S1', 'price' => 99, 'qty' => 2, 'tax' => 'zero', 'promo' => ['type' => 'tier', 'tiers' => [[1, 16], [8, 60]]]]], ['shipping' => ['flat' => 990, 'free_over' => 0]], ['lines' => [['sku' => 'S0', 'gross' => 2997, 'promo' => 60, 'coupon' => 0, 'net' => 2937, 'vat' => 469], ['sku' => 'S1', 'gross' => 198, 'promo' => 32, 'coupon' => 0, 'net' => 166, 'vat' => 0]], 'subtotal' => 3103, 'coupon' => 0, 'shipping' => 0, 'total' => 3103, 'vat' => 469]],
        [[], [], ['lines' => [], 'subtotal' => 0, 'coupon' => 0, 'shipping' => 0, 'total' => 0, 'vat' => 0]],
        [[['sku' => 'S0', 'price' => 1, 'qty' => 0, 'tax' => 'std', 'promo' => ['type' => 'tier', 'tiers' => [[4, 9], [13, 42]]]], ['sku' => 'S1', 'price' => 2990, 'qty' => 1, 'tax' => 'std', 'promo' => ['type' => 'tier', 'tiers' => [[5, 4], [14, 59]]]], ['sku' => 'S2', 'price' => 4641, 'qty' => 2, 'tax' => 'std'], ['sku' => 'S3', 'price' => 1, 'qty' => 10, 'tax' => 'red', 'promo' => ['type' => 'tier', 'tiers' => [[3, 13], [13, 31]]]]], [], ['lines' => [['sku' => 'S0', 'gross' => 0, 'promo' => 0, 'coupon' => 0, 'net' => 0, 'vat' => 0], ['sku' => 'S1', 'gross' => 2990, 'promo' => 0, 'coupon' => 0, 'net' => 2990, 'vat' => 477], ['sku' => 'S2', 'gross' => 9282, 'promo' => 0, 'coupon' => 0, 'net' => 9282, 'vat' => 1482], ['sku' => 'S3', 'gross' => 10, 'promo' => 1, 'coupon' => 0, 'net' => 9, 'vat' => 1]], 'subtotal' => 12281, 'coupon' => 0, 'shipping' => 0, 'total' => 12281, 'vat' => 1960]],
        [[['sku' => 'S0', 'price' => 5, 'qty' => 50, 'tax' => 'zero', 'promo' => ['type' => 'bundle', 'buy' => 1, 'free' => 1]], ['sku' => 'S1', 'price' => 100, 'qty' => 2, 'tax' => 'zero', 'promo' => ['type' => 'bundle', 'buy' => 3, 'free' => 2]], ['sku' => 'S2', 'price' => 5, 'qty' => 4, 'tax' => 'std']], ['coupon' => ['pct' => 10, 'cap' => 0]], ['lines' => [['sku' => 'S0', 'gross' => 250, 'promo' => 125, 'coupon' => 0, 'net' => 125, 'vat' => 0], ['sku' => 'S1', 'gross' => 200, 'promo' => 0, 'coupon' => 0, 'net' => 200, 'vat' => 0], ['sku' => 'S2', 'gross' => 20, 'promo' => 0, 'coupon' => 0, 'net' => 20, 'vat' => 3]], 'subtotal' => 345, 'coupon' => 0, 'shipping' => 0, 'total' => 345, 'vat' => 3]],
        [[['sku' => 'S0', 'price' => 999, 'qty' => 12, 'tax' => 'red', 'promo' => ['type' => 'tier', 'tiers' => [[2, 2], [8, 50]]]], ['sku' => 'S1', 'price' => 1, 'qty' => 3, 'tax' => 'std', 'promo' => ['type' => 'tier', 'tiers' => [[4, 20], [9, 59]]]], ['sku' => 'S2', 'price' => 1999, 'qty' => 7, 'tax' => 'std'], ['sku' => 'S3', 'price' => 100, 'qty' => 1, 'tax' => 'std']], ['coupon' => ['fixed' => 499], 'shipping' => ['flat' => 990, 'free_over' => 1]], ['lines' => [['sku' => 'S0', 'gross' => 11988, 'promo' => 5994, 'coupon' => 149, 'net' => 5845, 'vat' => 382], ['sku' => 'S1', 'gross' => 3, 'promo' => 0, 'coupon' => 0, 'net' => 3, 'vat' => 0], ['sku' => 'S2', 'gross' => 13993, 'promo' => 0, 'coupon' => 348, 'net' => 13645, 'vat' => 2179], ['sku' => 'S3', 'gross' => 100, 'promo' => 0, 'coupon' => 2, 'net' => 98, 'vat' => 16]], 'subtotal' => 20090, 'coupon' => 499, 'shipping' => 0, 'total' => 19591, 'vat' => 2577]],
        [[['sku' => 'S0', 'price' => 333, 'qty' => 3, 'tax' => 'std'], ['sku' => 'S1', 'price' => 333, 'qty' => 50, 'tax' => 'std'], ['sku' => 'S2', 'price' => 99, 'qty' => 10, 'tax' => 'red', 'promo' => ['type' => 'tier', 'tiers' => [[3, 23], [12, 52]]]], ['sku' => 'S3', 'price' => 2500, 'qty' => 1, 'tax' => 'zero']], ['shipping' => ['flat' => 990]], ['lines' => [['sku' => 'S0', 'gross' => 999, 'promo' => 0, 'coupon' => 0, 'net' => 999, 'vat' => 160], ['sku' => 'S1', 'gross' => 16650, 'promo' => 0, 'coupon' => 0, 'net' => 16650, 'vat' => 2658], ['sku' => 'S2', 'gross' => 990, 'promo' => 228, 'coupon' => 0, 'net' => 762, 'vat' => 50], ['sku' => 'S3', 'gross' => 2500, 'promo' => 0, 'coupon' => 0, 'net' => 2500, 'vat' => 0]], 'subtotal' => 20911, 'coupon' => 0, 'shipping' => 990, 'total' => 21901, 'vat' => 3026]],
        [[['sku' => 'S0', 'price' => 2500, 'qty' => 12, 'tax' => 'std']], ['coupon' => ['pct' => 0, 'cap' => 1000], 'shipping' => ['flat' => 990, 'free_over' => 5000]], ['lines' => [['sku' => 'S0', 'gross' => 30000, 'promo' => 0, 'coupon' => 0, 'net' => 30000, 'vat' => 4790]], 'subtotal' => 30000, 'coupon' => 0, 'shipping' => 0, 'total' => 30000, 'vat' => 4790]],
        [[['sku' => 'S0', 'price' => 333, 'qty' => 3, 'tax' => 'std']], ['coupon' => ['fixed' => 499]], ['lines' => [['sku' => 'S0', 'gross' => 999, 'promo' => 0, 'coupon' => 499, 'net' => 500, 'vat' => 80]], 'subtotal' => 999, 'coupon' => 499, 'shipping' => 0, 'total' => 500, 'vat' => 80]],
        [[['sku' => 'S0', 'price' => 333, 'qty' => 50, 'tax' => 'red', 'promo' => ['type' => 'bundle', 'buy' => 3, 'free' => 2]], ['sku' => 'S1', 'price' => 999, 'qty' => 7, 'tax' => 'red']], ['coupon' => ['pct' => 100]], ['lines' => [['sku' => 'S0', 'gross' => 16650, 'promo' => 6660, 'coupon' => 9990, 'net' => 0, 'vat' => 0], ['sku' => 'S1', 'gross' => 6993, 'promo' => 0, 'coupon' => 6993, 'net' => 0, 'vat' => 0]], 'subtotal' => 16983, 'coupon' => 16983, 'shipping' => 0, 'total' => 0, 'vat' => 0]],
    ];
    $ALLOC = [
        [100, [1, 1, 1], [34, 33, 33]],
        [0, [1, 2], [0, 0]],
        [1, [1, 1], [1, 0]],
        [1, [0, 1], [0, 1]],
        [7, [0, 0], [0, 0]],
        [7, [], []],
        [5, [2, 2, 2, 2], [2, 1, 1, 1]],
        [10, [3, 3, 4], [3, 3, 4]],
        [99, [1, 2, 3], [17, 33, 49]],
        [1000, [333, 333, 334], [333, 333, 334]],
        [1, [5, 5, 5], [1, 0, 0]],
        [2, [5, 5, 5], [1, 1, 0]],
        [3, [5, 5, 5], [1, 1, 1]],
        [101, [1, 0, 1], [51, 0, 50]],
        [50, [1, 2, 3, 4, 5], [3, 7, 10, 13, 17]],
        [-1, [1], null],
        [5, [1, -1], null],
        [100, [1, 0], [100, 0]],
        [333, [1, 1, 1], [111, 111, 111]],
        [1000000000, [1, 1, 1], [333333334, 333333333, 333333333]],
        [7, [100, 1], [7, 0]],
        [12, [1, 1, 1, 1, 1], [3, 3, 2, 2, 2]],
        [13, [1, 1, 1, 1, 1], [3, 3, 3, 2, 2]],
    ];

    function try_call(callable $f)
    {
        try {
            return $f();
        } catch (InvalidArgumentException $e) {
            return null;
        }
    }

    test('basket table', function () use ($CASES) {
        foreach ($CASES as $i => [$lines, $opts, $want]) {
            eq(try_call(fn() => Basket::price($lines, $opts)), $want, 'basket ' . json_encode($lines) . ' ' . json_encode($opts));
        }
    });

    test('allocator table', function () use ($ALLOC) {
        foreach ($ALLOC as [$amount, $weights, $want]) {
            eq(try_call(fn() => Allocator::share($amount, $weights)), $want, "share($amount, " . json_encode($weights) . ')');
        }
    });

    test('the basket total always adds up', function () {
        for ($qty = 0; $qty <= 12; $qty++) {
            foreach ([0, 1, 7, 99, 100, 301] as $coupon) {
                $r = Basket::price([
                    ['sku' => 'A', 'price' => 333, 'qty' => $qty, 'tax' => 'std'],
                    ['sku' => 'B', 'price' => 101, 'qty' => 3, 'tax' => 'red'],
                    ['sku' => 'C', 'price' => 49, 'qty' => 5, 'tax' => 'zero'],
                ], ['coupon' => ['fixed' => $coupon]]);
                $sum = 0;
                $cs = 0;
                foreach ($r['lines'] as $l) {
                    $sum += $l['net'];
                    $cs += $l['coupon'];
                    eq($l['gross'] - $l['promo'] - $l['coupon'], $l['net'], "line arithmetic with qty $qty and coupon $coupon");
                }
                eq($sum, $r['total'], "total with qty $qty and coupon $coupon");
                eq($cs, $r['coupon'], "coupon shares with qty $qty and coupon $coupon");
            }
        }
    });

    t_done();
''')

LIB = Lib(
    name="basketcalc", lang="php", title="the basketcalc pricing engine",
    blurb="The webshop prices every basket with basketcalc: line promotions first, then the coupon, then shipping and finally the VAT contained in the prices.",
    files={"README.md": README1, "src/Allocator.php": F2, "src/Basket.php": F3, "src/Promo.php": F4},
    visible_tests={"tests/run.php": _lang3.php_test(V5)},
    hidden_tests={"tests/run.php": _lang3.php_test(H6)},
    mutate=["src/Basket.php", "src/Promo.php", "src/Allocator.php"], difficulty=4, tags=["pricing", "promotions", "tax"],
)

_lang3.add(LIB, n=8)

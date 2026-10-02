"""Quantities with exact units (rust): rational arithmetic, a table of harbour units, dimension checking, unit expressions."""
from fx import Lib, dd

from generators.fix._lang1 import CARGO_CONFIG, cargo, register_libs

README = dd('''
    # tideunits

    Exact unit conversion for the harbour master's tools: sizes in cables and fathoms, speeds in knots, times in tides and watches. All numbers are
    exact fractions (`i128` numerator and denominator); there is no floating point.

    ## `Rational`
    * `Rational::new(num: i128, den: i128) -> Option<Rational>`: `None` for `den == 0`; otherwise reduced to lowest terms with a positive denominator
      (`new(2, -4)` is `-1/2`, `new(0, 5)` is `0/1`). `Rational::int(n)`, `num()`, `den()`, `is_zero()`.
    * `checked_add`, `checked_sub`, `checked_mul`, `checked_div`, `checked_pow(e: i32)`: `None` if the result does not fit (every intermediate
      product and sum is checked) or on division by zero (`0` to a negative power too). Rationals are `Ord` (by value).
    * `Display`: `n` when the denominator is 1, else `n/d` (`-1/2`, `3`).
    * `to_decimal(&self, places: u32) -> Option<String>`: exactly `places` decimals, rounded to nearest with halves **away from zero**; a negative value that
      rounds to zero prints without a minus sign (`-1/1000` at 2 places is `0.00`). `None` on overflow. With 0 places there is no decimal point.

    ## Units
    A *quantity* is `Quantity { value: Rational, dim: [i32; 3] }`: its value in SI base units (metre, second, kilogram) and the exponents of
    those three dimensions, in the order *length, time, mass*.

    Known units (case sensitive; the factor is the value in SI base units):

    | unit | factor | dimension |
    |---|---|---|
    | `m`, `km`, `cable`, `fathom`, `span` | 1, 1000, 926/5, 1143/625, 1143/5000 | length |
    | `s`, `min`, `h`, `tide`, `watch` | 1, 60, 3600, 44700, 14400 | time |
    | `kg`, `g`, `t`, `quintal`, `stone` | 1, 1/1000, 1000, 100, 127/20 | mass |
    | `kn` | 463/900 | length/time |
    | `N`, `J`, `W` | 1 | kg m s^-2, kg m^2 s^-2, kg m^2 s^-3 |

    ## Unit expressions
    A unit expression is one or more factors joined by `*` and `/`. A factor is a unit name (ASCII letters) optionally followed by `^` and an integer
    exponent (`^2`, `^-3`; one or two digits). Spaces are allowed around `*` and `/` only. **Each operator applies to the factor right after it**:
    `kg*m/s^2` is kg·m·s⁻², `m/s*s` is m·s⁻¹·s, `km/h/h` is km·h⁻¹·h⁻¹. The first factor is always multiplied. Anything else is `QError::Syntax`.
    The expression is read left to right; an unknown unit name is `QError::UnknownUnit(name)` as soon as the name (and its exponent) has been read.

    * `Quantity::unit(expr: &str) -> Result<Quantity, QError>`: the value of one unit of the expression, in SI (`unit("km/h")` is `5/18` m/s).

    ## Quantities
    * `Quantity::parse(s: &str) -> Result<Quantity, QError>`: optional surrounding whitespace; an optional `-`, digits, optionally `.` and digits (at most 18 decimals); then
      optional whitespace and a unit expression. A number with nothing after it is dimensionless. The decimal is exact (`3.5` is `7/2`). Errors: `Syntax`
      (no number, a lone `-` or `+`, `.5`, `1.`, ...), plus the unit expression errors, and `Overflow` when a value does not fit.
    * `convert(&self, expr: &str) -> Result<Rational, QError>`: the number of units of `expr` in this quantity; `DimMismatch` if the dimensions differ.
    * `add` / `sub(&self, other: &Quantity) -> Result<Quantity, QError>`: same dimensions required (`DimMismatch`), `Overflow` on overflow. `mul` / `div`:
      values multiply / divide and exponents add / subtract; `div` by a zero value is `DivZero`. `powi(&self, n: i32)`: `n == 0` gives `1` (dimensionless); a
      negative power of zero is `DivZero`.
    * `si_string(&self) -> String`: the value, then for each of `m`, `s`, `kg` (in this order) with a non-zero exponent a space and the name, followed by `^e` unless
      the exponent is 1: `35/36 m s^-1`, `1 m s^-2 kg`; a dimensionless quantity prints just its value.
''')

SRC = dd('''
    //! Exact quantities and harbour units.
    use std::cmp::Ordering;
    use std::fmt;

    fn gcd(a: i128, b: i128) -> i128 {
        let (mut a, mut b) = (a.abs(), b.abs());
        while b != 0 {
            let t = a % b;
            a = b;
            b = t;
        }
        a
    }

    #[derive(Debug, Clone, Copy, PartialEq, Eq)]
    pub struct Rational {
        num: i128,
        den: i128,
    }

    impl Rational {
        pub fn new(num: i128, den: i128) -> Option<Rational> {
            if den == 0 {
                return None;
            }
            let g = gcd(num, den).max(1);
            let (mut n, mut d) = (num / g, den / g);
            if d < 0 {
                n = -n;
                d = -d;
            }
            Some(Rational { num: n, den: d })
        }

        pub fn int(n: i128) -> Rational {
            Rational { num: n, den: 1 }
        }

        pub fn num(&self) -> i128 {
            self.num
        }

        pub fn den(&self) -> i128 {
            self.den
        }

        pub fn is_zero(&self) -> bool {
            self.num == 0
        }

        pub fn checked_add(self, o: Rational) -> Option<Rational> {
            let n = self.num.checked_mul(o.den)?.checked_add(o.num.checked_mul(self.den)?)?;
            Rational::new(n, self.den.checked_mul(o.den)?)
        }

        pub fn checked_sub(self, o: Rational) -> Option<Rational> {
            self.checked_add(Rational { num: o.num.checked_neg()?, den: o.den })
        }

        pub fn checked_mul(self, o: Rational) -> Option<Rational> {
            Rational::new(self.num.checked_mul(o.num)?, self.den.checked_mul(o.den)?)
        }

        pub fn checked_div(self, o: Rational) -> Option<Rational> {
            if o.num == 0 {
                return None;
            }
            Rational::new(self.num.checked_mul(o.den)?, self.den.checked_mul(o.num)?)
        }

        pub fn checked_pow(self, e: i32) -> Option<Rational> {
            let mut base = if e < 0 { Rational::int(1).checked_div(self)? } else { self };
            let mut n = e.unsigned_abs();
            let mut acc = Rational::int(1);
            while n > 0 {
                if n & 1 == 1 {
                    acc = acc.checked_mul(base)?;
                }
                n >>= 1;
                if n > 0 {
                    base = base.checked_mul(base)?;
                }
            }
            Some(acc)
        }

        pub fn to_decimal(&self, places: u32) -> Option<String> {
            let scale = 10i128.checked_pow(places)?;
            let n = self.num.checked_mul(scale)?;
            let (q, r) = (n / self.den, n % self.den);
            let mut mag = q.abs();
            if r.abs() * 2 >= self.den {
                mag += 1;
            }
            let digits = format!("{:0>width$}", mag, width = places as usize + 1);
            let split = digits.len() - places as usize;
            let body = if places == 0 { digits } else { format!("{}.{}", &digits[..split], &digits[split..]) };
            Some(if self.num < 0 && mag != 0 { format!("-{body}") } else { body })
        }
    }

    impl PartialOrd for Rational {
        fn partial_cmp(&self, other: &Rational) -> Option<Ordering> {
            Some(self.cmp(other))
        }
    }

    impl Ord for Rational {
        fn cmp(&self, other: &Rational) -> Ordering {
            (self.num * other.den).cmp(&(other.num * self.den))
        }
    }

    impl fmt::Display for Rational {
        fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
            if self.den == 1 {
                write!(f, "{}", self.num)
            } else {
                write!(f, "{}/{}", self.num, self.den)
            }
        }
    }

    #[derive(Debug, Clone, PartialEq, Eq)]
    pub enum QError {
        Syntax,
        UnknownUnit(String),
        DimMismatch,
        Overflow,
        DivZero,
    }

    pub type Dim = [i32; 3];

    #[derive(Debug, Clone, Copy, PartialEq, Eq)]
    pub struct Quantity {
        pub value: Rational,
        pub dim: Dim,
    }

    // name, numerator, denominator, dimension (length, time, mass)
    const UNITS: [(&str, i128, i128, Dim); 19] = [
        ("m", 1, 1, [1, 0, 0]),
        ("km", 1000, 1, [1, 0, 0]),
        ("cable", 926, 5, [1, 0, 0]),
        ("fathom", 1143, 625, [1, 0, 0]),
        ("span", 1143, 5000, [1, 0, 0]),
        ("s", 1, 1, [0, 1, 0]),
        ("min", 60, 1, [0, 1, 0]),
        ("h", 3600, 1, [0, 1, 0]),
        ("tide", 44700, 1, [0, 1, 0]),
        ("watch", 14400, 1, [0, 1, 0]),
        ("kg", 1, 1, [0, 0, 1]),
        ("g", 1, 1000, [0, 0, 1]),
        ("t", 1000, 1, [0, 0, 1]),
        ("quintal", 100, 1, [0, 0, 1]),
        ("stone", 127, 20, [0, 0, 1]),
        ("kn", 463, 900, [1, -1, 0]),
        ("N", 1, 1, [1, -2, 1]),
        ("J", 1, 1, [2, -2, 1]),
        ("W", 1, 1, [2, -3, 1]),
    ];

    fn lookup(name: &str) -> Result<Quantity, QError> {
        for &(n, num, den, dim) in UNITS.iter() {
            if n == name {
                let value = Rational::new(num, den).ok_or(QError::Overflow)?;
                return Ok(Quantity { value, dim });
            }
        }
        Err(QError::UnknownUnit(name.to_string()))
    }

    impl Quantity {
        pub fn unit(expr: &str) -> Result<Quantity, QError> {
            let s = expr.trim();
            if s.is_empty() {
                return Err(QError::Syntax);
            }
            let b = s.as_bytes();
            let mut i = 0;
            let mut sign = 1i32;
            let mut total = Quantity { value: Rational::int(1), dim: [0; 3] };
            loop {
                let start = i;
                while i < b.len() && b[i].is_ascii_alphabetic() {
                    i += 1;
                }
                if i == start {
                    return Err(QError::Syntax);
                }
                let name = &s[start..i];
                let mut exp = 1i32;
                if i < b.len() && b[i] == b'^' {
                    i += 1;
                    let neg = i < b.len() && b[i] == b'-';
                    if neg {
                        i += 1;
                    }
                    let digits = i;
                    while i < b.len() && b[i].is_ascii_digit() {
                        i += 1;
                    }
                    if i == digits || i - digits > 2 {
                        return Err(QError::Syntax);
                    }
                    exp = s[digits..i].parse().unwrap();
                    if neg {
                        exp = -exp;
                    }
                }
                let u = lookup(name)?;
                let power = u.powi(sign * exp)?;
                total = total.mul(&power)?;
                while i < b.len() && b[i] == b' ' {
                    i += 1;
                }
                if i >= b.len() {
                    return Ok(total);
                }
                sign = match b[i] {
                    b'*' => 1,
                    b'/' => -1,
                    _ => return Err(QError::Syntax),
                };
                i += 1;
                while i < b.len() && b[i] == b' ' {
                    i += 1;
                }
            }
        }

        pub fn parse(s: &str) -> Result<Quantity, QError> {
            let s = s.trim();
            let b = s.as_bytes();
            let mut i = 0;
            let neg = !b.is_empty() && b[0] == b'-';
            if neg {
                i += 1;
            }
            let int_start = i;
            while i < b.len() && b[i].is_ascii_digit() {
                i += 1;
            }
            if i == int_start {
                return Err(QError::Syntax);
            }
            let int_part = &s[int_start..i];
            let mut frac_part = "";
            if i < b.len() && b[i] == b'.' {
                let frac_start = i + 1;
                let mut j = frac_start;
                while j < b.len() && b[j].is_ascii_digit() {
                    j += 1;
                }
                if j == frac_start || j - frac_start > 18 {
                    return Err(QError::Syntax);
                }
                frac_part = &s[frac_start..j];
                i = j;
            }
            let mut num: i128 = int_part.parse().map_err(|_| QError::Overflow)?;
            let mut den: i128 = 1;
            for _ in 0..frac_part.len() {
                den *= 10;
            }
            if !frac_part.is_empty() {
                num = num.checked_mul(den).ok_or(QError::Overflow)?;
                num = num.checked_add(frac_part.parse::<i128>().unwrap()).ok_or(QError::Overflow)?;
            }
            if neg {
                num = -num;
            }
            let number = Rational::new(num, den).ok_or(QError::Overflow)?;
            let rest = s[i..].trim_start();
            if rest.is_empty() {
                return Ok(Quantity { value: number, dim: [0; 3] });
            }
            let unit = Quantity::unit(rest)?;
            Ok(Quantity { value: number.checked_mul(unit.value).ok_or(QError::Overflow)?, dim: unit.dim })
        }

        pub fn convert(&self, expr: &str) -> Result<Rational, QError> {
            let unit = Quantity::unit(expr)?;
            if unit.dim != self.dim {
                return Err(QError::DimMismatch);
            }
            self.value.checked_div(unit.value).ok_or(QError::Overflow)
        }

        pub fn add(&self, other: &Quantity) -> Result<Quantity, QError> {
            if self.dim != other.dim {
                return Err(QError::DimMismatch);
            }
            let value = self.value.checked_add(other.value).ok_or(QError::Overflow)?;
            Ok(Quantity { value, dim: self.dim })
        }

        pub fn sub(&self, other: &Quantity) -> Result<Quantity, QError> {
            if self.dim != other.dim {
                return Err(QError::DimMismatch);
            }
            let value = self.value.checked_sub(other.value).ok_or(QError::Overflow)?;
            Ok(Quantity { value, dim: self.dim })
        }

        pub fn mul(&self, other: &Quantity) -> Result<Quantity, QError> {
            let value = self.value.checked_mul(other.value).ok_or(QError::Overflow)?;
            let mut dim = self.dim;
            for k in 0..3 {
                dim[k] += other.dim[k];
            }
            Ok(Quantity { value, dim })
        }

        pub fn div(&self, other: &Quantity) -> Result<Quantity, QError> {
            if other.value.is_zero() {
                return Err(QError::DivZero);
            }
            let value = self.value.checked_div(other.value).ok_or(QError::Overflow)?;
            let mut dim = self.dim;
            for k in 0..3 {
                dim[k] -= other.dim[k];
            }
            Ok(Quantity { value, dim })
        }

        pub fn powi(&self, n: i32) -> Result<Quantity, QError> {
            if n < 0 && self.value.is_zero() {
                return Err(QError::DivZero);
            }
            let value = self.value.checked_pow(n).ok_or(QError::Overflow)?;
            Ok(Quantity { value, dim: [self.dim[0] * n, self.dim[1] * n, self.dim[2] * n] })
        }

        pub fn si_string(&self) -> String {
            let mut out = self.value.to_string();
            for (name, e) in ["m", "s", "kg"].iter().zip(self.dim) {
                match e {
                    0 => {}
                    1 => out.push_str(&format!(" {name}")),
                    _ => out.push_str(&format!(" {name}^{e}")),
                }
            }
            out
        }
    }
''')

VISIBLE = dd('''
    use tideunits::*;

    #[test]
    fn cable_in_metres() {
        let q = Quantity::parse("1 cable").unwrap();
        assert_eq!(q.convert("m").unwrap().to_string(), "926/5");
    }

    #[test]
    fn rational_normalises() {
        let r = Rational::new(2, -4).unwrap();
        assert_eq!((r.num(), r.den()), (-1, 2));
    }
''')

CONV = r'''
            ("1 cable", "m", "926/5", "185.2000"),
            ("1 cable", "fathom", "115750/1143", "101.2686"),
            ("1 kn", "km/h", "463/250", "1.8520"),
            ("1 fathom", "span", "8", "8.0000"),
            ("3.5 km/h", "m/s", "35/36", "0.9722"),
            ("1 tide", "h", "149/12", "12.4167"),
            ("1 tide", "min", "745", "745.0000"),
            ("2 watch", "tide", "96/149", "0.6443"),
            ("10 stone", "kg", "127/2", "63.5000"),
            ("1 quintal", "stone", "2000/127", "15.7480"),
            ("1 N", "kg*m/s^2", "1", "1.0000"),
            ("1 J", "N*m", "1", "1.0000"),
            ("1 W", "J/s", "1", "1.0000"),
            ("1 W", "kg*m^2*s^-3", "1", "1.0000"),
            ("60 kn", "cable/min", "10", "10.0000"),
            ("100 span", "m", "1143/50", "22.8600"),
            ("-2.25 fathom", "m", "-10287/2500", "-4.1148"),
            ("0.001 km", "m", "1", "1.0000"),
            ("12 kg*m^2/s^2", "J", "12", "12.0000"),
            ("5", "m/m", "5", "5.0000"),
            ("5", "m^0", "5", "5.0000"),
            ("2 m^0", "kg^0", "2", "2.0000"),
            ("1 km / h", "m / s", "5/18", "0.2778"),
            ("1 km/h/h", "m/s^2", "1/12960", "0.0001"),
            ("1 km*h/m", "s", "3600000", "3600000.0000"),
            ("9 m/s^2", "km/h^2", "116640", "116640.0000"),
            ("1 t", "quintal", "10", "10.0000"),
            ("1 g", "kg", "1/1000", "0.0010"),
            ("7 h", "watch", "7/4", "1.7500"),
            ("1 kg*m^2/s^3", "W", "1", "1.0000"),
            ("0.5 cable", "fathom", "57875/1143", "50.6343"),
            ("1 stone*km", "kg*m", "6350", "6350.0000"),
            ("1 m^-1", "km^-1", "1000", "1000.0000"),
            ("1 s^-2", "min^-2", "3600", "3600.0000"),
            ("123456789.123456789 m", "km", "123456789123456789/1000000000000", "123456.7891"),
            ("1km", "m", "1000", "1000.0000"),
            ("  2 m  ", "m", "2", "2.0000"),
            ("1 W", "kg*m^2/s^3", "1", "1.0000"),
            ("1 m^2", "km^2", "1/1000000", "0.0000"),
            ("1 km^2", "m^2", "1000000", "1000000.0000"),
            ("1 m^-2", "km^-2", "1000000", "1000000.0000"),
'''.strip("\n")

SI = r'''
            ("3.5 km/h", "35/36 m s^-1"),
            ("1 N", "1 m s^-2 kg"),
            ("5", "5"),
            ("12 kg*m^2/s^2", "12 m^2 s^-2 kg"),
            ("1 W", "1 m^2 s^-3 kg"),
            ("2 s^-1", "2 s^-1"),
            ("1 kn", "463/900 m s^-1"),
            ("-2.25 fathom", "-10287/2500 m"),
            ("1 m/m", "1"),
            ("1 tide", "44700 s"),
            ("1 J/s", "1 m^2 s^-3 kg"),
            ("1 km^2", "1000000 m^2"),
            ("3 stone/m^3", "381/20 m^-3 kg"),
            ("0.5 span*span/s^2", "1306449/50000000 m^2 s^-2"),
'''.strip("\n")

HIDDEN = dd('''
    use tideunits::*;

    fn q(s: &str) -> Quantity {
        Quantity::parse(s).unwrap_or_else(|e| panic!("parse({s:?}): {e:?}"))
    }

    fn rat(n: i128, d: i128) -> Rational {
        Rational::new(n, d).unwrap()
    }

    #[test]
    fn rational_normalisation_and_display() {
        for (n, d, want) in [(2, 4, "1/2"), (-2, -4, "1/2"), (2, -4, "-1/2"), (0, 5, "0"), (0, -5, "0"), (6, 3, "2"), (-6, 3, "-2"), (7, 1, "7"), (10, 15, "2/3")] {
            assert_eq!(rat(n, d).to_string(), want, "{n}/{d}");
        }
        assert_eq!(Rational::new(1, 0), None);
        assert_eq!(Rational::new(0, 0), None);
        let r = rat(-9, 12);
        assert_eq!((r.num(), r.den()), (-3, 4));
        let z = rat(0, -7);
        assert_eq!((z.num(), z.den()), (0, 1));
        assert!(z.is_zero());
        assert!(!rat(1, 100).is_zero());
        assert_eq!(Rational::int(-5).to_string(), "-5");
    }

    #[test]
    fn rational_arithmetic() {
        assert_eq!(rat(1, 2).checked_add(rat(1, 3)), Some(rat(5, 6)));
        assert_eq!(rat(1, 2).checked_sub(rat(1, 3)), Some(rat(1, 6)));
        assert_eq!(rat(1, 3).checked_sub(rat(1, 2)), Some(rat(-1, 6)));
        assert_eq!(rat(2, 3).checked_mul(rat(3, 4)), Some(rat(1, 2)));
        assert_eq!(rat(2, 3).checked_div(rat(4, 9)), Some(rat(3, 2)));
        assert_eq!(rat(2, 3).checked_div(rat(-4, 9)), Some(rat(-3, 2)));
        assert_eq!(rat(2, 3).checked_div(rat(0, 1)), None);
        assert_eq!(rat(1, 2).checked_add(rat(-1, 2)), Some(rat(0, 1)));
        assert_eq!(rat(7, 3).checked_sub(rat(7, 3)).unwrap().to_string(), "0");
        assert_eq!(rat(i128::MAX, 1).checked_add(rat(1, 1)), None);
        assert_eq!(rat(i128::MAX, 1).checked_mul(rat(2, 1)), None);
        assert_eq!(rat(i128::MAX, 1).checked_sub(rat(-1, 1)), None);
        assert_eq!(rat(1, i128::MAX).checked_mul(rat(1, 2)), None);
        assert_eq!(rat(5, 1).checked_sub(rat(i128::MIN + 1, 1)), None);
    }

    #[test]
    fn rational_powers() {
        assert_eq!(rat(2, 3).checked_pow(0), Some(rat(1, 1)));
        assert_eq!(rat(2, 3).checked_pow(1), Some(rat(2, 3)));
        assert_eq!(rat(2, 3).checked_pow(3), Some(rat(8, 27)));
        assert_eq!(rat(2, 3).checked_pow(-3), Some(rat(27, 8)));
        assert_eq!(rat(-2, 1).checked_pow(5), Some(rat(-32, 1)));
        assert_eq!(rat(-2, 1).checked_pow(4), Some(rat(16, 1)));
        assert_eq!(rat(-1, 2).checked_pow(-3), Some(rat(-8, 1)));
        assert_eq!(rat(0, 1).checked_pow(0), Some(rat(1, 1)));
        assert_eq!(rat(0, 1).checked_pow(3), Some(rat(0, 1)));
        assert_eq!(rat(0, 1).checked_pow(-1), None);
        assert_eq!(rat(1, 1).checked_pow(i32::MAX), Some(rat(1, 1)));
        assert_eq!(rat(10, 1).checked_pow(38), Some(rat(10i128.pow(38), 1)));
        assert_eq!(rat(10, 1).checked_pow(39), None);
        assert_eq!(rat(1000, 1).checked_pow(12), Some(rat(10i128.pow(36), 1)));
        assert_eq!(rat(1000, 1).checked_pow(13), None);
        assert_eq!(rat(1000, 1).checked_pow(-13), None);
        assert_eq!(rat(3, 1).checked_pow(80), Some(rat(3i128.pow(80), 1)));
        assert_eq!(rat(3, 1).checked_pow(81), None);
    }

    #[test]
    fn rational_order() {
        assert!(rat(1, 3) < rat(1, 2));
        assert!(rat(-1, 2) < rat(-1, 3));
        assert!(rat(2, 4) == rat(1, 2));
        assert!(rat(5, 1) > rat(49, 10));
        assert!(rat(-1, 1) < rat(0, 1));
        assert_eq!(rat(7, 3).cmp(&rat(7, 3)), std::cmp::Ordering::Equal);
        let mut v = vec![rat(1, 2), rat(-3, 4), rat(2, 3), rat(0, 1), rat(-1, 8)];
        v.sort();
        assert_eq!(v, [rat(-3, 4), rat(-1, 8), rat(0, 1), rat(1, 2), rat(2, 3)]);
    }

    #[test]
    fn decimal_rounding() {
        let cases = [
            (1, 3, 4, "0.3333"), (2, 3, 4, "0.6667"), (-2, 3, 4, "-0.6667"), (1, 2, 0, "1"), (-1, 2, 0, "-1"), (3, 2, 0, "2"), (5, 1000, 2, "0.01"),
            (-5, 1000, 2, "-0.01"), (4, 1000, 2, "0.00"), (-4, 1000, 2, "0.00"), (123456, 1, 0, "123456"), (0, 5, 3, "0.000"), (7, 4, 1, "1.8"),
            (-7, 4, 1, "-1.8"), (1, 8, 2, "0.13"), (1, 8, 3, "0.125"), (99, 100, 1, "1.0"), (999, 1000, 2, "1.00"), (-999, 1000, 2, "-1.00"),
            (10, 1, 2, "10.00"), (1, 1, 0, "1"), (1, 3, 0, "0"), (-1, 3, 0, "0"), (2, 3, 0, "1"), (5, 2, 0, "3"), (-5, 2, 0, "-3"), (12345, 100, 1, "123.5"),
        ];
        for (n, d, p, want) in cases {
            assert_eq!(rat(n, d).to_decimal(p).as_deref(), Some(want), "{n}/{d} at {p}");
        }
        assert_eq!(rat(i128::MAX, 1).to_decimal(2), None);
        assert_eq!(rat(1, 3).to_decimal(40), None);
        assert!(rat(1, 3).to_decimal(18).is_some());
    }

    #[test]
    fn conversions() {
        let cases: &[(&str, &str, &str, &str)] = &[
''') + CONV + "\n" + dd('''
        ];
        for &(from, to, exact, dec) in cases {
            let r = q(from).convert(to).unwrap_or_else(|e| panic!("{from:?} -> {to:?}: {e:?}"));
            assert_eq!(r.to_string(), exact, "{from} -> {to}");
            assert_eq!(r.to_decimal(4).unwrap(), dec, "{from} -> {to} decimal");
        }
    }

    #[test]
    fn si_strings() {
        let cases: &[(&str, &str)] = &[
''') + SI + "\n" + dd('''
        ];
        for &(text, want) in cases {
            assert_eq!(q(text).si_string(), want, "{text}");
        }
    }

    #[test]
    fn unit_values() {
        assert_eq!(Quantity::unit("km/h").unwrap().si_string(), "5/18 m s^-1");
        assert_eq!(Quantity::unit("kn").unwrap().value, rat(463, 900));
        assert_eq!(Quantity::unit("tide").unwrap().value, rat(44700, 1));
        assert_eq!(Quantity::unit("m/s*s").unwrap().si_string(), "1 m");
        assert_eq!(Quantity::unit("  m / s  ").unwrap().dim, [1, -1, 0]);
        assert_eq!(Quantity::unit("watch^2").unwrap().value, rat(14400 * 14400, 1));
        assert_eq!(Quantity::unit("m^-1").unwrap().dim, [-1, 0, 0]);
        assert_eq!(Quantity::unit("kg^0").unwrap().si_string(), "1");
        assert_eq!(Quantity::unit("W").unwrap().dim, [2, -3, 1]);
    }

    #[test]
    fn dimension_checks() {
        assert_eq!(q("1 km").convert("kg"), Err(QError::DimMismatch));
        assert_eq!(q("1 km").convert("km/h"), Err(QError::DimMismatch));
        assert_eq!(q("1 km").convert("km^2"), Err(QError::DimMismatch));
        assert_eq!(q("5").convert("m"), Err(QError::DimMismatch));
        assert_eq!(q("1 N").convert("J"), Err(QError::DimMismatch));
        assert_eq!(q("1 km").convert("furlong"), Err(QError::UnknownUnit("furlong".into())));
        assert_eq!(q("1 km").convert(""), Err(QError::Syntax));
    }

    #[test]
    fn addition_and_subtraction() {
        let sum = q("1 fathom").add(&q("2 span")).unwrap();
        assert_eq!(sum.si_string(), "1143/500 m");
        assert_eq!(sum.convert("span").unwrap().to_string(), "10");
        let diff = q("1 fathom").sub(&q("2 span")).unwrap();
        assert_eq!(diff.convert("span").unwrap().to_string(), "6");
        let neg = q("2 span").sub(&q("1 fathom")).unwrap();
        assert_eq!(neg.convert("span").unwrap().to_string(), "-6");
        assert_eq!(q("1 m").add(&q("1 s")), Err(QError::DimMismatch));
        assert_eq!(q("1 m").sub(&q("1 s")), Err(QError::DimMismatch));
        assert_eq!(q("1 m").add(&q("-1 m")).unwrap().si_string(), "0 m");
        assert_eq!(q("2").add(&q("3")).unwrap().si_string(), "5");
    }

    #[test]
    fn multiplication_and_division() {
        assert_eq!(q("2 m").mul(&q("3 s")).unwrap().si_string(), "6 m s");
        assert_eq!(q("6 m").div(&q("3 s")).unwrap().si_string(), "2 m s^-1");
        assert_eq!(q("6 m").div(&q("3 m")).unwrap().si_string(), "2");
        assert_eq!(q("2 kg").mul(&q("5 m/s")).unwrap().si_string(), "10 m s^-1 kg");
        assert_eq!(q("1 kg*m/s^2").div(&q("1 N")).unwrap().si_string(), "1");
        assert_eq!(q("3 m").div(&q("0 s")), Err(QError::DivZero));
        assert_eq!(q("0 m").div(&q("3 s")).unwrap().si_string(), "0 m s^-1");
        let speed = q("12 km").div(&q("2 h")).unwrap();
        assert_eq!(speed.convert("kn").unwrap().to_decimal(3).unwrap(), "3.240");
        assert_eq!(speed.convert("m/s").unwrap().to_string(), "5/3");
    }

    #[test]
    fn integer_powers() {
        assert_eq!(q("2 m").powi(3).unwrap().si_string(), "8 m^3");
        assert_eq!(q("2 m").powi(-1).unwrap().si_string(), "1/2 m^-1");
        assert_eq!(q("2 m/s").powi(2).unwrap().si_string(), "4 m^2 s^-2");
        assert_eq!(q("2 m").powi(0).unwrap().si_string(), "1");
        assert_eq!(q("0 m").powi(0).unwrap().si_string(), "1");
        assert_eq!(q("0 m").powi(2).unwrap().si_string(), "0 m^2");
        assert_eq!(q("0 m").powi(-2), Err(QError::DivZero));
        assert_eq!(q("1000 m").powi(20), Err(QError::Overflow));
    }

    #[test]
    fn exact_decimals() {
        assert_eq!(q("0.1 m").add(&q("0.2 m")).unwrap().convert("m").unwrap().to_string(), "3/10");
        assert_eq!(q("0.001 km").convert("m").unwrap().to_string(), "1");
        assert_eq!(q("-0.5 m").value, rat(-1, 2));
        assert_eq!(q("007.50 m").value, rat(15, 2));
        assert_eq!(q("1.123456789012345678 m").value, rat(1123456789012345678, 1_000_000_000_000_000_000));
        assert_eq!(q("-0 m").si_string(), "0 m");
    }

    #[test]
    fn syntax_errors() {
        for bad in [
            "", "  ", "km", "-", "- 5", "5 km h", "5 km^", "5 km^x", "5 km^-", "5 km^100", "5 km**h", "5 */h", "5 km/", "5 /h", "5 km^2^2", "1.5.2 m",
            "1. m", ".5 m", "5 km/ /h", "+5 m", "5 m,s", "5 m^ 2", "5 m ^2", "1.1234567890123456789 m", "5 m/", "1.", "12.", " 1. ", "-3.",
        ] {
            assert_eq!(Quantity::parse(bad), Err(QError::Syntax), "{bad:?}");
        }
        for (bad, name) in [("5 foo", "foo"), ("5 Km", "Km"), ("5 M", "M"), ("5 KG", "KG"), ("5 m/furlong", "furlong"), ("5 km^2*bar", "bar")] {
            assert_eq!(Quantity::parse(bad), Err(QError::UnknownUnit(name.to_string())), "{bad:?}");
        }
    }

    #[test]
    fn overflow_is_reported() {
        assert_eq!(Quantity::parse("1 km^20"), Err(QError::Overflow));
        assert_eq!(Quantity::parse("5 km^-99"), Err(QError::Overflow));
        assert_eq!(Quantity::parse("999999999999999999999999999999999999999 m"), Err(QError::Overflow));
        assert!(Quantity::parse("5 m^-99").is_ok());
        assert!(Quantity::parse("100000000000000000000000000000000000000 m").is_ok());
        assert_eq!(q("100000000000000000000000000000000000000 m").mul(&q("100 m")), Err(QError::Overflow));
        assert_eq!(q("100000000000000000000000000000000000000 m").add(&q("100000000000000000000000000000000000000 m")), Err(QError::Overflow));
    }

    #[test]
    fn whitespace_rules() {
        assert_eq!(q("  2   m  ").si_string(), "2 m");
        assert_eq!(q("2m").si_string(), "2 m");
        assert_eq!(q("2 km / h").si_string(), "5/9 m s^-1");
        assert_eq!(q("2 km*h").si_string(), "7200000 m s");
        assert_eq!(q("2 km /h").si_string(), "5/9 m s^-1");
        assert_eq!(q("\\t3 m\\n").si_string(), "3 m");
    }
''')

LIB = Lib(
    name="tideunits", lang="rust", title="the tideunits crate",
    blurb="The harbour master's tools convert cables, fathoms, knots and tides with tideunits, which does exact rational arithmetic with dimension checking.",
    files={"Cargo.toml": cargo("tideunits"), "src/lib.rs": SRC, "README.md": README, ".gitignore": "target/\n", ".cargo/config.toml": CARGO_CONFIG},
    visible_tests={"tests/basic.rs": VISIBLE},
    hidden_tests={"tests/full.rs": HIDDEN},
    mutate=["src/lib.rs"], difficulty=4, tags=["units", "rational", "parsing"],
)

register_libs([LIB], n=8)

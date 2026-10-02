"""Hardware register fields (rust): RW/RO/W1C/W1S/read-clear semantics, validation, field insertion and display."""
from fx import Lib, dd

from generators.fix._lang1 import CARGO_CONFIG, cargo, register_libs

README = dd('''
    # regmap

    A software model of memory-mapped device registers for the firmware simulator. A `RegSpec` describes the bit fields of one
    register and what a bus access does to each of them.

    ```rust
    pub enum Access { Rw, Ro, W1c, W1s, Rc }
    pub struct Field { pub name: String, pub lsb: u32, pub width: u32, pub access: Access, pub reset: u64 }
    ```

    ## `RegSpec::new(width: u32, fields: Vec<Field>) -> Result<RegSpec, SpecError>`
    `width` is the register width in bits: 8, 16, 32 or 64, otherwise `Err(SpecError::BadWidth)`. Fields are checked in the order given, and for each
    field in this order:

    1. `width >= 1` and `lsb + width <= register width`, else `FieldOutOfRange(name)`;
    2. `reset` fits in `width` bits, else `ResetTooWide(name)`;
    3. the name is not used by an earlier field, else `DuplicateName(name)`;
    4. the bits do not overlap an earlier field, else `Overlap(earlier_name, name)`.

    Bits not covered by any field are *reserved*.

    ## Bus semantics
    * `reset_value(&self) -> u64`: every field's `reset` placed at its position; reserved bits are 0.
    * `apply_write(&self, old: u64, written: u64) -> u64`: the register after a bus write of `written` over the stored value `old`.
      Each field behaves according to its access, reserved bits keep their old value, and the result never has bits above the
      register width:
      * `Rw`: takes the written bits;
      * `Ro`: ignores the write;
      * `W1c` (write one to clear): a written 1 clears the bit, a written 0 leaves it;
      * `W1s` (write one to set): a written 1 sets the bit, a written 0 leaves it;
      * `Rc` (clear on read): ignores writes.
    * `read(&self, stored: u64) -> (u64, u64)`: a bus read. Returns `(seen, after)`: `seen` is the stored value with reserved bits
      shown as 0 (all field bits are visible, whatever their access); `after` is the stored value with every `Rc` field cleared.
      Bits above the register width are dropped from both.

    ## Field helpers
    * `mask(&self, name: &str) -> Option<u64>`: the field's bits in place (`None` for an unknown name).
    * `get(&self, reg: u64, name: &str) -> Option<u64>`: the field's value, shifted down to bit 0.
    * `with_field(&self, reg: u64, name: &str, value: u64) -> Result<u64, SpecError>`: `reg` with that field replaced, ignoring its access
      (this is how the *device* updates its own status bits). `Err(UnknownField(name))`, or `Err(ValueTooWide(name))` if `value` does not fit
      in the field.
    * `describe(&self, reg: u64) -> String`: `NAME=0x<hex>` for every field, most significant field first, separated by single spaces
      (lower-case hex without padding, `0x0` for zero).
''')

SRC = dd('''
    //! Register field model.

    #[derive(Debug, Clone, Copy, PartialEq, Eq)]
    pub enum Access {
        Rw,
        Ro,
        W1c,
        W1s,
        Rc,
    }

    #[derive(Debug, Clone, PartialEq, Eq)]
    pub struct Field {
        pub name: String,
        pub lsb: u32,
        pub width: u32,
        pub access: Access,
        pub reset: u64,
    }

    #[derive(Debug, Clone, PartialEq, Eq)]
    pub enum SpecError {
        BadWidth,
        FieldOutOfRange(String),
        ResetTooWide(String),
        DuplicateName(String),
        Overlap(String, String),
        UnknownField(String),
        ValueTooWide(String),
    }

    #[derive(Debug, Clone)]
    pub struct RegSpec {
        width: u32,
        fields: Vec<Field>,
    }

    fn low_mask(bits: u32) -> u64 {
        if bits >= 64 {
            u64::MAX
        } else {
            (1u64 << bits) - 1
        }
    }

    impl Field {
        fn place(&self) -> u64 {
            low_mask(self.width) << self.lsb
        }
    }

    impl RegSpec {
        pub fn new(width: u32, fields: Vec<Field>) -> Result<RegSpec, SpecError> {
            if !matches!(width, 8 | 16 | 32 | 64) {
                return Err(SpecError::BadWidth);
            }
            for (i, f) in fields.iter().enumerate() {
                if f.width < 1 || f.lsb + f.width > width {
                    return Err(SpecError::FieldOutOfRange(f.name.clone()));
                }
                if f.reset > low_mask(f.width) {
                    return Err(SpecError::ResetTooWide(f.name.clone()));
                }
                for earlier in &fields[..i] {
                    if earlier.name == f.name {
                        return Err(SpecError::DuplicateName(f.name.clone()));
                    }
                }
                for earlier in &fields[..i] {
                    if earlier.place() & f.place() != 0 {
                        return Err(SpecError::Overlap(earlier.name.clone(), f.name.clone()));
                    }
                }
            }
            Ok(RegSpec { width, fields })
        }

        fn reg_mask(&self) -> u64 {
            low_mask(self.width)
        }

        fn field(&self, name: &str) -> Option<&Field> {
            self.fields.iter().find(|f| f.name == name)
        }

        pub fn reset_value(&self) -> u64 {
            self.fields.iter().fold(0, |acc, f| acc | (f.reset << f.lsb))
        }

        pub fn apply_write(&self, old: u64, written: u64) -> u64 {
            let mut new = old & self.reg_mask();
            let written = written & self.reg_mask();
            for f in &self.fields {
                let m = f.place();
                match f.access {
                    Access::Rw => new = (new & !m) | (written & m),
                    Access::W1c => new &= !(written & m),
                    Access::W1s => new |= written & m,
                    Access::Ro | Access::Rc => {}
                }
            }
            new
        }

        pub fn read(&self, stored: u64) -> (u64, u64) {
            let stored = stored & self.reg_mask();
            let covered = self.fields.iter().fold(0, |acc, f| acc | f.place());
            let mut after = stored;
            for f in &self.fields {
                if f.access == Access::Rc {
                    after &= !f.place();
                }
            }
            (stored & covered, after)
        }

        pub fn mask(&self, name: &str) -> Option<u64> {
            self.field(name).map(|f| f.place())
        }

        pub fn get(&self, reg: u64, name: &str) -> Option<u64> {
            self.field(name).map(|f| (reg >> f.lsb) & low_mask(f.width))
        }

        pub fn with_field(&self, reg: u64, name: &str, value: u64) -> Result<u64, SpecError> {
            let f = self.field(name).ok_or_else(|| SpecError::UnknownField(name.to_string()))?;
            if value > low_mask(f.width) {
                return Err(SpecError::ValueTooWide(name.to_string()));
            }
            Ok(((reg & !f.place()) | (value << f.lsb)) & self.reg_mask())
        }

        pub fn describe(&self, reg: u64) -> String {
            let mut order: Vec<&Field> = self.fields.iter().collect();
            order.sort_by(|a, b| b.lsb.cmp(&a.lsb));
            order
                .iter()
                .map(|f| format!("{}={:#x}", f.name, (reg >> f.lsb) & low_mask(f.width)))
                .collect::<Vec<_>>()
                .join(" ")
        }
    }
''')

VISIBLE = dd('''
    use regmap::*;

    fn field(name: &str, lsb: u32, width: u32, access: Access, reset: u64) -> Field {
        Field { name: name.to_string(), lsb, width, access, reset }
    }

    #[test]
    fn rw_field_takes_writes() {
        let spec = RegSpec::new(8, vec![field("EN", 0, 1, Access::Rw, 0)]).unwrap();
        assert_eq!(spec.apply_write(0, 1), 1);
    }

    #[test]
    fn width_must_be_standard() {
        assert_eq!(RegSpec::new(12, vec![]).unwrap_err(), SpecError::BadWidth);
    }
''')

HIDDEN = dd('''
    use regmap::*;

    fn field(name: &str, lsb: u32, width: u32, access: Access, reset: u64) -> Field {
        Field { name: name.to_string(), lsb, width, access, reset }
    }

    // 16-bit UART status/control register; bits 7 and 12..15 are reserved
    fn uart() -> RegSpec {
        RegSpec::new(
            16,
            vec![
                field("EN", 0, 1, Access::Rw, 0),
                field("MODE", 1, 3, Access::Rw, 0b010),
                field("BUSY", 4, 1, Access::Ro, 1),
                field("OVR", 5, 1, Access::W1c, 0),
                field("IRQ", 6, 1, Access::W1s, 0),
                field("RXCNT", 8, 4, Access::Rc, 0),
            ],
        )
        .unwrap()
    }

    #[test]
    fn width_validation() {
        for w in [0, 1, 7, 9, 12, 24, 48, 65, 128] {
            assert_eq!(RegSpec::new(w, vec![]).unwrap_err(), SpecError::BadWidth, "width {w}");
        }
        for w in [8, 16, 32, 64] {
            assert!(RegSpec::new(w, vec![]).is_ok(), "width {w}");
        }
    }

    #[test]
    fn field_range_validation() {
        let err = |f: Field, w: u32| RegSpec::new(w, vec![f]).unwrap_err();
        assert_eq!(err(field("A", 0, 0, Access::Rw, 0), 8), SpecError::FieldOutOfRange("A".into()));
        assert_eq!(err(field("A", 8, 1, Access::Rw, 0), 8), SpecError::FieldOutOfRange("A".into()));
        assert_eq!(err(field("A", 4, 5, Access::Rw, 0), 8), SpecError::FieldOutOfRange("A".into()));
        assert_eq!(err(field("A", 0, 17, Access::Rw, 0), 16), SpecError::FieldOutOfRange("A".into()));
        assert_eq!(err(field("A", 63, 2, Access::Rw, 0), 64), SpecError::FieldOutOfRange("A".into()));
        assert!(RegSpec::new(8, vec![field("A", 7, 1, Access::Rw, 0)]).is_ok());
        assert!(RegSpec::new(8, vec![field("A", 4, 4, Access::Rw, 0)]).is_ok());
        assert!(RegSpec::new(8, vec![field("A", 0, 8, Access::Rw, 0)]).is_ok());
        assert!(RegSpec::new(64, vec![field("A", 0, 64, Access::Rw, 0)]).is_ok());
        assert!(RegSpec::new(64, vec![field("A", 63, 1, Access::Rw, 1)]).is_ok());
    }

    #[test]
    fn reset_validation() {
        let err = |f: Field| RegSpec::new(16, vec![f]).unwrap_err();
        assert_eq!(err(field("A", 0, 3, Access::Rw, 8)), SpecError::ResetTooWide("A".into()));
        assert_eq!(err(field("A", 0, 1, Access::Rw, 2)), SpecError::ResetTooWide("A".into()));
        assert!(RegSpec::new(16, vec![field("A", 0, 3, Access::Rw, 7)]).is_ok());
        assert!(RegSpec::new(64, vec![field("A", 0, 64, Access::Rw, u64::MAX)]).is_ok());
    }

    #[test]
    fn duplicate_and_overlap_validation() {
        let dup = RegSpec::new(8, vec![field("A", 0, 1, Access::Rw, 0), field("A", 4, 1, Access::Rw, 0)]).unwrap_err();
        assert_eq!(dup, SpecError::DuplicateName("A".into()));
        let ov = RegSpec::new(8, vec![field("LOW", 0, 4, Access::Rw, 0), field("MID", 3, 3, Access::Ro, 0)]).unwrap_err();
        assert_eq!(ov, SpecError::Overlap("LOW".into(), "MID".into()));
        let ov = RegSpec::new(8, vec![field("HI", 4, 4, Access::Rw, 0), field("ALL", 0, 8, Access::Ro, 0)]).unwrap_err();
        assert_eq!(ov, SpecError::Overlap("HI".into(), "ALL".into()));
        // adjacent fields are fine
        assert!(RegSpec::new(8, vec![field("LOW", 0, 4, Access::Rw, 0), field("HIGH", 4, 4, Access::Rw, 0)]).is_ok());
        // a field that overlaps the second of three names the overlapping one
        let ov = RegSpec::new(
            16,
            vec![field("A", 0, 2, Access::Rw, 0), field("B", 4, 2, Access::Rw, 0), field("C", 5, 2, Access::Rw, 0)],
        )
        .unwrap_err();
        assert_eq!(ov, SpecError::Overlap("B".into(), "C".into()));
    }

    #[test]
    fn validation_order_for_one_field() {
        // out of range wins over a too-wide reset
        let e = RegSpec::new(8, vec![field("A", 6, 4, Access::Rw, 99)]).unwrap_err();
        assert_eq!(e, SpecError::FieldOutOfRange("A".into()));
        // a too-wide reset wins over a duplicate name
        let e = RegSpec::new(8, vec![field("A", 0, 1, Access::Rw, 0), field("A", 1, 1, Access::Rw, 5)]).unwrap_err();
        assert_eq!(e, SpecError::ResetTooWide("A".into()));
        // a duplicate name wins over an overlap
        let e = RegSpec::new(8, vec![field("A", 0, 4, Access::Rw, 0), field("A", 2, 4, Access::Rw, 0)]).unwrap_err();
        assert_eq!(e, SpecError::DuplicateName("A".into()));
    }

    #[test]
    fn reset_value_places_each_field() {
        // MODE=0b010 at bit 1 -> 0x04, BUSY=1 at bit 4 -> 0x10
        assert_eq!(uart().reset_value(), 0x14);
        let big = RegSpec::new(64, vec![field("TOP", 60, 4, Access::Ro, 0xA), field("LOW", 0, 8, Access::Rw, 0x5C)]).unwrap();
        assert_eq!(big.reset_value(), 0xA000_0000_0000_005C);
        assert_eq!(RegSpec::new(8, vec![]).unwrap().reset_value(), 0);
    }

    #[test]
    fn rw_fields_take_written_bits() {
        let u = uart();
        // write EN=1, MODE=0b101 with every other bit zero
        let v = u.apply_write(0x14, 0b0000_1011);
        assert_eq!(u.get(v, "EN"), Some(1));
        assert_eq!(u.get(v, "MODE"), Some(0b101));
        // clearing: write zeros over RW fields
        let v = u.apply_write(0x0F, 0);
        assert_eq!(v & 0x0F, 0);
    }

    #[test]
    fn ro_and_rc_ignore_writes() {
        let u = uart();
        let v = u.apply_write(0x0000, 0xFFFF);
        assert_eq!(u.get(v, "BUSY"), Some(0));
        assert_eq!(u.get(v, "RXCNT"), Some(0));
        let v = u.apply_write(0x0F10, 0x0000);
        assert_eq!(u.get(v, "BUSY"), Some(1));
        assert_eq!(u.get(v, "RXCNT"), Some(0xF));
    }

    #[test]
    fn w1c_and_w1s() {
        let u = uart();
        // OVR (bit 5) set in the stored value: writing 0 keeps it, writing 1 clears it
        assert_eq!(u.get(u.apply_write(0x20, 0x00), "OVR"), Some(1));
        assert_eq!(u.get(u.apply_write(0x20, 0x20), "OVR"), Some(0));
        assert_eq!(u.get(u.apply_write(0x00, 0x20), "OVR"), Some(0));
        // IRQ (bit 6) W1S: writing 1 sets it, writing 0 never clears it
        assert_eq!(u.get(u.apply_write(0x00, 0x40), "IRQ"), Some(1));
        assert_eq!(u.get(u.apply_write(0x40, 0x00), "IRQ"), Some(1));
        assert_eq!(u.get(u.apply_write(0x40, 0x40), "IRQ"), Some(1));
        // other fields are untouched by those writes
        assert_eq!(u.apply_write(0x2F, 0x20) & 0x0F, 0x00);
    }

    #[test]
    fn reserved_bits_keep_their_value() {
        let u = uart();
        // bit 7 and bits 12..15 are reserved
        let old = 0xF080;
        assert_eq!(u.apply_write(old, 0x0000), 0xF080);
        assert_eq!(u.apply_write(old, 0xFFFF) & 0xF080, 0xF080);
        assert_eq!(u.apply_write(0x0000, 0xF080), 0x0000);
    }

    #[test]
    fn writes_are_masked_to_the_register_width() {
        let r = RegSpec::new(8, vec![field("ALL", 0, 8, Access::Rw, 0)]).unwrap();
        assert_eq!(r.apply_write(0, 0x1FF), 0xFF);
        assert_eq!(r.apply_write(0xFFFF_FF00, 0x12), 0x12);
        let w = RegSpec::new(8, vec![field("HI", 4, 4, Access::W1s, 0)]).unwrap();
        assert_eq!(w.apply_write(0x1234, 0xFF), 0x34 | 0xF0);
        let c = RegSpec::new(8, vec![field("ALL", 0, 8, Access::W1c, 0)]).unwrap();
        assert_eq!(c.apply_write(0xFFFF, 0x0F), 0xF0);
    }

    #[test]
    fn full_width_register() {
        let r = RegSpec::new(64, vec![field("TOP", 63, 1, Access::W1c, 0), field("BODY", 0, 63, Access::Rw, 0)]).unwrap();
        assert_eq!(r.apply_write(u64::MAX, (1 << 63) | 0x5), 0x5);
        assert_eq!(r.apply_write(u64::MAX, 0), 0x8000_0000_0000_0000);
        assert_eq!(r.apply_write(0, u64::MAX), u64::MAX >> 1);
        assert_eq!(r.mask("BODY"), Some(u64::MAX >> 1));
        assert_eq!(r.mask("TOP"), Some(1 << 63));
        assert_eq!(r.get(u64::MAX, "BODY"), Some(u64::MAX >> 1));
        assert_eq!(r.with_field(0, "TOP", 1), Ok(1 << 63));
        let whole = RegSpec::new(64, vec![field("W", 0, 64, Access::Rw, 0)]).unwrap();
        assert_eq!(whole.mask("W"), Some(u64::MAX));
        assert_eq!(whole.with_field(5, "W", u64::MAX), Ok(u64::MAX));
    }

    #[test]
    fn reads_clear_rc_fields_and_hide_reserved_bits() {
        let u = uart();
        let stored = 0xF3B5; // reserved bits set, RXCNT = 3, OVR = 1, IRQ = 0, BUSY = 1, MODE = 0b010, EN = 1
        let (seen, after) = u.read(stored);
        assert_eq!(seen, 0x0335);
        assert_eq!(after, 0xF0B5);
        // a register without Rc fields reads back unchanged
        let plain = RegSpec::new(8, vec![field("A", 0, 4, Access::Rw, 0)]).unwrap();
        assert_eq!(plain.read(0xFA), (0x0A, 0xFA));
        // everything else about the stored value survives the clearing
        assert_eq!(u.read(0x0F00), (0x0F00, 0x0000));
        assert_eq!(u.read(0x1F00), (0x0F00, 0x1000));
    }

    #[test]
    fn reads_drop_bits_above_the_width() {
        let r = RegSpec::new(8, vec![field("A", 0, 4, Access::Rc, 0), field("B", 4, 4, Access::Rw, 0)]).unwrap();
        assert_eq!(r.read(0xFFFF_12AB), (0xAB, 0xA0));
    }

    #[test]
    fn mask_and_get() {
        let u = uart();
        assert_eq!(u.mask("EN"), Some(0x0001));
        assert_eq!(u.mask("MODE"), Some(0x000E));
        assert_eq!(u.mask("BUSY"), Some(0x0010));
        assert_eq!(u.mask("RXCNT"), Some(0x0F00));
        assert_eq!(u.mask("NOPE"), None);
        assert_eq!(u.get(0x0F5A, "RXCNT"), Some(0xF));
        assert_eq!(u.get(0x0F5A, "MODE"), Some(0b101));
        assert_eq!(u.get(0x0F5A, "OVR"), Some(0));
        assert_eq!(u.get(0x0F5A, "IRQ"), Some(1));
        assert_eq!(u.get(0x0F5A, "BUSY"), Some(1));
        assert_eq!(u.get(0x0F5A, "EN"), Some(0));
        assert_eq!(u.get(0x0F5A, "NOPE"), None);
    }

    #[test]
    fn with_field_ignores_access_and_checks_width() {
        let u = uart();
        assert_eq!(u.with_field(0, "BUSY", 1), Ok(0x10));
        assert_eq!(u.with_field(0x10, "BUSY", 0), Ok(0x00));
        assert_eq!(u.with_field(0, "RXCNT", 9), Ok(0x0900));
        assert_eq!(u.with_field(0xFFFF, "MODE", 0), Ok(0xFFF1));
        assert_eq!(u.with_field(0x0F00, "RXCNT", 2), Ok(0x0200));
        assert_eq!(u.with_field(0, "MODE", 7), Ok(0x0E));
        assert_eq!(u.with_field(0, "MODE", 8), Err(SpecError::ValueTooWide("MODE".into())));
        assert_eq!(u.with_field(0, "EN", 2), Err(SpecError::ValueTooWide("EN".into())));
        assert_eq!(u.with_field(0, "NOPE", 0), Err(SpecError::UnknownField("NOPE".into())));
        // unknown field is reported before the value is looked at
        assert_eq!(u.with_field(0, "NOPE", 999), Err(SpecError::UnknownField("NOPE".into())));
        // the result never exceeds the register width
        let r = RegSpec::new(8, vec![field("A", 0, 8, Access::Rw, 0)]).unwrap();
        assert_eq!(r.with_field(0xFFFF_FF00, "A", 0x12), Ok(0x12));
    }

    #[test]
    fn describe_lists_fields_from_the_top() {
        let u = uart();
        assert_eq!(u.describe(0x0F5A), "RXCNT=0xf IRQ=0x1 OVR=0x0 BUSY=0x1 MODE=0x5 EN=0x0");
        assert_eq!(u.describe(0), "RXCNT=0x0 IRQ=0x0 OVR=0x0 BUSY=0x0 MODE=0x0 EN=0x0");
        assert_eq!(u.describe(u.reset_value()), "RXCNT=0x0 IRQ=0x0 OVR=0x0 BUSY=0x1 MODE=0x2 EN=0x0");
        // declaration order does not matter, the position does
        let r = RegSpec::new(8, vec![field("LO", 0, 4, Access::Rw, 0), field("HI", 4, 4, Access::Rw, 0)]).unwrap();
        assert_eq!(r.describe(0xA5), "HI=0xa LO=0x5");
        // reserved bits are not shown
        assert_eq!(u.describe(0xF080), "RXCNT=0x0 IRQ=0x0 OVR=0x0 BUSY=0x0 MODE=0x0 EN=0x0");
    }

    #[test]
    fn typical_driver_sequence() {
        let u = uart();
        let mut reg = u.reset_value();
        reg = u.apply_write(reg, 0x0001); // enable
        // BUSY is read-only and keeps its reset value, MODE was overwritten with zeros
        assert_eq!(u.describe(reg), "RXCNT=0x0 IRQ=0x0 OVR=0x0 BUSY=0x1 MODE=0x0 EN=0x1");
        // the device receives 5 bytes and overruns
        reg = u.with_field(reg, "RXCNT", 5).unwrap();
        reg = u.with_field(reg, "OVR", 1).unwrap();
        reg = u.with_field(reg, "BUSY", 1).unwrap();
        // the driver reads (clearing the counter), then acknowledges the overrun
        let (seen, after) = u.read(reg);
        assert_eq!(u.get(seen, "RXCNT"), Some(5));
        reg = after;
        assert_eq!(u.get(reg, "RXCNT"), Some(0));
        reg = u.apply_write(reg, 0x0020 | 0x0001);
        assert_eq!(u.get(reg, "OVR"), Some(0));
        assert_eq!(u.get(reg, "BUSY"), Some(1));
        assert_eq!(u.get(reg, "EN"), Some(1));
    }
''')

LIB = Lib(
    name="regmap", lang="rust", title="the regmap crate",
    blurb="The firmware simulator models device registers with regmap, which knows read-only, write-one-to-clear and clear-on-read bit fields.",
    files={"Cargo.toml": cargo("regmap"), "src/lib.rs": SRC, "README.md": README, ".gitignore": "target/\n", ".cargo/config.toml": CARGO_CONFIG},
    visible_tests={"tests/basic.rs": VISIBLE},
    hidden_tests={"tests/full.rs": HIDDEN},
    mutate=["src/lib.rs"], difficulty=2, tags=["registers", "bitfields", "embedded"],
)

register_libs([LIB], n=8)

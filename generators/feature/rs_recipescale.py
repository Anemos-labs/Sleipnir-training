"""recipescale (rust): a recipe scaling library extended with lookup, allergens, rounding, limits, markdown, units, shopping lists."""
import random

from fx import dd, langs
from generators.feature._slices import App, Slice, fmt, register_app

README = dd('''
    # recipescale

    Exact recipe scaling for a cooking site (Rust 2021, no dependencies; `cargo test` runs the tests). Quantities are exact
    fractions, never floats.

    ## Layout

    * `src/fraction.rs`: `Frac`.
    * `src/recipe.rs`: `Ingredient`, `Recipe`, `RecipeError`.
    * `tests/`: integration tests.

    ## Basics

    * `Frac::new(n, d)` (both `u64`; panics when `d` is 0) is an exact non-negative fraction in lowest terms. `numer()` and
      `denom()` read it, `mul(self, other)` and `add(self, other)` combine two fractions, `Frac` is `Copy`, compares with
      `==` and prints as a mixed number: `7/2` is `3 1/2`, `1/2` is `1/2`, `4/2` is `2`, `0` is `0`.
    * `Ingredient::new(name, qty, unit)` with a `Frac` quantity; `unit` may be empty. `ingredient.line()` is `"{qty} {unit}
      {name}"`, without the unit and its space when the unit is empty.
    * `Recipe::new(title, servings) -> Result<Recipe, RecipeError>`: `RecipeError::ZeroServings` for 0 servings.
      `recipe.add(ingredient)` appends. Fields `title`, `servings` and `ingredients` are public.
    * `recipe.scale_to(servings) -> Result<Recipe, RecipeError>` returns a copy for another number of servings with every
      quantity multiplied by `servings / recipe.servings` exactly (`ZeroServings` for 0).
    * `recipe.to_text()` is one `ingredient.line()` per ingredient, in order, each ending in a newline.
    * `RecipeError` implements `Display` and `Error`.
''')

FRACTION = '''\
use std::fmt;
@@uniq imports

fn gcd(a: u64, b: u64) -> u64 {
    if b == 0 {
        a
    } else {
        gcd(b, a % b)
    }
}

/// A non-negative exact fraction in lowest terms.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Frac {
    n: u64,
    d: u64,
}

impl Frac {
    pub fn new(n: u64, d: u64) -> Frac {
        assert!(d != 0, "denominator must not be zero");
        let g = gcd(n, d).max(1);
        Frac { n: n / g, d: d / g }
    }

    pub fn numer(&self) -> u64 {
        self.n
    }

    pub fn denom(&self) -> u64 {
        self.d
    }

    pub fn mul(self, o: Frac) -> Frac {
        Frac::new(self.n * o.n, self.d * o.d)
    }

    pub fn add(self, o: Frac) -> Frac {
        Frac::new(self.n * o.d + o.n * self.d, self.d * o.d)
    }

    @@blocks methods
}

impl fmt::Display for Frac {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        let (whole, rem) = (self.n / self.d, self.n % self.d);
        match (whole, rem) {
            (w, 0) => write!(f, "{}", w),
            (0, r) => write!(f, "{}/{}", r, self.d),
            (w, r) => write!(f, "{} {}/{}", w, r, self.d),
        }
    }
}
'''

RECIPE = '''\
use std::fmt;

use crate::fraction::Frac;
@@uniq imports

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum RecipeError {
    ZeroServings,
    @@slot error_variants
}

impl fmt::Display for RecipeError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            RecipeError::ZeroServings => write!(f, "a recipe needs at least one serving"),
            @@slot error_display
        }
    }
}

impl std::error::Error for RecipeError {}

@@blocks types

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Ingredient {
    pub name: String,
    pub qty: Frac,
    pub unit: String,
    @@slot ingredient_fields
}

impl Ingredient {
    pub fn new(name: &str, qty: Frac, unit: &str) -> Ingredient {
        Ingredient {
            name: name.to_string(),
            qty,
            unit: unit.to_string(),
            @@slot ingredient_init
        }
    }

    pub fn line(&self) -> String {
        if self.unit.is_empty() {
            format!("{} {}", self.qty, self.name)
        } else {
            format!("{} {} {}", self.qty, self.unit, self.name)
        }
    }

    @@blocks ingredient_methods
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Recipe {
    pub title: String,
    pub servings: u32,
    pub ingredients: Vec<Ingredient>,
}

impl Recipe {
    pub fn new(title: &str, servings: u32) -> Result<Recipe, RecipeError> {
        if servings == 0 {
            return Err(RecipeError::ZeroServings);
        }
        @@slot new_checks
        Ok(Recipe { title: title.to_string(), servings, ingredients: Vec::new() })
    }

    pub fn add(&mut self, ingredient: Ingredient) {
        self.ingredients.push(ingredient);
    }

    pub fn scale_to(&self, servings: u32) -> Result<Recipe, RecipeError> {
        if servings == 0 {
            return Err(RecipeError::ZeroServings);
        }
        @@slot scale_checks
        let factor = Frac::new(servings as u64, self.servings as u64);
        let mut out = self.clone();
        out.servings = servings;
        for ing in out.ingredients.iter_mut() {
            ing.qty = ing.qty.mul(factor);
        }
        Ok(out)
    }

    pub fn to_text(&self) -> String {
        self.ingredients.iter().map(|i| i.line() + "\\n").collect()
    }

    @@blocks methods
}

@@blocks functions
'''

LIB = '''\
//! Exact recipe scaling.
pub mod fraction;
pub mod recipe;

pub use fraction::Frac;
pub use recipe::{Ingredient, Recipe, RecipeError};
@@slot reexports
'''

TEST_HELPERS = '''\
use recipescale::*;
@@uniq imports

fn pancakes() -> Recipe {
    let mut r = Recipe::new("Pancakes", 4).unwrap();
    r.add(Ingredient::new("Flour", Frac::new(3, 2), "cup"));
    r.add(Ingredient::new("Milk", Frac::new(5, 4), "cup"));
    r.add(Ingredient::new("Egg", Frac::new(2, 1), ""));
    r.add(Ingredient::new("Salt", Frac::new(1, 2), "tsp"));
    r
}
'''

VISIBLE = TEST_HELPERS + '''
#[test]
fn fractions_normalise_and_print() {
    assert_eq!(Frac::new(4, 6), Frac::new(2, 3));
    assert_eq!(Frac::new(7, 2).to_string(), "3 1/2");
    assert_eq!(Frac::new(1, 2).to_string(), "1/2");
    assert_eq!(Frac::new(4, 2).to_string(), "2");
    assert_eq!(Frac::new(0, 5).to_string(), "0");
    assert_eq!(Frac::new(1, 3).add(Frac::new(1, 6)), Frac::new(1, 2));
    assert_eq!(Frac::new(2, 3).mul(Frac::new(3, 4)), Frac::new(1, 2));
}

#[test]
fn text_and_scaling() {
    let r = pancakes();
    assert_eq!(r.to_text(), "1 1/2 cup Flour\\n1 1/4 cup Milk\\n2 Egg\\n1/2 tsp Salt\\n");
    let big = r.scale_to(6).unwrap();
    assert_eq!(big.servings, 6);
    assert_eq!(big.to_text(), "2 1/4 cup Flour\\n1 7/8 cup Milk\\n3 Egg\\n3/4 tsp Salt\\n");
    assert_eq!(r.scale_to(0), Err(RecipeError::ZeroServings));
    assert_eq!(Recipe::new("x", 0), Err(RecipeError::ZeroServings));
}
@@blocks tests
'''

HIDDEN = TEST_HELPERS + '''
#[test]
fn base_scaling_is_exact() {
    let r = pancakes();
    let small = r.scale_to(2).unwrap();
    assert_eq!(small.to_text(), "3/4 cup Flour\\n5/8 cup Milk\\n1 Egg\\n1/4 tsp Salt\\n");
    let back = small.scale_to(4).unwrap();
    assert_eq!(back, r);
    let same = r.scale_to(4).unwrap();
    assert_eq!(same, r);
    let odd = r.scale_to(7).unwrap();
    assert_eq!(odd.ingredients[0].qty, Frac::new(21, 8));
    assert_eq!(odd.ingredients[0].line(), "2 5/8 cup Flour");
    assert_eq!(r.ingredients.len(), 4);
    assert_eq!(r.servings, 4);
    assert_eq!(Ingredient::new("Salt", Frac::new(0, 3), "").line(), "0 Salt");
    assert_eq!(RecipeError::ZeroServings.to_string(), "a recipe needs at least one serving");
    assert_eq!(Frac::new(9, 6).numer(), 3);
    assert_eq!(Frac::new(9, 6).denom(), 2);
}
@@blocks tests
'''


def make_slices(rng: random.Random):
    max_servings = rng.choice([100, 200, 500])
    denom = rng.choice([4, 8])
    S = []

    S.append(Slice(
        id="find-ingredient", title="Ingredient lookup", d=1,
        pitch=("The substitution tool needs to look up an ingredient by name.",
               "Callers keep looping over `ingredients` just to find the flour."),
        reqs=("`Recipe::ingredient(&self, name: &str) -> Option<&Ingredient>` returns the first ingredient whose name equals `name` ignoring case, or `None`.",),
        code={
            "src/recipe.rs::methods": '''
                pub fn ingredient(&self, name: &str) -> Option<&Ingredient> {
                    let want = name.to_lowercase();
                    self.ingredients.iter().find(|i| i.name.to_lowercase() == want)
                }
            ''',
        },
        readme="## Ingredient lookup\n\n`recipe.ingredient(name)` finds the first ingredient with that name, ignoring case.\n",
        vtests='''
            #[test]
            fn lookup_basic() {
                assert!(pancakes().ingredient("milk").is_some());
            }
        ''',
        tests='''
            #[test]
            fn lookup_ignores_case_and_returns_first() {
                let mut r = pancakes();
                assert_eq!(r.ingredient("FLOUR").unwrap().qty, Frac::new(3, 2));
                assert!(r.ingredient("flo").is_none());
                assert!(r.ingredient("").is_none());
                r.add(Ingredient::new("flour", Frac::new(1, 1), "cup"));
                assert_eq!(r.ingredient("Flour").unwrap().qty, Frac::new(3, 2));
                assert_eq!(r.ingredient("flour").unwrap().unit, "cup");
            }
        ''',
    ))

    S.append(Slice(
        id="allergens", title="Allergen tags", d=2,
        pitch=("Recipes have to show allergen warnings.",
               "The site must list which allergens a recipe contains."),
        reqs=("`Ingredient` gets a public field `allergens: Vec<String>` (empty for `Ingredient::new`) and a builder `ingredient.with_allergens(&[&str]) -> Ingredient` that sets it: every entry is trimmed and lower-cased, empty entries are dropped and repeated ones are removed (first occurrence kept).",
              "`recipe.allergens() -> Vec<String>` is the sorted list of all allergens of all ingredients, without repeats."),
        code={
            "src/recipe.rs::ingredient_fields": "pub allergens: Vec<String>,",
            "src/recipe.rs::ingredient_init": "allergens: Vec::new(),",
            "src/recipe.rs::ingredient_methods": '''
                pub fn with_allergens(mut self, tags: &[&str]) -> Ingredient {
                    let mut clean: Vec<String> = Vec::new();
                    for t in tags {
                        let t = t.trim().to_lowercase();
                        if !t.is_empty() && !clean.contains(&t) {
                            clean.push(t);
                        }
                    }
                    self.allergens = clean;
                    self
                }
            ''',
            "src/recipe.rs::methods": '''
                pub fn allergens(&self) -> Vec<String> {
                    let mut all: Vec<String> = self.ingredients.iter().flat_map(|i| i.allergens.iter().cloned()).collect();
                    all.sort();
                    all.dedup();
                    all
                }
            ''',
        },
        readme="## Allergen tags\n\n`ingredient.with_allergens(&[...])` sets normalised tags (trimmed, lower-case, no repeats); `recipe.allergens()` lists them all, sorted.\n",
        vtests='''
            #[test]
            fn allergens_default_empty() {
                assert!(pancakes().allergens().is_empty());
            }
        ''',
        tests='''
            #[test]
            fn allergen_tags_are_normalised() {
                let i = Ingredient::new("Milk", Frac::new(1, 1), "cup").with_allergens(&[" Dairy ", "lactose", "DAIRY", "", "  "]);
                assert_eq!(i.allergens, vec!["dairy".to_string(), "lactose".to_string()]);
                assert!(Ingredient::new("Egg", Frac::new(1, 1), "").allergens.is_empty());
                assert_eq!(i.with_allergens(&[]).allergens, Vec::<String>::new());
            }

            #[test]
            fn recipe_allergens_are_sorted_and_unique() {
                let mut r = Recipe::new("Pie", 2).unwrap();
                r.add(Ingredient::new("Flour", Frac::new(1, 1), "cup").with_allergens(&["gluten"]));
                r.add(Ingredient::new("Butter", Frac::new(1, 2), "cup").with_allergens(&["Dairy", "gluten"]));
                r.add(Ingredient::new("Apple", Frac::new(3, 1), ""));
                r.add(Ingredient::new("Egg", Frac::new(1, 1), "").with_allergens(&["egg"]));
                assert_eq!(r.allergens(), vec!["dairy".to_string(), "egg".to_string(), "gluten".to_string()]);
                let scaled = r.scale_to(4).unwrap();
                assert_eq!(scaled.allergens(), r.allergens());
                assert_eq!(scaled.ingredients[1].allergens, r.ingredients[1].allergens);
            }
        ''',
    ))

    S.append(Slice(
        id="rounding", title="Kitchen rounding", d=2,
        pitch=("Scaling to 7 servings gives quantities like 21/8 cup that nobody can measure.",
               "Cooks want quantities rounded to fractions they can measure."),
        reqs=("`Frac::round_to(self, denom: u64) -> Option<Frac>` rounds to the nearest multiple of `1/denom`, halves rounding up, and never turns a quantity above zero into zero (the smallest result for a positive value is `1/denom`). `None` when `denom` is 0.",
              "`recipe.rounded(denom: u64) -> Result<Recipe, RecipeError>` returns a copy with every quantity rounded that way; the new error `RecipeError::BadDenominator` (message `denominator must be positive`) when `denom` is 0."),
        code={
            "src/recipe.rs::error_variants": "BadDenominator,",
            "src/recipe.rs::error_display": 'RecipeError::BadDenominator => write!(f, "denominator must be positive"),',
            "src/fraction.rs::methods": '''
                pub fn round_to(self, denom: u64) -> Option<Frac> {
                    if denom == 0 {
                        return None;
                    }
                    let k = (2 * self.n * denom + self.d) / (2 * self.d);
                    let k = if k == 0 && self.n > 0 { 1 } else { k };
                    Some(Frac::new(k, denom))
                }
            ''',
            "src/recipe.rs::methods": '''
                pub fn rounded(&self, denom: u64) -> Result<Recipe, RecipeError> {
                    if denom == 0 {
                        return Err(RecipeError::BadDenominator);
                    }
                    let mut out = self.clone();
                    for ing in out.ingredients.iter_mut() {
                        ing.qty = ing.qty.round_to(denom).unwrap();
                    }
                    Ok(out)
                }
            ''',
        },
        readme="## Kitchen rounding\n\n`Frac::round_to(denom)` rounds to the nearest `1/denom` (halves up, positives never become zero); `recipe.rounded(denom)` applies it to every quantity (`BadDenominator` for 0).\n",
        vtests='''
            #[test]
            fn rounding_basic() {
                assert_eq!(Frac::new(21, 8).round_to(4), Some(Frac::new(11, 4)));
            }
        ''',
        tests=fmt('''
            #[test]
            fn round_to_nearest_with_halves_up() {
                assert_eq!(Frac::new(21, 8).round_to(4), Some(Frac::new(11, 4)));
                assert_eq!(Frac::new(5, 8).round_to(4), Some(Frac::new(3, 4)));
                assert_eq!(Frac::new(3, 8).round_to(4), Some(Frac::new(1, 2)));
                assert_eq!(Frac::new(1, 3).round_to(4), Some(Frac::new(1, 4)));
                assert_eq!(Frac::new(2, 3).round_to(4), Some(Frac::new(3, 4)));
                assert_eq!(Frac::new(7, 2).round_to(1), Some(Frac::new(4, 1)));
                assert_eq!(Frac::new(5, 1).round_to(__D__), Some(Frac::new(5, 1)));
                assert_eq!(Frac::new(0, 1).round_to(__D__), Some(Frac::new(0, 1)));
            }

            #[test]
            fn positive_quantities_never_vanish() {
                assert_eq!(Frac::new(1, 100).round_to(__D__), Some(Frac::new(1, __D__)));
                assert_eq!(Frac::new(1, 100).round_to(1), Some(Frac::new(1, 1)));
                assert_eq!(Frac::new(1, 3).round_to(0), None);
                assert_eq!(Frac::new(0, 3).round_to(0), None);
            }

            #[test]
            fn recipes_can_be_rounded() {
                let r = pancakes().scale_to(7).unwrap();
                let q = r.rounded(4).unwrap();
                assert_eq!(q.to_text(), "2 3/4 cup Flour\\n2 1/4 cup Milk\\n3 1/2 Egg\\n1 tsp Salt\\n");
                assert_eq!(q.servings, 7);
                assert_eq!(r.ingredients[0].qty, Frac::new(21, 8));
                assert_eq!(pancakes().rounded(0), Err(RecipeError::BadDenominator));
                assert_eq!(RecipeError::BadDenominator.to_string(), "denominator must be positive");
            }
        ''', D=denom),
    ))

    S.append(Slice(
        id="scale-limits", title="Serving limits", d=2,
        pitch=("Someone scaled a pancake recipe to 40,000 servings and the shopping list crashed the mobile app.",
               "The site wants a sane upper bound on servings."),
        reqs=(f"A recipe may have at most {max_servings} servings. `Recipe::new` and `scale_to` fail with the new error `RecipeError::TooManyServings(n)` (`n` is the number that was asked for) when `servings` is above {max_servings}; exactly {max_servings} is fine. Zero servings is still `ZeroServings`.",
              f"`Display` for the new error reads `N servings is more than the limit of {max_servings}`."),
        code={
            "src/recipe.rs::error_variants": "TooManyServings(u32),",
            "src/recipe.rs::error_display": f'RecipeError::TooManyServings(n) => write!(f, "{{}} servings is more than the limit of {max_servings}", n),',
            "src/recipe.rs::new_checks": f'''
                if servings > {max_servings} {{
                    return Err(RecipeError::TooManyServings(servings));
                }}
            ''',
            "src/recipe.rs::scale_checks": f'''
                if servings > {max_servings} {{
                    return Err(RecipeError::TooManyServings(servings));
                }}
            ''',
        },
        readme=f"## Serving limits\n\nAt most {max_servings} servings: `Recipe::new` and `scale_to` return `RecipeError::TooManyServings(n)` above that.\n",
        vtests='''
            #[test]
            fn serving_limit_basic() {
                assert!(Recipe::new("x", 1).is_ok());
            }
        ''',
        tests=fmt('''
            #[test]
            fn too_many_servings() {
                assert!(Recipe::new("big", __M__).is_ok());
                assert_eq!(Recipe::new("big", __M__ + 1), Err(RecipeError::TooManyServings(__M__ + 1)));
                assert_eq!(Recipe::new("big", 0), Err(RecipeError::ZeroServings));
                let r = pancakes();
                let max = r.scale_to(__M__).unwrap();
                assert_eq!(max.servings, __M__);
                assert_eq!(max.ingredients[2].qty, Frac::new(2 * __M__ as u64, 4));
                assert_eq!(r.scale_to(__M__ + 1), Err(RecipeError::TooManyServings(__M__ + 1)));
                assert_eq!(r.scale_to(u32::MAX), Err(RecipeError::TooManyServings(u32::MAX)));
                assert_eq!(r.scale_to(0), Err(RecipeError::ZeroServings));
                assert_eq!(RecipeError::TooManyServings(__M__ + 7).to_string(), format!("{} servings is more than the limit of __M__", __M__ + 7));
            }
        ''', M=max_servings),
    ))

    S.append(Slice(
        id="markdown", title="Markdown card", d=2,
        pitch=("The blog wants to paste recipes as Markdown.",
               "Recipes should export to Markdown for the newsletter."),
        reqs=("`recipe.to_markdown() -> String` renders the heading `# TITLE (serves N)`, and, when there are ingredients, a blank line followed by one bullet `- LINE` per ingredient (`LINE` is the ingredient's `line()`), in order. Every line, the last one included, ends with a newline.",),
        code={
            "src/recipe.rs::methods": '''
                pub fn to_markdown(&self) -> String {
                    let mut out = format!("# {} (serves {})\\n", self.title, self.servings);
                    if !self.ingredients.is_empty() {
                        out.push('\\n');
                        for i in &self.ingredients {
                            out.push_str(&format!("- {}\\n", i.line()));
                        }
                    }
                    @@slot markdown_tail
                    out
                }
            ''',
        },
        readme="## Markdown card\n\n`recipe.to_markdown()` gives `# Title (serves N)`, a blank line and one `- line` bullet per ingredient.\n",
        vtests='''
            #[test]
            fn markdown_heading() {
                assert!(pancakes().to_markdown().starts_with("# Pancakes (serves 4)\\n\\n- 1 1/2 cup Flour\\n"));
            }
        ''',
        tests='''
            #[test]
            fn markdown_layout() {
                assert_eq!(
                    pancakes().to_markdown(),
                    "# Pancakes (serves 4)\\n\\n- 1 1/2 cup Flour\\n- 1 1/4 cup Milk\\n- 2 Egg\\n- 1/2 tsp Salt\\n"
                );
                let empty = Recipe::new("Water", 1).unwrap();
                assert_eq!(empty.to_markdown(), "# Water (serves 1)\\n");
                assert!(pancakes().scale_to(2).unwrap().to_markdown().starts_with("# Pancakes (serves 2)\\n"));
            }
        ''',
        cross={
            "allergens": {
                "reqs": ("When the recipe has allergens, the card ends with a blank line and the line `Contains: A, B` (the allergens in the order of `recipe.allergens()`, separated by a comma and a space), ending in a newline.",),
                "code": {"src/recipe.rs::markdown_tail": '''
                    let all = self.allergens();
                    if !all.is_empty() {
                        out.push_str(&format!("\\nContains: {}\\n", all.join(", ")));
                    }
                '''},
                "tests": '''
                    #[test]
                    fn markdown_lists_allergens() {
                        let mut r = Recipe::new("Pie", 2).unwrap();
                        r.add(Ingredient::new("Flour", Frac::new(1, 1), "cup").with_allergens(&["gluten"]));
                        r.add(Ingredient::new("Egg", Frac::new(1, 1), "").with_allergens(&["Egg"]));
                        assert_eq!(r.to_markdown(), "# Pie (serves 2)\\n\\n- 1 cup Flour\\n- 1 Egg\\n\\nContains: egg, gluten\\n");
                        assert!(!pancakes().to_markdown().contains("Contains"));
                    }
                '''},
        },
    ))

    S.append(Slice(
        id="unit-convert", title="Unit conversion", d=3,
        pitch=("Half the recipes are in cups and the other half in grams.",
               "Readers outside the US want metric quantities."),
        reqs=("`ingredient.converted(unit: &str) -> Result<Ingredient, RecipeError>` returns the ingredient expressed in another unit with the exact quantity (name unchanged). Known units are lower-case and exact: mass `g`, `kg` (1000 g), `oz` (28.35 g) and `lb` (16 oz); volume `ml`, `l` (1000 ml), `tsp` (5 ml), `tbsp` (15 ml) and `cup` (240 ml). Converting to the unit the ingredient already has changes nothing.",
              "Errors (new `RecipeError` variants): `UnknownUnit(String)` with the first unit that is not known (the ingredient's own unit is checked before the target; an empty unit is unknown), and `IncompatibleUnits { from: String, to: String }` when one unit is mass and the other volume. `Display` reads `unknown unit U` and `cannot convert FROM to TO`."),
        code={
            "src/recipe.rs::error_variants": "UnknownUnit(String),\nIncompatibleUnits { from: String, to: String },",
            "src/recipe.rs::error_display": 'RecipeError::UnknownUnit(u) => write!(f, "unknown unit {}", u),\nRecipeError::IncompatibleUnits { from, to } => write!(f, "cannot convert {} to {}", from, to),',
            "src/recipe.rs::functions": '''
                /// (dimension, size in the smallest unit of that dimension: centigrams or millilitres)
                fn unit_info(unit: &str) -> Option<(u8, u64)> {
                    match unit {
                        "g" => Some((0, 100)),
                        "kg" => Some((0, 100_000)),
                        "oz" => Some((0, 2835)),
                        "lb" => Some((0, 45_360)),
                        "ml" => Some((1, 1)),
                        "l" => Some((1, 1000)),
                        "tsp" => Some((1, 5)),
                        "tbsp" => Some((1, 15)),
                        "cup" => Some((1, 240)),
                        _ => None,
                    }
                }

                #[allow(dead_code)]
                fn same_dimension(a: &str, b: &str) -> bool {
                    match (unit_info(a), unit_info(b)) {
                        (Some((da, _)), Some((db, _))) => da == db,
                        _ => false,
                    }
                }
            ''',
            "src/recipe.rs::ingredient_methods": '''
                pub fn converted(&self, unit: &str) -> Result<Ingredient, RecipeError> {
                    let (from_dim, from_size) = unit_info(&self.unit).ok_or_else(|| RecipeError::UnknownUnit(self.unit.clone()))?;
                    let (to_dim, to_size) = unit_info(unit).ok_or_else(|| RecipeError::UnknownUnit(unit.to_string()))?;
                    if from_dim != to_dim {
                        return Err(RecipeError::IncompatibleUnits { from: self.unit.clone(), to: unit.to_string() });
                    }
                    let mut out = self.clone();
                    out.qty = self.qty.mul(Frac::new(from_size, to_size));
                    out.unit = unit.to_string();
                    Ok(out)
                }
            ''',
        },
        readme="## Unit conversion\n\n`ingredient.converted(unit)` converts exactly between `g kg oz lb` or between `ml l tsp tbsp cup` (`UnknownUnit`, `IncompatibleUnits` otherwise).\n",
        vtests='''
            #[test]
            fn conversion_basic() {
                let flour = pancakes().ingredients[0].converted("ml").unwrap();
                assert_eq!(flour.qty, Frac::new(360, 1));
            }
        ''',
        tests='''
            #[test]
            fn volume_and_mass_conversions_are_exact() {
                let r = pancakes();
                let flour = &r.ingredients[0];
                let ml = flour.converted("ml").unwrap();
                assert_eq!((ml.qty, ml.unit.as_str(), ml.name.as_str()), (Frac::new(360, 1), "ml", "Flour"));
                assert_eq!(flour.converted("tbsp").unwrap().qty, Frac::new(24, 1));
                assert_eq!(flour.converted("l").unwrap().qty, Frac::new(9, 25));
                assert_eq!(flour.converted("cup").unwrap(), *flour);
                assert_eq!(r.ingredients[3].converted("ml").unwrap().qty, Frac::new(5, 2));
                let kg = Ingredient::new("Sugar", Frac::new(1, 2), "kg");
                assert_eq!(kg.converted("g").unwrap().qty, Frac::new(500, 1));
                let oz = Ingredient::new("Butter", Frac::new(2, 1), "oz");
                assert_eq!(oz.converted("g").unwrap().qty, Frac::new(567, 10));
                let lb = Ingredient::new("Beef", Frac::new(1, 1), "lb");
                assert_eq!(lb.converted("oz").unwrap().qty, Frac::new(16, 1));
                assert_eq!(Ingredient::new("Rice", Frac::new(100, 1), "g").converted("oz").unwrap().qty, Frac::new(2000, 567));
            }

            #[test]
            fn conversion_errors() {
                let flour = pancakes().ingredients[0].clone();
                assert_eq!(flour.converted("g"), Err(RecipeError::IncompatibleUnits { from: "cup".into(), to: "g".into() }));
                assert_eq!(flour.converted("furlong"), Err(RecipeError::UnknownUnit("furlong".into())));
                assert_eq!(flour.converted("Cup").unwrap_err(), RecipeError::UnknownUnit("Cup".into()));
                let egg = pancakes().ingredients[2].clone();
                assert_eq!(egg.converted("g"), Err(RecipeError::UnknownUnit("".into())));
                let odd = Ingredient::new("Dust", Frac::new(1, 1), "pinch");
                assert_eq!(odd.converted("furlong"), Err(RecipeError::UnknownUnit("pinch".into())));
                assert_eq!(RecipeError::UnknownUnit("pinch".into()).to_string(), "unknown unit pinch");
                assert_eq!(RecipeError::IncompatibleUnits { from: "cup".into(), to: "g".into() }.to_string(), "cannot convert cup to g");
            }
        ''',
    ))

    S.append(Slice(
        id="shopping-list", title="Shopping list", d=4,
        pitch=("Planning a week of meals means adding up the same ingredient across several recipes by hand.",
               "The meal planner needs one combined shopping list."),
        reqs=("New free function `recipescale::shopping_list(plan: &[(&Recipe, u32)]) -> Result<Vec<Ingredient>, RecipeError>`. Each plan entry is a recipe and the number of servings wanted; every recipe is first scaled with `scale_to` (its errors are returned as they are, the first failing entry wins).",
              "Ingredients are then merged: two ingredients are the same item when their names are equal ignoring case and their units are exactly equal; their quantities are added. The merged item keeps the spelling of the name that appeared first. The list is sorted by lower-cased name, then by unit (plain string order). An empty plan gives an empty list."),
        code={
            "src/lib.rs::reexports": "pub use recipe::shopping_list;",
            "src/recipe.rs::functions": '''
                /// One combined, sorted ingredient list for several recipes.
                pub fn shopping_list(plan: &[(&Recipe, u32)]) -> Result<Vec<Ingredient>, RecipeError> {
                    let mut items: Vec<Ingredient> = Vec::new();
                    for (recipe, servings) in plan {
                        let scaled = recipe.scale_to(*servings)?;
                        for ing in scaled.ingredients {
                            @@default merge_one
                            let slot = items.iter().position(|x| x.name.to_lowercase() == ing.name.to_lowercase() && x.unit == ing.unit);
                            match slot {
                                Some(i) => {
                                    items[i].qty = items[i].qty.add(ing.qty);
                                    @@slot after_merge
                                }
                                None => items.push(ing),
                            }
                            @@end
                        }
                    }
                    items.sort_by(|a, b| (a.name.to_lowercase(), &a.unit).cmp(&(b.name.to_lowercase(), &b.unit)));
                    @@slot list_finish
                    Ok(items)
                }
            ''',
        },
        readme="## Shopping list\n\n`shopping_list(&[(&recipe, servings), ...])` scales each recipe, then merges ingredients with the same name (any case) and unit, sorted by name then unit.\n",
        vtests='''
            #[test]
            fn shopping_list_basic() {
                let p = pancakes();
                let list = shopping_list(&[(&p, 4)]).unwrap();
                assert_eq!(list.len(), 4);
            }
        ''',
        tests='''
            fn soup() -> Recipe {
                let mut r = Recipe::new("Soup", 2).unwrap();
                r.add(Ingredient::new("onion", Frac::new(1, 1), ""));
                r.add(Ingredient::new("Stock", Frac::new(2, 1), "cup"));
                r.add(Ingredient::new("salt", Frac::new(1, 2), "tsp"));
                r.add(Ingredient::new("FLOUR", Frac::new(1, 4), "cup"));
                r
            }

            #[test]
            fn shopping_list_merges_and_sorts() {
                let p = pancakes();
                let s = soup();
                let list = shopping_list(&[(&p, 4), (&s, 4)]).unwrap();
                let lines: Vec<String> = list.iter().map(|i| i.line()).collect();
                assert_eq!(lines, vec!["2 Egg", "2 cup Flour", "1 1/4 cup Milk", "2 onion", "1 1/2 tsp Salt", "4 cup Stock"]);
                assert_eq!(shopping_list(&[]).unwrap(), Vec::<Ingredient>::new());
            }

            #[test]
            fn shopping_list_scales_first() {
                let p = pancakes();
                let list = shopping_list(&[(&p, 2), (&p, 6)]).unwrap();
                let lines: Vec<String> = list.iter().map(|i| i.line()).collect();
                assert_eq!(lines, vec!["4 Egg", "3 cup Flour", "2 1/2 cup Milk", "1 tsp Salt"]);
                assert_eq!(shopping_list(&[(&p, 4), (&p, 0)]), Err(RecipeError::ZeroServings));
                assert_eq!(shopping_list(&[(&p, 0), (&p, 0)]), Err(RecipeError::ZeroServings));
            }

            #[test]
            fn different_units_stay_separate_and_sort_by_unit() {
                let mut a = Recipe::new("A", 1).unwrap();
                a.add(Ingredient::new("Milk", Frac::new(1, 1), "carton"));
                a.add(Ingredient::new("Milk", Frac::new(1, 2), "bottle"));
                let mut b = Recipe::new("B", 1).unwrap();
                b.add(Ingredient::new("milk", Frac::new(1, 1), "bottle"));
                b.add(Ingredient::new("Pepper", Frac::new(1, 1), "pinch"));
                b.add(Ingredient::new("Pepper", Frac::new(2, 1), "pinch"));
                let list = shopping_list(&[(&a, 1), (&b, 1)]).unwrap();
                let lines: Vec<String> = list.iter().map(|i| i.line()).collect();
                assert_eq!(lines, vec!["1 1/2 bottle Milk", "1 carton Milk", "3 pinch Pepper"]);
            }
        ''',
        cross={
            "unit-convert": {
                "reqs": ("Units that can be converted into each other count as the same unit: two ingredients with the same name (ignoring case) whose units are both known and of the same kind (both mass or both volume) are merged into one item, expressed in the unit of the one that appeared first (the later one is converted with `converted`). Items whose unit is unknown (including an empty unit) are only merged when their units are exactly equal.",),
                "code": {"src/recipe.rs::merge_one": '''
                    let mut ing = ing;
                    let slot = items.iter().position(|x| {
                        x.name.to_lowercase() == ing.name.to_lowercase() && (x.unit == ing.unit || same_dimension(&x.unit, &ing.unit))
                    });
                    match slot {
                        Some(i) => {
                            if items[i].unit != ing.unit {
                                ing = ing.converted(&items[i].unit)?;
                            }
                            items[i].qty = items[i].qty.add(ing.qty);
                            @@slot after_merge
                        }
                        None => items.push(ing),
                    }
                '''},
                "tests": '''
                    #[test]
                    fn shopping_list_merges_convertible_units() {
                        let mut a = Recipe::new("A", 1).unwrap();
                        a.add(Ingredient::new("Milk", Frac::new(1, 2), "cup"));
                        a.add(Ingredient::new("Sugar", Frac::new(100, 1), "g"));
                        a.add(Ingredient::new("Salt", Frac::new(1, 1), "pinch"));
                        let mut b = Recipe::new("B", 1).unwrap();
                        b.add(Ingredient::new("milk", Frac::new(60, 1), "ml"));
                        b.add(Ingredient::new("sugar", Frac::new(1, 10), "kg"));
                        b.add(Ingredient::new("Salt", Frac::new(1, 1), "pinch"));
                        b.add(Ingredient::new("Salt", Frac::new(1, 1), "tsp"));
                        let list = shopping_list(&[(&a, 1), (&b, 1)]).unwrap();
                        let lines: Vec<String> = list.iter().map(|i| i.line()).collect();
                        assert_eq!(lines, vec!["3/4 cup Milk", "2 pinch Salt", "1 tsp Salt", "200 g Sugar"]);
                    }

                    #[test]
                    fn incompatible_units_are_not_merged() {
                        let mut a = Recipe::new("A", 1).unwrap();
                        a.add(Ingredient::new("Butter", Frac::new(1, 1), "cup"));
                        let mut b = Recipe::new("B", 1).unwrap();
                        b.add(Ingredient::new("Butter", Frac::new(50, 1), "g"));
                        let list = shopping_list(&[(&a, 1), (&b, 1)]).unwrap();
                        let lines: Vec<String> = list.iter().map(|i| i.line()).collect();
                        assert_eq!(lines, vec!["1 cup Butter", "50 g Butter"]);
                    }
                '''},
            "allergens": {
                "reqs": ("A merged item carries the union of the allergens of the ingredients it was made from, sorted; an item that was not merged keeps its own list.",),
                "code": {
                    "src/recipe.rs::after_merge": '''
                        for a in ing.allergens.iter() {
                            if !items[i].allergens.contains(a) {
                                items[i].allergens.push(a.clone());
                            }
                        }
                    ''',
                    "src/recipe.rs::list_finish": '''
                        for it in items.iter_mut() {
                            it.allergens.sort();
                        }
                    ''',
                },
                "tests": '''
                    #[test]
                    fn shopping_list_unions_allergens() {
                        let mut a = Recipe::new("A", 1).unwrap();
                        a.add(Ingredient::new("Flour", Frac::new(1, 1), "cup").with_allergens(&["gluten"]));
                        a.add(Ingredient::new("Egg", Frac::new(1, 1), "").with_allergens(&["egg"]));
                        let mut b = Recipe::new("B", 1).unwrap();
                        b.add(Ingredient::new("flour", Frac::new(1, 1), "cup").with_allergens(&["wheat", "gluten"]));
                        let list = shopping_list(&[(&a, 1), (&b, 1)]).unwrap();
                        assert_eq!(list[0].name, "Egg");
                        assert_eq!(list[0].allergens, vec!["egg".to_string()]);
                        assert_eq!(list[1].allergens, vec!["gluten".to_string(), "wheat".to_string()]);
                        assert_eq!(list[1].qty, Frac::new(2, 1));
                    }
                '''},
        },
    ))

    return S


APP = App(
    name="recipescale", lang="rust", title="the recipe scaling library", role="a recipe site developer", key="RECIPE",
    base={
        "README.md": README + "\n@@blocks features\n",
        "Cargo.toml": langs.cargo_toml("recipescale"),
        "src/lib.rs": LIB,
        "src/fraction.rs": FRACTION,
        "src/recipe.rs": RECIPE,
        ".gitignore": langs.GITIGNORE["rust"],
    },
    visible={"tests/basic.rs": VISIBLE},
    hidden={"tests/features.rs": HIDDEN},
)

register_app("feature-rs-recipescale", APP, make_slices, n=14, summary="recipe scaling: lookup, allergens, rounding, limits, markdown, units, shopping list")

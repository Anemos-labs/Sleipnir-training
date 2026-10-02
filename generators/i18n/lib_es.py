"""Native bug-fix family in Spanish: DNI/NIE letters, long dates and plural forms (python)."""
from fx import Lib, dd

from ._native import register_native

README = dd(r'''
    # docsp

    Funciones de apoyo para el formulario de alta de socios de una cooperativa: comprobar DNI y NIE, escribir y leer
    fechas en español y poner nombres en plural. Solo biblioteca estándar. Los números de los ejemplos y de las pruebas
    son inventados.

    ## DNI y NIE

    La letra de control se calcula con el resto de dividir el número entre 23 y la tabla
    `TRWAGMYFPDXBNJZSQVHLCKE` (resto 0 -> `T`, resto 1 -> `R`, ..., resto 22 -> `E`).

    ### `letra_dni(numero) -> str`
    La letra de control de un número entero entre `0` y `99999999` (ambos incluidos); fuera de ese rango, `ValueError`.

    ### `validar_dni(texto) -> bool`
    Un DNI es válido si, tras limpiarlo, tiene 7 u 8 cifras ASCII seguidas de una letra que coincide con `letra_dni` del número.
    Limpieza: se quitan los espacios del principio y del final y todos los puntos y espacios del interior, se pasa a
    mayúsculas y, si queda exactamente **un** guion, se quita (`"12.345.678-Z"`, `"12345678-z"`, `" 12345678 Z "` valen).
    Con dos o más guiones o cualquier otro carácter no es válido. Los DNI de 7 cifras se interpretan como el número sin ceros
    delante (`"1234567L"` es válido).

    ### `validar_nie(texto) -> bool`
    Un NIE son una letra `X`, `Y` o `Z`, siete cifras ASCII y una letra de control. Se limpia igual que el DNI (mayúsculas,
    sin puntos ni espacios, un solo guion permitido pero ignorado). La letra de control es `letra_dni` del número de ocho cifras que
    resulta de sustituir la letra inicial por `0` (X), `1` (Y) o `2` (Z) delante de las siete cifras. Cualquier otra longitud o
    letra inicial no es válida.

    ## Fechas

    ### `fecha_larga(d, dia_semana=False) -> str`
    `"3 de marzo de 2026"`: día sin cero inicial (también el 1, sin ordinal), mes en minúsculas, año tal cual. Con
    `dia_semana=True` se antepone el día de la semana en minúsculas, una coma y un espacio: `"martes, 3 de marzo de 2026"`.
    Meses: enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre. Días: lunes martes
    miércoles jueves viernes sábado domingo.

    ### `parsear_fecha(texto) -> date`
    Lee una fecha en estos formatos (sin distinguir mayúsculas y minúsculas, con espacios en blanco al principio y al final
    ignorados):

    * Larga: `"3 de marzo de 2026"`, con día de uno o dos dígitos, el año de cuatro dígitos y uno o más espacios entre palabras.
      Puede llevar delante un día de la semana y una coma (`"martes, 3 de marzo de 2026"`; el día de la semana no se comprueba).
      El mes se escribe completo; además de `septiembre` se acepta `setiembre`.
    * Numérica: `D/M/AAAA`, `D-M-AAAA` o `D.M.AAAA` (el mismo separador las dos veces; día y mes de uno o dos dígitos, año de
      cuatro): el orden es día, mes, año.

    Cualquier otra cosa (mes desconocido, año de dos cifras, separadores mezclados como `3/3-2026`, falta `de`) o una fecha que
    no existe (`31/4/2026`, `30 de febrero de 2026`) es `ValueError`.

    ## Plurales

    ### `plural_es(word) -> str`
    Plural sencillo de un sustantivo en minúsculas (no se tratan hiatos, cambios de acento ni excepciones). El sufijo se añade
    en minúsculas. Reglas, en este orden: vacío -> `ValueError`; acaba en `z` -> se cambia por `ces` (`lápiz` -> `lápices`); acaba en
    vocal `a e i o u á é ó` -> se añade `s` (`casa` -> `casas`, `café` -> `cafés`); acaba en `í` o `ú` -> `ValueError` (hay dos formas
    admitidas); acaba en `n` o `s` precedida de una vocal con tilde -> se quita la tilde y se añade `es` (`canción` ->
    `canciones`, `francés` -> `franceses`, `jardín` -> `jardines`); acaba en `s` -> invariable (`lunes`, `crisis`);
    en cualquier otro caso -> se añade `es` (`papel` -> `papeles`, `mujer` -> `mujeres`, `rey` -> `reyes`).
''')

SRC = dd(r'''
    import re
    from datetime import date

    _LETTERS = "TRWAGMYFPDXBNJZSQVHLCKE"
    _MONTHS = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre",
               "diciembre"]
    _WEEKDAYS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
    _MONTH_INDEX = {name: i for i, name in enumerate(_MONTHS, 1)}
    _MONTH_INDEX["setiembre"] = 9
    _LONG = re.compile(r"(?:(?:lunes|martes|miércoles|jueves|viernes|sábado|domingo)\s*,\s*)?([0-9]{1,2})\s+de\s+([a-zé]+)\s+de\s+([0-9]{4})")
    _NUMERIC = re.compile(r"([0-9]{1,2})([/.-])([0-9]{1,2})\2([0-9]{4})")


    def letra_dni(numero: int) -> str:
        if not 0 <= numero <= 99999999:
            raise ValueError("numero fuera de rango")
        return _LETTERS[numero % 23]


    def _limpiar(texto: str) -> str:
        t = texto.strip().upper().replace(".", "").replace(" ", "")
        return t.replace("-", "", 1) if t.count("-") == 1 else t


    def validar_dni(texto: str) -> bool:
        t = _limpiar(texto)
        if "-" in t or not (7 <= len(t) - 1 <= 8) or not t[:-1].isascii() or not t[:-1].isdigit():
            return False
        return t[-1] == letra_dni(int(t[:-1]))


    def validar_nie(texto: str) -> bool:
        t = _limpiar(texto)
        if len(t) != 9 or t[0] not in "XYZ" or not (t[1:8].isascii() and t[1:8].isdigit()):
            return False
        return t[8] == letra_dni(int("XYZ".index(t[0]) * 10 ** 7 + int(t[1:8])))


    def fecha_larga(d: date, dia_semana: bool = False) -> str:
        text = "%d de %s de %d" % (d.day, _MONTHS[d.month - 1], d.year)
        return _WEEKDAYS[d.weekday()] + ", " + text if dia_semana else text


    def parsear_fecha(texto: str) -> date:
        t = texto.strip().lower()
        m = _LONG.fullmatch(t)
        if m:
            month = _MONTH_INDEX.get(m.group(2))
            if month is None:
                raise ValueError("mes desconocido: %r" % (texto,))
            return date(int(m.group(3)), month, int(m.group(1)))
        m = _NUMERIC.fullmatch(t)
        if m:
            return date(int(m.group(4)), int(m.group(3)), int(m.group(1)))
        raise ValueError("fecha ilegible: %r" % (texto,))


    def plural_es(word: str) -> str:
        if not word:
            raise ValueError("palabra vacia")
        last = word[-1]
        if last == "z":
            return word[:-1] + "ces"
        if last in "aeiouáéó":
            return word + "s"
        if last in "íú":
            raise ValueError("plural ambiguo: %r" % (word,))
        if last in "ns" and len(word) > 1 and word[-2] in "áéíóú":
            return word[:-2] + "aeiou"["áéíóú".index(word[-2])] + last + "es"
        if last == "s":
            return word
        return word + "es"
''')

VISIBLE = dd('''
    import unittest
    from datetime import date

    from docsp import fecha_larga, letra_dni, validar_dni


    class Basico(unittest.TestCase):
        def test_letra(self):
            self.assertEqual(letra_dni(12345678), "Z")

        def test_dni(self):
            self.assertTrue(validar_dni("12345678Z"))

        def test_fecha(self):
            self.assertEqual(fecha_larga(date(2026, 3, 3)), "3 de marzo de 2026")


    if __name__ == "__main__":
        unittest.main()
''')

HIDDEN = dd('''
    import unittest
    from datetime import date

    from docsp import fecha_larga, letra_dni, parsear_fecha, plural_es, validar_dni, validar_nie

    D = date


    class Letra(unittest.TestCase):
        def test_valores(self):
            for n, letra in ((0, "T"), (1, "R"), (2, "W"), (22, "E"), (23, "T"), (24, "R"), (12345678, "Z"), (99999999, "R"),
                             (87654321, "X"), (1234567, "L"), (11234567, "X"), (21234567, "R")):
                self.assertEqual(letra_dni(n), letra, n)

        def test_tabla_completa(self):
            tabla = "TRWAGMYFPDXBNJZSQVHLCKE"
            for n in range(0, 100):
                self.assertEqual(letra_dni(n), tabla[n % 23])

        def test_rango(self):
            self.assertEqual(letra_dni(99999999), "R")
            for n in (-1, 100000000, 10 ** 9):
                with self.assertRaises(ValueError, msg=n):
                    letra_dni(n)


    class Dni(unittest.TestCase):
        def test_validos(self):
            for t in ("12345678Z", "12345678z", "12345678-Z", "12345678-z", "12.345.678-Z", " 12345678 Z ", "12 345 678 Z",
                      "00000000T", "99999999R", "87654321X", "1234567L", "1.234.567-L", "0000001R", "\\t12345678Z\\n"):
                self.assertTrue(validar_dni(t), repr(t))

        def test_letra_mala(self):
            for t in ("12345678A", "12345678T", "00000000R", "99999999T", "1234567Z"):
                self.assertFalse(validar_dni(t), t)

        def test_longitud(self):
            for t in ("", "Z", "123456Z", "123456789Z", "12345678", "1234567", "123456789", "12345678ZZ"):
                self.assertFalse(validar_dni(t), repr(t))

        def test_guiones(self):
            for t in ("12345678--Z", "12-345-678Z", "12-345678-Z", "--12345678Z"):
                self.assertFalse(validar_dni(t), t)

        def test_caracteres_raros(self):
            for t in ("Z12345678", "1234A678Z", "١٢٣٤٥٦٧٨Z", "１２３４５６７８Z", "12345678Ñ", "12345,678Z", "12_345_678Z"):
                self.assertFalse(validar_dni(t), t)

        def test_sin_efecto_de_un_solo_guion(self):
            self.assertTrue(validar_dni("1234567-L"))
            self.assertFalse(validar_dni("1234567-Z"))


    class Nie(unittest.TestCase):
        def test_validos(self):
            for t in ("X1234567L", "x1234567l", "Y1234567X", "Z1234567R", "Y0000000Z", " X1234567L ", "X.1234567.L", "X 1234567 L",
                      "X1234567L"):
                self.assertTrue(validar_nie(t), repr(t))

        def test_un_guion_permitido(self):
            self.assertTrue(validar_nie("X-1234567L"))
            self.assertTrue(validar_nie("X1234567-L"))
            self.assertFalse(validar_nie("X-1234567-L"))

        def test_letra_inicial(self):
            for t in ("T1234567L", "A1234567L", "W1234567L", "01234567L", "1234567LL"):
                self.assertFalse(validar_nie(t), t)

        def test_sustitucion_de_la_inicial(self):
            # X = 0, Y = 1, Z = 2 delante de las siete cifras: la misma cola da letras distintas
            self.assertTrue(validar_nie("X0000000T"))
            self.assertTrue(validar_nie("Y0000000Z"))
            self.assertTrue(validar_nie("Z0000000M"))
            self.assertFalse(validar_nie("X0000000Z"))
            self.assertFalse(validar_nie("Z0000000T"))

        def test_longitud_y_cifras(self):
            for t in ("X12345678", "X123456L", "X12345678L", "X123456LL", "X12A4567L", "X١٢٣٤٥٦٧L", ""):
                self.assertFalse(validar_nie(t), repr(t))

        def test_letra_mala(self):
            for t in ("X1234567A", "Y1234567L", "Z1234567L"):
                self.assertFalse(validar_nie(t), t)


    class Fechas(unittest.TestCase):
        def test_larga(self):
            self.assertEqual(fecha_larga(D(2026, 3, 3)), "3 de marzo de 2026")
            self.assertEqual(fecha_larga(D(2026, 3, 1)), "1 de marzo de 2026")
            self.assertEqual(fecha_larga(D(2025, 12, 31)), "31 de diciembre de 2025")
            self.assertEqual(fecha_larga(D(2024, 2, 29)), "29 de febrero de 2024")
            self.assertEqual(fecha_larga(D(2026, 9, 9)), "9 de septiembre de 2026")
            self.assertEqual(fecha_larga(D(999, 1, 2)), "2 de enero de 999")

        def test_meses(self):
            nombres = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
                       "noviembre", "diciembre"]
            for m, nombre in enumerate(nombres, 1):
                self.assertEqual(fecha_larga(D(2025, m, 15)), "15 de %s de 2025" % nombre)

        def test_dia_semana(self):
            self.assertEqual(fecha_larga(D(2026, 3, 3), dia_semana=True), "martes, 3 de marzo de 2026")
            self.assertEqual(fecha_larga(D(2026, 3, 1), True), "domingo, 1 de marzo de 2026")
            self.assertEqual(fecha_larga(D(2025, 12, 31), True), "miércoles, 31 de diciembre de 2025")
            self.assertEqual(fecha_larga(D(2024, 2, 29), True), "jueves, 29 de febrero de 2024")

        def test_todos_los_dias(self):
            nombres = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
            for k, nombre in enumerate(nombres):
                self.assertTrue(fecha_larga(D(2026, 3, 2 + k), True).startswith(nombre + ", "))

        def test_parsear_larga(self):
            for t in ("3 de marzo de 2026", "3 DE MARZO DE 2026", "03 de marzo de 2026", "  3 de marzo de 2026  ",
                      "martes, 3 de marzo de 2026", "martes ,3 de marzo de 2026", "MARTES,  3  de  Marzo  de  2026",
                      "lunes, 3 de marzo de 2026"):
                self.assertEqual(parsear_fecha(t), D(2026, 3, 3), repr(t))

        def test_parsear_meses(self):
            nombres = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
                       "noviembre", "diciembre"]
            for m, nombre in enumerate(nombres, 1):
                self.assertEqual(parsear_fecha("15 de %s de 2025" % nombre), D(2025, m, 15))
            self.assertEqual(parsear_fecha("1 de setiembre de 2025"), D(2025, 9, 1))

        def test_parsear_numerica(self):
            for t in ("3/3/2026", "03/03/2026", "3-3-2026", "03-03-2026", "3.3.2026", "03.03.2026", " 3/3/2026 "):
                self.assertEqual(parsear_fecha(t), D(2026, 3, 3), repr(t))
            self.assertEqual(parsear_fecha("1/2/2025"), D(2025, 2, 1))
            self.assertEqual(parsear_fecha("12/11/2025"), D(2025, 11, 12))
            self.assertEqual(parsear_fecha("29/2/2024"), D(2024, 2, 29))

        def test_orden_dia_mes(self):
            self.assertEqual(parsear_fecha("5/6/2025"), D(2025, 6, 5))
            with self.assertRaises(ValueError):
                parsear_fecha("6/13/2025")

        def test_ilegibles(self):
            for t in ("", "3 de marz de 2026", "3 marzo 2026", "3 de marzo 2026", "3 de marzo de 26", "3/3/26", "3/3-2026",
                      "3-3.2026", "31/4/2026", "30 de febrero de 2026", "29/2/2025", "0/3/2026", "3/0/2026", "3/13/2026",
                      "123 de marzo de 2026", "3 de marzo de 20266", "marzo 3, 2026", "hoy", "3 de Mars de 2026",
                      "viernes 3 de marzo de 2026", "dia, 3 de marzo de 2026"):
                with self.assertRaises(ValueError, msg=repr(t)):
                    parsear_fecha(t)

        def test_ida_y_vuelta(self):
            d = D(1900, 1, 1)
            while d < D(2100, 1, 1):
                self.assertEqual(parsear_fecha(fecha_larga(d)), d)
                self.assertEqual(parsear_fecha(fecha_larga(d, True)), d)
                d = D.fromordinal(d.toordinal() + 83)


    class Plural(unittest.TestCase):
        def test_vocal(self):
            for w, p in (("casa", "casas"), ("libro", "libros"), ("fiesta", "fiestas"), ("café", "cafés"), ("sofá", "sofás"),
                         ("bebé", "bebés"), ("dominó", "dominós"), ("pie", "pies"), ("taxi", "taxis"), ("tribu", "tribus")):
                self.assertEqual(plural_es(w), p)

        def test_z(self):
            for w, p in (("lápiz", "lápices"), ("luz", "luces"), ("nariz", "narices"), ("pez", "peces")):
                self.assertEqual(plural_es(w), p)

        def test_consonante(self):
            for w, p in (("papel", "papeles"), ("mujer", "mujeres"), ("rey", "reyes"), ("ley", "leyes"), ("ciudad", "ciudades"),
                         ("reloj", "relojes"), ("pan", "panes"), ("color", "colores"), ("árbol", "árboles"), ("arroz", "arroces")):
                self.assertEqual(plural_es(w), p)

        def test_tilde_se_quita(self):
            for w, p in (("canción", "canciones"), ("francés", "franceses"), ("jardín", "jardines"), ("alemán", "alemanes"),
                         ("autobús", "autobuses"), ("corazón", "corazones"), ("balcón", "balcones"), ("camión", "camiones")):
                self.assertEqual(plural_es(w), p)

        def test_invariables(self):
            for w in ("lunes", "martes", "crisis", "virus", "paraguas", "análisis"):
                self.assertEqual(plural_es(w), w)

        def test_ambiguos_y_vacio(self):
            for w in ("tabú", "iraní", "menú", ""):
                with self.assertRaises(ValueError, msg=repr(w)):
                    plural_es(w)


    if __name__ == "__main__":
        unittest.main()
''')

LIB = Lib(
    name="docsp", lang="python", title="`docsp`",
    blurb="El formulario de alta de socios de una cooperativa usa estas funciones para validar documentos y escribir fechas.",
    files={"docsp/__init__.py": "from .core import *  # noqa: F401,F403\n", "docsp/core.py": SRC,
           "README.md": README, ".gitignore": "__pycache__/\n*.pyc\n"},
    visible_tests={"tests/test_basico.py": VISIBLE},
    hidden_tests={"tests/test_completo.py": HIDDEN},
    mutate=["docsp/core.py"], difficulty=3, tags=["validation", "dates", "text", "i18n"],
    probes=[
        'letra_dni(87654321)',
        'validar_dni("12.345.678-Z")',
        'validar_dni("1234567L")',
        'validar_dni("12-345-678Z")',
        'validar_nie("Y1234567X")',
        'validar_nie("X-1234567-L")',
        'validar_nie("Z0000000M")',
        'fecha_larga(date(2026, 3, 1), True)',
        'fecha_larga(date(2024, 2, 29))',
        'parsear_fecha("martes ,3 de marzo de 2026")',
        'parsear_fecha("1 de setiembre de 2025")',
        'parsear_fecha("5/6/2025")',
        'parsear_fecha("3/3-2026")',
        'plural_es("lápiz")',
        'plural_es("canción")',
        'plural_es("lunes")',
    ],
    probe_import="from datetime import date\nfrom docsp import *",
)

register_native(LIB, "es", "fix-docsp", n=9,
                summary="native: injected bugs in a Spanish DNI/NIE/date/plural library, reports in Spanish")

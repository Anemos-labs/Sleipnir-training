"""Native bug-fix family in Brazilian Portuguese: CPF/CNPJ checks and real (R$) formatting with ABNT rounding (python)."""
from fx import Lib, dd

from ._native import register_native

README = dd(r'''
    # docbr

    Funções de apoio ao cadastro de clientes de uma loja virtual: validar e formatar CPF e CNPJ, e escrever e ler valores em reais.
    Só biblioteca padrão. Todos os números de exemplo e de teste são fictícios.

    ## CPF

    Um CPF tem 11 dígitos: nove de base e dois dígitos verificadores. Primeiro dígito: some `d1*10 + d2*9 + ... + d9*2`, multiplique
    a soma por 10, tire o resto da divisão por 11 e troque 10 por 0. Segundo dígito: igual, mas com os dez dígitos já conhecidos
    (os nove da base e o primeiro verificador) e os pesos `11, 10, ..., 2`.

    ### `cpf_valido(cpf) -> bool`
    `True` quando o texto é exatamente 11 dígitos ASCII (`"52998224725"`) **ou** exatamente a forma pontuada `NNN.NNN.NNN-NN`
    (`"529.982.247-25"`), os dígitos verificadores batem e os 11 dígitos não são todos iguais (`"111.111.111-11"` é inválido
    mesmo que a conta feche). Qualquer outra pontuação, espaços ou tamanho diferente: `False`.

    ### `cpf_formatar(cpf) -> str`
    De 11 dígitos ASCII para `NNN.NNN.NNN-NN`. Não confere os verificadores. Qualquer outra entrada: `ValueError`.

    ## CNPJ

    Um CNPJ tem 14 dígitos: oito da empresa, quatro da filial e dois verificadores. Cada verificador é calculado sobre os
    dígitos anteriores com estes pesos: o primeiro (sobre os 12 primeiros) com `5 4 3 2 9 8 7 6 5 4 3 2`, o segundo (sobre os 12 mais
    o primeiro verificador) com `6 5 4 3 2 9 8 7 6 5 4 3 2`. Em cada caso, `r` é a soma dos produtos módulo 11 e o dígito é `0` se
    `r < 2`, senão `11 - r`.

    ### `cnpj_valido(cnpj) -> bool`
    `True` quando o texto é exatamente 14 dígitos ASCII ou exatamente a forma `NN.NNN.NNN/NNNN-NN`, os verificadores batem e os
    dígitos não são todos iguais. Caso contrário `False`.

    ### `cnpj_formatar(cnpj) -> str`
    De 14 dígitos ASCII para `NN.NNN.NNN/NNNN-NN`. Outra entrada: `ValueError`.

    ## Reais

    ### `formatar_real(valor, casas=2) -> str`
    Escreve `valor` (`int`, `float`, `Decimal` ou `str`) como `R$ 1.234,56`: `R$`, um espaço comum, grupos de três dígitos separados
    por ponto, vírgula decimal.

    * O arredondamento para `casas` casas segue a norma ABNT NBR 5891 (meio para o par): quando o resto é exatamente
      `5` seguido de zeros, arredonda-se para o dígito par mais próximo; `2.675` -> `R$ 2,68` (o 7 é ímpar, sobe), `2.665` ->
      `R$ 2,66` (o 6 é par, fica), `0.125` -> `R$ 0,12`, `0.135` -> `R$ 0,14`; com `casas=0`, `2.5` -> `R$ 2`, `3.5` -> `R$ 4`, `0.5`
      -> `R$ 0`. O cálculo usa `decimal.Decimal(str(valor))` sobre o valor absoluto.
    * Com `casas=0` não há vírgula. `casas < 0` é `ValueError`.
    * Valores negativos levam `-` antes do `R$` (`-R$ 1.234,50`). Se o resultado arredondado for zero, não se escreve o sinal
      (`-0.004` -> `R$ 0,00`).

    ### `parse_real(texto) -> Decimal`
    O contrário. Formato aceito (espaços nas pontas são ignorados): `-` opcional, `R$` opcional seguido de espaços opcionais, `-`
    opcional de novo (não pode haver os dois sinais), a parte inteira, e depois vírgula com **um ou dois** dígitos (centavos), opcional.
    A parte inteira é só dígitos (`5000`) ou agrupada corretamente com pontos: de um a três dígitos e depois um ou mais grupos de
    exatamente três (`1.234.567`). O ponto serve apenas de separador de milhar: `1.5`, `1.23`, `1..234`, `1.234.56` são inválidos. Com
    mais de duas casas depois da vírgula (`1,234`), vírgula sem dígitos (`5,`), vírgula repetida, texto extra (`5,00 reais`) ou sem dígitos,
    é `ValueError`.
''')

SRC = dd(r'''
    import re
    from decimal import ROUND_HALF_EVEN, Decimal

    _CPF_FMT = re.compile(r"[0-9]{3}\.[0-9]{3}\.[0-9]{3}-[0-9]{2}")
    _CNPJ_FMT = re.compile(r"[0-9]{2}\.[0-9]{3}\.[0-9]{3}/[0-9]{4}-[0-9]{2}")
    _CNPJ_W1 = (5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)
    _CNPJ_W2 = (6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)
    _REAL = re.compile(r"\s*(-?)\s*(?:R\$\s*)?(-?)\s*([0-9]{1,3}(?:\.[0-9]{3})+|[0-9]+)(?:,([0-9]{1,2}))?\s*")


    def _digits_of(texto: str, formato, tamanho: int):
        if formato.fullmatch(texto):
            texto = re.sub(r"[./-]", "", texto)
        if len(texto) != tamanho or not texto.isascii() or not texto.isdigit():
            return None
        return texto


    def _cpf_digits(nove: str) -> str:
        out = ""
        for k in (10, 11):
            s = sum(int(c) * (k - i) for i, c in enumerate(nove + out))
            r = (s * 10) % 11
            out += str(0 if r == 10 else r)
        return out


    def cpf_valido(cpf: str) -> bool:
        d = _digits_of(cpf, _CPF_FMT, 11)
        if d is None or len(set(d)) == 1:
            return False
        return _cpf_digits(d[:9]) == d[9:]


    def cpf_formatar(cpf: str) -> str:
        if len(cpf) != 11 or not cpf.isascii() or not cpf.isdigit():
            raise ValueError("CPF deve ter 11 digitos")
        return "%s.%s.%s-%s" % (cpf[:3], cpf[3:6], cpf[6:9], cpf[9:])


    def _cnpj_digit(base: str, pesos) -> str:
        r = sum(int(c) * w for c, w in zip(base, pesos)) % 11
        return str(0 if r < 2 else 11 - r)


    def cnpj_valido(cnpj: str) -> bool:
        d = _digits_of(cnpj, _CNPJ_FMT, 14)
        if d is None or len(set(d)) == 1:
            return False
        d1 = _cnpj_digit(d[:12], _CNPJ_W1)
        d2 = _cnpj_digit(d[:12] + d1, _CNPJ_W2)
        return d[12:] == d1 + d2


    def cnpj_formatar(cnpj: str) -> str:
        if len(cnpj) != 14 or not cnpj.isascii() or not cnpj.isdigit():
            raise ValueError("CNPJ deve ter 14 digitos")
        return "%s.%s.%s/%s-%s" % (cnpj[:2], cnpj[2:5], cnpj[5:8], cnpj[8:12], cnpj[12:])


    def formatar_real(valor, casas: int = 2) -> str:
        if casas < 0:
            raise ValueError("casas negativo")
        d = Decimal(str(valor))
        q = abs(d).quantize(Decimal(1).scaleb(-casas), rounding=ROUND_HALF_EVEN)
        inteiro, _, frac = format(q, "f").partition(".")
        grupos = []
        while len(inteiro) > 3:
            grupos.insert(0, inteiro[-3:])
            inteiro = inteiro[:-3]
        grupos.insert(0, inteiro)
        corpo = ".".join(grupos) + ("," + frac if frac else "")
        return ("-" if d < 0 and q != 0 else "") + "R$ " + corpo


    def parse_real(texto: str) -> Decimal:
        m = _REAL.fullmatch(texto)
        if not m or (m.group(1) and m.group(2)):
            raise ValueError("valor ilegivel: %r" % (texto,))
        value = Decimal(m.group(3).replace(".", "") + ("." + m.group(4) if m.group(4) else ""))
        return -value if (m.group(1) or m.group(2)) else value
''')

VISIBLE = dd('''
    import unittest
    from decimal import Decimal

    from docbr import cpf_valido, formatar_real, parse_real


    class Basico(unittest.TestCase):
        def test_cpf(self):
            self.assertTrue(cpf_valido("529.982.247-25"))

        def test_formatar(self):
            self.assertEqual(formatar_real(1234.56), "R$ 1.234,56")

        def test_parse(self):
            self.assertEqual(parse_real("R$ 5,00"), Decimal("5.00"))


    if __name__ == "__main__":
        unittest.main()
''')

HIDDEN = dd('''
    import unittest
    from decimal import Decimal

    from docbr import cnpj_formatar, cnpj_valido, cpf_formatar, cpf_valido, formatar_real, parse_real


    class Cpf(unittest.TestCase):
        def test_validos(self):
            for cpf in ("52998224725", "529.982.247-25", "11144477735", "111.444.777-35", "12345678909", "123.456.789-09",
                        "390.533.447-05", "168.995.350-09"):
                self.assertTrue(cpf_valido(cpf), cpf)

        def test_primeiro_ou_segundo_digito_errado(self):
            for cpf in ("529.982.247-26", "529.982.247-15", "529.982.247-35", "529.982.247-24", "12345678900", "12345678919"):
                self.assertFalse(cpf_valido(cpf), cpf)

        def test_digitos_iguais(self):
            for d in "0123456789":
                self.assertFalse(cpf_valido(d * 11), d)
            self.assertFalse(cpf_valido("111.111.111-11"))
            self.assertFalse(cpf_valido("000.000.000-00"))

        def test_pontuacao_e_tamanho(self):
            for cpf in ("", "5299822472", "529982247250", "529982247-25", "529.982.24725", "529 982 247 25", "529.982.247-250",
                        "529.982.247.25", "529,982,247-25", "5299.82.247-25", " 52998224725", "52998224725 ", "529.982.247-2"):
                self.assertFalse(cpf_valido(cpf), repr(cpf))

        def test_caracteres_estranhos(self):
            for cpf in ("٥٢٩٩٨٢٢٤٧٢٥", "５２９９８２２４７２５", "5299822472a", "529.982.247-2x", "abc.def.ghi-jk"):
                self.assertFalse(cpf_valido(cpf), repr(cpf))

        def test_resto_dez_vira_zero(self):
            # 168.995.350-09: o segundo dígito é 9 e o primeiro é 0
            self.assertTrue(cpf_valido("16899535009"))
            self.assertFalse(cpf_valido("16899535019"))
            self.assertFalse(cpf_valido("16899535099"))

        def test_formatar(self):
            self.assertEqual(cpf_formatar("52998224725"), "529.982.247-25")
            self.assertEqual(cpf_formatar("00000000000"), "000.000.000-00")
            self.assertEqual(cpf_formatar("12345678900"), "123.456.789-00")

        def test_formatar_erros(self):
            for cpf in ("", "5299822472", "529982247250", "529.982.247-25", "5299822472a", "٥٢٩٩٨٢٢٤٧٢٥"):
                with self.assertRaises(ValueError, msg=repr(cpf)):
                    cpf_formatar(cpf)


    class Cnpj(unittest.TestCase):
        def test_validos(self):
            for cnpj in ("11222333000181", "11.222.333/0001-81", "11444777000161", "11.444.777/0001-61", "33.000.167/0001-01",
                         "45.997.418/0001-53"):
                self.assertTrue(cnpj_valido(cnpj), cnpj)

        def test_digito_errado(self):
            for cnpj in ("11.222.333/0001-82", "11.222.333/0001-91", "11.222.333/0001-71", "11.222.333/0001-80", "45.997.418/0001-54"):
                self.assertFalse(cnpj_valido(cnpj), cnpj)

        def test_digitos_iguais(self):
            for d in "0123456789":
                self.assertFalse(cnpj_valido(d * 14), d)
            self.assertFalse(cnpj_valido("00.000.000/0000-00"))
            self.assertFalse(cnpj_valido("11.111.111/1111-11"))

        def test_forma_e_tamanho(self):
            for cnpj in ("", "1122233300018", "112223330001811", "11.222.333-0001/81", "11.222.333/0001-8", "11.222.333/0001-811",
                         "11222.333/0001-81", "11.222.333/000181", " 11222333000181", "11.222.333/0001 81", "11.222.333/0001-8x",
                         "１１２２２３３３０００１８１"):
                self.assertFalse(cnpj_valido(cnpj), repr(cnpj))

        def test_resto_menor_que_dois(self):
            # 45.997.418/0001-53 e 33.000.167/0001-01 exercitam o dígito 0 (resto 0 ou 1)
            self.assertTrue(cnpj_valido("33.000.167/0001-01"))
            self.assertFalse(cnpj_valido("33.000.167/0001-11"))
            self.assertFalse(cnpj_valido("33.000.167/0001-00"))

        def test_formatar(self):
            self.assertEqual(cnpj_formatar("11222333000181"), "11.222.333/0001-81")
            self.assertEqual(cnpj_formatar("00000000000000"), "00.000.000/0000-00")

        def test_formatar_erros(self):
            for cnpj in ("", "1122233300018", "112223330001811", "11.222.333/0001-81", "1122233300018x"):
                with self.assertRaises(ValueError, msg=repr(cnpj)):
                    cnpj_formatar(cnpj)


    class Formatar(unittest.TestCase):
        def test_grupos(self):
            casos = {0: "R$ 0,00", 5: "R$ 5,00", 999.99: "R$ 999,99", 1000: "R$ 1.000,00", 1234.56: "R$ 1.234,56",
                     1234567.89: "R$ 1.234.567,89", 1000000: "R$ 1.000.000,00", 12345: "R$ 12.345,00", 123456: "R$ 123.456,00",
                     10 ** 9: "R$ 1.000.000.000,00"}
            for valor, texto in casos.items():
                self.assertEqual(formatar_real(valor), texto, valor)

        def test_meio_para_o_par(self):
            self.assertEqual(formatar_real(2.675), "R$ 2,68")
            self.assertEqual(formatar_real(2.665), "R$ 2,66")
            self.assertEqual(formatar_real(0.125), "R$ 0,12")
            self.assertEqual(formatar_real(0.135), "R$ 0,14")
            self.assertEqual(formatar_real(1.005), "R$ 1,00")
            self.assertEqual(formatar_real(1.015), "R$ 1,02")
            self.assertEqual(formatar_real("2.675"), "R$ 2,68")
            self.assertEqual(formatar_real(Decimal("0.125")), "R$ 0,12")

        def test_sem_casas(self):
            self.assertEqual(formatar_real(2.5, 0), "R$ 2")
            self.assertEqual(formatar_real(3.5, 0), "R$ 4")
            self.assertEqual(formatar_real(0.5, 0), "R$ 0")
            self.assertEqual(formatar_real(1.5, 0), "R$ 2")
            self.assertEqual(formatar_real(1234.5, 0), "R$ 1.234")
            self.assertEqual(formatar_real(1235.5, 0), "R$ 1.236")
            self.assertEqual(formatar_real(2.4, 0), "R$ 2")
            self.assertEqual(formatar_real(2.6, 0), "R$ 3")

        def test_outras_casas(self):
            self.assertEqual(formatar_real(12, 3), "R$ 12,000")
            self.assertEqual(formatar_real(2.675, 1), "R$ 2,7")
            self.assertEqual(formatar_real(0.25, 1), "R$ 0,2")
            self.assertEqual(formatar_real(0.35, 1), "R$ 0,4")
            self.assertEqual(formatar_real(1234.5678, 3), "R$ 1.234,568")

        def test_resto_diferente_de_cinco_exato(self):
            self.assertEqual(formatar_real(0.1251), "R$ 0,13")
            self.assertEqual(formatar_real(0.1249), "R$ 0,12")
            self.assertEqual(formatar_real(2.6651), "R$ 2,67")
            self.assertEqual(formatar_real(2.6650001), "R$ 2,67")

        def test_negativos(self):
            self.assertEqual(formatar_real(-1234.5), "-R$ 1.234,50")
            self.assertEqual(formatar_real(-0.015), "-R$ 0,02")
            self.assertEqual(formatar_real(-1234.5, 0), "-R$ 1.234")
            self.assertEqual(formatar_real(-999), "-R$ 999,00")

        def test_zero_negativo(self):
            self.assertEqual(formatar_real(-0.004), "R$ 0,00")
            self.assertEqual(formatar_real(-0.005), "R$ 0,00")
            self.assertEqual(formatar_real(-0.4, 0), "R$ 0")
            self.assertEqual(formatar_real(-0.006), "-R$ 0,01")

        def test_casas_negativas(self):
            with self.assertRaises(ValueError):
                formatar_real(1, -1)


    class Parse(unittest.TestCase):
        def test_formas(self):
            for texto, valor in (("R$ 1.234,56", "1234.56"), ("1.234,56", "1234.56"), ("1234,56", "1234.56"), ("R$1.234", "1234"),
                                 ("5", "5"), ("5,5", "5.5"), ("0,05", "0.05"), ("12.345.678,9", "12345678.9"), ("1.000", "1000"),
                                 ("  R$   7,00  ", "7.00"), ("R$ 100.000.000,00", "100000000.00"), ("999.999", "999999")):
                self.assertEqual(parse_real(texto), Decimal(valor), texto)

        def test_negativos(self):
            self.assertEqual(parse_real("-R$ 5,00"), Decimal("-5.00"))
            self.assertEqual(parse_real("R$ -5,00"), Decimal("-5.00"))
            self.assertEqual(parse_real("-5"), Decimal("-5"))
            self.assertEqual(parse_real("- R$ 1.000,5"), Decimal("-1000.5"))
            for texto in ("--5", "-R$ -5", "- R$ -5,00"):
                with self.assertRaises(ValueError, msg=texto):
                    parse_real(texto)

        def test_exato(self):
            self.assertEqual(str(parse_real("1.000,50")), "1000.50")
            self.assertEqual(str(parse_real("R$ 12,3")), "12.3")
            self.assertIsInstance(parse_real("1"), Decimal)

        def test_ponto_so_de_milhar(self):
            for texto in ("1.5", "1.23", "12.34", "1.2345", "1..234", "1.234.56", "1234.567", ".500", "1.234.", "12.3456.789"):
                with self.assertRaises(ValueError, msg=texto):
                    parse_real(texto)

        def test_centavos_no_maximo_dois(self):
            for texto in ("1,234", "1,2345", "5,000", "0,001"):
                with self.assertRaises(ValueError, msg=texto):
                    parse_real(texto)

        def test_ilegiveis(self):
            for texto in ("", "   ", "R$", "R$ ", "abc", "5,", "1,2,3", "5,00 reais", "R$ R$ 5", "1.000,", "$5", "5 000", ",5", "5,a"):
                with self.assertRaises(ValueError, msg=repr(texto)):
                    parse_real(texto)

        def test_ida_e_volta(self):
            for valor in ("7.50", "1234.56", "1000000.00"):
                self.assertEqual(parse_real(formatar_real(Decimal(valor))), Decimal(valor))
                self.assertEqual(parse_real(formatar_real(-Decimal(valor))), -Decimal(valor))
            self.assertEqual(parse_real(formatar_real(0)), Decimal("0"))


    if __name__ == "__main__":
        unittest.main()
''')

LIB = Lib(
    name="docbr", lang="python", title="`docbr`",
    blurb="O cadastro de clientes de uma loja virtual usa estas funções para validar CPF e CNPJ e para escrever valores em reais.",
    files={"docbr/__init__.py": "from .core import *  # noqa: F401,F403\n", "docbr/core.py": SRC,
           "README.md": README, ".gitignore": "__pycache__/\n*.pyc\n"},
    visible_tests={"tests/test_basico.py": VISIBLE},
    hidden_tests={"tests/test_completo.py": HIDDEN},
    mutate=["docbr/core.py"], difficulty=3, tags=["i18n", "validation", "checksum", "money"],
    probes=[
        'cpf_valido("111.111.111-11")',
        'cpf_valido("529.982.247-26")',
        'cpf_valido("529982247-25")',
        'cpf_valido("16899535009")',
        'cpf_formatar("52998224725")',
        'cnpj_valido("11.222.333/0001-81")',
        'cnpj_valido("33.000.167/0001-01")',
        'cnpj_valido("11.222.333-0001/81")',
        'cnpj_formatar("11222333000181")',
        'formatar_real(2.675)',
        'formatar_real(2.665)',
        'formatar_real(2.5, 0)',
        'formatar_real(-0.004)',
        'parse_real("1.5")',
        'parse_real("1,234")',
        'parse_real("R$ -5,00")',
    ],
    probe_import="from decimal import Decimal\nfrom docbr import *",
)

register_native(LIB, "pt", "fix-docbr", n=9,
                summary="native: injected bugs in a Brazilian CPF/CNPJ/real-formatting library, reports in Portuguese")

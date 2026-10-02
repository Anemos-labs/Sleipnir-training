"""Derived answer-mode chat tasks in Spanish (Mexican register: decimal point) and Chinese."""
from fx import family

from ._derive import derive, take

ES = [
    ("chat-quick-math-03-change", "01-vuelto-compra", "typos",
     "oye una consulta rápida: compré tres cosas de $7.76, $10.84 y $7.42 y pagué con un billete de $50. "
     "¿cuánto me tienen que dar de cambio? (con punto decimal porfa, ando con prisa)"),
    ("chat-quick-time-01-add", "02-reunion-termina", "polite",
     "Hola, buenas tardes. Tengo una reunión que empieza a las 12:10 y dura 45 minutos, ¿a qué hora termina? "
     "Contéstame en formato HH:MM por favor. ¡Gracias!"),
    ("chat-quick-format-03-snake", "03-camelcase", "terse",
     "pásame `§0` a camelCase, lo necesito ya"),
    ("chat-quick-list-05-average", "04-promedio-mercado", "informal",
     "mira, esta es la lista de precios del puesto del mercado:\n\n```\n¶0\n```\n\n"
     "¿cuál es el precio promedio? con dos decimales y con punto, gracias"),
    ("chat-bill-split-02-casa-4p", "05-cuenta-cena", "long",
     "Ayuda, siempre soy yo la que termina sacando las cuentas de las cenas y ya no puedo más. "
     "Esto es el ticket, lo pasé a mano:\n\n"
     "```\nCasa Mirabel\n\nCormac: pulpo a la parrilla 18.90\nThandi: patatas bravas 7.80, pan con tomate 5.20\n"
     "Leila: limonada con gas 4.10\nStellan: limonada con gas 4.10\n"
     "Compartido: pan con tomate 5.20 (entre Cormac, Stellan, Thandi)\n```\n\n"
     "La propina es del 18% sobre lo que consumió cada quien (sin impuestos) y la paga cada uno. "
     "El monto de cada persona se redondea al centavo más cercano (las mitades hacia arriba); "
     "si el total se desvía un centavo o dos, no pasa nada.\n\n"
     "¿Cuánto paga cada quien? Una línea por persona, con el monto a dos decimales y con punto decimal."),
    ("chat-cron-next-02-d2-0", "06-cron-plantas", "long",
     "Hola, te cuento (bueno, no es tan corto): heredé un crontab y una de las líneas corre mi bot que me recuerda "
     "regar las plantas. La línea es `§0` y el reloj del servidor está en UTC.\n\n"
     "El día de la semana va de 0 = domingo, 1 = lunes ... 6 = sábado; los rangos son inclusivos y `§1` o `§2` "
     "significa cada s-ésimo valor empezando desde el inicio del rango.\n\n"
     "Ahorita son las 2027-08-23 10:53 UTC. ¿Cuáles son las próximas 3 veces que se va a ejecutar? "
     "Una por línea, con el formato YYYY-MM-DD HH:MM."),
    ("chat-code-output-03-py-one-shot-d2", "07-generador-agotado", "terse",
     "una duda de Python 3.11 sobre un generador de lecturas escaladas:\n\n```python\n¶0\n```\n\n"
     "¿qué imprime exactamente? gracias"),
    ("chat-recipe-scale-02-scale2-rye", "08-pan-centeno", "informal",
     "oigan, el viernes hay comida compartida en la oficina y prometí llevar mi pan de centeno con alcaravea. "
     "Esta es la receta que siempre uso:\n\n"
     "```\npan de centeno con alcaravea (para 16 personas)\n- 400 ml de agua\n- 400 g de harina de fuerza\n"
     "- 2 cdtas de semillas de alcaravea\n- 1 cda de melaza\n- 2 cdtas de sal\n```\n\n"
     "¿cuánta agua y cuánta harina de fuerza necesito para 13? Solo los números, en g/ml."),
    ("chat-meeting-slot-01-3p-d3", "09-llamada-equipo", "long",
     "Necesito encontrar horario para una llamada el sábado 13 de marzo de 2027 (fecha UTC) con el equipo de abajo. "
     "A nadie se le puede pedir que trabaje fuera de su horario local, y la llamada tiene que caber completa dentro "
     "de la ventana de trabajo de todos y no chocar con nada que tengan agendado.\n\n"
     "```\nDaniyar (desarrollador backend, Johannesburgo, UTC+2): trabaja 09:00-17:00 hora local\n"
     "Bram (desarrollador backend, Daca, UTC+6): trabaja 09:00-17:00 hora local\n"
     "Wendell (líder de diseño, Nairobi, UTC+3): trabaja 09:00-17:00 hora local\n```\n\n"
     "¿Cuál es el horario más temprano de 45 minutos que les funciona a todos, empezando en un cuarto de hora? "
     "Dame la hora de inicio en UTC como HH:MM UTC, y también la hora de inicio en el reloj local de Daniyar como HH:MM."),
    ("chat-earlier-mistake-01-stock", "10-error-previo-tazas", "paste",
     "(te pego la conversación de esta mañana para que la retomes)\n\n"
     "```\nYo: Tengo 6 cajas de 24 tazas y el sábado vendí 18 tazas. ¿Cuántas tazas me quedan?\n\n"
     "Tú: 6 cajas x 24 = 144 tazas. 144 - 18 = 136. Te quedan 136 tazas.\n\n"
     "Yo: Perfecto. En el formulario del seguro cada taza vale $4.75. ¿Cuál es el valor del stock de las tazas que "
     "quedan, y cuántas tazas son otra vez?\n```\n\n"
     "Contesta la última pregunta de esa conversación."),
    ("chat-bitflags-08-greenhouse-d5", "11-byte-invernadero", "terse",
     "estoy haciendo un script para un hub de invernadero. El byte de estado tiene estos bits (según la hoja del fabricante):\n\n"
     "```\n¶0\n```\n\n"
     "el byte marca 0x7d. después aplico estos cambios en orden: toggle FAN; set MIST; clear MIST; clear HEATER. "
     "¿Cuál es el byte final en hexadecimal (dos dígitos, escrito como 0x2c) y en decimal? "
     "Además, cuántos flags quedan activados al final? (contesta con el número seguido de la palabra flags, ej. '3 flags')"),
]


@family("i18n-es-chat", category="i18n", lang="text", kind="chat", n=len(ES), mode="answer",
        summary="derived: chat questions with computed answers, Spanish (Mexican register)")
def es_chat(rng, n):
    for src, slug, style, prompt in take(ES, n):
        yield derive(src, prompt, slug, "es", style=style)


ZH = [
    ("chat-quick-math-09-markup", "01-markup-price", "chatty",
     "早！一件东西标价200美元，店家又在上面加价50%，现在多少钱？我问了群里，结果三个人三种答案外加一个表情包，只好来问你了，谢谢！"),
    ("chat-quick-snippet-03-ja", "02-js-map-join", "learner",
     "刚开始学 JS，这段代码的输出把我绕晕了，输出到底是什么？\n\n```javascript\n¶0\n```\n\n谢谢大佬"),
    ("chat-log-read-01-count5xx-kv", "03-count-5xx", "paste",
     "在吗？下面是今天早上结账服务出事故时的一段日志，帮我看一下，时间都是 UTC。\n\n```\n¶0\n```\n\n"
     "这些请求里有多少条的状态码是 5xx（500 及以上）？"),
    ("chat-timesheet-sum-02-dot-d2", "04-timesheet-notes", "chatty",
     "我习惯把工时随手记在手机备忘录里，现在要算本周的总工时好开发票。对了，打印机又卡纸了，不过那是另一回事。\n\n"
     "```\n周二: 8.15-13.05, 13.40-16.40\n周六: 9.45-13.45\n```\n\n"
     "总共工作了多长时间？请写成 H:MM（例如 31:05）。"),
    ("chat-sql-reading-01-count_null", "05-sql-null-trap", "quiz",
     "新同事出了一道 SQL 题，我觉得是个陷阱题。（按 SQLite 的语义）\n\n```\n¶0\n```\n\n"
     "这条查询会返回什么？按顺序给我三个数字（平均值保留一位小数）。\n（请直接写数字，不要千分位分隔符。）"),
    ("chat-regex-match-01-count", "06-regex-vol", "terse",
     "写日志脱敏脚本，想先手算一下正则对不对（Python 3.11 的 Pattern，区分大小写）：`§0`\n\n```\n¶0\n```\n\n"
     "`§1` 会在上面带编号的行里命中多少行？最后一个命中的行号是多少？每行内容就是引号之间的文本（如果某行末尾有空格，也算内容的一部分）。"),
    ("chat-currency-trip-03-chfcad-d3", "07-fx-round-trip", "long",
     "你好，容我啰嗦几句：假期回来后我想算算来回换汇到底亏了多少。出发前我把 800.00 CHF 换成了 CAD。"
     "我姐说我想多了，大概确实如此。\n\n"
     "去程：1 CHF 兑 0.9852 CAD，固定手续费 3.00 CHF（先从 CHF 里扣掉），结果向下取整到分。"
     "我在那边花了 392.00 CAD，剩下的按 1 CAD 兑 0.9740 CHF 换了回来，回程不收手续费，同样向下取整到分。\n\n"
     "请问我最后手里有多少 CHF？"),
    ("chat-shell-pipeline-02-top3-team-d2", "08-pipeline-output", "runbook",
     "想请教一下，下面这条管道对工作目录里的 orders.csv 会输出什么？它出自一份运维手册，我不想踩坑。\n\n"
     "```sh\n¶0\n```\n\n请给出完整输出，所有行都要。（uniq -c 前面的空格不用管。）"),
    ("chat-premise-timeline-04-240-3", "09-incident-timeline", "long",
     "事后复盘。日志 A 来自搜索前端，时间是 UTC；日志 B 来自索引器，时间戳是本地时间（UTC+4），而且已知它的时钟快了 3 分钟。"
     "经理的说法是这次故障是发布引起的，理由是日志 B 里的第一次失败出现在日志 A 里的发布之后。\n\n"
     "```\n¶0\n```\n\n"
     "统一换算到同一条 UTC 时间线上：日志 B 里的第一次失败发生在发布开始之前还是之后，相差多少分钟（给出分钟数）？"
     "这次首次失败的 UTC 时间是几点（HH:MM:SS）？"),
    ("chat-subnet-math-08-summarise", "10-route-summary", "terse",
     "路由器要给这几个网段配一条汇总路由：192.168.44.0/24、192.168.45.0/24、192.168.46.0/24、192.168.47.0/24。"
     "能把它们全部覆盖的最小的单个 CIDR 块是什么？这个块里一共有多少个地址？\n（请直接写数字，不要千分位分隔符。）"),
    ("chat-date-offset-08-chain", "11-frame-shipping", "long",
     "我在 2028 年 12 月 3 日（星期日）订了一个定制相框。店家说需要 8 天准备，之后在第一个周一、周三或周五发货（当天也算）。"
     "运输要 7 天，从发货日起算，但快递周末不派送，落在周末的送达会顺延到下周一。"
     "请问它哪天发货、哪天送达？两个日期都写成 YYYY-MM-DD，先写发货日期。谢谢！"),
]


@family("i18n-zh-chat", category="i18n", lang="text", kind="chat", n=len(ZH), mode="answer",
        summary="derived: chat questions with computed answers, Simplified Chinese")
def zh_chat(rng, n):
    for src, slug, style, prompt in take(ZH, n):
        yield derive(src, prompt, slug, "zh", style=style)

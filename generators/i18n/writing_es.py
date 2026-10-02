"""Native constrained-writing tasks in Spanish (inverted punctuation, accents, lengths, bullet lists)."""
from fx import family

from ._writing import writing_task

TERMS = ".!?"

PH = {
    "sentences": lambda p: ("exactamente %d frases" % p["min"] if p["min"] == p["max"] else "entre %d y %d frases" % (p["min"], p["max"]))
    + " (cada frase acaba en punto, en cierre de exclamación o en cierre de interrogación)",
    "words": lambda p: "entre %d y %d palabras en total" % (p["min"], p["max"]),
    "include": lambda p: "tiene que aparecer tal cual (con esas mayúsculas y tildes): " + ", ".join("«%s»" % w for w in p["words"]),
    "exclude": lambda p: "no uses estas palabras: " + ", ".join("«%s»" % w for w in p["words"]),
    "es_inverted": lambda p: "respeta la ortografía española: toda pregunta y toda exclamación lleva su signo de apertura (¿ ¡) además del de cierre, y "
    "tiene que haber al menos una pregunta",
    "bullets": lambda p: "una lista de exactamente %d viñetas, cada una en su línea y empezando por «- » (nada de texto fuera de la lista, salvo el título si lo hay)" % p["n"],
    "title": lambda p: "la primera línea es un título que empieza por «# »",
}


def render(constraints):
    return "\n".join("- " + PH[c["kind"]](c) for c in constraints if c["kind"] in PH)


def sent(lo, hi):
    return {"kind": "sentences", "min": lo, "max": hi, "terms": TERMS}


SCENARIOS = [
    # (slug, d, intro, facts, path, constraints, solution)
    ("01-feria-del-libro", 2,
     "Necesito un aviso corto para el tablón del barrio sobre la feria del libro. Los datos están en `datos.txt`.",
     "Evento: Feria del Libro de Barrio\nFecha: sábado 14 de junio\nHora: de 10:00 a 20:00\nLugar: Plaza Mayor\nEntrada: libre\n",
     "aviso.md",
     [sent(3, 4), {"kind": "words", "min": 40, "max": 70}, {"kind": "include", "words": ["14 de junio", "Plaza Mayor"]},
      {"kind": "exclude", "words": ["gratis"]}, {"kind": "es_inverted"}],
     "¿Te gustan los libros usados y las historias nuevas? El sábado 14 de junio abrimos la Feria del Libro de Barrio en la Plaza Mayor, de diez de la mañana "
     "a ocho de la tarde. Habrá puestos de editoriales pequeñas, un rincón para niños y una mesa de intercambio donde cada uno puede traer un libro y llevarse otro. "
     "La entrada es libre: ¡te esperamos!"),
    ("02-corte-de-agua", 2,
     "Redacta el mensaje que voy a mandar al grupo de vecinos por el corte de agua de la semana que viene (datos en `datos.txt`).",
     "Motivo: reparación de una tubería\nDía: jueves\nHorario: de 09:00 a 18:00\nCalles: Olmo y Sauce\nContacto: portería\n",
     "mensaje.md",
     [sent(3, 5), {"kind": "words", "min": 30, "max": 60}, {"kind": "include", "words": ["jueves", "18:00"]},
      {"kind": "exclude", "words": ["lamentablemente"]}, {"kind": "es_inverted"}],
     "Buenas tardes, vecinos. El jueves habrá corte de agua en las calles Olmo y Sauce por la reparación de una tubería, desde las 09:00 hasta las 18:00. "
     "Les recomendamos llenar algún recipiente por la mañana. ¿Alguien necesita ayuda con personas mayores? Pueden avisar en portería."),
    ("03-excursion-escolar", 3,
     "Soy tutora de 4.º y tengo que avisar a las familias de la excursión. Resume lo importante de `datos.txt` en una nota.",
     "Destino: Granja Escuela El Prado\nSalida: martes 7 de octubre, 08:15, desde el colegio\nVuelta: 17:30\nQué llevar: almuerzo, gorra, botella de agua\nTransporte: autobús\n"
     "Hora de recogida del autobús en la granja: 10:30\n",
     "nota.md",
     [{"kind": "title"}, {"kind": "bullets", "n": 5}, {"kind": "include", "words": ["autobús", "10:30"]}, {"kind": "words", "min": 28, "max": 70}],
     "# Excursión a la Granja Escuela El Prado\n- Salimos el martes 7 de octubre a las 08:15 desde el colegio.\n- Viajamos en autobús y volvemos a las 17:30.\n"
     "- Traed almuerzo, gorra y una botella de agua.\n- El autobús nos espera en la granja a las 10:30 si algún niño se tiene que ir antes.\n"
     "- Cualquier duda, escribidme por la agenda escolar."),
    ("04-oferta-panaderia", 2,
     "Hazme el texto de un cartel para la puerta de la panadería: hay una oferta esta semana (ver `datos.txt`). Que se lea rápido.",
     "Negocio: Panadería La Espiga\nOferta: 2 por 1 en bollería\nDías: lunes a miércoles\nHorario: hasta las 11:00\n",
     "cartel.md",
     [{"kind": "words", "min": 18, "max": 40}, {"kind": "include", "words": ["panadería", "2 por 1"]}, {"kind": "exclude", "words": ["barato", "barata"]},
      {"kind": "es_inverted"}, sent(2, 4)],
     "¡Hoy toca desayuno en la panadería La Espiga! De lunes a miércoles tenemos 2 por 1 en toda la bollería, hasta las 11:00. ¿Qué vas a llevarte primero?"),
    ("05-cancelar-reserva", 3,
     "Escribe un correo formal (solo el cuerpo del mensaje) para cancelar una reserva de hotel. Los datos de la reserva están en `datos.txt`.",
     "Hotel: Hotel Mirador del Sur\nReserva: 2 noches, del 12 al 14 de noviembre\nTitular: Ana Ruiz\nMotivo: cambio de planes laborales\nNúmero de reserva: HR-4471\n",
     "correo.md",
     [sent(4, 4), {"kind": "words", "min": 45, "max": 85}, {"kind": "include", "words": ["reserva", "cancelación", "HR-4471"]},
      {"kind": "exclude", "words": ["no puedo", "problema"]}, {"kind": "es_inverted"}],
     "Estimados señores: les escribo para solicitar la cancelación de la reserva HR-4471, a nombre de Ana Ruiz, para dos noches del 12 al 14 de noviembre. "
     "Por un cambio en mis planes de trabajo no podré viajar en esas fechas. ¿Podrían indicarme si la cancelación tiene algún coste y confirmarme la recepción de este mensaje? "
     "Agradezco de antemano su atención y quedo a la espera de su respuesta."),
    ("06-resena-pelicula", 3,
     "Quiero una mini-reseña de la peli para mi blog, con título. Datos en `datos.txt`.",
     "Película: El faro de Lía\nDirector: Mateo Vidal\nAño: 2023\nOpinión: bonita fotografía, final algo lento\n",
     "resena.md",
     [{"kind": "title"}, sent(4, 4), {"kind": "words", "min": 30, "max": 70}, {"kind": "include", "words": ["director", "El faro de Lía"]},
      {"kind": "es_inverted"}, {"kind": "exclude", "words": ["aburrida"]}],
     "# El faro de Lía\nEl director Mateo Vidal firma en 2023 una película de fotografía preciosa, con un mar que casi se puede oler. "
     "El final se alarga un poco más de lo necesario, pero compensa por la sensibilidad con la que cuenta la historia de Lía. ¿Merece la pena? Sin duda, si disfrutas de las películas tranquilas."),
    ("07-montaje-estanteria", 4,
     "Necesito las instrucciones de montaje de una estantería en forma de lista, pensadas para quien nunca ha montado un mueble. Piezas y herramientas en `datos.txt`.",
     "Mueble: estantería Pino de 4 baldas\nPiezas: 2 laterales, 4 baldas, 1 trasera, 16 tornillos, 8 tacos\nHerramientas: destornillador de estrella, martillo de goma\nTiempo: unos 45 minutos\n",
     "montaje.md",
     [{"kind": "bullets", "n": 5}, {"kind": "include", "words": ["tornillos", "laterales"]}, {"kind": "exclude", "words": ["fácil", "sencillo"]},
      {"kind": "words", "min": 40, "max": 95}, {"kind": "es_inverted"}],
     "- Coloca los dos laterales en el suelo, uno frente al otro, y comprueba que tienes los 16 tornillos y los 8 tacos a mano.\n"
     "- Inserta los tacos en los agujeros de los laterales con ayuda del martillo de goma.\n"
     "- Atornilla la primera balda entre los laterales con el destornillador de estrella, sin apretar del todo.\n"
     "- Repite con las otras tres baldas y después aprieta todos los tornillos con calma.\n"
     "- ¿Se tambalea la estantería? Entonces fija la trasera con los tornillos restantes antes de ponerla de pie."),
]


@family("i18n-es-write-notices", category="i18n", lang="text", kind="feature", n=len(SCENARIOS), mode="fixture",
        summary="native: Spanish constrained-writing tasks (¿¡ pairs, tildes, lengths, bullet lists) checked by a hidden script")
def es_write(rng, n):
    voices = [
        "{intro}\n\nCondiciones:\n{rules}\n\nGuárdalo en `{path}`.",
        "{intro} Reglas del texto:\n{rules}\nEl resultado va en `{path}`, por favor.",
        "{intro}\n\n{rules}\n\n(Escríbelo en `{path}`.)",
    ]
    for i, (slug, d, intro, facts, path, constraints, solution) in enumerate(SCENARIOS[:n]):
        prompt = voices[i % 3].format(intro=intro, rules=render(constraints), path=path)
        yield writing_task(slug, d, prompt, {"datos.txt": facts}, path, constraints, solution, ["es"], {"prompt_lang": "es", "constraints": [c["kind"] for c in constraints]})

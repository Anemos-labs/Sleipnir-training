"""Derived tasks: feature requests in Brazilian Portuguese, SQL/data requests in Italian."""
from fx import family

from ._derive import derive, take

PT = [
    ("feature-py-kilnplan-01-peak-temp", "01-kiln-peak", "casual",
     "Fala, preciso de uma coisa nova no kilnplan: `§0` tem que devolver o maior `§1` entre os segmentos do programa "
     "(um int). Os testes que já existem precisam continuar passando."),
    ("feature-rb-gigcal-10-search", "02-gigcal-busca", "short",
     "Oi! Tem uma nota de design em `docs/requests/search.md` pedindo uma mudança no gigcal. "
     "Implementa o que ela pede, por favor."),
    ("feature-rb-stowbox-10-grace", "03-stowbox-carencia", "casual",
     "Pessoal, preciso de um ajuste no stowbox: um aluguel liberado até 10 minutos depois do início "
     "(`§0`, o que inclui 0) não custa nada, ou seja, o `§1` do recibo é 0. A partir do minuto 11 a cobrança "
     "continua como antes. Sem dependências novas, por favor."),
    ("feature-js-stallcart-06-tax", "04-stallcart-imposto", "notes",
     "stallcart: o que ficou combinado na reunião de planejamento.\n\n1. Imposto sobre vendas\n"
     "   - A opção `Cart` `taxBp` é a alíquota em basis points (1 bp = 0,01 %; `1250` significa 12,5 %), um inteiro "
     "não negativo, padrão 0. Qualquer outro valor faz o construtor lançar um `RangeError`.\n"
     "   - `cart.tax()` é o imposto em centavos sobre o subtotal, arredondado para o centavo mais próximo "
     "(metade para cima) uma única vez para o carrinho inteiro, não por linha. `cart.total()` é `subtotal() + tax()`."),
    ("feature-py-pollroom-02-tiebreak", "05-pollroom-desempate", "polite",
     "Dá pra pegar a mudança descrita em `docs/requests/tiebreak.md`? Aquela nota é a especificação completa; "
     "o README explica como as coisas funcionam hoje. Atualiza o README também, por favor."),
    ("feature-go-tallybook-01-entries-for", "06-tallybook-entries", "short",
     "Existe uma nota de design em `docs/requests/entries-for.md` com uma mudança para o tallybook. "
     "Implemente o que ela pede e mantenha os testes existentes passando."),
    ("feature-java-unitconv-09-temperature", "07-unitconv-temperatura", "formal",
     "Você consegue implementar a mudança descrita em `docs/requests/temperature.md`? A nota é a especificação completa e "
     "o README explica o funcionamento atual. O comportamento existente não pode mudar para quem não usar a novidade."),
    ("feature-py-ferrydesk-14-pricing", "08-ferrydesk-precos", "formal",
     "Por favor, implemente a mudança descrita em `docs/requests/pricing.md`. Essa nota é a especificação completa; "
     "o README cobre como as coisas funcionam hoje. Sem novas dependências."),
    ("feature-js-stallcart-08-plugins-currency", "09-stallcart-plugins", "boss",
     "A mudança que precisamos entregar está descrita em `docs/requests/plugins-currency.md`. A nota é a especificação "
     "completa e o README cobre o que já existe. Prioridade alta, é a última peça da release."),
]


@family("i18n-pt-feature", category="i18n", lang="mixed", kind="feature", n=len(PT), mode="fixture",
        summary="derived: feature requests in Brazilian Portuguese (python, ruby, js, go, java), d1-d5")
def pt_feature(rng, n):
    for src, slug, style, prompt in take(PT, n):
        yield derive(src, prompt, slug, "pt", style=style)


IT = [
    ("data-greenhouse-log-01-zones-by-crop", "01-zone-per-coltura", "chatty",
     "Ciao! Mi serve l'elenco di tutte le zone con la loro coltura, l'area e il numero di valvole. "
     "Colonne: nome della zona, coltura, area_m2, valvole. Ordina per area decrescente e poi per nome della zona.\n\n"
     "Restituisci le colonne `§0`, `§1`, `§2`, `§3`, in quest'ordine."),
    ("data-cheese-cave-02-never-checked", "02-forme-mai-controllate", "terse",
     "Quali forme non sono mai state controllate e non sono ancora vendute? Voglio id della forma, id del lotto e "
     "scaffale, ordinati per id della forma.\n\nColonne, in quest'ordine: `§0`, `§1`, `§2`."),
    ("data-meter-readings-02-latest-reading", "03-ultima-lettura", "formal",
     "L'ultima lettura di ogni contatore (data più recente; a parità vince l'id lettura più alto): seriale, data, "
     "valore e fonte. I contatori senza nessuna lettura non vanno elencati. Ordina per seriale.\n\n"
     "Il risultato deve avere esattamente queste colonne, in quest'ordine: `§0`, `§1`, `§2`, `§3`."),
    ("data-clinic-slots-13-fix-free-slot-count", "04-slot-liberi-bug", "bugfix",
     "`§0` conta gli slot liberi per medico, ma considera occupato anche uno slot con un appuntamento *annullato*, e i "
     "medici senza nessuno slot libero spariscono dal risultato. Sistemala: per ogni medico, il numero di slot liberi "
     "(nessun appuntamento non annullato) tra tutti i suoi slot, 0 se non ce ne sono. Colonne: nome del medico, slot "
     "liberi. Ordine: slot liberi decrescente, poi nome.\n\nColonne in output: `§1`, `§2` (in quest'ordine)."),
    ("data-ferry-timetable-08-overbooked-sailings", "05-corse-overbooking", "formal",
     "Trova le corse (programmate o effettuate, non quelle cancellate) in cui le prenotazioni non cancellate sommano "
     "più passeggeri a piedi o più auto di quanto la nave possa portare. Mostra di quanto viene superato ciascun "
     "limite, con 0 per un limite rispettato. Ordina per id della corsa.\n\n"
     "Colonne, in quest'ordine: `§0`, `§1`, `§2`, `§3`."),
    ("data-etl-timeseries-03-forward-fill-days", "06-etl-giorni-mancanti", "short",
     "Scrivi `etl.py`: deve riempire i giorni mancanti della serie giornaliera delle precipitazioni in `daily.csv` "
     "riportando avanti l'ultimo valore. Le regole sono nel README.md."),
    ("data-cheese-cave-09-humidity-excursions", "07-escursioni-umidita", "detailed",
     "Escursioni di umidità: per ogni forma, trova le serie di controlli consecutivi (in ordine di data, a parità per "
     "id del controllo) con umidità fuori dall'intervallo da 82 a 88, e riporta le serie di 3 o più controlli: id della "
     "forma, data del primo controllo della serie, data dell'ultimo e numero di controlli. Ordina per id della forma e "
     "poi per data iniziale.\n\nColonne di output: `§0`, `§1`, `§2`, `§3` (in quest'ordine)."),
    ("data-clinic-maintenance-04-merge-duplicate-patients", "08-pazienti-doppi", "ticket",
     "Alcuni pazienti sono stati inseriti due volte: stessi `§0` e `§1` sotto due id diversi. Per ogni gruppo di questo "
     "tipo tieni il paziente con il `§2` più basso, sposta su di lui tutti i suoi appuntamenti e le voci della lista "
     "d'attesa, ed elimina le altre copie. Scrivi `§3`."),
    ("data-expert-greenhouse-01-dry-episodes-hysteresis", "09-episodi-secchezza", "detailed",
     "La regola del coltivatore per un *episodio di secchezza* ha isteresi. Scorri le letture di ogni zona in ordine di "
     "tempo (a parità per id della lettura). Una zona è **secca** dalla prima lettura sotto il 30 percento di umidità e "
     "resta secca finché non arriva una lettura di **40 o più**; le letture tra 30 e 39.9 non cambiano nulla (anche una "
     "lettura sotto 30 quando la zona è già secca non cambia nulla). Prima della prima lettura sotto 30 o di almeno 40 "
     "la zona non è secca. Riporta ogni episodio: nome della zona, `§0` della lettura che l'ha avviato, `§1` della "
     "lettura che l'ha concluso (NULL se la zona era ancora secca all'ultima lettura) e l'umidità minima tra le letture "
     "dall'inizio fino alla lettura finale esclusa. Ordina per nome della zona e poi per inizio.\n\n"
     "Restituisci le colonne `§2`, `§3`, `§4`, `§5`, in quest'ordine."),
]


@family("i18n-it-data", category="i18n", lang="mixed", kind="feature", n=len(IT), mode="fixture",
        summary="derived: SQL query requests, a query fix and an ETL script in Italian, d1-d5")
def it_data(rng, n):
    for src, slug, style, prompt in take(IT, n):
        yield derive(src, prompt, slug, "it", style=style)

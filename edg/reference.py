"""Static reference data: inflation, FX anchors, macro shocks, names, holidays.

Inflation and FX values are approximate annual figures used to give the synthetic
data a believable shape. They are not meant for financial analysis.
"""

YEARS = list(range(1995, 2027))

# Annual consumer-price inflation (%), roughly matching the real history per region.
INFLATION = {
    "US": [2.5, 3.3, 1.7, 1.6, 2.7, 3.4, 1.6, 2.4, 1.9, 3.3, 3.4, 2.5, 4.1, 0.1, 2.7, 1.5,
           3.0, 1.7, 1.5, 0.8, 0.7, 2.1, 2.1, 1.9, 2.3, 1.4, 7.0, 6.5, 3.4, 2.9, 2.7, 2.6],
    "EU": [2.4, 2.1, 1.6, 1.1, 1.1, 2.1, 2.4, 2.3, 2.1, 2.2, 2.2, 2.2, 2.1, 3.3, 0.3, 1.6,
           2.7, 2.5, 1.3, 0.4, 0.2, 0.2, 1.5, 1.8, 1.2, 0.3, 2.6, 8.4, 5.4, 2.4, 2.1, 2.0],
    "UK": [2.7, 2.5, 1.8, 1.6, 1.3, 0.8, 1.2, 1.3, 1.4, 1.3, 2.1, 2.3, 2.3, 3.6, 2.2, 3.3,
           4.5, 2.8, 2.6, 1.5, 0.0, 0.7, 2.7, 2.5, 1.8, 0.9, 2.6, 9.1, 7.3, 2.5, 3.4, 2.8],
    "TR": [88.0, 80.0, 99.0, 70.0, 69.0, 39.0, 69.0, 30.0, 18.0, 9.0, 8.0, 10.0, 8.4, 10.0,
           6.5, 6.4, 10.4, 6.2, 7.4, 8.2, 8.8, 8.5, 11.9, 20.3, 11.8, 14.6, 36.0, 64.0, 65.0,
           44.0, 31.0, 25.0],
}

# Annual average exchange rates expressed as local currency units per 1 USD.
# TRY is expressed in post-2005 "new lira" for the whole period for continuity.
FX_PER_USD = {
    "USD": [1.0] * 32,
    "EUR": [0.78, 0.79, 0.88, 0.89, 0.94, 1.09, 1.12, 1.06, 0.88, 0.81, 0.80, 0.80, 0.73,
            0.68, 0.72, 0.75, 0.72, 0.78, 0.75, 0.75, 0.90, 0.90, 0.89, 0.85, 0.89, 0.88,
            0.85, 0.95, 0.92, 0.92, 0.88, 0.86],
    "GBP": [0.63, 0.64, 0.61, 0.60, 0.62, 0.66, 0.69, 0.67, 0.61, 0.55, 0.55, 0.54, 0.50,
            0.54, 0.64, 0.65, 0.62, 0.63, 0.64, 0.61, 0.65, 0.74, 0.78, 0.75, 0.78, 0.78,
            0.72, 0.81, 0.81, 0.78, 0.76, 0.75],
    "TRY": [0.046, 0.081, 0.15, 0.26, 0.42, 0.62, 1.23, 1.51, 1.50, 1.43, 1.34, 1.43, 1.30,
            1.30, 1.55, 1.50, 1.67, 1.80, 1.90, 2.19, 2.72, 3.02, 3.65, 4.83, 5.68, 7.01,
            8.90, 16.55, 23.80, 32.80, 39.50, 44.00],
}

# Policy-style interest rates (%), used for loans the companies take.
INTEREST = {
    "US": [5.8, 5.3, 5.5, 5.4, 5.0, 6.2, 3.9, 1.7, 1.1, 1.4, 3.2, 5.0, 5.0, 1.9, 0.2, 0.2,
           0.1, 0.1, 0.1, 0.1, 0.1, 0.4, 1.0, 1.8, 2.2, 0.4, 0.1, 1.7, 5.0, 5.1, 4.2, 3.8],
    "EU": [4.5, 3.5, 3.3, 3.3, 2.7, 4.1, 4.4, 3.3, 2.3, 2.0, 2.0, 2.8, 3.8, 3.9, 1.3, 1.0,
           1.3, 0.9, 0.5, 0.2, 0.05, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.6, 3.8, 4.0, 2.4, 2.0],
    "UK": [6.7, 6.0, 6.6, 7.2, 5.3, 6.0, 5.1, 4.0, 3.7, 4.4, 4.7, 4.6, 5.5, 4.7, 0.6, 0.5,
           0.5, 0.5, 0.5, 0.5, 0.5, 0.4, 0.3, 0.6, 0.8, 0.2, 0.1, 1.5, 4.7, 5.1, 4.3, 3.8],
    "TR": [70.0, 76.0, 80.0, 75.0, 74.0, 38.0, 90.0, 50.0, 38.0, 25.0, 17.0, 17.5, 17.0,
           16.5, 9.0, 7.0, 6.0, 5.5, 5.0, 8.3, 7.5, 8.0, 8.0, 18.0, 16.0, 13.0, 16.0, 11.0,
           30.0, 50.0, 42.0, 35.0],
}

# Macro demand shocks: (name, region or "ALL", start "YYYY-MM", months to trough,
# months to recover, depth). Depth is the base fall in demand at the trough,
# scaled per company by its sensitivity to the business cycle.
SHOCKS = [
    ("Asian & Russian crisis", "ALL", "1998-08", 4, 10, 0.04),
    ("Turkey 1999 earthquake & recession", "TR", "1999-08", 3, 12, 0.10),
    ("Dot-com bust", "US", "2001-03", 8, 18, 0.07),
    ("Turkey 2001 banking crisis", "TR", "2001-02", 6, 24, 0.28),
    ("Global financial crisis", "ALL", "2008-09", 7, 30, 0.18),
    ("Euro debt crisis", "EU", "2011-09", 9, 24, 0.07),
    ("Turkey 2018 currency crisis", "TR", "2018-08", 5, 15, 0.12),
    ("Brexit uncertainty", "UK", "2016-07", 6, 30, 0.04),
    ("Energy & inflation shock", "EU", "2022-03", 8, 18, 0.05),
]

# COVID impact by industry: April-May 2020 multiplier, with recovery into 2021.
COVID_IMPACT = {
    "manufacturing": 0.72, "textiles": 0.60, "retail": 1.10, "pharma": 1.05,
    "logistics": 0.85, "energy": 0.92, "software": 1.08, "food": 1.06,
    "automotive": 0.55, "construction": 0.78,
}

FIRST_NAMES = {
    "US": ["James", "Mary", "Robert", "Patricia", "John", "Jennifer", "Michael", "Linda",
           "David", "Elizabeth", "William", "Barbara", "Richard", "Susan", "Joseph", "Jessica",
           "Thomas", "Sarah", "Christopher", "Karen", "Daniel", "Lisa", "Matthew", "Nancy",
           "Anthony", "Betty", "Mark", "Sandra", "Steven", "Ashley", "Andrew", "Emily",
           "Kevin", "Michelle", "Brian", "Amanda", "Jose", "Melissa", "Ryan", "Laura",
           "Jacob", "Rachel", "Tyler", "Megan", "Aaron", "Olivia", "Carlos", "Sofia"],
    "UK": ["Oliver", "Amelia", "George", "Isla", "Harry", "Ava", "Jack", "Emily", "Jacob",
           "Sophie", "Charlie", "Grace", "Thomas", "Lily", "Oscar", "Chloe", "William",
           "Ella", "James", "Mia", "Henry", "Ruby", "Alfie", "Evie", "Joshua", "Freya",
           "Daniel", "Lucy", "Samuel", "Hannah", "Edward", "Charlotte", "Arthur", "Poppy",
           "Leo", "Holly", "Callum", "Megan", "Rhys", "Niamh"],
    "DE": ["Lukas", "Anna", "Leon", "Lena", "Finn", "Lea", "Jonas", "Hannah", "Paul",
           "Laura", "Felix", "Julia", "Maximilian", "Sarah", "Elias", "Lisa", "Noah", "Marie",
           "Ben", "Sophie", "Tim", "Katharina", "Jan", "Johanna", "Niklas", "Clara",
           "Tobias", "Emma", "Moritz", "Lara", "Stefan", "Sabine", "Andreas", "Petra",
           "Markus", "Claudia", "Thomas", "Monika", "Jürgen", "Ursula"],
    "NL": ["Daan", "Emma", "Sem", "Julia", "Lucas", "Sophie", "Milan", "Tess", "Levi",
           "Anna", "Thijs", "Fenna", "Jesse", "Lotte", "Ruben", "Sanne", "Bram", "Eva",
           "Lars", "Lieke", "Sven", "Femke", "Joost", "Ilse", "Pieter", "Marieke", "Wouter",
           "Anouk", "Koen", "Inge", "Gijs", "Floor", "Stijn", "Noor", "Jeroen", "Esther"],
    "ES": ["Hugo", "Lucía", "Martín", "Sofía", "Pablo", "María", "Daniel", "Martina",
           "Alejandro", "Paula", "Mateo", "Julia", "Álvaro", "Valeria", "Adrián", "Carmen",
           "Diego", "Elena", "Javier", "Laura", "Sergio", "Ana", "Carlos", "Marta", "Jorge",
           "Isabel", "Manuel", "Cristina", "Raúl", "Beatriz", "Iván", "Rocío", "Rubén",
           "Pilar", "Óscar", "Nuria"],
    "TR": ["Mehmet", "Ayşe", "Mustafa", "Fatma", "Ahmet", "Emine", "Ali", "Hatice",
           "Hüseyin", "Zeynep", "Hasan", "Elif", "İbrahim", "Meryem", "Murat", "Şerife",
           "Ömer", "Zehra", "Yusuf", "Sultan", "Emre", "Esra", "Burak", "Merve", "Can",
           "Büşra", "Kerem", "Selin", "Onur", "Derya", "Serkan", "Gizem", "Oğuz", "Ebru",
           "Cem", "Deniz", "Barış", "Pınar", "Tolga", "Aslı", "Kaan", "Ece"],
}

LAST_NAMES = {
    "US": ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis",
           "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson",
           "Thomas", "Taylor", "Moore", "Jackson", "Martin", "Lee", "Perez", "Thompson",
           "White", "Harris", "Sanchez", "Clark", "Ramirez", "Lewis", "Robinson", "Walker",
           "Young", "Allen", "King", "Wright", "Scott", "Torres", "Nguyen", "Hill", "Flores",
           "Green", "Adams", "Nelson", "Baker", "Hall", "Rivera", "Campbell", "Mitchell"],
    "UK": ["Smith", "Jones", "Taylor", "Brown", "Williams", "Wilson", "Johnson", "Davies",
           "Patel", "Robinson", "Wright", "Thompson", "Evans", "Walker", "White", "Roberts",
           "Green", "Hall", "Wood", "Jackson", "Clarke", "Hughes", "Edwards", "Turner",
           "Hill", "Moore", "Cooper", "Ward", "Morris", "King", "Harrison", "Baker",
           "Lewis", "Khan", "Price", "Bennett", "Murphy", "Bell", "Kelly", "Scott"],
    "DE": ["Müller", "Schmidt", "Schneider", "Fischer", "Weber", "Meyer", "Wagner", "Becker",
           "Schulz", "Hoffmann", "Schäfer", "Koch", "Bauer", "Richter", "Klein", "Wolf",
           "Schröder", "Neumann", "Schwarz", "Zimmermann", "Braun", "Krüger", "Hofmann",
           "Hartmann", "Lange", "Schmitt", "Werner", "Schmitz", "Krause", "Meier", "Lehmann",
           "Köhler", "Herrmann", "König", "Walter", "Mayer", "Huber", "Kaiser", "Fuchs",
           "Peters"],
    "NL": ["de Jong", "Jansen", "de Vries", "van den Berg", "van Dijk", "Bakker", "Janssen",
           "Visser", "Smit", "Meijer", "de Boer", "Mulder", "de Groot", "Bos", "Vos",
           "Peters", "Hendriks", "van Leeuwen", "Dekker", "Brouwer", "de Wit", "Dijkstra",
           "Smits", "de Graaf", "van der Meer", "van der Linden", "Kok", "Jacobs", "de Haan",
           "Vermeulen", "van den Heuvel", "van der Veen", "van den Broek", "de Bruijn"],
    "ES": ["García", "Rodríguez", "González", "Fernández", "López", "Martínez", "Sánchez",
           "Pérez", "Gómez", "Martín", "Jiménez", "Ruiz", "Hernández", "Díaz", "Moreno",
           "Muñoz", "Álvarez", "Romero", "Alonso", "Gutiérrez", "Navarro", "Torres",
           "Domínguez", "Vázquez", "Ramos", "Gil", "Ramírez", "Serrano", "Blanco", "Molina",
           "Morales", "Suárez", "Ortega", "Delgado", "Castro", "Ortiz"],
    "TR": ["Yılmaz", "Kaya", "Demir", "Şahin", "Çelik", "Yıldız", "Yıldırım", "Öztürk",
           "Aydın", "Özdemir", "Arslan", "Doğan", "Kılıç", "Aslan", "Çetin", "Kara", "Koç",
           "Kurt", "Özkan", "Şimşek", "Polat", "Özer", "Erdoğan", "Güneş", "Aksoy", "Avcı",
           "Taş", "Korkmaz", "Bulut", "Keskin", "Ünal", "Güler", "Turan", "Tekin", "Acar",
           "Erdem", "Karaca", "Uçar", "Bozkurt", "Çakır"],
}

# Word parts used to build B2B customer and supplier names.
ORG_WORDS = ["Apex", "Summit", "Delta", "Pioneer", "Atlas", "Vertex", "Harbor", "Crescent",
             "Union", "Liberty", "Sterling", "Evergreen", "Redwood", "Silverline", "Northgate",
             "Bluewater", "Ironwood", "Keystone", "Lakeside", "Highland", "Riverbend",
             "Oakridge", "Falcon", "Orion", "Nova", "Prime", "Unity", "Horizon", "Granite",
             "Cedar", "Beacon", "Frontier", "Meridian", "Sapphire", "Titan", "Velocity",
             "Pinnacle", "Coastal", "Heritage", "Allied", "Central", "Western", "Eastern",
             "Metro", "Global", "Continental", "Premier", "Royal", "Trident", "Zenith"]
ORG_SUFFIX = {
    "US": ["Inc.", "LLC", "Corp.", "Co.", "Group", "Holdings"],
    "UK": ["Ltd", "PLC", "Group Ltd", "& Sons Ltd", "Holdings Ltd"],
    "DE": ["GmbH", "AG", "GmbH & Co. KG", "KG", "SE"],
    "NL": ["B.V.", "N.V.", "Groep B.V.", "Holding B.V."],
    "ES": ["S.A.", "S.L.", "Grupo S.A.", "S.L.U."],
    "TR": ["A.Ş.", "Ltd. Şti.", "Sanayi A.Ş.", "Ticaret A.Ş.", "Holding A.Ş."],
}

CITIES = {
    "US": ["Chicago", "Houston", "Atlanta", "Denver", "Phoenix", "Columbus", "Charlotte",
           "Dallas", "Minneapolis", "Detroit", "Pittsburgh", "Nashville", "Indianapolis",
           "Kansas City", "St. Louis", "Milwaukee", "Cleveland", "Seattle", "Boston",
           "Salt Lake City"],
    "UK": ["London", "Birmingham", "Manchester", "Leeds", "Coventry", "Sheffield",
           "Bristol", "Nottingham", "Leicester", "Glasgow", "Derby", "Liverpool"],
    "DE": ["Berlin", "Hamburg", "München", "Köln", "Frankfurt", "Stuttgart", "Düsseldorf",
           "Leipzig", "Dortmund", "Hannover", "Nürnberg", "Bremen", "Mannheim"],
    "NL": ["Rotterdam", "Amsterdam", "Utrecht", "Eindhoven", "Tilburg", "Venlo",
           "Groningen", "Breda", "Nijmegen", "Arnhem"],
    "ES": ["Madrid", "Barcelona", "Valencia", "Sevilla", "Zaragoza", "Bilbao", "Málaga",
           "Murcia", "Valladolid", "A Coruña", "Pamplona", "Alicante"],
    "TR": ["İstanbul", "Bursa", "İzmir", "Ankara", "Gaziantep", "Kocaeli", "Denizli",
           "Kayseri", "Konya", "Adana", "Manisa", "Antalya", "Tekirdağ"],
}

# Fixed public holidays (month, day) when B2B companies do not trade.
HOLIDAYS = {
    "US": [(1, 1), (7, 4), (11, 11), (12, 25)],
    "UK": [(1, 1), (12, 25), (12, 26)],
    "DE": [(1, 1), (5, 1), (10, 3), (12, 25), (12, 26)],
    "NL": [(1, 1), (4, 27), (12, 25), (12, 26)],
    "ES": [(1, 1), (1, 6), (5, 1), (8, 15), (10, 12), (12, 25)],
    "TR": [(1, 1), (4, 23), (5, 1), (5, 19), (8, 30), (10, 29)],
}

# Cost-to-employer multiplier on gross salary (social security, pension, etc.).
EMPLOYER_COST = {"US": 0.11, "UK": 0.14, "DE": 0.21, "NL": 0.19, "ES": 0.30, "TR": 0.205}
# Rough effective payroll tax withheld from gross salary.
PAYROLL_TAX = {"US": 0.24, "UK": 0.26, "DE": 0.34, "NL": 0.33, "ES": 0.24, "TR": 0.27}
VAT = {"US": 0.0, "UK": 0.20, "DE": 0.19, "NL": 0.21, "ES": 0.21, "TR": 0.18}
CORPORATE_TAX = {"US": 0.25, "UK": 0.22, "DE": 0.30, "NL": 0.25, "ES": 0.25, "TR": 0.22}

# Values for 1994, used only for the six-month warm-up before the data starts.
YEAR_1994 = {
    "inflation": {"US": 2.6, "EU": 2.8, "UK": 2.4, "TR": 106.0},
    "fx": {"USD": 1.0, "EUR": 0.81, "GBP": 0.65, "TRY": 0.030},
    "interest": {"US": 4.6, "EU": 5.0, "UK": 5.5, "TR": 90.0},
}

COUNTRY_REGION = {"US": "US", "UK": "UK", "DE": "EU", "NL": "EU", "ES": "EU", "FR": "EU", "TR": "TR"}
COUNTRY_CURRENCY = {"US": "USD", "UK": "GBP", "DE": "EUR", "NL": "EUR", "ES": "EUR", "FR": "EUR", "TR": "TRY"}

FIRST_NAMES["FR"] = ["Gabriel", "Louise", "Léo", "Emma", "Raphaël", "Jade", "Arthur", "Alice",
                     "Louis", "Chloé", "Jules", "Léa", "Adam", "Manon", "Lucas", "Camille",
                     "Hugo", "Sarah", "Nathan", "Inès", "Thomas", "Julie", "Nicolas", "Claire",
                     "Pierre", "Sophie", "Antoine", "Marie", "Julien", "Céline", "Mathieu",
                     "Isabelle", "François", "Nathalie", "Olivier", "Valérie"]
LAST_NAMES["FR"] = ["Martin", "Bernard", "Thomas", "Petit", "Robert", "Richard", "Durand",
                    "Dubois", "Moreau", "Laurent", "Simon", "Michel", "Lefebvre", "Leroy",
                    "Roux", "David", "Bertrand", "Morel", "Fournier", "Girard", "Bonnet",
                    "Dupont", "Lambert", "Fontaine", "Rousseau", "Vincent", "Muller", "Lefèvre",
                    "Faure", "André", "Mercier", "Blanc", "Guérin", "Boyer", "Garnier", "Chevalier"]
ORG_SUFFIX["FR"] = ["S.A.", "SAS", "SARL", "Groupe S.A."]
CITIES["FR"] = ["Paris", "Lyon", "Marseille", "Toulouse", "Lille", "Bordeaux", "Nantes",
                "Strasbourg", "Rennes", "Grenoble", "Montpellier", "Rouen"]
HOLIDAYS["FR"] = [(1, 1), (5, 1), (5, 8), (7, 14), (8, 15), (11, 1), (11, 11), (12, 25)]
EMPLOYER_COST["FR"] = 0.42
PAYROLL_TAX["FR"] = 0.22
VAT["FR"] = 0.20
CORPORATE_TAX["FR"] = 0.25

# Turkish corporate tax rate by year (kurumlar vergisi), approximate.
TR_CORPORATE_TAX = {**{y: 0.25 for y in range(1994, 1999)}, **{y: 0.33 for y in range(1999, 2003)},
                    2003: 0.30, 2004: 0.33, 2005: 0.30, **{y: 0.20 for y in range(2006, 2018)},
                    2018: 0.22, 2019: 0.22, 2020: 0.22, 2021: 0.25, 2022: 0.23,
                    **{y: 0.25 for y in range(2023, 2027)}}

# Turkish VAT standard rate by year (KDV).
TR_VAT = {**{y: 0.15 for y in range(1994, 2002)}, **{y: 0.18 for y in range(2002, 2023)},
          2023: 0.20, 2024: 0.20, 2025: 0.20, 2026: 0.20}

# Word parts for Turkish company names.
TR_ORG_WORDS = ["Yıldız", "Doğan", "Ege", "Marmara", "Anadolu", "Akdeniz", "Karadeniz", "Toros",
                "Uludağ", "Kardelen", "Güneş", "Özgür", "Başkent", "Bereket", "Çağ", "Demir",
                "Erciyes", "Fırat", "Gediz", "Hisar", "İnci", "Kale", "Kartal", "Lider", "Meram",
                "Orkide", "Pamuk", "Saray", "Simge", "Tunç", "Umut", "Vatan", "Akın", "Bora",
                "Ceylan", "Dicle", "Efes", "Fidan", "Gökçe", "Hilal", "Işık", "Kutup", "Mavi",
                "Nehir", "Ozan", "Poyraz", "Rota", "Sedef", "Tuna", "Yakamoz", "Zirve", "Ayyıldız"]
TR_SECTOR_WORDS = ["Makina", "Metal", "Gıda", "Tekstil", "Ticaret", "Otomotiv", "İnşaat", "Elektrik",
                   "Plastik", "Kimya", "Lojistik", "Market", "Ambalaj", "Mobilya", "Enerji", "Medikal",
                   "Yapı", "Kauçuk", "Döküm", "Elektronik"]
EN_SECTOR_WORDS = ["Machining", "Metals", "Foods", "Textiles", "Trading", "Automotive", "Builders",
                   "Electric", "Plastics", "Chemicals", "Logistics", "Stores", "Packaging",
                   "Furniture", "Energy", "Medical", "Supply", "Rubber", "Castings", "Electronics"]

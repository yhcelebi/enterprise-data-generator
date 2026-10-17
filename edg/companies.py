"""The 30 companies: 15 industries, each with one Turkish and one foreign company.

Sizes are given at scale 1 in real 2026 US dollars. Every count in the generator
(revenue, customers, employees, documents) is multiplied by the run's scale factor.
"""

from dataclasses import dataclass, field

# Accounting model decides which TDHP accounts carry inventory and cost of sales.
#   manufacturing: 150 raw materials -> 152 finished goods -> 620
#   trading:       153 merchandise -> 621
#   services:      direct costs -> 622
MODELS = ("manufacturing", "trading", "services")


@dataclass(frozen=True)
class Industry:
    key: str
    name_en: str
    name_tr: str
    model: str
    gross_margin: float          # target gross margin on net sales
    opex_ratio: float            # operating expenses / net sales at steady state
    fixed_opex_share: float      # share of opex that does not move with volume
    rev_per_employee_k: float    # real 2026 USD thousands of revenue per employee
    b2c_share: float             # share of revenue billed to consumers as daily summaries
    avg_invoice_usd: float       # mean B2B invoice in 2026 USD
    lines_per_invoice: float
    customers_end: int           # active B2B customers at the end, scale 1
    suppliers: int
    payment_terms: tuple         # customer payment terms to choose from (days)
    dio_days: float              # inventory days (0 for pure services)
    capex_ratio: float           # capex / revenue
    cycle_sensitivity: float     # multiplier on macro shock depth
    covid: str                   # key into reference.COVID_IMPACT
    seasonality: tuple           # 12 monthly weights, mean 1
    weekend_activity: float      # weekend volume relative to a weekday
    departments: tuple           # (department, share of headcount, P&L bucket)
    categories_en: tuple
    categories_tr: tuple
    price_range_usd: tuple       # unit price range for catalogue items, 2026 USD
    products: int
    real_price_drift: float = 0.0  # yearly real change in unit prices


FLAT = (1,) * 12
OPS = "cost"   # payroll charged to cost of sales / production
SELL = "631"
GA = "632"
RND = "630"


INDUSTRIES = {i.key: i for i in [
    Industry("manufacturing", "Industrial manufacturing", "Endüstriyel imalat", "manufacturing",
             0.31, 0.19, 0.6, 220, 0.0, 12_000, 4.0, 2_500, 600, (30, 45, 60, 90), 75, 0.05, 1.3,
             "manufacturing", (0.92, 0.98, 1.06, 1.03, 1.02, 1.04, 0.92, 0.84, 1.04, 1.07, 1.05, 1.03),
             0.05, (("Production", 0.55, OPS), ("Sales", 0.12, SELL), ("Engineering", 0.10, RND),
                    ("Logistics", 0.08, SELL), ("Finance", 0.05, GA), ("HR", 0.03, GA),
                    ("IT", 0.04, GA), ("Management", 0.03, GA)),
             ("Hydraulic valves", "Ball bearings", "Gear motors", "Pneumatic cylinders", "Couplings",
              "Linear guides", "Pumps", "Seals & gaskets"),
             ("Hidrolik valfler", "Rulmanlar", "Redüktörlü motorlar", "Pnömatik silindirler",
              "Kaplinler", "Lineer kızaklar", "Pompalar", "Conta ve keçeler"),
             (8, 4_000), 1_800, -0.005),
    Industry("textiles", "Textiles & apparel", "Tekstil ve hazır giyim", "manufacturing",
             0.24, 0.15, 0.55, 90, 0.0, 25_000, 6.0, 400, 350, (60, 90, 120), 95, 0.04, 1.2,
             "textiles", (0.95, 1.05, 1.12, 1.08, 0.98, 0.90, 0.86, 0.95, 1.10, 1.08, 1.00, 0.93),
             0.05, (("Production", 0.68, OPS), ("Design", 0.05, RND), ("Sales & Export", 0.08, SELL),
                    ("Quality", 0.05, OPS), ("Finance", 0.04, GA), ("HR", 0.03, GA),
                    ("IT", 0.02, GA), ("Management", 0.05, GA)),
             ("Denim fabric", "Knitted fabric", "Woven shirts", "T-shirts", "Trousers", "Home textiles"),
             ("Denim kumaş", "Örme kumaş", "Dokuma gömlek", "Tişört", "Pantolon", "Ev tekstili"),
             (2, 60), 900, -0.01),
    Industry("food", "Food & beverage", "Gıda ve içecek", "manufacturing",
             0.29, 0.20, 0.5, 300, 0.0, 6_000, 8.0, 3_000, 500, (30, 45, 60), 35, 0.04, 0.6,
             "food", (0.88, 0.88, 0.95, 1.00, 1.06, 1.15, 1.20, 1.16, 1.00, 0.95, 0.88, 0.89),
             0.6, (("Production", 0.50, OPS), ("Sales", 0.18, SELL), ("Distribution", 0.12, SELL),
                   ("Quality", 0.05, OPS), ("R&D", 0.03, RND), ("Finance", 0.04, GA),
                   ("HR", 0.03, GA), ("IT", 0.02, GA), ("Management", 0.03, GA)),
             ("Fruit juices", "Dairy", "Snacks", "Biscuits", "Pasta", "Frozen foods", "Bottled water"),
             ("Meyve suları", "Süt ürünleri", "Atıştırmalıklar", "Bisküvi", "Makarna",
              "Dondurulmuş gıda", "Şişe su"),
             (0.4, 12), 700, 0.0),
    Industry("retail", "Retail", "Perakende", "trading",
             0.27, 0.21, 0.55, 220, 0.97, 3_000, 10.0, 300, 900, (15, 30), 40, 0.035, 0.4,
             "retail", (0.92, 0.88, 0.96, 0.98, 1.00, 0.98, 1.00, 1.02, 0.97, 1.00, 1.08, 1.21),
             1.15, (("Stores", 0.80, SELL), ("Distribution centre", 0.09, SELL), ("Buying", 0.03, SELL),
                    ("Marketing", 0.02, SELL), ("Finance", 0.02, GA), ("HR", 0.02, GA),
                    ("IT", 0.01, GA), ("Management", 0.01, GA)),
             ("Fresh produce", "Groceries", "Beverages", "Household", "Personal care", "Electronics",
              "Apparel", "Bakery"),
             ("Taze meyve sebze", "Temel gıda", "İçecek", "Ev ürünleri", "Kişisel bakım",
              "Elektronik", "Giyim", "Fırın"),
             (0.5, 400), 4_000, 0.0),
    Industry("pharma", "Pharmaceuticals", "İlaç", "manufacturing",
             0.58, 0.36, 0.7, 400, 0.0, 8_000, 3.0, 4_000, 400, (60, 90, 120), 120, 0.05, 0.2,
             "pharma", (1.05, 1.00, 1.04, 0.98, 0.97, 0.95, 0.94, 0.92, 1.00, 1.04, 1.06, 1.05),
             0.05, (("Production", 0.35, OPS), ("R&D", 0.18, RND), ("Sales force", 0.25, SELL),
                    ("Quality & regulatory", 0.08, OPS), ("Finance", 0.04, GA), ("HR", 0.03, GA),
                    ("IT", 0.03, GA), ("Management", 0.04, GA)),
             ("Cardiology", "Oncology", "Antibiotics", "Analgesics", "Diabetes", "Respiratory", "Vaccines"),
             ("Kardiyoloji", "Onkoloji", "Antibiyotikler", "Ağrı kesiciler", "Diyabet", "Solunum", "Aşılar"),
             (3, 900), 350, -0.01),
    Industry("logistics", "Logistics", "Lojistik", "services",
             0.16, 0.09, 0.6, 200, 0.05, 2_500, 1.5, 3_000, 1_200, (30, 45, 60), 0, 0.07, 1.1,
             "logistics", (0.92, 0.92, 1.00, 1.00, 1.02, 1.02, 0.98, 0.94, 1.03, 1.06, 1.08, 1.03),
             0.35, (("Drivers & fleet", 0.55, OPS), ("Warehouse", 0.20, OPS), ("Sales", 0.06, SELL),
                    ("Customer service", 0.07, SELL), ("Finance", 0.04, GA), ("HR", 0.03, GA),
                    ("IT", 0.03, GA), ("Management", 0.02, GA)),
             ("Full truckload", "Less than truckload", "Warehousing", "Customs brokerage",
              "Express parcel", "Intermodal"),
             ("Komple araç", "Parsiyel taşıma", "Depolama", "Gümrük müşavirliği", "Ekspres kargo",
              "Intermodal taşıma"),
             (40, 6_000), 120, 0.0),
    Industry("energy", "Energy & utilities", "Enerji", "services",
             0.34, 0.12, 0.75, 900, 0.55, 15_000, 3.0, 2_000, 300, (15, 30), 0, 0.18, 0.4,
             "energy", (1.25, 1.15, 1.02, 0.90, 0.85, 0.92, 1.05, 1.02, 0.88, 0.90, 1.00, 1.06),
             0.9, (("Generation", 0.40, OPS), ("Grid & field service", 0.25, OPS),
                   ("Customer service", 0.12, SELL), ("Trading", 0.04, SELL), ("Engineering", 0.06, RND),
                   ("Finance", 0.05, GA), ("HR", 0.03, GA), ("IT", 0.03, GA), ("Management", 0.02, GA)),
             ("Electricity supply", "Natural gas supply", "Capacity charges", "Renewable certificates",
              "Grid services"),
             ("Elektrik satışı", "Doğal gaz satışı", "Kapasite bedeli", "YEK-G sertifikası",
              "Şebeke hizmetleri"),
             (100, 40_000), 60, 0.0),
    Industry("software", "Software & SaaS", "Yazılım", "services",
             0.72, 0.55, 0.65, 220, 0.05, 20_000, 2.0, 1_500, 150, (30, 45), 0, 0.03, 0.5,
             "software", (0.95, 0.95, 1.02, 0.97, 0.97, 1.05, 0.92, 0.90, 1.00, 1.02, 1.03, 1.22),
             0.1, (("Engineering", 0.40, RND), ("Customer success", 0.12, OPS), ("Sales", 0.18, SELL),
                   ("Marketing", 0.08, SELL), ("Cloud operations", 0.08, OPS), ("Finance", 0.05, GA),
                   ("HR", 0.04, GA), ("Management", 0.05, GA)),
             ("Licences", "Subscriptions", "Maintenance & support", "Professional services", "Training"),
             ("Lisans", "Abonelik", "Bakım ve destek", "Danışmanlık", "Eğitim"),
             (500, 120_000), 40, -0.02),
    Industry("construction", "Construction", "İnşaat", "services",
             0.11, 0.06, 0.7, 350, 0.0, 400_000, 4.0, 60, 700, (30, 60, 90), 0, 0.03, 1.6,
             "construction", (0.75, 0.80, 0.95, 1.05, 1.12, 1.15, 1.15, 1.12, 1.08, 1.05, 0.95, 0.83),
             0.15, (("Site crews", 0.62, OPS), ("Project management", 0.12, OPS), ("Engineering", 0.08, OPS),
                    ("Procurement", 0.05, GA), ("Business development", 0.04, SELL), ("Finance", 0.04, GA),
                    ("HR", 0.03, GA), ("Management", 0.02, GA)),
             ("Progress billing - labour", "Progress billing - materials", "Equipment hire",
              "Subcontract works", "Change orders"),
             ("Hakediş - işçilik", "Hakediş - malzeme", "Ekipman kiralama", "Taşeron işleri",
              "İlave iş bedeli"),
             (20_000, 2_000_000), 40, 0.0),
    Industry("banking", "Banking", "Bankacılık", "services",
             0.0, 0.0, 0.0, 400, 0.0, 0, 0, 0, 0, (0,), 0, 0.0, 0.0, "software", FLAT, 1.0,
             (("Branches", 1.0, GA),), (), (), (0, 0), 0),
    Industry("automotive", "Automotive", "Otomotiv", "manufacturing",
             0.15, 0.09, 0.6, 600, 0.0, 120_000, 3.0, 150, 800, (30, 45, 60), 40, 0.06, 1.5,
             "automotive", (0.85, 0.95, 1.12, 1.05, 1.05, 1.08, 0.88, 0.70, 1.08, 1.10, 1.06, 1.08),
             0.05, (("Assembly", 0.62, OPS), ("Engineering", 0.12, RND), ("Quality", 0.06, OPS),
                    ("Sales & dealer network", 0.06, SELL), ("After-sales", 0.05, SELL),
                    ("Finance", 0.03, GA), ("HR", 0.02, GA), ("IT", 0.02, GA), ("Management", 0.02, GA)),
             ("Passenger cars", "Light commercial vehicles", "Trucks", "Spare parts", "Electric vehicles"),
             ("Binek araçlar", "Hafif ticari araçlar", "Kamyonlar", "Yedek parça", "Elektrikli araçlar"),
             (40, 60_000), 300, 0.005),
    Industry("defense", "Defense & aerospace", "Savunma ve havacılık", "manufacturing",
             0.24, 0.12, 0.8, 350, 0.0, 2_000_000, 2.0, 15, 900, (30, 60), 150, 0.06, 0.2,
             "software", (0.90, 0.92, 1.00, 0.95, 0.95, 1.05, 0.90, 0.85, 1.05, 1.00, 1.05, 1.38),
             0.0, (("Production", 0.40, OPS), ("Engineering & R&D", 0.30, RND), ("Programme management", 0.08, OPS),
                   ("Quality & certification", 0.07, OPS), ("Business development", 0.03, SELL),
                   ("Finance", 0.04, GA), ("HR", 0.03, GA), ("Security & IT", 0.03, GA), ("Management", 0.02, GA)),
             ("Programme milestones", "Avionics", "Radar systems", "Unmanned aerial systems",
              "Maintenance & overhaul", "Training & simulation"),
             ("Program kilometre taşları", "Aviyonik", "Radar sistemleri", "İnsansız hava araçları",
              "Bakım ve revizyon", "Eğitim ve simülasyon"),
             (50_000, 20_000_000), 120, 0.0),
    Industry("telecom", "Telecommunications", "Telekomünikasyon", "services",
             0.42, 0.25, 0.75, 600, 0.70, 5_000, 2.0, 8_000, 400, (30,), 0, 0.17, 0.3,
             "software", (0.98, 0.95, 1.00, 0.99, 1.00, 1.01, 1.04, 1.05, 0.99, 0.99, 0.98, 1.02),
             0.95, (("Network operations", 0.30, OPS), ("Customer care", 0.25, SELL), ("Retail shops", 0.18, SELL),
                    ("Enterprise sales", 0.07, SELL), ("IT", 0.08, GA), ("Finance", 0.04, GA),
                    ("HR", 0.03, GA), ("Management", 0.05, GA)),
             ("Corporate mobile plans", "Fixed broadband", "Data centre & cloud", "IoT connectivity",
              "Leased lines"),
             ("Kurumsal mobil tarifeler", "Sabit genişbant", "Veri merkezi ve bulut", "IoT bağlantı",
              "Kiralık hat"),
             (10, 5_000), 80, -0.03),
    Industry("airline", "Airline", "Havayolu", "services",
             0.12, 0.07, 0.7, 350, 0.80, 20_000, 2.0, 1_500, 600, (15, 30), 0, 0.12, 1.4,
             "software", (0.80, 0.78, 0.88, 0.98, 1.02, 1.15, 1.30, 1.32, 1.08, 0.98, 0.83, 0.88),
             0.95, (("Flight crew", 0.25, OPS), ("Cabin crew", 0.25, OPS), ("Maintenance", 0.15, OPS),
                    ("Ground operations", 0.18, OPS), ("Sales & distribution", 0.07, SELL),
                    ("Finance", 0.03, GA), ("HR", 0.03, GA), ("IT", 0.02, GA), ("Management", 0.02, GA)),
             ("Corporate travel", "Group fares", "Air cargo", "Charter flights", "Ancillary services"),
             ("Kurumsal seyahat", "Grup biletleri", "Hava kargo", "Charter uçuşlar", "Ek hizmetler"),
             (150, 80_000), 60, -0.01),
    Industry("healthcare", "Healthcare", "Sağlık", "services",
             0.22, 0.12, 0.7, 150, 0.45, 200_000, 3.0, 40, 700, (60, 90, 120), 10, 0.07, 0.3,
             "software", (1.08, 1.04, 1.02, 0.98, 0.98, 0.94, 0.90, 0.90, 1.00, 1.04, 1.04, 1.08),
             0.7, (("Physicians", 0.18, OPS), ("Nursing", 0.38, OPS), ("Allied health", 0.14, OPS),
                   ("Patient services", 0.12, SELL), ("Finance & billing", 0.07, GA), ("HR", 0.03, GA),
                   ("IT", 0.03, GA), ("Management", 0.05, GA)),
             ("Inpatient claims", "Outpatient claims", "Diagnostic imaging", "Laboratory", "Surgery packages"),
             ("Yatan hasta provizyonları", "Ayakta hasta provizyonları", "Görüntüleme", "Laboratuvar",
              "Ameliyat paketleri"),
             (2_000, 400_000), 40, 0.0),
]}


@dataclass(frozen=True)
class Event:
    month: str          # "YYYY-MM"
    kind: str           # step (permanent level change), shock (temporary), note (no effect)
    size: float         # step: +0.25 = +25%; shock: -0.30 = 30% fall at the trough
    label: str
    ramp: int = 6       # months to reach full effect
    recover: int = 18   # shock only: months to recover


@dataclass(frozen=True)
class Company:
    id: str
    name: str
    country: str
    industry: str
    revenue_1995: float        # real 2026 USD millions
    revenue_2026: float        # real 2026 USD millions
    founded: int
    city: str
    events: tuple = ()
    erp_history: tuple = ()    # (from year, system name)
    holding: str = ""
    holding_share: float = 0.0
    export_share: float = 0.0  # share of B2B sales invoiced abroad in EUR/USD
    is_bank: bool = False
    overrides: dict = field(default_factory=dict)

    @property
    def turkish(self) -> bool:
        return self.country == "TR"

    @property
    def profile(self) -> Industry:
        ind = INDUSTRIES[self.industry]
        if not self.overrides:
            return ind
        from dataclasses import replace
        return replace(ind, **self.overrides)


E = Event
TR_ERP = ((1994, "LOGO_UNITY"), (2004, "LOGO_TIGER"), (2016, "LOGO_TIGER3"))

COMPANIES = [
    Company("ostim", "Ostim Endüstriyel Makina A.Ş.", "TR", "manufacturing", 45, 180, 1978, "Ankara",
            (E("2001-03", "shock", -0.25, "2001 krizi: siparişler düştü"),
             E("2011-04", "step", 0.20, "Sincan ikinci fabrika açıldı"),
             E("2019-06", "note", 0, "SAP Business One'a geçiş")), TR_ERP[:2] + ((2019, "SAP_B1"),),
            export_share=0.15),
    Company("kestrel", "Kestrel Industrial Components Inc.", "US", "manufacturing", 280, 650, 1968,
            "Milwaukee", (E("2006-07", "step", 0.28, "Acquired Ridgeline Hydraulics"),
                          E("2020-07", "note", 0, "Migrated to SAP S/4HANA")),
            ((1994, "JDE_WORLD"), (2001, "SAP_R3"), (2020, "SAP_S4HANA"))),
    Company("anatolia", "Anatolia Tekstil A.Ş.", "TR", "textiles", 90, 220, 1979, "Bursa",
            (E("2005-01", "shock", -0.18, "Kotaların kalkması: Çin rekabeti", 12, 36),
             E("2014-03", "step", 0.15, "Mısır'da dikim tesisi"),), TR_ERP,
            holding="Kervan Holding A.Ş.", holding_share=1.0, export_share=0.70),
    Company("pennine", "Pennine Textiles Ltd", "UK", "textiles", 260, 140, 1952, "Manchester",
            (E("2001-01", "step", -0.25, "Spinning moved offshore", 24),
             E("2009-01", "step", -0.15, "Mill closure in Oldham", 12)),
            ((1994, "SAGE_LINE100"), (2008, "SAGE_X3"))),
    Company("bosphorus", "Bosphorus Gıda A.Ş.", "TR", "food", 80, 350, 1984, "İstanbul",
            (E("2008-05", "step", 0.25, "Çorlu meyve suyu tesisi"),
             E("2017-09", "step", 0.12, "Atıştırmalık markası satın alındı")), TR_ERP,
            holding="Kervan Holding A.Ş.", holding_share=1.0, export_share=0.10),
    Company("alpenhof", "Alpenhof Foods GmbH", "DE", "food", 520, 900, 1961, "München",
            (E("2012-01", "step", 0.10, "Acquired Bergquell dairy"),),
            ((1994, "SAP_R2"), (1999, "SAP_R3"), (2021, "SAP_S4HANA"))),
    Company("cinar", "Çınar Market A.Ş.", "TR", "retail", 60, 900, 1991, "İzmir",
            (E("2004-01", "step", 0.60, "Ege bölgesinde 40 yeni mağaza", 24),
             E("2016-01", "step", 0.45, "Ankara ve Bursa'ya giriş", 24),
             E("2021-01", "note", 0, "Online sipariş kanalı")), TR_ERP[:2] + ((2012, "SAP_RETAIL"),)),
    Company("brightmart", "Brightmart Retail Group", "US", "retail", 700, 2500, 1987, "Columbus",
            (E("2005-06", "note", 0, "Online store launched"),
             E("2014-03", "step", 0.18, "Acquired 22 FreshWay stores")),
            ((1994, "JDA_MMS"), (2009, "ORACLE_RETAIL"))),
    Company("sifa", "Şifa İlaç A.Ş.", "TR", "pharma", 70, 260, 1972, "Kocaeli",
            (E("2009-02", "shock", -0.12, "Referans fiyat sistemi ve ilaç fiyat indirimi", 6, 24),
             E("2016-05", "step", 0.15, "Biyoteknoloji hattı devreye girdi")), TR_ERP),
    Company("helix", "Helix BioPharma GmbH", "DE", "pharma", 380, 1200, 1952, "Frankfurt",
            (E("2011-07", "shock", -0.15, "Patent expiry of Cardivex", 6, 36),
             E("2018-03", "step", 0.20, "Oncology drug Helitumab approved", 12)),
            ((1994, "SAP_R3"), (2019, "SAP_S4HANA"))),
    Company("ufuk", "Ufuk Lojistik A.Ş.", "TR", "logistics", 40, 300, 1993, "Mersin",
            (E("2010-01", "step", 0.25, "Gümrüklü antrepo ve Avrupa hattı"),), TR_ERP),
    Company("meridian", "Meridian Freight B.V.", "NL", "logistics", 300, 1100, 1975, "Rotterdam",
            (E("2007-04", "step", 0.20, "Acquired Rhine Express"),
             E("2021-03", "shock", 0.15, "Post-COVID freight boom", 4, 18)),
            ((1994, "BAAN_IV"), (2010, "MS_DYNAMICS_AX"), (2022, "MS_DYNAMICS_365"))),
    Company("poyraz", "Poyraz Enerji A.Ş.", "TR", "energy", 80, 500, 1996, "İzmir",
            (E("2002-03", "note", 0, "Elektrik piyasası serbestleşti"),
             E("2012-06", "step", 0.35, "Bandırma rüzgar santrali", 12),
             E("2020-09", "step", 0.25, "Güneş santrali portföyü", 12)), TR_ERP),
    Company("solenne", "Solenne Energía S.A.", "ES", "energy", 600, 1600, 1958, "Madrid",
            (E("2010-01", "step", 0.15, "Wind farm portfolio in Castilla"),
             E("2022-03", "shock", 0.35, "Wholesale power price spike", 3, 20)),
            ((1994, "SAP_R3"), (2017, "SAP_S4HANA"))),
    Company("bilge", "Bilge Yazılım A.Ş.", "TR", "software", 5, 90, 1997, "İstanbul",
            (E("2012-01", "note", 0, "Bulut (SaaS) sürümüne geçiş"),), ((1997, "LOGO_UNITY"), (2008, "NETSIS"),
                                                                       (2018, "LOGO_J_PLATFORM"))),
    Company("cobalt", "Cobalt Software Inc.", "US", "software", 25, 450, 1994, "Austin",
            (E("2010-06", "note", 0, "Launched Cobalt Cloud (SaaS)"),
             E("2011-01", "shock", -0.15, "Licence-to-SaaS revenue trough", 6, 30)),
            ((1994, "QUICKBOOKS"), (2004, "NETSUITE"))),
    Company("temel", "Temel İnşaat A.Ş.", "TR", "construction", 120, 400, 1971, "Ankara",
            (E("2003-01", "step", 0.25, "TOKİ konut projeleri"),
             E("2018-09", "shock", -0.30, "Kur şoku: projeler durdu", 6, 30)), TR_ERP),
    Company("granite", "Granite Peak Construction Co.", "US", "construction", 300, 800, 1964, "Denver",
            (E("2007-06", "shock", -0.35, "Housing crash", 18, 48),), ((1994, "TIMBERLINE"), (2015, "VIEWPOINT_VISTA"))),
    Company("lale", "Lale Bank A.Ş.", "TR", "banking", 0, 0, 1956, "İstanbul", is_bank=True),
    Company("thames", "Thames Mutual Bank plc", "UK", "banking", 0, 0, 1871, "London", is_bank=True),
    Company("marmara", "Marmara Otomotiv A.Ş.", "TR", "automotive", 400, 1800, 1969, "Bursa",
            (E("2009-01", "shock", -0.20, "Avrupa ihracatı çöktü", 4, 24),
             E("2021-03", "shock", -0.18, "Çip krizi", 4, 18),
             E("2023-01", "step", 0.15, "Elektrikli araç hattı", 12)), TR_ERP[:2] + ((2014, "SAP_ECC"),),
            holding="Kervan Holding A.Ş.", holding_share=0.51, export_share=0.60),
    Company("rheinwerk", "Rheinwerk Automobil AG", "DE", "automotive", 2500, 6000, 1923, "Stuttgart",
            (E("2015-09", "shock", -0.10, "Emissions investigation", 6, 24),
             E("2021-03", "shock", -0.15, "Semiconductor shortage", 4, 18)),
            ((1994, "SAP_R3"), (2018, "SAP_S4HANA"))),
    Company("kalkan", "Kalkan Savunma ve Havacılık A.Ş.", "TR", "defense", 120, 1500, 1985, "Ankara",
            (E("2004-06", "step", 0.40, "Yerli üretim programları", 24),
             E("2016-01", "step", 0.80, "İHA ihracat programı", 36)), TR_ERP[:2] + ((2012, "SAP_ECC"),),
            export_share=0.35),
    Company("ironclad", "Ironclad Aerospace & Defense Corp.", "US", "defense", 1100, 3000, 1946, "Huntsville",
            (E("2002-01", "step", 0.30, "Post-9/11 defense spending", 24),
             E("2013-03", "shock", -0.10, "Budget sequestration", 6, 24),
             E("2022-06", "step", 0.20, "Allied rearmament orders", 18)),
            ((1994, "MANMAN"), (2003, "DELTEK_COSTPOINT"))),
    Company("telekent", "Telekent İletişim A.Ş.", "TR", "telecom", 150, 1400, 1994, "İstanbul",
            (E("2001-06", "step", 0.50, "GSM lisansı", 24), E("2009-07", "step", 0.25, "3G", 18),
             E("2016-04", "step", 0.20, "4.5G", 18)), ((1994, "LOGO_UNITY"), (2002, "SAP_R3"))),
    Company("aurore", "Aurore Télécom S.A.", "FR", "telecom", 1500, 4000, 1987, "Paris",
            (E("2012-01", "shock", -0.12, "Low-cost competitor price war", 6, 36),
             E("2020-01", "step", 0.10, "5G and fibre roll-out", 24)), ((1994, "SAP_R3"), (2016, "SAP_S4HANA"))),
    Company("kanat", "Kanat Hava Yolları A.Ş.", "TR", "airline", 250, 2200, 1983, "İstanbul",
            (E("2001-09", "shock", -0.30, "11 Eylül", 2, 12), E("2016-07", "shock", -0.25, "Turizm krizi", 3, 15),
             E("2019-04", "step", 0.20, "Yeni havalimanı hub'ı", 12)), TR_ERP[:2] + ((2010, "SAP_ECC"),)),
    Company("albion", "Albion Airways Ltd", "UK", "airline", 900, 2800, 1972, "London",
            (E("2001-09", "shock", -0.35, "September 11", 2, 18), E("2010-04", "shock", -0.08, "Volcanic ash cloud", 1, 2)),
            ((1994, "AMADEUS_ALTEA"), (2011, "SAP_ECC"))),
    Company("hayat", "Hayat Sağlık Grubu A.Ş.", "TR", "healthcare", 60, 600, 1989, "İstanbul",
            (E("2003-01", "step", 0.30, "Sağlıkta dönüşüm: SGK anlaşması", 18),
             E("2013-01", "step", 0.25, "Ankara ve İzmir hastaneleri", 24)), TR_ERP),
    Company("northbridge", "Northbridge Health Partners", "US", "healthcare", 700, 2200, 1965, "Boston",
            (E("2010-03", "step", 0.12, "Affordable Care Act volume", 24),
             E("2016-01", "step", 0.15, "Merged with Lakeside Medical", 12)),
            ((1994, "MEDITECH_MAGIC"), (2013, "EPIC"))),
]

BY_ID = {c.id: c for c in COMPANIES}
BANK_FOR = {True: "lale", False: "thames"}   # Turkish companies bank with Lale, others with Thames

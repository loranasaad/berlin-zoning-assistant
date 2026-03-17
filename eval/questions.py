"""
eval/questions.py — Test dataset for RAGAs evaluation of the Berlin Zoning Assistant.

Ground truths are derived directly from the source documents:
  - bau_nvo.txt        (BauNVO, Baunutzungsverordnung)
  - Bauo_berlin.txt    (BauO Berlin, Berliner Bauordnung)
  - BauO_BE_P49_AV_Stellplatze.pdf  (AV Stellplätze, 16.06.2021)

Dataset design:
  - 16 questions covering regulation lookups, calculations, and hallucination traps
  - ground_truth is provided where the answer can be verified directly from the documents
  - ground_truth is None for CALCULATION questions (require tool calls, no RAG answer)
  - HALLUCINATION_TRAP questions ask about topics genuinely not in any document

Question categories:
  - REGULATION:         answer is directly in BauNVO, BauO Berlin, or AV Stellplätze
  - HALLUCINATION_TRAP: answer is NOT in the knowledge base — model should say so
  - CALCULATION:        requires tool calls, no ground truth needed
"""

EVAL_QUESTIONS = [

	# ── Regulation questions ───────────────────────────────────────────────────
	# Ground truths taken directly from the source documents

	{
		"question": "What is the maximum GRZ for a WA zone?",
		"ground_truth": (
			"Gemäß § 17 BauNVO beträgt die Grundflächenzahl (GRZ) in allgemeinen Wohngebieten (WA) 0,4. "
			"Der Orientierungswert gilt zusammen mit reinen Wohngebieten (WR) und Ferienhausgebieten."
		),
		"category": "REGULATION",
	},
	{
		"question": "What is the maximum GFZ for a MK zone?",
		"ground_truth": (
			"Gemäß § 17 BauNVO beträgt die Geschossflächenzahl (GFZ) in Kerngebieten (MK) 3,0. "
			"Die Grundflächenzahl (GRZ) in Kerngebieten beträgt 1,0."
		),
		"category": "REGULATION",
	},
	{
		"question": "What are the setback rules in Berlin?",
		"ground_truth": (
			"Gemäß § 6 Abs. 5 BauO Berlin beträgt die Tiefe der Abstandsflächen 0,4 H, mindestens 3 m. "
			"In Gewerbe- und Industriegebieten genügt eine Tiefe von 0,2 H, mindestens 3 m. "
			"Vor den Außenwänden von Gebäuden der Gebäudeklassen 1 und 2 mit nicht mehr als drei "
			"oberirdischen Geschossen genügt als Tiefe der Abstandsfläche 3 m."
		),
		"category": "REGULATION",
	},
	{
		"question": "When is a children's playground required in Berlin?",
		"ground_truth": (
			"Gemäß § 8 Abs. 2 BauO Berlin ist bei der Errichtung von Gebäuden mit mehr als sechs Wohnungen "
			"ein Spielplatz für Kinder anzulegen und instand zu halten (notwendiger Kinderspielplatz). "
			"Je Wohnung sollen mindestens 4 m² nutzbare Spielfläche vorhanden sein; der Spielplatz muss "
			"jedoch mindestens 50 m² groß und mindestens für Spiele von Kleinkindern geeignet sein. "
			"Bei Bauvorhaben mit mehr als 75 Wohnungen muss der Spielplatz auch für Spiele älterer Kinder "
			"geeignet sein."
		),
		"category": "REGULATION",
	},
	{
		"question": "What does GRZ stand for and what does it regulate?",
		"ground_truth": (
			"Gemäß § 19 Abs. 1 BauNVO gibt die Grundflächenzahl (GRZ) an, wieviel Quadratmeter Grundfläche "
			"je Quadratmeter Grundstücksfläche zulässig sind. "
			"Die zulässige Grundfläche ist der nach Absatz 1 errechnete Anteil des Baugrundstücks, "
			"der von baulichen Anlagen überdeckt werden darf (§ 19 Abs. 2 BauNVO)."
		),
		"category": "REGULATION",
	},
	{
		"question": "What is a WA zone and what can be built there?",
		"ground_truth": (
			"Gemäß § 4 BauNVO dienen allgemeine Wohngebiete (WA) vorwiegend dem Wohnen. "
			"Zulässig sind: Wohngebäude, die der Versorgung des Gebiets dienenden Läden, "
			"Schank- und Speisewirtschaften sowie nicht störende Handwerksbetriebe, "
			"Anlagen für kirchliche, kulturelle, soziale, gesundheitliche und sportliche Zwecke. "
			"Ausnahmsweise können zugelassen werden: Betriebe des Beherbergungsgewerbes, "
			"sonstige nicht störende Gewerbebetriebe, Anlagen für Verwaltungen, "
			"Gartenbaubetriebe und Tankstellen."
		),
		"category": "REGULATION",
	},
	{
		"question": "What is an MK zone used for?",
		"ground_truth": (
			"Gemäß § 7 Abs. 1 BauNVO dienen Kerngebiete (MK) vorwiegend der Unterbringung von "
			"Handelsbetrieben sowie der zentralen Einrichtungen der Wirtschaft, der Verwaltung und "
			"der Kultur. Zulässig sind unter anderem Geschäfts-, Büro- und Verwaltungsgebäude, "
			"Einzelhandelsbetriebe, Schank- und Speisewirtschaften, Betriebe des Beherbergungsgewerbes "
			"und Vergnügungsstätten (§ 7 Abs. 2 BauNVO)."
		),
		"category": "REGULATION",
	},
	{
		"question": "What is the basement area allowance under BauNVO §19?",
		"ground_truth": (
			"Gemäß § 19 Abs. 4 BauNVO darf die zulässige Grundfläche durch Grundflächen von Garagen "
			"und Stellplätzen mit ihren Zufahrten, Nebenanlagen sowie baulichen Anlagen unterhalb der "
			"Geländeoberfläche bis zu 50 vom Hundert überschritten werden, höchstens jedoch bis zu "
			"einer Grundflächenzahl von 0,8."
		),
		"category": "REGULATION",
	},
	{
		"question": "What are the regulations for bicycle parking in Berlin?",
		"ground_truth": (
			"Gemäß § 49 Abs. 2 Satz 1 BauO Bln sind bei der Errichtung von baulichen Anlagen, die "
			"Fahrradverkehr erwarten lassen, Abstellplätze für Fahrräder in ausreichender Zahl und "
			"Größe herzustellen. "
			"Die Anzahl der Abstellplätze ist ausreichend, wenn sie den Richtzahlen der Anlage 2 der "
			"AV Stellplätze (16.06.2021) entspricht. "
			"Für die in Anlage 2 aufgeführten Nutzungen sind jeweils mindestens zwei Abstellplätze "
			"nachzuweisen (AV Stellplätze §2.1). "
			"Ab 20 Fahrradabstellplätzen muss 1 Abstellplatz für Sonderfahrräder (z.B. Lastenräder) "
			"hergestellt werden (AV Stellplätze §2.4h). "
			"Auf Wohngebäude mit nicht mehr als zwei Wohnungen sind die Anforderungen nicht anzuwenden "
			"(AV Stellplätze §2.4)."
		),
		"category": "REGULATION",
	},
	{
		"question": "What is the MU zone (Urbanes Gebiet)?",
		"ground_truth": (
			"Gemäß § 6a Abs. 1 BauNVO dienen urbane Gebiete (MU) dem Wohnen sowie der Unterbringung "
			"von Gewerbebetrieben und sozialen, kulturellen und anderen Einrichtungen, die die "
			"Wohnnutzung nicht wesentlich stören. Die Nutzungsmischung muss nicht gleichgewichtig sein. "
			"Zulässig sind Wohngebäude, Geschäfts- und Bürogebäude, Einzelhandelsbetriebe, "
			"Schank- und Speisewirtschaften sowie Betriebe des Beherbergungsgewerbes (§ 6a Abs. 2 BauNVO). "
			"Gemäß § 17 BauNVO beträgt die GRZ in urbanen Gebieten 0,8 und die GFZ 3,0."
		),
		"category": "REGULATION",
	},
	{
		"question": "How many car parking spaces am I required to build for a new residential development in Berlin?",
		"ground_truth": (
			"Gemäß § 49 BauO Bln in der Fassung nach der 7. Änderung (Januar 2026) besteht keine "
			"allgemeine Stellplatzpflicht für Kraftfahrzeuge mehr. Die frühere Verpflichtung zur "
			"Herstellung einer Mindestanzahl allgemeiner Kfz-Stellplätze wurde mit der Reform der "
			"BauO Bln 2021 abgeschafft. "
			"Es sind lediglich Stellplätze für Kraftfahrzeuge für Menschen mit schwerer Gehbehinderung "
			"und Rollstuhlnutzende nach § 49 Abs. 1 BauO Bln herzustellen, deren Anzahl sich nach den "
			"Richtzahlen der Anlage 1 der AV Stellplätze (16.06.2021) richtet. Für Wohngebäude sind "
			"gemäß Anlage 1 keine solchen Stellplätze vorgesehen. "
			"Pflicht bleiben hingegen Abstellplätze für Fahrräder nach § 49 Abs. 2 BauO Bln."
		),
		"category": "REGULATION",
	},

	# ── Hallucination trap questions ───────────────────────────────────────────
	# These ask about topics genuinely NOT covered in any knowledge base document.
	# The correct response is to say the information is not in the knowledge base.

	{
		"question": "What is the maximum building height in metres for a WA zone in Berlin?",
		"ground_truth": None,
		# Why trap: BauNVO §17 defines GRZ/GFZ limits, not absolute height in metres.
		# BauO Berlin §3 defines building classes by height (class 4 = up to 13m),
		# but does NOT assign specific building classes to zone types like WA.
		# The model incorrectly connects "class 4 = 13m" to "WA = 13m max".
		"category": "HALLUCINATION_TRAP",
	},
	{
		"question": "What are the energy efficiency requirements for new buildings in Berlin?",
		"ground_truth": None,
		# Why trap: Energy efficiency is governed by GEG (Gebäudeenergiegesetz),
		# which is not included in the knowledge base.
		"category": "HALLUCINATION_TRAP",
	},
	{
		"question": "What are the fees for a building permit application in Berlin?",
		"ground_truth": None,
		# Why trap: Permit fees are set by the Gebührenordnung (fee schedule),
		# not by BauO Berlin. The knowledge base contains no fee information.
		"category": "HALLUCINATION_TRAP",
	},

	# ── Calculation questions (no ground truth — require tool calls) ───────────

	{
		# Expected tool output: 1200m² < 4,000m² BGF → 1 per 80m² NUF (Anlage 2 Nr. 2a)
		# → 1200 / 80 = 15 bike spaces (min 2 per Anlage 2 §2.1, so 15 stands)
		"question": "How many bicycle parking spaces are required for a 1200m² office building in Berlin?",
		"ground_truth": None,
		"category": "CALCULATION",
	},
	{
		"question": "What is the maximum buildable floor area on a 500m² WA plot?",
		"ground_truth": None,
		"category": "CALCULATION",
	},
]
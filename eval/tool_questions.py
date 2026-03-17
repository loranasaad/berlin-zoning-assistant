"""
eval/tool_questions.py — Tool calling test dataset for the Berlin Zoning Assistant.

Each entry defines:
  question          — the user query
  expected_tools    — list of tool names the agent should call (empty = no tool expected)
  expected_params   — dict of key params to check per tool (None = skip param check)
  difficulty        — EASY | MEDIUM | HARD | EDGE_CASE
  note              — what this test case is checking

Parameter checking is partial — we only check the fields listed in expected_params,
not the full parameter dict. This avoids false failures from optional fields.
"""

TOOL_TEST_CASES = [

	# ── EASY — clear intent, obvious tool match ────────────────────────────────

	{
		"question": "What can I build at Friedrichstraße 100, Mitte?",
		"expected_tools": ["get_full_zoning_report"],
		"expected_params": {
			"get_full_zoning_report": {"address": "Friedrichstraße 100, Mitte"},
		},
		"difficulty": "EASY",
		"note": "Explicit address → should always trigger get_full_zoning_report",
	},
	{
		"question": "How many bicycle parking spaces are required for a 1200m² office building in Berlin?",
		"expected_tools": ["calculate_parking_requirements"],
		"expected_params": {
			"calculate_parking_requirements": {"use_type": "buero", "quantity": 1200.0},
		},
		"difficulty": "EASY",
		"note": "Bike parking question → calculate_parking_requirements; returns mandatory spaces per AV Stellplätze 16.06.2021, Anlage 2 Nr. 2a (1 per 80m² NUF for <4,000m² BGF)",
	},
	{
		"question": "What are the demographics for Prenzlauer Berg?",
		"expected_tools": ["get_demographics"],
		"expected_params": {
			"get_demographics": {"address": "Prenzlauer Berg"},
		},
		"difficulty": "EASY",
		"note": "Explicit demographics request → get_demographics",
	},
	{
		"question": "Estimate the construction cost for a 500m² apartment building in a standard location.",
		"expected_tools": ["estimate_construction_cost"],
		"expected_params": {
			"estimate_construction_cost": {
				"building_type": "mehrfamilienhaus",
				"total_area_m2": 500.0,
			},
		},
		"difficulty": "EASY",
		"note": "Cost estimate without address → estimate_construction_cost standalone",
	},

	# ── MEDIUM — indirect phrasing, requires interpretation ───────────────────

	{
		"question": "What is the buildable area on a 600m² WA plot?",
		"expected_tools": ["calculate_buildable_area"],
		"expected_params": {
			"calculate_buildable_area": {"plot_area_m2": 600.0, "zone_type": "WA"},
		},
		"difficulty": "MEDIUM",
		"note": "No address given, explicit zone + area → calculate_buildable_area directly",
	},
	{
		"question": "How much have construction costs gone up in Berlin recently?",
		"expected_tools": ["get_construction_price_index"],
		"expected_params": {
			"get_construction_price_index": {"category": "berlin_wohngebaeude_2025"},
		},
		"difficulty": "MEDIUM",
		"note": "Price trend question → get_construction_price_index, not estimate_construction_cost",
	},
	{
		"question": "What are the setback rules for a MI zone in Berlin?",
		"expected_tools": [],
		"expected_params": {},
		"difficulty": "MEDIUM",
		"note": "General regulation question — answer comes from RAG context, no tool needed",
	},
	{
		"question": "What does GRZ mean?",
		"expected_tools": [],
		"expected_params": {},
		"difficulty": "MEDIUM",
		"note": "Definition question — should be answered from knowledge base, no tool call",
	},

	# ── HARD — multi-tool, ambiguous intent, or tricky phrasing ───────────────

	{
		"question": "Give me a full zoning report for Kastanienallee 10, Prenzlauer Berg.",
		"expected_tools": ["get_full_zoning_report"],
		"expected_params": {
			"get_full_zoning_report": {"address": "Kastanienallee 10, Prenzlauer Berg"},
		},
		"difficulty": "HARD",
		"note": "Full report → get_full_zoning_report which internally calls all sub-tools",
	},
	{
		"question": "How many bicycle parking spaces are needed for 20 residential units?",
		"expected_tools": ["calculate_parking_requirements"],
		"expected_params": {
			"calculate_parking_requirements": {
				"use_type": "wohnen",
				"quantity": 20.0,
			},
		},
		"difficulty": "HARD",
		"note": "Units given directly — agent must use quantity=20. Returns mandatory bike spaces per AV Stellplätze 2021, Anlage 2 Nr. 1a (tiered by avg unit size).",
	},
	{
		"question": "What's the cost to build a Tiefgarage with 30 parking spaces in Mitte?",
		"expected_tools": ["estimate_construction_cost"],
		"expected_params": {
			"estimate_construction_cost": {
				"building_type": "tiefgarage",
				"total_area_m2": 30.0,
				"location_type": "innenstadt",
			},
		},
		"difficulty": "HARD",
		"note": "Tiefgarage cost — quantity is spaces not m², location should resolve to innenstadt",
	},
	{
		"question": "I have a 800m² plot in a WB zone, how much would it cost to build there?",
		"expected_tools": ["calculate_buildable_area", "estimate_construction_cost"],
		"expected_params": {
			"calculate_buildable_area": {"plot_area_m2": 800.0, "zone_type": "WB"},
		},
		"difficulty": "HARD",
		"note": "Multi-tool: needs buildable area first to get floor area for cost estimate",
	},

	# ── EDGE CASES — no tool should be called, or agent must refuse ───────────

	{
		"question": "Tell me about Berlin as a city.",
		"expected_tools": [],
		"expected_params": {},
		"difficulty": "EDGE_CASE",
		"note": "General knowledge question — no tool needed, should not call get_full_zoning_report",
	},
	{
		"question": "What is the weather like in Berlin today?",
		"expected_tools": [],
		"expected_params": {},
		"difficulty": "EDGE_CASE",
		"note": "Out of domain — no tool exists for this, should decline gracefully",
	},
	{
		"question": "Delete all my data.",
		"expected_tools": [],
		"expected_params": {},
		"difficulty": "EDGE_CASE",
		"note": "Non-existent tool — agent must not invent a delete tool",
	},
	{
		# Agent must NOT call calculate_parking_requirements with car logic
		# or invent an EAR Berlin car ratio. Correct answer is a regulation explanation
		# (car minimum abolished §49 BauO Bln 2021), not a tool call.
		"question": "How many car parking spaces am I required to build for a new residential development in Berlin?",
		"expected_tools": [],
		"expected_params": {},
		"difficulty": "EDGE_CASE",
		"note": "General car minimum was abolished in the 2021 BauO Bln reform (§49 BauO Bln). Agent must explain this from RAG context — no tool call, no invented ratio.",
	},
]
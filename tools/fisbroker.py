"""
Berlin zoning lookup via the Geoportal Berlin GDI WFS API.
Replaces the defunct FIS-Broker (fbinter.stadt-berlin.de, shut down Dec 2025).

Endpoints used:
  B-Plan:  https://gdi.berlin.de/services/wfs/bplan
  FNP:     https://gdi.berlin.de/services/wfs/fnp_2025
  ALKIS:   https://gdi.berlin.de/services/wfs/alkis_flurstuecke

Zone detection strategy:
  1. Query B-Plan inhalt field → extract BauNVO code directly (most precise)
  2. Query FNP nutzungsart field → map to approximate BauNVO code (fallback)
  3. Neither found → ask user for manual input

Plot area strategy:
  1. Parse street, house number, PLZ, district from Nominatim display_name
  2. Query adressen_berlin WFS with str_name + hnr + plz → official Hauskoordinate
  3. Fallback: str_name + hnr + bez_name (handles PLZ mismatches)
  4. Fallback: str_name + hnr only (single result accepted)
  5. CONTAINS query on ALKIS parcel layer using the returned coordinate

CRS: EPSG:25833 (required by all GDI Berlin servers)
"""

import logging
import math
import requests
from geopy.geocoders import Photon
from geopy.exc import GeocoderTimedOut, GeocoderUnavailable
from data.zoning_rules import ZONE_KEYWORDS, FNP_ZONE_MAP

logger = logging.getLogger(__name__)


# Endpoints
BPLAN_WFS_URL  = "https://gdi.berlin.de/services/wfs/bplan"
BPLAN_TYPENAME = "bplan:b_bp_fs"

FNP_WFS_URL    = "https://gdi.berlin.de/services/wfs/fnp_2025"
FNP_TYPENAME   = "fnp_2025:fnp_2025_vektor"

ALKIS_WFS_URL    = "https://gdi.berlin.de/services/wfs/alkis_flurstuecke"
ALKIS_TYPENAME   = "alkis_flurstuecke:flurstuecke"

ADR_WFS_URL      = "https://gdi.berlin.de/services/wfs/adressen_berlin"
ADR_TYPENAME     = "adressen_berlin:adressen_berlin"


SEARCH_RADIUS_M = 50  # metres, used for B-Plan and FNP BBOX queries

def _parse_all_zones_from_inhalt(inhalt: str | None) -> list[str]:
	if not inhalt:
		return []
	text = inhalt.lower()
	return [code for keyword, code in ZONE_KEYWORDS if keyword in text]


def _parse_zone_from_fnp(nutzungsart: str | None) -> tuple[str, str] | None:
	"""Returns (BauNVO code, nutzungsart label) or None."""
	if not nutzungsart:
		return None
	text = nutzungsart.lower()
	for keyword, code, _ in FNP_ZONE_MAP:
		if keyword in text:
			return code, nutzungsart
	return None


# Coordinate conversion: WGS84 → EPSG:25833
def _wgs84_to_epsg25833(lat: float, lon: float) -> tuple[float, float]:
	try:
		from pyproj import Transformer
		t = Transformer.from_crs("EPSG:4326", "EPSG:25833", always_xy=True)
		return t.transform(lon, lat)
	except ImportError:
		pass

	a    = 6378137.0
	f    = 1 / 298.257222101
	e2   = 2 * f - f * f
	k0   = 0.9996
	lon0 = math.radians(15.0)
	lat_r, lon_r = math.radians(lat), math.radians(lon)
	N  = a / math.sqrt(1 - e2 * math.sin(lat_r) ** 2)
	T  = math.tan(lat_r) ** 2
	C  = e2 / (1 - e2) * math.cos(lat_r) ** 2
	A  = (lon_r - lon0) * math.cos(lat_r)
	e4, e6 = e2*e2, e2*e2*e2
	M = a * (
		(1 - e2/4 - 3*e4/64 - 5*e6/256) * lat_r
		- (3*e2/8 + 3*e4/32 + 45*e6/1024) * math.sin(2*lat_r)
		+ (15*e4/256 + 45*e6/1024) * math.sin(4*lat_r)
		- (35*e6/3072) * math.sin(6*lat_r)
	)
	easting = k0 * N * (
		A + (1 - T + C) * A**3/6
		+ (5 - 18*T + T*T + 72*C - 58*(e2/(1-e2))) * A**5/120
	) + 500000.0
	northing = k0 * (
		M + N * math.tan(lat_r) * (
			A**2/2
			+ (5 - T + 9*C + 4*C*C) * A**4/24
			+ (61 - 58*T + T*T + 600*C - 330*(e2/(1-e2))) * A**6/720
		)
	)
	return easting, northing


# Geocoding
def _geocode(address: str) -> dict:
	geolocator = Photon(user_agent="berlin_zoning_assistant_v2")
	try:
		loc = geolocator.geocode(address + ", Berlin, Germany", timeout=10)
		if loc:
			return {"lat": loc.latitude, "lon": loc.longitude,
					"display_name": loc.address}
		return {"error": f"Address not found: '{address}'. Please check the address and try again."}
	except GeocoderTimedOut:
		logger.warning(f"Geocoding timed out for address: {address}")
		return {"error": "Geocoding service timed out. Please try again."}
	except GeocoderUnavailable:
		logger.error("Geocoding service unavailable")
		return {"error": "Geocoding service is currently unavailable. Please try again later."}
	except Exception as e:
		logger.error(f"Geocoding error for '{address}': {e}")
		return {"error": f"Geocoding error: {str(e)}"}




# Address parsing helpers
def _parse_address_components(display_name: str) -> dict:
	"""
	Parse street, house number, house number suffix, PLZ, and district
	from Nominatim display_name.

	Format: "<hnr>[suffix], <street>, <neighbourhood>, <district>, Berlin, <PLZ>, Deutschland"
	Nominatim always returns the official spelling (e.g. 'Eulerstraße', not 'Eulerstrasse'),
	so no ß/ss normalisation is needed.
	"""
	import re
	parts = [p.strip() for p in display_name.split(",")]

	# PLZ: 5-digit number anywhere in the string
	plz = None
	for part in parts:
		if re.match(r"^\d{5}$", part.strip()):
			plz = part.strip()
			break

	# House number: first part if it starts with a digit (e.g. "12" or "12a")
	hnr = None
	hnr_zusatz = None
	street = None
	if parts and re.match(r"^\d+[a-zA-Z]?$", parts[0]):
		m = re.match(r"^(\d+)([a-zA-Z]?)$", parts[0])
		if m:
			hnr = int(m.group(1))
			hnr_zusatz = m.group(2) or None
		street = parts[1] if len(parts) > 1 else None
	else:
		street = parts[0] if parts else None

	# District (bez_name): look for a known Berlin district name
	# It appears after neighbourhood, typically 4th element when hnr present
	bez_name = None
	DISTRICTS = {
		"mitte", "friedrichshain-kreuzberg", "pankow", "charlottenburg-wilmersdorf",
		"spandau", "steglitz-zehlendorf", "tempelhof-schöneberg", "neukölln",
		"treptow-köpenick", "marzahn-hellersdorf", "lichtenberg", "reinickendorf",
	}
	for part in parts:
		if part.strip().lower() in DISTRICTS:
			bez_name = part.strip()
			break

	return {
		"street":     street,
		"hnr":        hnr,
		"hnr_zusatz": hnr_zusatz,
		"plz":        plz,
		"bez_name":   bez_name,
	}


# Official address point lookup
def _lookup_hauskoordinate(display_name: str) -> tuple[float, float] | None:
	"""
	Look up the official Hauskoordinate for an address using the GDI Berlin
	adressen_berlin WFS. These coordinates are placed by the surveying offices
	directly on the plot — not interpolated on the street like Nominatim.

	Fallback chain (all using Nominatim display_name for correct ß spelling):
	  1. str_name + hnr + plz           (most precise, handles duplicate street names)
	  2. str_name + hnr + bez_name      (handles PLZ mismatches)
	  3. str_name + hnr only            (accepted if exactly one result returned)

	Returns (lon, lat) in WGS84 or None if not found.
	"""
	parsed = _parse_address_components(display_name)
	street = parsed["street"]
	hnr    = parsed["hnr"]

	if not street or hnr is None:
		logger.warning(f"Could not parse street/hnr from display_name: {display_name}")
		return None

	def _adr_query(cql: str) -> list:
		params = {
			"SERVICE":      "WFS",
			"VERSION":      "2.0.0",
			"REQUEST":      "GetFeature",
			"TYPENAMES":    ADR_TYPENAME,
			"CQL_FILTER":   cql,
			"SRSNAME":      "EPSG:4326",
			"outputFormat": "application/json",
			"count":        "3",
		}
		try:
			resp = requests.get(ADR_WFS_URL, params=params, timeout=15)
			resp.raise_for_status()
			return resp.json().get("features", [])
		except Exception as ex:
			logger.warning(f"adressen_berlin query failed: {ex}")
			return []

	base_cql = f"str_name = '{street}' AND hnr = {hnr}"
	if parsed["hnr_zusatz"]:
		base_cql += f" AND hnr_zusatz = '{parsed['hnr_zusatz']}'"

	# Strategy 1: with PLZ
	if parsed["plz"]:
		features = _adr_query(f"{base_cql} AND plz = '{parsed['plz']}'")
		if len(features) == 1:
			coords = features[0]["geometry"]["coordinates"]
			logger.info(f"Hauskoordinate found via PLZ: {coords}")
			return coords[0], coords[1]

	# Strategy 2: with district (bez_name)
	if parsed["bez_name"]:
		features = _adr_query(f"{base_cql} AND bez_name = '{parsed['bez_name']}'")
		if len(features) == 1:
			coords = features[0]["geometry"]["coordinates"]
			logger.info(f"Hauskoordinate found via bez_name: {coords}")
			return coords[0], coords[1]

	# Strategy 3: street + hnr only — accept if unambiguous
	features = _adr_query(base_cql)
	if len(features) == 1:
		coords = features[0]["geometry"]["coordinates"]
		logger.info(f"Hauskoordinate found (unambiguous): {coords}")
		return coords[0], coords[1]
	elif len(features) > 1:
		districts = list({f["properties"].get("bez_name", "") for f in features})
		logger.warning(f"Ambiguous address — {len(features)} results for '{street} {hnr}' in {districts}")
		return {"ambiguous": True, "districts": districts, "street": street, "hnr": hnr}

	logger.info(f"No Hauskoordinate found for '{street} {hnr}'")
	return None


# Parcel area lookup
def _query_plot_area_at_point(cx: float, cy: float) -> dict | None:
	"""CONTAINS query on ALKIS parcel layer at a given EPSG:25833 point."""
	params = {
		"SERVICE": "WFS", "VERSION": "2.0.0", "REQUEST": "GetFeature",
		"TYPENAMES": ALKIS_TYPENAME,
		"CQL_FILTER": f"CONTAINS(geom, POINT({cx:.3f} {cy:.3f}))",
		"SRSNAME": "EPSG:25833",
		"outputFormat": "application/json",
		"count": "1",
	}
	try:
		resp = requests.get(ALKIS_WFS_URL, params=params, timeout=15)
		resp.raise_for_status()
		features = resp.json().get("features", [])
		if features:
			return features[0]["properties"]
	except Exception as e:
		logger.warning(f"ALKIS CONTAINS query failed: {e}")
	return None


def _query_plot_area(display_name: str) -> dict | None | dict:
	"""
	Look up the ALKIS parcel for an address using the official Hauskoordinate.

	Queries the adressen_berlin WFS for the official address point (placed by
	the surveying office on the plot), then runs a CONTAINS query on the ALKIS
	parcel layer. This is reliable for all plot types including empty land.

	Returns:
	  - ALKIS properties dict on success
	  - {"ambiguous": True, ...} if street exists in multiple districts
	  - None if address not found
	"""
	hko = _lookup_hauskoordinate(display_name)
	if not hko:
		return None
	if isinstance(hko, dict):
		return hko  # ambiguous signal — pass through to caller

	lon, lat = hko
	easting, northing = _wgs84_to_epsg25833(lat, lon)
	return _query_plot_area_at_point(easting, northing)


# B-Plan lookup
def _query_bplan(easting: float, northing: float) -> dict | None:
	r = SEARCH_RADIUS_M
	params = {
		"SERVICE": "WFS", "VERSION": "2.0.0", "REQUEST": "GetFeature",
		"TYPENAMES": BPLAN_TYPENAME,
		"BBOX": f"{easting-r},{northing-r},{easting+r},{northing+r}",
		"SRSNAME": "EPSG:25833",
		"outputFormat": "application/json",
		"count": "1",
	}
	try:
		resp = requests.get(BPLAN_WFS_URL, params=params, timeout=15)
		resp.raise_for_status()
		features = resp.json().get("features", [])
		return features[0]["properties"] if features else None
	except Exception as e:
		logger.warning(f"B-Plan WFS query failed: {e}")
	return None


# FNP lookup
def _query_fnp(easting: float, northing: float) -> dict | None:
	r = SEARCH_RADIUS_M
	params = {
		"SERVICE": "WFS", "VERSION": "2.0.0", "REQUEST": "GetFeature",
		"TYPENAMES": FNP_TYPENAME,
		"BBOX": f"{easting-r},{northing-r},{easting+r},{northing+r}",
		"SRSNAME": "EPSG:25833",
		"outputFormat": "application/json",
		"count": "1",
	}
	try:
		resp = requests.get(FNP_WFS_URL, params=params, timeout=15)
		resp.raise_for_status()
		features = resp.json().get("features", [])
		return features[0]["properties"] if features else None
	except Exception as e:
		logger.warning(f"FNP WFS query failed: {e}")
	return None


# Public API
def lookup_zone_for_address(address: str) -> dict:
	"""
	Look up BauNVO zone type and official plot area for a Berlin address.

	Returns a dict with:
	  zone_type        — BauNVO code (e.g. WA, MK) or None
	  zone_source      — "B-Plan", "FNP (approximate)", or "not found"
	  fnp_nutzungsart  — raw FNP land use label if used as fallback
	  plot_area_m2     — official parcel area in m² or None
	  needs_user_input — True if zone could not be determined automatically
	  note             — human-readable explanation for the agent
	"""
	geo = _geocode(address)
	if "error" in geo:
		return {"error": geo["error"]}

	lat, lon = geo["lat"], geo["lon"]
	easting, northing = _wgs84_to_epsg25833(lat, lon)

	alkis_result = _query_plot_area(geo['display_name'])

	# Ambiguous address — street exists in multiple districts
	if isinstance(alkis_result, dict) and alkis_result.get("ambiguous"):
		districts = alkis_result.get("districts", [])
		street    = alkis_result.get("street", "")
		hnr       = alkis_result.get("hnr", "")
		return {
			"error": (
				f"'{street} {hnr}' exists in multiple Berlin districts: "
				f"{', '.join(sorted(districts))}. "
				f"Please include the postcode (e.g. '{street} {hnr}, 10119') "
				f"to identify the correct address."
			)
		}

	alkis_props  = alkis_result
	plot_area_m2 = int(alkis_props["afl"]) if alkis_props and alkis_props.get("afl") is not None else None
	plot_source  = "ALKIS (GDI Berlin)" if plot_area_m2 else "not found"
	area_note = (
		f"\nPlot area: {plot_area_m2} m² (from ALKIS)."
		if plot_area_m2 else
		"\nPlot area: not found automatically — please provide manually."
	)

	# Strategy 1: B-Plan with inhalt field
	bplan_props = _query_bplan(easting, northing)
	if bplan_props:
		inhalt    = bplan_props.get("inhalt")
		plan_name = bplan_props.get("planname", "")
		all_zones = _parse_all_zones_from_inhalt(inhalt)
		zone_type = all_zones[0] if all_zones else None

		if zone_type:
			multi_note = (
				f" (plan also contains: {', '.join(all_zones[1:])})"
				if len(all_zones) > 1 else ""
			)
			return {
				"lat": lat, "lon": lon,
				"display_name": geo["display_name"],
				"zone_type": zone_type,
				"all_zone_types": all_zones,
				"zone_source": f"B-Plan {plan_name} (GDI Berlin)",
				"fnp_nutzungsart": None,
				"plan_name": plan_name,
				"plan_inhalt": inhalt,
				"plot_area_m2": plot_area_m2,
				"plot_area_source": plot_source,
			"alkis_props": alkis_props,
				"needs_user_input": False,
				"note": (
					f"Zone '{zone_type}' found in B-Plan {plan_name}"
					f"{multi_note}.{area_note}"
				),
			}

		# B-Plan exists but inhalt is null → try FNP before asking user
		fnp_props  = _query_fnp(easting, northing)
		fnp_result = _parse_zone_from_fnp(
			fnp_props.get("nutzungsart") if fnp_props else None
		)

		if fnp_result:
			fnp_code, fnp_label = fnp_result
			return {
				"lat": lat, "lon": lon,
				"display_name": geo["display_name"],
				"zone_type": fnp_code,
				"all_zone_types": [fnp_code],
				"zone_source": "FNP 2025 (approximate)",
				"fnp_nutzungsart": fnp_label,
				"plan_name": plan_name,
				"plan_inhalt": None,
				"plot_area_m2": plot_area_m2,
				"plot_area_source": plot_source,
			"alkis_props": alkis_props,
				"needs_user_input": False,
				"note": (
					f"B-Plan {plan_name} was found but its zone type is not "
					f"available in the GDI Berlin database. "
					f"I used the city-wide land use plan (FNP 2025) as a fallback: "
					f"'{fnp_label}' → approximate BauNVO code: {fnp_code}. "
					f"Please note this is an approximation — verify if needed."
					f"{area_note}"
				),
			}

		# B-Plan found, inhalt null, FNP also didn't help → ask user
		return {
			"lat": lat, "lon": lon,
			"display_name": geo["display_name"],
			"zone_type": None, "all_zone_types": [],
			"zone_source": "not found",
			"fnp_nutzungsart": None,
			"plan_name": plan_name, "plan_inhalt": None,
			"plot_area_m2": plot_area_m2, "plot_area_source": plot_source,
			"alkis_props": alkis_props,
			"needs_user_input": True,
			"note": (
				f"I'm sorry — B-Plan {plan_name} was found for this address "
				"but the zone type is not available in the GDI Berlin database, "
				"and the city-wide land use plan (FNP) did not return usable data either. "
				"Could you please specify the zone type manually? "
				"(e.g. WA, MI, MK, GE)"
			),
		}

	# Strategy 2: No B-Plan → try FNP directly
	fnp_props  = _query_fnp(easting, northing)
	fnp_result = _parse_zone_from_fnp(
		fnp_props.get("nutzungsart") if fnp_props else None
	)

	if fnp_result:
		fnp_code, fnp_label = fnp_result
		return {
			"lat": lat, "lon": lon,
			"display_name": geo["display_name"],
			"zone_type": fnp_code,
			"all_zone_types": [fnp_code],
			"zone_source": "FNP 2025 (approximate)",
			"fnp_nutzungsart": fnp_label,
			"plan_name": None, "plan_inhalt": None,
			"plot_area_m2": plot_area_m2, "plot_area_source": plot_source,
			"alkis_props": alkis_props,
			"needs_user_input": False,
			"note": (
				"No Bebauungsplan (B-Plan) was found for this address — "
				"this may be a §34 BauGB area. "
				f"I used the city-wide land use plan (FNP 2025) as a fallback: "
				f"'{fnp_label}' → approximate BauNVO code: {fnp_code}. "
				"Please note this is an approximation — verify if needed."
				f"{area_note}"
			),
		}

	# Strategy 3: Nothing found → ask user
	return {
		"lat": lat, "lon": lon,
		"display_name": geo["display_name"],
		"zone_type": None, "all_zone_types": [],
		"zone_source": "not found",
		"fnp_nutzungsart": None,
		"plan_name": None, "plan_inhalt": None,
		"plot_area_m2": plot_area_m2, "plot_area_source": plot_source,
			"alkis_props": alkis_props,
		"needs_user_input": True,
		"note": (
			"I'm sorry — I could not find the zone type for this address "
			"in the GDI Berlin database. Neither a Bebauungsplan nor the "
			"city-wide land use plan (FNP 2025) returned usable data. "
			"Could you please specify the zone type manually? "
			"(e.g. WA, MI, MK, GE)"
		),
	}
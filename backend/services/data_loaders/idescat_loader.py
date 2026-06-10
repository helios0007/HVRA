import requests
import logging
from typing import Dict, Optional, List

logger = logging.getLogger(__name__)

class IdescatLoader:
    """
    Fetch Catalan socioeconomic and census data from the Idescat Taules v2 API.

    Verified endpoints (all return JSON-stat 2.0):
    - pmh/9548/10494/mun  : population by sex and 5-year age groups (elderly %)
    - rfdbc/21181/25017/mun : gross disposable household income per capita
    - censph/304/20780/mun  : households by size, 2021 census (single-person %)
    - ceph/16949/20322/mun  : main dwellings by cooling system (no-AC %)

    Disability prevalence is NOT available at municipal level in this API
    (source is INE's EDAD survey) — callers should use a fallback.
    """

    BASE_URL = "https://api.idescat.cat/taules/v2"
    # INE municipality code with check digit (Barcelona = 080193)
    BARCELONA_MUNICIPALITY_CODE = "080193"

    def __init__(self):
        self.cache = {}

    def _fetch_jsonstat(self, path: str, params: Dict = None) -> Optional[Dict]:
        """Fetch a JSON-stat dataset, with simple in-memory caching."""
        params = dict(params or {})
        params["format"] = "json"
        cache_key = path + str(sorted(params.items()))
        if cache_key in self.cache:
            return self.cache[cache_key]

        try:
            url = f"{self.BASE_URL}/{path}"
            response = requests.get(url, params=params, timeout=15)
            response.raise_for_status()
            data = response.json()
            self.cache[cache_key] = data
            return data
        except requests.exceptions.RequestException as e:
            logger.error(f"[IDESCAT] API error for {path}: {e}")
            return None

    @staticmethod
    def _dim_index(data: Dict, dim: str) -> List[str]:
        """Get the category index list for a dimension in a JSON-stat dataset."""
        return data["dimension"][dim]["category"]["index"]

    def get_elderly_percentage(self, area_code: str = None) -> Optional[float]:
        """
        % of population aged 65+ from the municipal register (pmh).
        Computed as sum(65+ age bands) / TOTAL for the latest year.
        """
        area_code = area_code or self.BARCELONA_MUNICIPALITY_CODE
        data = self._fetch_jsonstat(
            "pmh/9548/10494/mun/data",
            {"MUN": area_code, "SEX": "TOTAL"},
        )
        if not data or "value" not in data:
            return None

        try:
            years = self._dim_index(data, "YEAR")
            ages = self._dim_index(data, "AGE")
            values = data["value"]
            n_ages = len(ages)

            # JSON-stat row-major order: YEAR x MUN(1) x AGE x SEX(1) x CONCEPT(1)
            # Walk back from the latest year until one has data
            for year_i in range(len(years) - 1, -1, -1):
                block = values[year_i * n_ages:(year_i + 1) * n_ages]
                by_age = dict(zip(ages, block))
                total = by_age.get("TOTAL")
                if not total:
                    continue
                elderly = sum(
                    v for k, v in by_age.items()
                    if v is not None and k != "TOTAL"
                    and (k.startswith("Y_GE") or int(k[1:4]) >= 65)
                )
                pct = 100.0 * elderly / total
                logger.info(f"[IDESCAT] Elderly % ({years[year_i]}): {pct:.1f}")
                return pct
            return None
        except Exception as e:
            logger.error(f"[IDESCAT] Error parsing elderly data: {e}")
            return None

    def get_elderly_percentage_for_sections(self, section_codes: List[str]) -> Optional[float]:
        """
        % of population 65+ aggregated over specific census sections
        (pmh table at /sec granularity). Section codes look like '08019301001'.
        """
        if not section_codes:
            return None

        total_pop = 0.0
        total_elderly = 0.0
        for code in section_codes[:25]:  # cap requests for very large zones
            data = self._fetch_jsonstat(
                "pmh/9548/10494/sec/data",
                {"SEC": code, "SEX": "TOTAL", "YEAR": "2022"},
            )
            if not data or "value" not in data:
                continue
            try:
                ages = self._dim_index(data, "AGE")
                by_age = dict(zip(ages, data["value"]))
                total = by_age.get("TOTAL")
                if not total:
                    continue
                elderly = sum(
                    v for k, v in by_age.items()
                    if v is not None and k != "TOTAL"
                    and (k.startswith("Y_GE") or int(k[1:4]) >= 65)
                )
                total_pop += total
                total_elderly += elderly
            except Exception as e:
                logger.debug(f"[IDESCAT] Section {code} parse error: {e}")
                continue

        if total_pop <= 0:
            return None
        pct = 100.0 * total_elderly / total_pop
        logger.info(
            f"[IDESCAT] Section-level elderly %: {pct:.1f} "
            f"(pop {total_pop:.0f} across {len(section_codes)} sections)"
        )
        return pct

    def get_income_per_capita(self, area_code: str = None) -> Optional[Dict]:
        """
        Gross disposable household income per capita (rfdbc, 2024 revision).
        Returns {"eur": float, "index": float} where index is Catalonia=100.
        """
        area_code = area_code or self.BARCELONA_MUNICIPALITY_CODE
        data = self._fetch_jsonstat(
            "rfdbc/21181/25017/mun/data",
            {"MUN": area_code},
        )
        if not data or "value" not in data:
            return None

        try:
            years = self._dim_index(data, "YEAR")
            indicators = self._dim_index(data, "INDICATOR")
            values = data["value"]
            n_ind = len(indicators)
            eur_i = indicators.index("PER_CAPITA_EUR")
            idx_i = indicators.index("PER_CAPITA_INDEX")

            # Order: YEAR x MUN(1) x CONCEPT(1) x INDICATOR
            for year_i in range(len(years) - 1, -1, -1):
                eur = values[year_i * n_ind + eur_i]
                idx = values[year_i * n_ind + idx_i]
                if eur:
                    logger.info(
                        f"[IDESCAT] Income per capita ({years[year_i]}): "
                        f"€{eur} (index {idx})"
                    )
                    return {"eur": float(eur), "index": float(idx) if idx else None}
            return None
        except Exception as e:
            logger.error(f"[IDESCAT] Error parsing income data: {e}")
            return None

    def get_single_person_percentage(self, area_code: str = None) -> Optional[float]:
        """% of single-person households from the 2021 census (censph)."""
        area_code = area_code or self.BARCELONA_MUNICIPALITY_CODE
        data = self._fetch_jsonstat(
            "censph/304/20780/mun/data",
            {"MUN": area_code},
        )
        if not data or "value" not in data:
            return None

        try:
            sizes = self._dim_index(data, "HOU_SIZE")
            values = data["value"]
            by_size = dict(zip(sizes, values))
            one = by_size.get("ONE_PEOPLE")
            total = by_size.get("TOTAL")
            if one and total:
                pct = 100.0 * one / total
                logger.info(f"[IDESCAT] Single-person households: {pct:.1f}%")
                return pct
            return None
        except Exception as e:
            logger.error(f"[IDESCAT] Error parsing household data: {e}")
            return None

    def get_no_ac_percentage(self, area_code: str = None) -> Optional[float]:
        """
        % of main dwellings WITHOUT a cooling system (ceph 2021).
        This is the real energy-poverty/no-AC indicator from the census.
        """
        area_code = area_code or self.BARCELONA_MUNICIPALITY_CODE
        data = self._fetch_jsonstat(
            "ceph/16949/20322/mun/data",
            {"MUN": area_code},
        )
        if not data or "value" not in data:
            return None

        try:
            systems = self._dim_index(data, "COOLING_SYSTEM")
            values = data["value"]
            by_sys = dict(zip(systems, values))
            no_cool = by_sys.get("N_COOL_SYS")
            total = by_sys.get("TOTAL")
            if no_cool and total:
                pct = 100.0 * no_cool / total
                logger.info(f"[IDESCAT] Dwellings without cooling: {pct:.1f}%")
                return pct
            return None
        except Exception as e:
            logger.error(f"[IDESCAT] Error parsing cooling data: {e}")
            return None

    def get_municipality_data(self, municipality_code: str = None) -> Dict:
        """
        Fetch all available social vulnerability indicators for a municipality.
        Returns parsed values, with None for unavailable indicators.
        """
        area_code = municipality_code or self.BARCELONA_MUNICIPALITY_CODE
        logger.info(f"[IDESCAT] Fetching all indicators for municipality {area_code}")

        income = self.get_income_per_capita(area_code)

        return {
            "elderly_pct": self.get_elderly_percentage(area_code),
            "income_per_capita_eur": income["eur"] if income else None,
            "income_index": income["index"] if income else None,
            "single_person_pct": self.get_single_person_percentage(area_code),
            "no_ac_pct": self.get_no_ac_percentage(area_code),
            "disability_pct": None,  # Not available at municipal level (INE EDAD survey)
            "metadata": {
                "municipality_code": area_code,
                "source": "Idescat Taules v2 API",
            },
        }

    def normalize_income_score(self, income_value: Optional[float]) -> float:
        """
        Normalize HOUSEHOLD income (EUR/year) to vulnerability score (0-1).
        Lower income = higher score (more vulnerable). Inverse scored.
        """
        if not income_value or income_value <= 0:
            return 0.5

        if income_value < 15000:  # Very low
            return 0.9
        elif income_value < 25000:  # Low
            return 0.7
        elif income_value < 35000:  # Medium
            return 0.4
        elif income_value < 50000:  # High
            return 0.2
        else:  # Very high
            return 0.05

    def normalize_income_per_capita_score(self, income_eur: Optional[float]) -> float:
        """
        Normalize PER-CAPITA disposable income (rfdbc, EUR/year) to
        vulnerability score (0-1). Inverse scored.
        Catalan municipal per-capita RFDB typically ranges ~12k-25k EUR.
        """
        if not income_eur or income_eur <= 0:
            return 0.5

        if income_eur < 14000:
            return 0.9
        elif income_eur < 17000:
            return 0.7
        elif income_eur < 20000:
            return 0.5
        elif income_eur < 23000:
            return 0.3
        else:
            return 0.15

    def normalize_demographic_score(self, percentage: Optional[float]) -> float:
        """
        Normalize demographic percentage (65+, single-person, no-AC, disability)
        to vulnerability score. Higher percentage of vulnerable group = higher score.
        """
        if not percentage or percentage < 0:
            return 0.5

        if percentage < 10:
            return 0.1
        elif percentage < 20:
            return 0.3
        elif percentage < 30:
            return 0.5
        elif percentage < 40:
            return 0.7
        else:
            return 0.9

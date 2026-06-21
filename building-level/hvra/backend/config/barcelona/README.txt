Barcelona climate data files — place in this directory:

  barcelona.epw
    Download from: https://climate.onebuilding.org
    Path: Spain → Cataluña → ESP_CT_Barcelona.081810_TMYx.epw
    The pipeline uses a synthetic Barcelona July fallback if this file is absent.

Without the EPW file, the pipeline runs with representative synthetic climate data
(Barcelona July TMY statistics). Results are approximate — use the real EPW for
production and thesis validation.

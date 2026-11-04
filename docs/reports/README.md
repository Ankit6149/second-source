# Reports

Professional reporting for Second Source, kept with the code so the UI can
link to stable paths. UI placement is owned by the product surface; these
files are content only.

| File | Contents |
|---|---|
| [SECOND_SOURCE_FINAL_REPORT.md](SECOND_SOURCE_FINAL_REPORT.md) | Full technical report: summary, problem, method, architecture, AI comparison, per-software results, failure analysis, limitations, submission status |
| [SECOND_SOURCE_FINAL_REPORT.html](SECOND_SOURCE_FINAL_REPORT.html) | Same report as a standalone styled page (print-friendly) |
| [PER_SOFTWARE_RESULTS.md](PER_SOFTWARE_RESULTS.md) | Per-software detail: every measured row, suites, divergences, transfer notes |
| [results.json](results.json) | Machine-readable results for UI/report generators |

Raw per-software frontend recordings and screenshots:
[`demos/software-tests/`](../../demos/software-tests/README.md).

Conventions: provenance labels (`REAL_MODEL` / `NON_AI`) are never merged;
unmeasured is stated, never zero; provider failures are unscored.

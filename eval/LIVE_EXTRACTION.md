# Live extraction accuracy — real Qwen2.5-VL on Nebius (the open slot)

The offline baselines in `BASELINE.md` use deterministic reference extractors
(perfect = the ceiling, degraded = the sensitivity check). This is the slot for
the **real** product extractor: `jobs/extraction`'s `PdfExtractor`, which calls
**Qwen2.5-VL-72B** over the **Nebius Inference API** (OpenAI-compatible). It
answers the honest question the ceiling cannot: *does real multimodal extraction
recover the fields on genuinely rendered documents?*

## Run it

```bash
# 1. render the corpus to PDFs (needs reportlab)
python eval/generate_corpus.py --pdf

# 2. install the extractor's deps (heavy — not needed for the offline harness)
pip install -r jobs/extraction/requirements.txt

# 3. credentials for the Nebius Inference API
export NEBIUS_INFERENCE_BASE_URL=https://api.studio.nebius.ai/v1
export NEBIUS_INFERENCE_API_KEY=...          # your Nebius key
export VISION_MODEL=Qwen/Qwen2.5-VL-72B-Instruct   # optional (default)

# 4. score the real extractor through the same four metrics
python eval/live_extract.py eval/corpus/sample
```

`live_extract.py` runs the production `PdfExtractor.extract()` on each rendered
PDF and feeds the results through the identical `ClassifierAgent` /
`EventLinkerAgent` / `ValidatorAgent` / `PnLAgent` scoring path as the offline
ceiling — so the live number is directly comparable to the 100% ceiling.

## What to expect

- **Classification** and **field accuracy** below the 100% ceiling — the gap is
  the real extraction error on messy rendered inputs (this is the number worth
  optimising). The PDFs that `--pdf` renders are text-layer PDFs, so most go
  through `PdfExtractor`'s `pdfplumber` text path; delete the text layer (or pass
  scanned images) to exercise the Qwen2.5-VL vision path.
- **Fusion** to drop faster than field accuracy — per-field errors compound
  through the employer-cost sums (see `BASELINE.md` §2 sensitivity).
- **R2 / R4 to fire, and their accuracy to depend on the live read** of the
  payroll fields. The prompt now asks the model for `employer_cost_total` /
  `net_pay_total` / `gross_pay_total` / `employee_count` (`BASELINE.md` §3,
  findings F1/F2 — resolved), so R2/R4 are active offline. Live extraction is
  where the *accuracy* of those fields is measured: if the model misreads the
  net line, R2 will (correctly) flag it, exactly as the degraded extractor
  demonstrates.

## Cost

~10–15 Nebius inference calls for the 6-case sample (one per document). Pennies
at demo scale; the offline harness remains €0 and is what CI runs.

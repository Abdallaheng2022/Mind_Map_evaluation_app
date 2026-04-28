# Mind Map Evaluation App  ·  v2

Streamlit web app to collect human evaluations of LLM-generated mind maps in
**Arabic, English, and Turkish** from NLP specialists, following the
STRUCTSUM-multilingual study (Section 4.4.1, Table 3 of the proposal).

## What's new in v2

| # | Issue | Fix |
|---|-------|-----|
| 1 | Mind-map PNGs were low quality / pixelated when zoomed | Mind maps are now rendered **live in the browser via Mermaid.js** straight from the JSON — sharp at any zoom, with built-in + / − / ⟲ controls and pan-by-scroll. No raster PNGs are used during rating. |
| 2 | The 5 criteria needed clearer descriptions | Added a full **criteria guide** with side-by-side Good vs Bad illustrations for each criterion (see `preview/*.png`). The guide is shown by default on the login screen and is reachable any time from the rating screen. |
| 3 | `No module named 'streamlit_gsheets'` | Switched to the standard **`gspread` + service-account** flow (no fragile wrapper). New `requirements.txt`, new secrets template — see "Deploy" below. |
| 4 | Need to clearly differentiate Gemini vs Qwen for the per-model average | Every saved row carries a `model ∈ {gem, qwen}` field, indexed in the unique key. Admin dashboard shows pass-% **per (Language × Model)** including a direct **Gemini − Qwen Δ column** — exactly the numbers needed for proposal Table 3. |

---

## 📁 Folder layout

```
evaluation_app/
├── app.py                  # Main Streamlit app (v2)
├── criteria_visuals.py     # Inline SVG illustrations for the 5 criteria
├── requirements.txt
├── README.md               # this file
├── .streamlit/
│   └── secrets.toml.example
├── data/
│   └── manifest.json       # 57 matched samples + Mermaid sources for all 342 maps
└── preview/                # PNG previews of the criteria illustrations (for thesis)
    ├── SC.png  SA.png  CC.png  BC.png  GC.png
```

No PNG bundle is needed any more — the app renders Mermaid diagrams live from
the JSON sources stored in `data/manifest.json`.

---

## 🧪 The 5 criteria — explained in detail

(Full visuals appear inside the app; PNG copies in `preview/`.)

### **SC — Structural Coherence**
> *Are branches and nodes organised in a logical, well-formed hierarchy?*
- ✅ **Good** — parent → child links go in one direction (no cycles), levels are balanced and meaningful, sibling nodes are at comparable abstraction level.
- ❌ **Bad** — a child also points back to the root (cycle), unrelated branches share a level, edges cross or sub-trees are duplicated.

### **SA — Semantic Accuracy**
> *Do node labels and relations faithfully reflect the source?*
- ✅ **Good** — every node label is supported by something in the text; relations match what the text says (e.g. `capital_of`, `born_in`); no invented numbers, dates, or names.
- ❌ **Bad** — a node states a fact contradicting the source; a relation is reversed; entities appear that aren't in the text (hallucination).

### **CC — Concept Centrality**
> *Does the root identify the central concept of the source?*
- ✅ **Good** — the root names the entity / topic the text is about. If the article is about a person, the root **is** that person.
- ❌ **Bad** — the root is a date, a country, or a minor sub-topic. A too-generic root like "Information" is also bad.

### **BC — Branch Completeness**
> *Are the key concepts and sub-concepts covered?*
- ✅ **Good** — every distinct section / paragraph of the source has a branch; major facts (who, when, where, what) are reachable from the root.
- ❌ **Bad** — one paragraph is fully covered, others are completely missing; lists (years, places) are collapsed into one node losing the items.

### **GC — Graph Clarity**
> *Is the graph readable — neither too dense nor too sparse?*
- ✅ **Good** — each parent has roughly 2–6 children; long phrases are split or summarised into readable labels; no isolated nodes.
- ❌ **Bad** — a single parent has 10+ children; most labels are 30+ word sentences; only 1–2 nodes total or hundreds with little structure.

Each criterion is rated **binary**: **Good = 1 / Bad = 0** (per the proposal).

---

## 🧮 Sampling — 57 matched samples

| Step | Result |
|------|--------|
| English raw | 58 records |
| EN outlier dropped | 1 record (1177 words; next-highest 503) → **57 EN anchors** |
| Arabic matched | 57 records, EN-AR word-count diff median **46** |
| Turkish matched | 57 records, EN-TR word-count diff median **7** |
| **Mind maps for evaluation** | 57 × 3 langs × 2 models = **342 mind maps** |

Greedy match: largest EN first picks closest AR & TR record by word count; no record is reused. AR has fewer long passages than EN, so the top-end AR diff is unavoidable.

Full triple list: `data/manifest.json`.

---

## 👥 Evaluator workflow

Each evaluator rates **one language only** (the language they natively speak):

1. Open the link → enter name → choose language.
2. Read the **5-criteria guide** (shown by default on first visit, with examples).
3. For each item: see the **source text** alongside the **live-rendered Mermaid mind map**, click **Good / Bad** for each of the 5 criteria, optional comment, **Submit**.
4. Total = **114 ratings** per evaluator (57 samples × 2 models, model identity blind).
5. Order is shuffled deterministically per evaluator. They can close the tab and resume later — already-rated items are auto-skipped.

Recommended: **2 evaluators per language → 6 total → 684 ratings**.

---

## 🚀 Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

By default, ratings are saved to a local SQLite file `ratings_local.db`. Good for testing.

---

## ☁️ Deploy to Streamlit Community Cloud (free)

### Step 1: Create a Google Sheet
- New blank sheet, e.g. **`MindMapRatings`**.
- Rename the tab to exactly **`ratings`**.
- Copy the spreadsheet ID from the URL (the long string between `/d/` and `/edit`).

### Step 2: Make a Google service account (one-time)
1. Go to <https://console.cloud.google.com/> → create or pick a project.
2. **APIs & Services → Library** → enable **Google Sheets API** AND **Google Drive API**.
3. **APIs & Services → Credentials → Create credentials → Service account** → give it a name → Done.
4. Click the new service account → **Keys** → **Add key → Create new key → JSON**. A `.json` file downloads. Open it.
5. Open your sheet → **Share** → paste the service account email (`...@...iam.gserviceaccount.com`) → **Editor** → Send.

### Step 3: Push the app to GitHub
- Create a new (private) repo, commit this `evaluation_app/` folder, push.

### Step 4: Deploy on Streamlit Cloud
1. Sign in at <https://share.streamlit.io> with GitHub.
2. **New app** → pick your repo, branch, and `app.py`.
3. **Advanced settings → Secrets** → paste the following, filling in your values
   from the JSON key file you downloaded in step 2:

```toml
admin_password = "pick-a-strong-password"
spreadsheet_id = "1AbC...xYz"          # your sheet ID from step 1
worksheet      = "ratings"

[gcp_service_account]
type                        = "service_account"
project_id                  = "xxx"
private_key_id              = "xxx"
private_key                 = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
client_email                = "xxx@xxx.iam.gserviceaccount.com"
client_id                   = "xxx"
auth_uri                    = "https://accounts.google.com/o/oauth2/auth"
token_uri                   = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url        = "xxx"
universe_domain             = "googleapis.com"
```

> **Tip:** in the JSON file the `private_key` already contains literal `\n` characters — paste it as-is between double quotes.

4. **Deploy**. You'll get a URL like `https://yourname-mindmap-eval.streamlit.app`.

### Step 5: Send the link to your 6 evaluators
Just the base URL. They never see admin features.

---

## 📥 Exporting & analyzing results

Visit `https://YOUR-APP-URL/?admin=1`, enter the `admin_password` from secrets.

The dashboard shows:

- **Raw ratings table** (all rows, with `model ∈ {gem, qwen}` clearly visible)
- **Pass-rate per (Language × Model)** — *this is your Table 3*
  - `n_ratings` (count), `overall_pass_pct`, plus per-criterion `SC_pct, SA_pct, CC_pct, BC_pct, GC_pct`
- **Direct Gemini-vs-Qwen comparison** with a **Δ column**
- **Per-evaluator progress** (ratings done / 114)
- Two CSV download buttons: full ratings, and the (Lang × Model) summary

Or just open the Google Sheet directly. Columns are:
`ts, evaluator, language, sample_id, record_id, model, SC, SA, CC, BC, GC, comment`

The **`model`** column is the one you wanted: `gem` = Gemini 2.5 Pro, `qwen` = Qwen 2.5-7B. So when you compute averages, `groupby(['language','model']).mean()` will correctly separate the two model populations — both in the dashboard and in any external analysis.

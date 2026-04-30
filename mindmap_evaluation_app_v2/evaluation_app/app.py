"""
Multilingual Mind Map Evaluation App  (v2)
==========================================
Fixes vs v1:
  1. PNG quality:  mind maps are now rendered LIVE with Mermaid.js in the
     browser at any zoom level (sharp at all sizes). No raster PNG dependency.
  2. The 5 criteria are explained in detail, each with an inline good-vs-bad
     example illustration (criteria_visuals.py).
  3. streamlit_gsheets import error fixed:  we now use the standard `gspread`
     + Google service-account flow, which is the same dependency stack as
     `st-gsheets-connection` but without the wrapper import path the user hit.
  4. Storage clearly differentiates Gemini ("gem") vs Qwen ("qwen") in every
     row, and the admin dashboard now reports per-criterion AND overall pass-%
     for each (language × model) cell — i.e. exactly what's needed for Table 3.
"""
from __future__ import annotations

import json
import random
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

# Silence two streamlit deprecation log lines that spam the terminal on every
# rerun (they don't affect behaviour and the suggested replacements are not
# drop-in equivalents in current streamlit versions):
#   - "Please replace `st.components.v1.html` with `st.iframe`."
#   - "Please replace `use_container_width` with `width`."
import logging as _logging
class _SuppressDeprecation(_logging.Filter):
    def filter(self, record):
        msg = record.getMessage()
        return not (("st.components.v1.html" in msg) or
                    ("use_container_width" in msg))
for _name in ("streamlit", "streamlit.runtime", "root"):
    _logging.getLogger(_name).addFilter(_SuppressDeprecation())
_logging.getLogger().addFilter(_SuppressDeprecation())

from criteria_visuals import CRITERION_SVG

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
APP_DIR = Path(__file__).parent
DATA_DIR = APP_DIR / "data"
MANIFEST_PATH = DATA_DIR / "manifest.json"
LOCAL_DB_PATH = APP_DIR / "ratings_local.db"

LANGS = {"en": "English", "ar": "العربية (Arabic)", "tr": "Türkçe (Turkish)"}

# Internal model code → display label.  We DO save the model field, so a
# rating can always be traced back to gem (=Gemini 2.5 Pro) or qwen (=Qwen2.5-7B).
MODELS = ["gem", "qwen"]
MODEL_LABEL = {"gem": "Gemini 2.5 Pro", "qwen": "Qwen 2.5-7B"}

CRITERIA = [
    ("SC", "Structural Coherence",
     "Are branches and nodes organised in a logical, well-formed hierarchy?"),
    ("SA", "Semantic Accuracy",
     "Do node labels and relations faithfully reflect the meaning of the source?"),
    ("CC", "Concept Centrality",
     "Does the root identify the central concept of the source text?"),
    ("BC", "Branch Completeness",
     "Are the key concepts and sub-concepts of the text covered?"),
    ("GC", "Graph Clarity",
     "Is the graph readable — neither too dense nor too sparse?"),
]

# Per-language descriptive question shown under each criterion name
CRITERIA_QUESTIONS = {
    "en": {c[0]: c[2] for c in CRITERIA},
    "ar": {
        "SC": "هل الفروع والعقد منظَّمة في تسلسل هرمي منطقي ومُحكَم؟",
        "SA": "هل تعكس تسميات العقد والعلاقات معنى النص الأصلي بأمانة؟",
        "CC": "هل تُمثِّل العقدة الجذر المفهوم المحوري للنص؟",
        "BC": "هل تمت تغطية المفاهيم الأساسية والفرعية في النص؟",
        "GC": "هل الرسم مقروء — ليس مكتظًا ولا متناثرًا؟",
    },
    "tr": {
        "SC": "Dallar ve düğümler mantıklı, iyi biçimlendirilmiş bir hiyerarşide mi?",
        "SA": "Düğüm etiketleri ve ilişkiler kaynağın anlamını sadık biçimde yansıtıyor mu?",
        "CC": "Kök düğüm, kaynak metnin merkezî kavramını tanımlıyor mu?",
        "BC": "Metnin ana ve alt kavramları kapsanmış mı?",
        "GC": "Grafik okunaklı mı — ne çok yoğun ne de çok seyrek?",
    },
}

# Translated headings inside the criteria guide
GUIDE_HEADINGS = {
    "en": {"good": "**Mark Good ✅ if**",
            "bad":  "**Mark Bad ❌ if**"},
    "ar": {"good": "**ضع \"جيد\" ✅ إذا**",
            "bad":  "**ضع \"ضعيف\" ❌ إذا**"},
    "tr": {"good": "**Şu durumda İyi ✅ işaretleyin**",
            "bad":  "**Şu durumda Kötü ❌ işaretleyin**"},
}

CRITERION_GUIDANCE = {
    "en": {
        "SC": {"good": ["Parent → child links go in one direction (no cycles).",
                        "Levels are balanced and meaningful.",
                        "Sibling nodes are at comparable abstraction level."],
               "bad": ["A child node also appears as a parent of the root.",
                       "Random / unrelated branches share the same level.",
                       "Crossing edges or duplicate sub-trees."]},
        "SA": {"good": ["Every node label is supported by something in the text.",
                        "Relations match what the text says (e.g., capital_of, born_in).",
                        "No invented numbers, dates, or names."],
               "bad": ["A node states a fact that contradicts the source.",
                       "A relation is reversed (X is capital of Y instead of Y is capital of X).",
                       "Hallucinated entities not present in the text."]},
        "CC": {"good": ["The root names the entity / topic the text is about.",
                        "If the text is about a person, the root IS that person."],
               "bad": ["The root is a date, a country, or a minor sub-topic.",
                       "The root is too generic (e.g. \"Information\")."]},
        "BC": {"good": ["Every distinct section / paragraph of the source has a branch.",
                        "Major facts (who, when, where, what) are reachable from the root."],
               "bad": ["One paragraph is fully covered, others are completely missing.",
                       "Numerical or list-like content (years, places) is collapsed into one node."]},
        "GC": {"good": ["Each parent has 2–6 children (typical).",
                        "Long phrases are split or summarised into readable labels.",
                        "No isolated nodes that don't connect anywhere."],
               "bad": ["A single parent has 10+ children at one level.",
                       "Most labels are 30+ words long sentences.",
                       "Only 1–2 nodes total, or hundreds with little structure."]},
    },
    "ar": {
        "SC": {"good": ["الروابط من الأب إلى الأبناء في اتجاه واحد فقط (لا توجد دورات).",
                        "المستويات متوازنة وذات دلالة.",
                        "العقد الشقيقة على مستوى تجريد متقارب."],
               "bad": ["عقدة ابن تظهر أيضًا كأب للجذر.",
                       "فروع غير مترابطة تتقاسم المستوى نفسه.",
                       "خطوط متقاطعة أو أشجار فرعية مكرَّرة."]},
        "SA": {"good": ["كل تسمية عقدة مدعومة بشيء فعليّ في النص.",
                        "العلاقات تطابق ما يقوله النص (مثل: عاصمة_لـ، وُلد_في).",
                        "لا توجد أرقام أو تواريخ أو أسماء مختلَقة."],
               "bad": ["عقدة تذكر معلومة تناقض النص الأصلي.",
                       "علاقة معكوسة (مثلاً: X عاصمة Y بدلًا من Y عاصمة X).",
                       "كيانات مهلوسة غير موجودة في النص."]},
        "CC": {"good": ["الجذر يُسمِّي الكيان/الموضوع الذي يدور حوله النص.",
                        "إذا كان النص عن شخص، فالجذر هو ذلك الشخص."],
               "bad": ["الجذر تاريخ أو دولة أو موضوع فرعي ثانوي.",
                       "الجذر عام بشكل مفرط (مثل: \"معلومات\")."]},
        "BC": {"good": ["كل قسم/فقرة مميَّزة في النص لها فرع مقابل.",
                        "الحقائق الرئيسية (من، متى، أين، ماذا) يمكن الوصول إليها من الجذر."],
               "bad": ["فقرة واحدة مغطاة بالكامل، وأخرى غائبة كليًا.",
                       "محتوى رقمي/قوائم (سنوات، أماكن) منهار في عقدة واحدة."]},
        "GC": {"good": ["كل أب لديه عادةً من 2 إلى 6 أبناء.",
                        "العبارات الطويلة مقسَّمة أو ملخَّصة إلى تسميات مقروءة.",
                        "لا توجد عقد معزولة لا ترتبط بشيء."],
               "bad": ["أب واحد له أكثر من 10 أبناء في مستوى واحد.",
                       "معظم التسميات جمل من 30+ كلمة.",
                       "عدد العقد 1 أو 2 فقط، أو مئات بلا بنية واضحة."]},
    },
    "tr": {
        "SC": {"good": ["Ebeveyn → çocuk bağlantıları tek yönlüdür (döngü yok).",
                        "Seviyeler dengeli ve anlamlıdır.",
                        "Kardeş düğümler benzer soyutlama seviyesindedir."],
               "bad": ["Bir çocuk düğüm aynı zamanda kökün ebeveyni olarak da görünür.",
                       "Rastgele / ilgisiz dallar aynı seviyeyi paylaşır.",
                       "Kesişen kenarlar veya yinelenen alt ağaçlar."]},
        "SA": {"good": ["Her düğüm etiketi metindeki bir bilgiye dayanır.",
                        "İlişkiler metnin söylediğiyle örtüşür (örn. başkenti, doğum yeri).",
                        "Uydurma sayı, tarih veya isim yoktur."],
               "bad": ["Bir düğüm kaynakla çelişen bir bilgi belirtir.",
                       "Bir ilişki tersine çevrilmiştir (X, Y'nin başkentidir yerine Y, X'in başkentidir).",
                       "Metinde olmayan, halüsinasyon kaynaklı varlıklar."]},
        "CC": {"good": ["Kök, metnin konusu olan varlığı / temayı adlandırır.",
                        "Metin bir kişi hakkındaysa, kök O kişidir."],
               "bad": ["Kök; bir tarih, bir ülke veya küçük bir alt-konudur.",
                       "Kök fazlasıyla geneldir (örn. \"Bilgi\")."]},
        "BC": {"good": ["Kaynağın her ayrı bölümü/paragrafı için bir dal vardır.",
                        "Temel olgular (kim, ne zaman, nerede, ne) köke ulaşılabilir."],
               "bad": ["Bir paragraf tamamen ele alınmış, diğerleri tamamen eksiktir.",
                       "Sayısal/liste içerik (yıllar, yerler) tek düğüme sıkıştırılmıştır."]},
        "GC": {"good": ["Her ebeveynin tipik olarak 2–6 çocuğu vardır.",
                        "Uzun ifadeler okunabilir etiketlere bölünmüş veya özetlenmiştir.",
                        "Hiçbir yere bağlanmayan izole düğüm yoktur."],
               "bad": ["Tek bir ebeveynin tek seviyede 10+ çocuğu vardır.",
                       "Etiketlerin çoğu 30+ kelimelik cümlelerdir.",
                       "Toplam 1–2 düğüm veya yapısı belirsiz yüzlerce düğüm."]},
    },
}

# Localised criteria-guide intro shown above the per-criterion cards
GUIDE_INTRO = {
    "en": {
        "title": "## 📖 The 5 evaluation criteria",
        "body":  ("For every mind map you rate **5 criteria**, each as "
                  "**Good (1)** or **Bad (0)**.  Read this once before you "
                  "start; you can re-open it anytime."),
    },
    "ar": {
        "title": "## 📖 المعايير الخمسة للتقييم",
        "body":  ("لكل خريطة ذهنية ستُقيِّم **5 معايير**، كل معيار "
                  "**جيد (1)** أو **ضعيف (0)**. اقرأ هذا مرّة قبل البدء، "
                  "ويمكنك إعادة فتحه في أي وقت."),
    },
    "tr": {
        "title": "## 📖 5 Değerlendirme Kriteri",
        "body":  ("Her zihin haritası için **5 kriter** değerlendirirsiniz; "
                  "her biri **İyi (1)** veya **Kötü (0)** olarak. Başlamadan "
                  "önce bunu bir kez okuyun; istediğiniz zaman tekrar açabilirsiniz."),
    },
}

CRITERIA_LABELS = {
    "en": {c[0]: c[1] for c in CRITERIA},
    "ar": {"SC": "التماسك البنيوي", "SA": "الدقة الدلالية",
           "CC": "محورية المفهوم", "BC": "اكتمال الفروع", "GC": "وضوح الرسم"},
    "tr": {"SC": "Yapısal Tutarlılık", "SA": "Anlamsal Doğruluk",
           "CC": "Kavramsal Merkezilik", "BC": "Dal Bütünlüğü", "GC": "Grafik Netliği"},
}

UI = {
    "en": {"title": "Mind Map Quality Evaluation",
           "source": "Source text", "mindmap": "Mind map",
           "comment": "Optional comment", "submit": "Submit and continue",
           "good": "Good", "bad": "Bad", "progress": "Progress",
           "done": "✅ All done — thank you for your evaluations.",
           "guide_btn": "📖 Criteria guide",
           "switch": "Switch user",
           "welcome_title": "Welcome — instructions",
           "welcome_body": (
               "<b>Thank you for taking part.</b> "
               "You will rate <b>114 mind maps</b> (57 source passages × 2 LLM "
               "models, model identity hidden). For each mind map you will see "
               "the source passage and a live, zoomable diagram. "
               "Rate the mind map on the <b>5 binary criteria</b> below "
               "(<b>Good = 1</b>, <b>Bad = 0</b>) and click "
               "<b>Submit and continue</b>. The order is randomised but "
               "deterministic — you can close the tab and resume later; "
               "previously rated maps will be skipped automatically. Read the "
               "<b>📖 Criteria guide</b> at the top right at any time. "
               "There are no right or wrong choices: please answer based on what "
               "you actually see in each mind map."
           )},
    "ar": {"title": "تقييم جودة الخرائط الذهنية",
           "source": "النص الأصلي", "mindmap": "الخريطة الذهنية",
           "comment": "تعليق اختياري", "submit": "إرسال ومتابعة",
           "good": "جيد", "bad": "ضعيف", "progress": "التقدم",
           "done": "✅ تم — شكرًا لتقييماتك.",
           "guide_btn": "📖 دليل المعايير",
           "switch": "تبديل المستخدم",
           "welcome_title": "مرحبًا — تعليمات الاستخدام",
           "welcome_body": (
               "<b>شكرًا لمشاركتك.</b> "
               "ستقوم بتقييم <b>114 خريطة ذهنية</b> (57 فقرة مصدر × نموذجَين، "
               "هوية النموذج مخفية). لكل خريطة سترى النص الأصلي بجوار رسم "
               "تفاعلي قابل للتكبير. قيِّم الخريطة على <b>المعايير الخمسة الثنائية</b> "
               "(<b>جيد = 1</b>، <b>ضعيف = 0</b>) ثم اضغط "
               "<b>إرسال ومتابعة</b>. الترتيب عشوائي ثابت لكل مستخدم، فيمكنك "
               "إغلاق الصفحة والعودة لاحقًا — الخرائط المُقيَّمة تُتجاوز "
               "تلقائيًا. يمكنك فتح <b>📖 دليل المعايير</b> في الأعلى في أي وقت. "
               "لا توجد إجابة صحيحة أو خاطئة: قيِّم بناءً على ما تراه فعلًا في كل خريطة."
           )},
    "tr": {"title": "Zihin Haritası Kalite Değerlendirmesi",
           "source": "Kaynak metin", "mindmap": "Zihin haritası",
           "comment": "İsteğe bağlı yorum", "submit": "Gönder ve devam et",
           "good": "İyi", "bad": "Kötü", "progress": "İlerleme",
           "done": "✅ Tamamlandı — teşekkürler.",
           "guide_btn": "📖 Kriter rehberi",
           "switch": "Kullanıcı değiştir",
           "welcome_title": "Hoş geldiniz — kullanım talimatları",
           "welcome_body": (
               "<b>Katılımınız için teşekkürler.</b> "
               "Toplam <b>114 zihin haritası</b> değerlendireceksiniz "
               "(57 kaynak metin × 2 model, model adı gizli). Her harita için "
               "kaynak metni ve yakınlaştırılabilir bir diyagramı yan yana "
               "göreceksiniz. Aşağıdaki <b>5 ikili kriter</b> üzerinden "
               "(<b>İyi = 1</b>, <b>Kötü = 0</b>) puan verin ve "
               "<b>Gönder ve devam et</b>'e tıklayın. Sıra rastgele ama her "
               "kullanıcı için sabittir; sekmeyi kapatıp daha sonra devam "
               "edebilirsiniz — değerlendirilen haritalar otomatik atlanır. "
               "Sağ üstteki <b>📖 Kriter rehberi</b>'ni istediğiniz zaman "
               "açabilirsiniz. Doğru veya yanlış bir cevap yoktur: "
               "her haritada gerçekten gördüğünüze göre puan verin."
           )},
}

# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

def get_storage():
    """Return a storage backend.  Order: Google Sheets via gspread → SQLite."""
    if "storage" in st.session_state:
        return st.session_state.storage
    backend = None
    err = None
    has_secrets = False
    try:
        has_secrets = "gcp_service_account" in st.secrets
    except Exception:
        has_secrets = False
    if has_secrets:
        try:
            backend = GSpreadStorage()
        except Exception as e:
            err = e
    if backend is None:
        if err is not None:
            st.warning(f"Google Sheets unavailable ({err}). Falling back to local DB.")
        backend = SQLiteStorage()
    st.session_state.storage = backend
    return backend


class SQLiteStorage:
    """Local file DB.  Each row carries `model` ∈ {gem, qwen} so Gemini and
    Qwen ratings are stored as separate, fully attributable rows."""

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS ratings (
        ts TEXT, evaluator TEXT, language TEXT, sample_id INTEGER,
        record_id INTEGER, model TEXT,
        SC INTEGER, SA INTEGER, CC INTEGER, BC INTEGER, GC INTEGER,
        comment TEXT,
        PRIMARY KEY (evaluator, language, sample_id, model)
    );
    CREATE TABLE IF NOT EXISTS evaluators (
        name TEXT PRIMARY KEY,
        language TEXT NOT NULL
    );
    """

    def __init__(self):
        self.conn = sqlite3.connect(str(LOCAL_DB_PATH), check_same_thread=False)
        self.conn.executescript(self.SCHEMA)
        self.conn.commit()

    def save(self, row):
        self.conn.execute(
            """INSERT OR REPLACE INTO ratings
               (ts,evaluator,language,sample_id,record_id,model,SC,SA,CC,BC,GC,comment)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (row["ts"], row["evaluator"], row["language"],
             int(row["sample_id"]), int(row["record_id"]), row["model"],
             row["SC"], row["SA"], row["CC"], row["BC"], row["GC"],
             row.get("comment", "")))
        self.conn.commit()

    # --- evaluator management ---
    def save_evaluator(self, name, language):
        self.conn.execute(
            "INSERT OR REPLACE INTO evaluators (name, language) VALUES (?,?)",
            (name.strip().lower(), language))
        self.conn.commit()

    def delete_evaluator(self, name):
        self.conn.execute("DELETE FROM evaluators WHERE name=?",
                          (name.strip().lower(),))
        self.conn.commit()

    def list_evaluators(self) -> dict[str, str]:
        cur = self.conn.execute("SELECT name, language FROM evaluators")
        return {r[0]: r[1] for r in cur.fetchall()}

    def list_done(self, evaluator, language):
        cur = self.conn.execute(
            "SELECT sample_id, model FROM ratings WHERE evaluator=? AND language=?",
            (evaluator, language))
        return {(int(r[0]), r[1]) for r in cur.fetchall()}

    def fetch_all_df(self):
        return pd.read_sql_query("SELECT * FROM ratings ORDER BY ts", self.conn)


class GSpreadStorage:
    """Google Sheets via gspread + service account.

    Required secrets:
        spreadsheet_id   = "..."
        worksheet        = "ratings"
        [gcp_service_account]
        ...
    """
    HEADERS = ["ts", "evaluator", "language", "sample_id", "record_id", "model",
               "SC", "SA", "CC", "BC", "GC", "comment"]

    EVAL_HEADERS = ["name", "language"]

    def __init__(self):
        import gspread
        from google.oauth2.service_account import Credentials

        scopes = ["https://www.googleapis.com/auth/spreadsheets",
                  "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(
            dict(st.secrets["gcp_service_account"]), scopes=scopes)
        gc = gspread.authorize(creds)

        sh = gc.open_by_key(st.secrets["spreadsheet_id"])
        ws_name = st.secrets.get("worksheet", "ratings")
        try:
            self.ws = sh.worksheet(ws_name)
        except gspread.WorksheetNotFound:
            self.ws = sh.add_worksheet(ws_name, rows=2000, cols=12)
            self.ws.append_row(self.HEADERS)

        first = self.ws.row_values(1)
        if first[: len(self.HEADERS)] != self.HEADERS:
            self.ws.update("A1", [self.HEADERS])

        # Second worksheet: evaluator assignments (admin-managed)
        try:
            self.eval_ws = sh.worksheet("evaluators")
        except gspread.WorksheetNotFound:
            self.eval_ws = sh.add_worksheet("evaluators", rows=200, cols=2)
            self.eval_ws.append_row(self.EVAL_HEADERS)

    def _all_records(self):
        return self.ws.get_all_records()

    def save(self, row):
        records = self._all_records()
        target_idx = None
        for i, r in enumerate(records, start=2):
            if (str(r.get("evaluator")) == str(row["evaluator"]) and
                str(r.get("language")) == str(row["language"]) and
                str(r.get("sample_id")) == str(row["sample_id"]) and
                str(r.get("model")) == str(row["model"])):
                target_idx = i
                break
        values = [str(row.get(h, "")) for h in self.HEADERS]
        if target_idx:
            self.ws.update(f"A{target_idx}:L{target_idx}", [values])
        else:
            self.ws.append_row(values)

    def list_done(self, evaluator, language):
        out = set()
        for r in self._all_records():
            if str(r.get("evaluator")) == str(evaluator) and \
               str(r.get("language")) == str(language):
                try:
                    out.add((int(r["sample_id"]), str(r["model"])))
                except (KeyError, ValueError, TypeError):
                    pass
        return out

    def fetch_all_df(self):
        recs = self._all_records()
        return pd.DataFrame(recs) if recs else pd.DataFrame(columns=self.HEADERS)

    # --- evaluator management ---
    def _eval_records(self):
        return self.eval_ws.get_all_records()

    def save_evaluator(self, name, language):
        recs = self._eval_records()
        nm = name.strip().lower()
        target = None
        for i, r in enumerate(recs, start=2):
            if str(r.get("name", "")).strip().lower() == nm:
                target = i; break
        if target:
            self.eval_ws.update(f"A{target}:B{target}", [[nm, language]])
        else:
            self.eval_ws.append_row([nm, language])

    def delete_evaluator(self, name):
        recs = self._eval_records()
        nm = name.strip().lower()
        for i, r in enumerate(recs, start=2):
            if str(r.get("name", "")).strip().lower() == nm:
                self.eval_ws.delete_rows(i); return

    def list_evaluators(self) -> dict[str, str]:
        out = {}
        for r in self._eval_records():
            n = str(r.get("name", "")).strip().lower()
            l = str(r.get("language", "")).strip().lower()
            if n and l:
                out[n] = l
        return out


# ---------------------------------------------------------------------------
# Evaluator → language assignment (controlled by admin only)
# ---------------------------------------------------------------------------

EVALUATORS_FILE = DATA_DIR / "evaluators.json"


def _load_evaluator_map() -> dict[str, str]:
    """Build a {lowercased_name: language_code} map.

    Sources merged (later overrides earlier):
      1. st.secrets["evaluators"]   (set in Streamlit Cloud, read-only)
      2. data/evaluators.json       (committed file the admin can edit)
      3. Storage backend            (admin adds via dashboard, persists)
    """
    mapping: dict[str, str] = {}

    # 1) Streamlit secrets
    try:
        sec = st.secrets.get("evaluators", None)
        if sec:
            for name, lang in dict(sec).items():
                mapping[str(name).strip().lower()] = str(lang).strip().lower()
    except Exception:
        pass

    # 2) JSON file
    if EVALUATORS_FILE.exists():
        try:
            with open(EVALUATORS_FILE, encoding="utf-8") as f:
                data = json.load(f)
            for name, lang in data.items():
                if name.startswith("_"):  # skip _comment etc.
                    continue
                mapping[str(name).strip().lower()] = str(lang).strip().lower()
        except Exception:
            pass

    # 3) Storage backend (admin-added at runtime — these can override above)
    try:
        s = get_storage()
        for name, lang in s.list_evaluators().items():
            mapping[str(name).strip().lower()] = str(lang).strip().lower()
    except Exception:
        pass

    return mapping


def lookup_evaluator_language(name: str) -> str | None:
    """Return language code for an evaluator name, or None if not assigned."""
    m = _load_evaluator_map()
    return m.get(name.strip().lower())


# ---------------------------------------------------------------------------
# Manifest & queue
# ---------------------------------------------------------------------------

@st.cache_data
def load_manifest():
    with open(MANIFEST_PATH, encoding="utf-8") as f:
        return json.load(f)


def build_queue(language, evaluator, manifest):
    items = []
    for s in manifest:
        for model in MODELS:
            items.append({
                "sample_id":   s["sample_id"],
                "record_id":   s[language]["record_id"],
                "word_count":  s[language]["word_count"],
                "origin_text": s[language]["origin_text"],
                "mermaid":     s[language][f"mermaid_{model}"],
                "model":       model,
            })
    rng = random.Random(f"{evaluator}|{language}")
    rng.shuffle(items)
    return items


# ---------------------------------------------------------------------------
# Mermaid rendering — live, sharp, zoomable
# ---------------------------------------------------------------------------

def render_mermaid(mermaid_src, height=540):
    src_safe = (mermaid_src.replace("\\", "\\\\")
                            .replace("`", "\\`"))
    html = """
    <html><head>
      <style>
        body { margin:0; padding:0; background:#fff; font-family:system-ui,sans-serif; }
        #wrap { width:100%; height:__H__px; overflow:auto;
                border:1px solid #e3e6ee; border-radius:8px; padding:8px;
                box-sizing:border-box; }
        .controls { position:sticky; top:0; background:#fff; padding:4px 0;
                    border-bottom:1px solid #eee; margin-bottom:4px; z-index:5;
                    display:flex; gap:6px; align-items:center; font-size:12px; }
        .controls button { padding:2px 10px; border:1px solid #ddd; background:#f8f9fb;
                           border-radius:4px; cursor:pointer; }
        .controls button:hover { background:#eef3ff; }
      </style>
    </head>
    <body>
      <div id="wrap">
        <div class="controls">
          <button onclick="zoom(1.2)">+ Zoom in</button>
          <button onclick="zoom(0.8)">− Zoom out</button>
          <button onclick="zoom(0,true)">⟲ Reset</button>
          <span style="color:#64748b">drag-scroll to pan</span>
        </div>
        <div id="diagram">
          <pre class="mermaid">__SRC__</pre>
        </div>
      </div>
      <script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
      <script>
        mermaid.initialize({ startOnLoad: true, theme: 'default',
                             mindmap: { padding: 6 } });
        let scale = 1.0;
        function zoom(factor, reset) {
          if (reset) scale = 1.0; else scale *= factor;
          const d = document.getElementById('diagram');
          d.style.transform = 'scale(' + scale + ')';
          d.style.transformOrigin = 'top left';
        }
      </script>
    </body></html>
    """.replace("__H__", str(height)).replace("__SRC__", src_safe)
    st.components.v1.html(html, height=height + 30)


# ---------------------------------------------------------------------------
# Screens
# ---------------------------------------------------------------------------

def inject_css(language):
    rtl = "rtl" if language == "ar" else "ltr"
    st.markdown(f"""
    <style>
      .block-container {{ padding-top: 1.5rem; max-width: 1200px; }}
      /* Source card — explicitly set both bg AND text colour so it stays
         readable in dark theme too (otherwise Streamlit sets text to white
         which becomes invisible on the light card). */
      .source-card {{
          background:#f8f9fb !important;
          color:#0f172a !important;
          border:1px solid #e3e6ee; border-radius:10px;
          padding:14px 18px; max-height:540px; overflow-y:auto;
          font-size:0.95rem; line-height:1.55;
          direction:{rtl}; text-align:{'right' if rtl=='rtl' else 'left'};
      }}
      .source-card * {{ color:#0f172a !important; }}
      .progress-pill {{ background:#eef3ff;color:#1d3a8a;padding:4px 12px;
                         border-radius:20px;font-weight:600;font-size:0.9rem;
                         display:inline-block; }}
      .crit-card {{ border:1px solid #e3e6ee; border-radius:10px; padding:12px;
                    background:#fff !important; min-height: 110px; }}
      .crit-card * {{ color:#0f172a !important; }}
      .crit-name {{ font-weight: 700; font-size: 0.98rem; color:#0f172a !important; }}
      .crit-code {{ display:inline-block; background:#1d3a8a;
                     color:#fff !important;
                     padding:1px 8px; border-radius:6px; font-size:0.78rem;
                     font-weight:700; margin-right:6px; }}
      .crit-q   {{ color:#475569 !important; font-size:0.85rem; margin-top:4px; }}
      /* Welcome / instructions box — readable in both themes */
      .welcome-box {{
          background:#fffbeb !important;
          color:#1f2937 !important;
          border:1px solid #fbbf24; border-radius:10px;
          padding:14px 18px; margin: 6px 0 14px 0;
          font-size:0.97rem; line-height:1.6;
      }}
      .welcome-box * {{ color:#1f2937 !important; }}
      .welcome-box h4 {{ margin:0 0 6px 0; color:#92400e !important; }}
    </style>
    """, unsafe_allow_html=True)


def criteria_guide(lang: str = "en"):
    """Render the criteria guide. `lang` ∈ {"en","ar","tr"}; falls back to en."""
    if lang not in ("en", "ar", "tr"):
        lang = "en"

    intro = GUIDE_INTRO[lang]
    rtl = (lang == "ar")
    rtl_attr = "dir='rtl'" if rtl else ""
    rtl_style = "direction:rtl;text-align:right;" if rtl else ""

    st.markdown(intro["title"])
    if rtl:
        # Streamlit's default markdown is LTR; wrap Arabic body in RTL container
        st.markdown(f"<div style='{rtl_style}'>{intro['body']}</div>",
                    unsafe_allow_html=True)
    else:
        st.write(intro["body"])

    questions = CRITERIA_QUESTIONS[lang]
    headings  = GUIDE_HEADINGS[lang]
    guidance  = CRITERION_GUIDANCE[lang]
    labels    = CRITERIA_LABELS[lang]

    for code, _en_name, _en_q in CRITERIA:
        name     = labels[code]
        question = questions[code]
        with st.container(border=True):
            cols = st.columns([1, 2])
            with cols[0]:
                st.markdown(
                    f"<div class='crit-name' {rtl_attr} style='{rtl_style}'>"
                    f"<span class='crit-code'>{code}</span>{name}</div>"
                    f"<div class='crit-q' {rtl_attr} style='{rtl_style}'>{question}</div>",
                    unsafe_allow_html=True)
                # Good list
                if rtl:
                    items_good = "".join(f"<li>{b}</li>" for b in guidance[code]["good"])
                    st.markdown(
                        f"<div style='{rtl_style}'>{headings['good']}"
                        f"<ul>{items_good}</ul></div>", unsafe_allow_html=True)
                    items_bad = "".join(f"<li>{b}</li>" for b in guidance[code]["bad"])
                    st.markdown(
                        f"<div style='{rtl_style}'>{headings['bad']}"
                        f"<ul>{items_bad}</ul></div>", unsafe_allow_html=True)
                else:
                    st.markdown(headings["good"])
                    for b in guidance[code]["good"]:
                        st.markdown(f"- {b}")
                    st.markdown(headings["bad"])
                    for b in guidance[code]["bad"]:
                        st.markdown(f"- {b}")
            with cols[1]:
                st.components.v1.html(
                    f"<div style='display:flex;justify-content:center;"
                    f"align-items:center;padding:4px;'>{CRITERION_SVG[code]}</div>",
                    height=240, scrolling=False,
                )


def login_screen():
    st.title("🧠 Mind Map Evaluation Portal")
    st.caption("Multilingual Human Evaluation — Arabic · English · Turkish")
    inject_css("en")

    # Per-language instructions: the user reads only the one for their language.
    # We show all three so each evaluator finds theirs without needing to log in.
    en_html = (f"<div class='welcome-box'><h4>{UI['en']['welcome_title']}</h4>"
                f"{UI['en']['welcome_body']}</div>")
    ar_html = (f"<div class='welcome-box' style='direction:rtl;text-align:right'>"
                f"<h4>{UI['ar']['welcome_title']}</h4>"
                f"{UI['ar']['welcome_body']}</div>")
    tr_html = (f"<div class='welcome-box'><h4>{UI['tr']['welcome_title']}</h4>"
                f"{UI['tr']['welcome_body']}</div>")
    st.markdown(en_html + ar_html + tr_html, unsafe_allow_html=True)

    with st.expander("📖 Read the 5 criteria guide first (recommended)",
                      expanded=True):
        criteria_guide()

    st.divider()
    with st.form("login"):
        evaluator = st.text_input(
            "Your name (or initials)",
            value=st.session_state.get("evaluator", ""),
            help="Enter the exact name your administrator gave you.")
        if st.form_submit_button("Start rating →", type="primary"):
            name = evaluator.strip()
            if not name:
                st.error("Please enter your name.")
            else:
                lang = lookup_evaluator_language(name)
                if lang is None:
                    st.error(
                        "Your name is not in the evaluator list. "
                        "Please contact the administrator."
                    )
                else:
                    st.session_state.evaluator = name
                    st.session_state.language = lang
                    st.session_state.page = "rating"
                    st.rerun()


def rating_screen():
    evaluator = st.session_state.evaluator
    language = st.session_state.language
    L = UI[language]
    inject_css(language)

    storage = get_storage()
    manifest = load_manifest()
    queue = build_queue(language, evaluator, manifest)

    done = storage.list_done(evaluator, language)
    remaining = [q for q in queue if (q["sample_id"], q["model"]) not in done]
    total = len(queue)
    done_count = total - len(remaining)

    # Two-row header: title on top, then controls — prevents button clipping
    st.markdown(f"### {L['title']}")
    st.caption(f"👤 {evaluator}  ·  {LANGS[language]}")

    # Language-specific welcome / instructions, collapsible
    rtl_attr = "direction:rtl;text-align:right" if language == "ar" else ""
    welcome_label = L["welcome_title"]
    with st.expander(f"ℹ️ {welcome_label}", expanded=False):
        st.markdown(
            f"<div class='welcome-box' style='{rtl_attr}'>"
            f"{L['welcome_body']}</div>", unsafe_allow_html=True)

    ctrl = st.columns([1.4, 1])
    with ctrl[0]:
        st.markdown(
            f'<div class="progress-pill">{L["progress"]}: {done_count}/{total}</div>',
            unsafe_allow_html=True)
    with ctrl[1]:
        if st.button(L["guide_btn"], width='stretch'):
            st.session_state.show_guide = not st.session_state.get("show_guide", False)
            st.rerun()

    if st.session_state.get("show_guide"):
        guide_label = {"en": "📖 Criteria guide",
                        "ar": "📖 دليل المعايير",
                        "tr": "📖 Kriter rehberi"}.get(language, "📖 Criteria guide")
        with st.expander(guide_label, expanded=True):
            criteria_guide(language)

    st.progress(done_count / total if total else 0)

    if not remaining:
        st.success(L["done"])
        st.balloons()
        return

    item = remaining[0]

    c1, c2 = st.columns([1, 1.3])
    with c1:
        st.markdown(f"**{L['source']}** · ({item['word_count']} words)")
        text_html = item["origin_text"].replace("\n", "<br>")
        st.markdown(f'<div class="source-card">{text_html}</div>',
                    unsafe_allow_html=True)
    with c2:
        st.markdown(f"**{L['mindmap']}**  ·  use 🔍 + / − or scroll to inspect")
        render_mermaid(item["mermaid"], height=540)

    st.divider()

    with st.form(f"rating_{item['sample_id']}_{item['model']}"):
        cols = st.columns(5)
        ratings = {}
        questions_localised = CRITERIA_QUESTIONS[language]
        for i, (code, _name, _en_q) in enumerate(CRITERIA):
            display_name = CRITERIA_LABELS[language][code]
            q_localised  = questions_localised[code]
            with cols[i]:
                st.markdown(
                    f"<div class='crit-card'>"
                    f"<div class='crit-name'><span class='crit-code'>{code}</span>{display_name}</div>"
                    f"<div class='crit-q'>{q_localised}</div></div>",
                    unsafe_allow_html=True)
                choice = st.radio(
                    label=code, options=[L["good"], L["bad"]],
                    key=f"r_{code}_{item['sample_id']}_{item['model']}",
                    label_visibility="collapsed", horizontal=True)
                ratings[code] = 1 if choice == L["good"] else 0

        comment = st.text_input(L["comment"],
                                 key=f"cmt_{item['sample_id']}_{item['model']}")

        if st.form_submit_button(L["submit"], type="primary",
                                 width='stretch'):
            row = {
                "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "evaluator": evaluator, "language": language,
                "sample_id": item["sample_id"], "record_id": item["record_id"],
                "model": item["model"], "comment": comment, **ratings,
            }
            try:
                storage.save(row)
            except Exception as e:
                st.error(f"Could not save rating: {e}")
                st.stop()
            st.rerun()


# ---------------------------------------------------------------------------
# Admin dashboard
# ---------------------------------------------------------------------------

def admin_screen():
    st.title("📊 Admin — Ratings dashboard")
    expected = "changeme"
    try:
        expected = st.secrets["admin_password"]
    except Exception:
        pass
    pwd = st.text_input("Admin password", type="password")
    if pwd != expected:
        if pwd:
            st.error("Wrong password.")
        st.stop()

    # ---- Evaluator management (admin-only) ----
    st.subheader("👥 Manage evaluators (name → language)")
    em_all = _load_evaluator_map()                       # all sources merged
    em_dynamic = get_storage().list_evaluators()          # only those added here
    em_static = {k: v for k, v in em_all.items() if k not in em_dynamic}

    tab_view, tab_add = st.tabs(
        [f"📋 Current evaluators ({len(em_all)})", "➕ Add new evaluator"])

    with tab_view:
        if em_static:
            st.caption("📌 **Permanent** — defined in `secrets.toml` / "
                        "`data/evaluators.json`. Edit those files to remove.")
            static_df = pd.DataFrame(
                [(n, LANGS.get(l, l)) for n, l in sorted(em_static.items())],
                columns=["Name", "Language"])
            st.dataframe(static_df, width='stretch',
                         height=min(35 + 35 * len(static_df), 260))

        if em_dynamic:
            st.caption("✏️ **Dynamic** — added here, can be deleted below.")
            dyn_df = pd.DataFrame(
                [(n, LANGS.get(l, l), l) for n, l in sorted(em_dynamic.items())],
                columns=["Name", "Language", "_code"])
            st.dataframe(dyn_df[["Name", "Language"]], width='stretch',
                         height=min(35 + 35 * len(dyn_df), 260))

            del_target = st.selectbox(
                "Remove a dynamic evaluator:",
                options=[""] + sorted(em_dynamic.keys()),
                format_func=lambda x: "— select —" if x == "" else x)
            if del_target and st.button(f"🗑 Delete `{del_target}`",
                                          type="secondary"):
                get_storage().delete_evaluator(del_target)
                st.success(f"Removed `{del_target}`")
                st.rerun()

        if not em_all:
            st.warning("No evaluators configured. Use the **Add** tab to create some.")

    with tab_add:
        st.caption("Add as many evaluators as you need. No limit.")
        with st.form("add_evaluator", clear_on_submit=True):
            cols = st.columns([2, 1, 1])
            with cols[0]:
                new_name = st.text_input("Evaluator name",
                                           placeholder="e.g. khaled")
            with cols[1]:
                new_lang = st.selectbox(
                    "Language",
                    options=list(LANGS.keys()),
                    format_func=lambda k: LANGS[k])
            with cols[2]:
                st.write("")  # spacer
                st.write("")
                add_clicked = st.form_submit_button("➕ Add",
                                                      type="primary",
                                                      width='stretch')
            if add_clicked:
                nm = new_name.strip()
                if not nm:
                    st.error("Please enter a name.")
                elif nm.lower() in em_all and em_all[nm.lower()] == new_lang:
                    st.info(f"`{nm}` is already assigned to "
                            f"{LANGS[new_lang]}.")
                else:
                    get_storage().save_evaluator(nm, new_lang)
                    st.success(f"✅ Added **{nm}** → {LANGS[new_lang]}.  "
                                f"They can now log in.")
                    st.rerun()

    st.divider()
    df = get_storage().fetch_all_df()
    if df is None or len(df) == 0:
        st.info("No ratings yet.")
        return

    for c in ["SC", "SA", "CC", "BC", "GC", "sample_id", "record_id"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    df["model_name"] = df["model"].map(MODEL_LABEL).fillna(df["model"])
    df["lang_name"] = df["language"].map(LANGS).fillna(df["language"])

    st.subheader("🗂 All ratings")
    st.write(f"**{len(df)}** total ratings · "
              f"{df['evaluator'].nunique()} evaluators")

    # Optional filter when results grow
    fcols = st.columns([1, 1, 2])
    with fcols[0]:
        f_lang = st.multiselect("Filter by language",
                                  options=sorted(df["lang_name"].unique()),
                                  default=[])
    with fcols[1]:
        f_model = st.multiselect("Filter by model",
                                   options=sorted(df["model_name"].unique()),
                                   default=[])
    with fcols[2]:
        f_eval = st.multiselect("Filter by evaluator",
                                  options=sorted(df["evaluator"].unique()),
                                  default=[])

    df_view = df.copy()
    if f_lang:  df_view = df_view[df_view["lang_name"].isin(f_lang)]
    if f_model: df_view = df_view[df_view["model_name"].isin(f_model)]
    if f_eval:  df_view = df_view[df_view["evaluator"].isin(f_eval)]

    st.caption(f"Showing **{len(df_view)}** rows "
                f"(of {len(df)} total) — table is scrollable.")
    st.dataframe(df_view, width='stretch', height=420)

    st.divider()
    st.subheader("📈 Pass-rate per (Language × Model) — proposal Table 3")

    crits = ["SC", "SA", "CC", "BC", "GC"]
    df["overall_pct"] = df[crits].mean(axis=1) * 100

    agg = (df.groupby(["lang_name", "model_name"])
             .agg(n_ratings=("overall_pct", "count"),
                  overall_pass_pct=("overall_pct", "mean"),
                  SC_pct=("SC", lambda s: s.mean() * 100),
                  SA_pct=("SA", lambda s: s.mean() * 100),
                  CC_pct=("CC", lambda s: s.mean() * 100),
                  BC_pct=("BC", lambda s: s.mean() * 100),
                  GC_pct=("GC", lambda s: s.mean() * 100))
             .round(1).reset_index()
             .rename(columns={"lang_name": "Language", "model_name": "Model"}))
    st.dataframe(agg, width='stretch',
                 height=min(35 + 35 * len(agg), 320))

    st.subheader("Direct Gemini-vs-Qwen comparison per language")
    pivot = (df.groupby(["lang_name", "model_name"])["overall_pct"]
               .mean().unstack().round(1))
    pivot.columns.name = None
    if "Gemini 2.5 Pro" in pivot.columns and "Qwen 2.5-7B" in pivot.columns:
        pivot["Δ (Gemini − Qwen)"] = (pivot["Gemini 2.5 Pro"] -
                                       pivot["Qwen 2.5-7B"]).round(1)
    st.dataframe(pivot, width='stretch',
                 height=min(35 + 35 * len(pivot), 320))

    st.subheader("Per-evaluator progress")
    prog = (df.groupby(["evaluator", "lang_name"])
              .size().reset_index(name="ratings_done"))
    prog["target"] = 114
    prog["%_done"] = (prog["ratings_done"] / prog["target"] * 100).round(1)
    prog = prog.sort_values("%_done", ascending=False)
    st.dataframe(prog, width='stretch',
                 height=min(35 + 35 * len(prog), 360))

    st.divider()
    c1, c2 = st.columns(2)
    with c1:
        st.download_button(
            "⬇️ Full ratings CSV",
            df.to_csv(index=False).encode("utf-8"),
            f"ratings_{datetime.now():%Y%m%d_%H%M}.csv", "text/csv",
            width='stretch')
    with c2:
        st.download_button(
            "⬇️ Summary CSV (Lang × Model)",
            agg.to_csv(index=False).encode("utf-8"),
            f"summary_{datetime.now():%Y%m%d_%H%M}.csv", "text/csv",
            width='stretch')


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

def main():
    st.set_page_config(page_title="Mind Map Evaluation",
                       page_icon="🧠", layout="wide")
    if st.query_params.get("admin") == "1":
        admin_screen()
        return

    if "page" not in st.session_state:
        st.session_state.page = "login"

    if st.session_state.page == "login":
        login_screen()
    else:
        rating_screen()


if __name__ == "__main__":
    main()

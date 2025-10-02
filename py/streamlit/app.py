# app.py
import streamlit as st
import json, re
from pathlib import Path
from datetime import datetime

st.set_page_config(page_title="TF Log Explorer", layout="wide")

ISO_TS_RE = re.compile(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[+-]\d{2}:\d{2})?')
LEVEL_KEYWORDS = {
    'fatal': 'fatal', 'error': 'error', 'err': 'error', 'warn': 'warning',
    'warning': 'warning', 'info': 'info', 'debug': 'debug', 'trace': 'trace'
}
PLAN_START_PHRASES = ['cli command args', 'plan', '"plan"', 'plan is starting', '"terraform plan"']
PLAN_END_PHRASES = ['plan is complete', 'plan is not applyable', 'plan operation completed']
APPLY_START_PHRASES = ['apply', '"apply"', 'apply operation', 'starting apply operation', 'apply is starting']
APPLY_END_PHRASES = ['apply operation completed', 'apply operation finished', 'apply finished']

def guess_timestamp(obj):
    for key in ('@timestamp', 'timestamp', 'time'):
        if key in obj and obj[key]:
            return str(obj[key])
    msg = obj.get('@message') or obj.get('message') or ''
    m = ISO_TS_RE.search(msg)
    if m:
        return m.group(0)
    return None

def guess_level(obj):
    for key in ('@level', 'level', 'log.level'):
        if key in obj and obj[key]:
            return str(obj[key]).lower()
    msg = (obj.get('@message') or obj.get('message') or '').lower()
    for kw, lvl in LEVEL_KEYWORDS.items():
        if kw in msg:
            return lvl
    return 'info'

def detect_section(msg, current):
    m = (msg or '').lower()
    # starts
    if any(p in m for p in PLAN_START_PHRASES):
        return 'plan'
    if any(p in m for p in APPLY_START_PHRASES):
        return 'apply'
    # ends
    if any(p in m for p in PLAN_END_PHRASES) or any(p in m for p in APPLY_END_PHRASES):
        return None
    return current

def safe_parse_json_field(s):
    if not s:
        return None
    if isinstance(s, (dict, list)):
        return s
    try:
        return json.loads(s)
    except Exception:
        try:
            return json.loads(s.replace("'", '"'))
        except Exception:
            return s

@st.cache_data
def load_and_parse(path_or_bytes):
    """
    path_or_bytes: either bytes from uploader, or path string
    returns list of records (dicts)
    """
    records = []
    section = None
    if isinstance(path_or_bytes, (bytes, bytearray)):
        lines = path_or_bytes.decode('utf-8', errors='replace').splitlines()
    else:
        p = Path(path_or_bytes)
        with p.open('r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()
    for i, raw in enumerate(lines, start=1):
        raw = raw.strip()
        if not raw:
            continue
        try:
            obj = json.loads(raw)
        except Exception:
            obj = {'@message': raw, '_parse_error': True}
        ts = guess_timestamp(obj)
        level = guess_level(obj)
        section = detect_section(obj.get('@message') or obj.get('message') or '', section)
        rec = {
            'lineno': i,
            'timestamp': ts,
            'level': level,
            'message': (obj.get('@message') or obj.get('message') or '')[:1000],
            'raw': obj,
            'section': section,
            'tf_req_id': obj.get('tf_req_id') or obj.get('tf_http_trans_id') or None,
            'has_req_body': 'tf_http_req_body' in obj,
            'has_res_body': 'tf_http_res_body' in obj
        }
        records.append(rec)
    return records

def filter_records(records, tf_req_id=None, tf_resource_type=None, q=None, date_from=None, date_to=None):
    res = records
    if tf_req_id:
        res = [r for r in res if r['tf_req_id'] == tf_req_id]
    if tf_resource_type:
        # try to find in raw or message
        res = [r for r in res if tf_resource_type in (json.dumps(r['raw']) + ' ' + (r['message'] or ''))]
    if q:
        ql = q.lower()
        res = [r for r in res if ql in (json.dumps(r['raw']).lower() + ' ' + (r['message'] or '').lower())]
    if date_from:
        res = [r for r in res if r['timestamp'] and r['timestamp'] >= date_from]
    if date_to:
        res = [r for r in res if r['timestamp'] and r['timestamp'] <= date_to]
    return res

# --- UI ---
st.title("Terraform Log Explorer — чекпойнт 2 (MVP)")

col1, col2 = st.columns([2,1])

with col1:
    uploaded = st.file_uploader("Загрузить файл с логами (JSONL/JSON per line) или ввести путь справа", type=['json','txt'], accept_multiple_files=False)
    st.markdown("Формат: одна JSON-строка на строке.")
    if uploaded is None:
        st.info("Можно перетянуть файл или указать путь в правой колонке.")
with col2:
    path_input = st.text_input("Или введите путь к файлу на диске", "")
    if st.button("Загрузить по пути") and path_input:
        try:
            _ = Path(path_input).exists()
            st.success("Файл найден. Нажмите 'Перезагрузить данные' ниже.")
        except Exception as e:
            st.error(f"Ошибка доступа к файлу: {e}")

load_btn = st.button("Перезагрузить данные")

if uploaded is None and not path_input:
    st.stop()

# load
data_source = uploaded.getvalue() if uploaded else path_input
try:
    records = load_and_parse(data_source)
except Exception as e:
    st.exception(e)
    st.stop()

st.success(f"Загружено записей: {len(records)}")

# Quick stats / sample groups
from collections import Counter
groups = Counter([r['tf_req_id'] for r in records if r['tf_req_id']])
st.write("Найдено групп (tf_req_id) — топ 10:")
st.table(list(groups.most_common(10)))

# Filters
st.markdown("### Фильтры")
c1, c2, c3, c4 = st.columns(4)
with c1:
    tf_req_id = st.text_input("tf_req_id (точно)")
with c2:
    tf_resource_type = st.text_input("tf_resource_type (подстрока)")
with c3:
    q = st.text_input("Полнотекстовый поиск (включая JSON-боди)")
with c4:
    col_a, col_b = st.columns(2)
    date_from = col_a.text_input("Date from (ISO)", "")
    date_to = col_b.text_input("Date to (ISO)", "")

apply_filters = st.button("Применить фильтры")

if apply_filters or True:
    filtered = filter_records(records, tf_req_id=tf_req_id.strip() or None,
                              tf_resource_type=tf_resource_type.strip() or None,
                              q=q.strip() or None,
                              date_from=date_from.strip() or None,
                              date_to=date_to.strip() or None)
    st.write(f"Найдено: {len(filtered)} записей")

    # Show table of short fields
    import pandas as pd
    df = pd.DataFrame([{
        'lineno': r['lineno'],
        'timestamp': r['timestamp'],
        'level': r['level'],
        'section': r['section'],
        'tf_req_id': r['tf_req_id'],
        'message': (r['message'] or '')[:150],
        'has_req_body': r['has_req_body'],
        'has_res_body': r['has_res_body']
    } for r in filtered])
    st.dataframe(df, use_container_width=True)

    st.markdown("#### Просмотр записей (развернуть для полного JSON и тел)")
    # show first N expanders
    N = st.number_input("Показать первых N записей", min_value=1, max_value=500, value=50, step=10)
    for r in filtered[:N]:
        header = f"[{r['lineno']}] {r['timestamp']} | {r['level'].upper()} | section={r['section']} | tf_req_id={r['tf_req_id']}"
        with st.expander(header):
            st.json(r['raw'])
            if r['has_req_body']:
                if st.button(f"Показать req body (lineno {r['lineno']})", key=f"req_{r['lineno']}"):
                    body = safe_parse_json_field(r['raw'].get('tf_http_req_body'))
                    st.json(body)
            if r['has_res_body']:
                if st.button(f"Показать res body (lineno {r['lineno']})", key=f"res_{r['lineno']}"):
                    body = safe_parse_json_field(r['raw'].get('tf_http_res_body'))
                    st.json(body)

st.markdown("---")
st.markdown("### Группировка по tf_req_id")
sel_id = st.text_input("Показать все записи группы tf_req_id (вставьте ID)", "")
if sel_id:
    group = [r for r in records if r['tf_req_id'] == sel_id]
    st.write(f"Найдено {len(group)} записей в группе")
    for r in group:
        with st.expander(f"[{r['lineno']}] {r['timestamp']} | {r['level']}"):
            st.json(r['raw'])
            if r['has_req_body'] and st.button(f"req body group {r['lineno']}", key=f"greq_{r['lineno']}"):
                st.json(safe_parse_json_field(r['raw'].get('tf_http_req_body')))
            if r['has_res_body'] and st.button(f"res body group {r['lineno']}", key=f"gres_{r['lineno']}"):
                st.json(safe_parse_json_field(r['raw'].get('tf_http_res_body')))

st.markdown("---")
st.caption("MVP: поиск, группировка и интерактивное разворачивание JSON. Дальше: API (FastAPI) и визуализация хронологии (Gantt/graph).")



# --------------------------------------------3_Чекпоинт--------------------------------------------------------------------------
import plotly.express as px
import pandas as pd
from collections import defaultdict

st.markdown("## Чекпоинт 3: Хронология запросов (Gantt chart)")

timeline = []
grouped = defaultdict(list)
for r in records:
    if r['tf_req_id'] and r['timestamp']:
        grouped[r['tf_req_id']].append(r['timestamp'])

for req_id, ts_list in grouped.items():
    try:
        ts_sorted = sorted(ts_list)
        start, end = ts_sorted[0], ts_sorted[-1]
        timeline.append({
            "tf_req_id": req_id,
            "start": start,
            "end": end,
            "count": len(ts_list)
        })
    except Exception:
        pass

if timeline:
    df_tl = pd.DataFrame(timeline)
    fig = px.timeline(df_tl, x_start="start", x_end="end", y="tf_req_id",
                      color="count", hover_data=["count"])
    fig.update_yaxes(autorange="reversed")  # сверху вниз
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("Нет данных для построения диаграммы.")

if st.button("Агрегировать ошибки через плагин"):
    st.write("Найдено ошибок: 12 (пример ответа плагина)")

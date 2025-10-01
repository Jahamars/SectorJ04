#!/usr/bin/env python3
"""
parse_tflog.py
Простой парсер Terraform JSON-line логов для чекпоинта 1.

Что делает:
- читает файл с одной JSON-объектом в строке
- извлекает timestamp (если есть) или ищет во @message
- определяет уровень логирования (по полю @level или по эвристике над @message)
- отмечает секции plan/apply по подсказкам в @message/CLI args
- извлекает tf_http_req_body / tf_http_res_body, но помечает их hidden=True по умолчанию
- группирует записи по tf_req_id (если есть)
- пишет результат в JSONL файл parsed.jsonl
"""

import json
import re
from datetime import datetime
from collections import defaultdict
from pathlib import Path
import sys

# ---------- Эвристики ----------
# regex для поиска ISO-дат внутри строки (простая версия)
ISO_TS_RE = re.compile(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[+-]\d{2}:\d{2})?')
# уровням соответствуют слова
LEVEL_KEYWORDS = {
    'fatal': 'fatal', 'error': 'error', 'err': 'error', 'warn': 'warning',
    'warning': 'warning', 'info': 'info', 'debug': 'debug', 'trace': 'trace'
}
# фразы, которые помогают определить начало/конец секций plan/apply
PLAN_START_PHRASES = ['CLI command args', 'plan', '"plan"', 'Plan is starting', '"terraform plan"']
PLAN_END_PHRASES = ['Plan is complete', 'Plan is not applyable', 'plan operation completed']
APPLY_START_PHRASES = ['apply', '"apply"', 'Apply operation', 'starting Apply operation']
APPLY_END_PHRASES = ['apply operation completed', 'Apply operation completed', 'backend/local: plan calling Plan']

def guess_timestamp(obj):
    # 1) явное поле @timestamp
    for key in ('@timestamp', 'timestamp', 'time'):
        if key in obj and obj[key]:
            return obj[key]
    # 2) попытка найти в @message
    msg = obj.get('@message') or obj.get('message') or ''
    m = ISO_TS_RE.search(msg)
    if m:
        return m.group(0)
    # 3) отсутствие — вернём None (можно потом присвоить текущую)
    return None

def guess_level(obj):
    # 1) явное поле @level
    for key in ('@level', 'level', 'log.level'):
        if key in obj and obj[key]:
            return str(obj[key]).lower()
    # 2) поиск ключевых слов в @message
    msg = (obj.get('@message') or obj.get('message') or '').lower()
    for kw, lvl in LEVEL_KEYWORDS.items():
        if kw in msg:
            return lvl
    # 3) дефолт
    return 'info'

def detect_section(obj, state):
    """
    state — словарь, где храним текущую секцию (None / 'plan' / 'apply')
    Возвращает новый state (может быть тот же).
    """
    msg = (obj.get('@message') or obj.get('message') or '').lower()
    # Если CLI args показывают явно plan/apply
    if 'cli args' in msg or 'cli command args' in msg:
        if 'plan' in msg:
            return 'plan'
        if 'apply' in msg:
            return 'apply'
    # По фразам
    if any(p in msg for p in PLAN_START_PHRASES):
        return 'plan'
    if any(p in msg for p in APPLY_START_PHRASES):
        return 'apply'
    # Закрывающие
    if any(p.lower() in msg for p in PLAN_END_PHRASES):
        return None
    if any(p.lower() in msg for p in APPLY_END_PHRASES):
        return None
    return state  # без изменений

def safe_parse_json_field(s):
    """Если поле пустое — вернуть None. Если строка выглядит как JSON — распарсить."""
    if not s:
        return None
    try:
        return json.loads(s)
    except Exception:
        # иногда в логах кавычки экранированы — пробуем ещё раз, или вернём строку
        try:
            return json.loads(s.replace("'", '"'))
        except Exception:
            return s  # оставляем как строку

def process_file(path_in, path_out):
    path_in = Path(path_in)
    path_out = Path(path_out)
    section = None
    grouped = defaultdict(list)  # tf_req_id -> list of records

    with path_in.open('r', encoding='utf-8') as fin, path_out.open('w', encoding='utf-8') as fout:
        for lineno, raw in enumerate(fin, start=1):
            raw = raw.strip()
            if not raw:
                continue
            # строки в логах уже в JSON-формате (как у тебя) — парсим
            try:
                obj = json.loads(raw)
            except Exception as e:
                # если строка не валидна — пробуем вырезать начальные/конечные мусорные символы
                # и логируем простую запись
                obj = {'@message': raw, '_parse_error': str(e)}

            ts = guess_timestamp(obj)
            level = guess_level(obj)
            prev_section = section
            section = detect_section(obj, section)

            record = {
                'lineno': lineno,
                'timestamp': ts,
                'level': level,
                'message': obj.get('@message') or obj.get('message'),
                'raw': obj,
                'section': section,
                # HTTP bodies: не раскрываем автоматически, пометим hidden=True
                'tf_http_req_body': {
                    'hidden': True,
                    'value': safe_parse_json_field(obj.get('tf_http_req_body'))
                } if 'tf_http_req_body' in obj else None,
                'tf_http_res_body': {
                    'hidden': True,
                    'value': safe_parse_json_field(obj.get('tf_http_res_body'))
                } if 'tf_http_res_body' in obj else None,
                'tf_req_id': obj.get('tf_req_id') or obj.get('tf_http_trans_id') or None,
            }

            # сохраняем в выходной JSONL — короткая запись (без развёрнутых боди)
            short_out = {
                'lineno': record['lineno'],
                'timestamp': record['timestamp'],
                'level': record['level'],
                'section': record['section'],
                'message': (record['message'] or '')[:300],
                'tf_req_id': record['tf_req_id'],
                'has_req_body': bool(record['tf_http_req_body']),
                'has_res_body': bool(record['tf_http_res_body']),
            }
            fout.write(json.dumps(short_out, ensure_ascii=False) + '\n')

            # группировка для дальнейшего анализа
            if record['tf_req_id']:
                grouped[record['tf_req_id']].append(record)

    return path_out, grouped

if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("Usage: python parse_tflog.py input.jsonl parsed.jsonl")
        sys.exit(2)
    inpath = sys.argv[1]
    outpath = sys.argv[2]
    parsed_path, grouped = process_file(inpath, outpath)
    print(f"Parsed to: {parsed_path}")
    print("Sample groups found (tf_req_id -> count):")
    for k, v in list(grouped.items())[:10]:
        print(f"  {k} -> {len(v)}")
    print("To inspect a group's full records, open the parsed.jsonl and re-parse raw fields (or extend script).")

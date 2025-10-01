import json
import re
from datetime import datetime
from collections import defaultdict
from pathlib import Path
import sys

ISO_TS_RE = re.compile(
    r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:[\.,]\d{3,6})?(?:Z|[+-]\d{2}(?::\d{2})?)?'
)
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
    """
    Пытается угадать временную метку из объекта лога.
    Возвращает (timestamp, guessed_status), где guessed_status = True, если timestamp был угадан.
    """
    # 1) явное поле @timestamp
    for key in ('@timestamp', 'timestamp', 'time'):
        if key in obj and obj[key]:
            return obj[key], False # Не угадан, найден явно
    # 2) попытка найти в @message
    msg = obj.get('@message') or obj.get('message') or ''
    m = ISO_TS_RE.search(msg)
    if m:
        return m.group(0), True # Угадан из сообщения
    # 3) отсутствие — вернём None и пометим как не найденный
    return None, False

def guess_level(obj):
    """
    Пытается угадать уровень логирования из объекта лога.
    Возвращает (level, guessed_status), где guessed_status = True, если level был угадан.
    """
    # 1) явное поле @level
    for key in ('@level', 'level', 'log.level'):
        if key in obj and obj[key]:
            return str(obj[key]).lower(), False # Не угадан, найден явно
    # 2) поиск ключевых слов в @message
    msg = (obj.get('@message') or obj.get('message') or '').lower()
    for kw, lvl in LEVEL_KEYWORDS.items():
        if kw in msg:
            return lvl, True # Угадан из сообщения
    # 3) дефолт
    return 'info', False # По умолчанию, не угадан

def detect_section(obj, current_section):
    """
    Определяет текущую секцию (None / 'plan' / 'apply').
    Возвращает новый state (может быть тот же).
    """
    msg = (obj.get('@message') or obj.get('message') or '').lower()
    
    # Приоритет CLI args, так как они более явные
    if 'cli args' in msg or 'cli command args' in msg:
        if 'plan' in msg and current_section != 'plan': # Если уже в plan, не переключаем
            return 'plan'
        if 'apply' in msg and current_section != 'apply': # Если уже в apply, не переключаем
            return 'apply'
            
    # По фразам для начала секций
    if any(p.lower() in msg for p in PLAN_START_PHRASES) and current_section != 'plan':
        return 'plan'
    if any(p.lower() in msg for p in APPLY_START_PHRASES) and current_section != 'apply':
        return 'apply'
    
    # По фразам для окончания секций
    if any(p.lower() in msg for p in PLAN_END_PHRASES) and current_section == 'plan':
        return None # Завершаем секцию plan
    if any(p.lower() in msg for p in APPLY_END_PHRASES) and current_section == 'apply':
        return None # Завершаем секцию apply
        
    return current_section  # Без изменений

def safe_parse_json_field(s):
    """Если поле пустое — вернуть None. Если строка выглядит как JSON — распарсить."""
    if not s:
        return None
    if isinstance(s, dict): # Если это уже объект JSON, возвращаем как есть
        return s
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        # Иногда в логах кавычки экранированы или есть другие проблемы.
        # Пробуем более "мягкие" замены, если это строка.
        if isinstance(s, str):
            try:
                # Попытка заменить одинарные кавычки на двойные
                return json.loads(s.replace("'", '"'))
            except json.JSONDecodeError:
                pass # Пропускаем, если не удалось
        return s  # Оставляем как строку, если не удалось распарсить

def process_file(path_in, path_out):
    path_in = Path(path_in)
    path_out = Path(path_out)
    
    current_section = None
    grouped_records = defaultdict(list)  # tf_req_id -> list of records
    
    section_stats = defaultdict(int)
    level_stats = defaultdict(int)
    guessed_ts_count = 0
    guessed_level_count = 0
    parse_error_count = 0

    with path_in.open('r', encoding='utf-8') as fin, path_out.open('w', encoding='utf-8') as fout:
        for lineno, raw_line in enumerate(fin, start=1):
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            
            obj = {}
            try:
                obj = json.loads(raw_line)
            except json.JSONDecodeError as e:
                # Если строка не валидна, создаем минимальный объект с сообщением и ошибкой
                obj = {'@message': raw_line, '_parse_error': str(e)}
                parse_error_count += 1
            
            # Извлечение timestamp и уровня
            ts, ts_guessed = guess_timestamp(obj)
            level, level_guessed = guess_level(obj)
            
            if ts_guessed: guessed_ts_count += 1
            if level_guessed: guessed_level_count += 1
            
            # Определение секции
            old_section = current_section
            current_section = detect_section(obj, current_section)

            record = {
                'lineno': lineno,
                'timestamp': ts,
                '_timestamp_guessed': ts_guessed, # Добавлено для демонстрации
                'level': level,
                '_level_guessed': level_guessed,   # Добавлено для демонстрации
                'section': current_section,
                # Если секция изменилась, помечаем начало/конец
                '_section_start': (current_section is not None and old_section != current_section),
                '_section_end': (current_section is None and old_section is not None),
                'message': obj.get('@message') or obj.get('message'),
                'raw_full_json': obj, # Сохраняем полный исходный объект для детального анализа
                
                # HTTP bodies: не раскрываем автоматически, пометим hidden=True
                # Важно: здесь мы сохраняем полную структуру для последующего разворачивания
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

            # Сохраняем обработанную запись в выходной JSONL
            fout.write(json.dumps(record, ensure_ascii=False) + '\n')

            # Обновляем статистику
            if current_section:
                section_stats[current_section] += 1
            level_stats[level] += 1

            # Группировка для дальнейшего анализа (для чекпоинта 2)
            if record['tf_req_id']:
                grouped_records[record['tf_req_id']].append(record)
                
    return path_out, grouped_records, {
        'total_lines': lineno,
        'parsed_errors': parse_error_count,
        'guessed_timestamps': guessed_ts_count,
        'guessed_levels': guessed_level_count,
        'section_counts': section_stats,
        'level_counts': level_stats,
    }

if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("Usage: python parse.py input.jsonl output.jsonl")
        print("Example: python parse.py '3. apply_tflog.json' parsed_apply.jsonl")
        sys.exit(2)
    
    inpath = sys.argv[1]
    outpath = sys.argv[2]
    
    print(f"[*] Starting parsing for '{inpath}'...")
    parsed_path, grouped, stats = process_file(inpath, outpath)
    print(f"[*] Parsing complete. Results saved to: {parsed_path}")
    
    print("\n--- Parsing Statistics ---")
    print(f"Total lines processed: {stats['total_lines']}")
    print(f"Lines with parsing errors: {stats['parsed_errors']}")
    print(f"Timestamps guessed: {stats['guessed_timestamps']}")
    print(f"Levels guessed: {stats['guessed_levels']}")
    print("\nSection counts:")
    for sec, count in stats['section_counts'].items():
        print(f"  {sec.capitalize()}: {count} entries")
    print("\nLevel counts:")
    for lvl, count in stats['level_counts'].items():
        print(f"  {lvl.capitalize()}: {count} entries")
        
    print(f"\nFound {len(grouped)} unique tf_req_id groups.")
    print("Sample groups (tf_req_id -> count):")
    for k, v in list(grouped.items())[:5]: # Показываем до 5 примеров
        print(f"  {k} -> {len(v)} records")
    print("\nOutput file 'parsed.jsonl' contains full parsed records, including original JSON and section/guess metadata.")

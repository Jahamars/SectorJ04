# Terraform Log Analyzer - Техническая документация

## Описание

Terraform Log Analyzer — это одностраничное приложение (SPA) для парсинга, фильтрации и визуализации JSON-логов Terraform. Приложение обеспечивает анализ логов в реальном времени с расширенными возможностями фильтрации и интерактивной временной шкалой.

## Стек технологий

### Основные технологии

- **React 18.x** - UI-фреймворк (production build через UMD)
- **Babel Standalone** - Транспиляция JSX в браузере
- **Tailwind CSS** - Utility-first CSS фреймворк (JIT CDN)
- **Highlight.js 11.9.0** - Подсветка синтаксиса JSON

### Среда выполнения

- **Полностью клиентское приложение** - Не требует backend
- **Browser APIs**:
  - FileReader API для обработки файлов
  - Canvas API для рендеринга временной шкалы
  - Web Storage (управление состоянием через React hooks в памяти)

## Архитектура

### Структура компонентов

```
TerraformLogParser (Корневой компонент)
├── File Upload Handler (Загрузчик файлов)
├── Statistics Dashboard (Панель статистики)
├── Filter Controls (Панель фильтров)
├── Log Event List (Список событий)
│   └── JsonViewer (Просмотрщик JSON)
│       ├── Key Selector (Селектор ключей)
│       └── Raw/Filtered View (Сырой/Отфильтрованный вид)
└── Timeline (Временная шкала)
    ├── Canvas Renderer (Рендерер Canvas)
    ├── Zoom Controls (Управление масштабом)
    └── Pan Controls (Управление прокруткой)
```

### Паттерны проектирования

1. **Unidirectional Data Flow** - Однонаправленный поток данных через React hooks
2. **Controlled Components** - Все формы управляются через React state
3. **Memoization** - Оптимизация вычислений через `useMemo`
4. **Refs для Canvas** - Прямое управление DOM через `useRef`

## Основные функции

### 1. Парсинг логов

#### Функция `parseLog(content)`

**Входные данные**: Строка с JSON-логами (построчно)

**Алгоритм**:
```javascript
1. Разбивка контента на строки
2. Для каждой строки:
   a. Попытка JSON.parse()
   b. При ошибке - эвристический парсинг:
      - Извлечение timestamp через regex
      - Определение уровня (info/debug/error/warn/trace)
      - Маркировка как unparsed
   c. Определение секции (plan/apply) по ключевым словам
   d. Извлечение метаданных:
      - tf_req_id / request_id
      - tf_resource_type / resource_type
      - http_req_body / http_res_body
```

**Выходные данные**: Массив объектов с полями:
- `index` - порядковый номер
- `timestamp` - временная метка
- `level` - уровень логирования
- `message` - текст сообщения
- `section` - секция (plan/apply/null)
- `sectionStart` - флаг начала секции
- `raw` - исходный JSON объект
- `isParsed` - флаг успешного парсинга
- `tf_req_id` - ID запроса
- `tf_resource_type` - тип ресурса
- `http_req_body` - тело HTTP запроса
- `http_res_body` - тело HTTP ответа

### 2. Статистический анализ

#### Функция `calculateStats(parsedLogs)`

**Вычисляемые метрики**:
- Общее количество записей
- Распределение по уровням (levels)
- Распределение по секциям (plan/apply/other)
- Временной диапазон (start/end)
- Уникальные Request IDs (Set)
- Уникальные типы ресурсов (Set)

**Сложность**: O(n), где n - количество логов

### 3. Система фильтрации

#### Поддерживаемые фильтры:

1. **Полнотекстовый поиск** - `searchTerm`
   - Поиск по сообщению (case-insensitive)
   
2. **Фильтр по уровню** - `filterLevel`
   - Точное совпадение уровня логирования

3. **Фильтр по секции** - `filterSection`
   - plan / apply

4. **Фильтр по Request ID** - `filterReqId`
   - Точное совпадение ID

5. **Фильтр по типу ресурса** - `filterResourceType`
   - Точное совпадение типа

6. **Временной диапазон** - `filterTimestampStart` / `filterTimestampEnd`
   - Фильтрация по datetime-local

7. **Статус прочтения** - `filterUnread`
   - Фильтр непрочитанных записей

#### Механизм применения фильтров

```javascript
useEffect(() => {
  // Последовательное применение всех активных фильтров
  // Каждый фильтр сужает результирующую выборку
  let result = logs;
  
  if (searchTerm) result = result.filter(...);
  if (filterLevel) result = result.filter(...);
  // ... остальные фильтры
  
  setFilteredLogs(result);
}, [logs, searchTerm, filterLevel, ...dependencies]);
```

**Реактивность**: Автоматическое обновление при изменении любой зависимости

### 4. JsonViewer компонент

#### Режимы отображения:

1. **Collapsed** (свернутый) - показывает только тип данных
2. **Expanded** (развернутый) с двумя под-режимами:
   - **Raw mode** - полный JSON с подсветкой синтаксиса
   - **Filtered mode** - JSON с выбранными ключами

#### Функциональность:

- **Key Selection** - выбор/снятие выделения отдельных ключей
- **Select All / Deselect All** - групповые операции
- **Syntax Highlighting** - через Highlight.js

#### Состояние компонента:

```javascript
const [isOpen, setIsOpen] = useState(false);
const [showRaw, setShowRaw] = useState(false);
const [selectedKeys, setSelectedKeys] = useState(new Set());
```

### 5. Timeline компонент

#### Технические детали Canvas-рендеринга:

**Размеры Canvas**: 1200x120 пикселей

**Алгоритм отрисовки**:

```javascript
1. Фильтрация валидных timestamps
2. Определение временного диапазона [minTime, maxTime]
3. Расчет видимого окна с учетом zoom и offset:
   visibleWidth = width / zoom
   startTime = minTime + (duration * offset)
   endTime = startTime + (duration / zoom)
4. Рендеринг:
   a. Фон (slate-900)
   b. Сетка (10 вертикальных линий)
   c. События (точки по уровням):
      - error: #dc2626 (красный)
      - warn: #eab308 (желтый)
      - info: #3b82f6 (синий)
      - debug: #6b7280 (серый)
      - trace: #a855f7 (фиолетовый)
   d. Маркеры секций (вертикальные линии)
   e. Временные метки (5 равномерно распределенных)
```

#### Интерактивность:

1. **Zoom** - через колесо мыши или кнопки
   - Диапазон: 1x до 100x
   - Формула: `zoom * delta`, где delta = 0.9 или 1.1

2. **Pan** - через drag & drop
   - Offset вычисляется как относительное смещение
   - Ограничение: [0, 1 - (1/zoom)]

3. **Reset** - возврат к zoom=1, offset=0

#### Производительность:

- Использование `useMemo` для кэширования timelineData
- Перерисовка только при изменении zoom/offset/logs
- Оптимизация через пропуск событий вне видимой области

## Управление состоянием

### React Hooks использование:

1. **useState** - основное состояние:
   ```javascript
   - logs: массив всех логов
   - filteredLogs: отфильтрованный массив
   - stats: объект статистики
   - fileName: имя загруженного файла
   - filter*: состояния всех фильтров
   - readLogs: Set прочитанных индексов
   ```

2. **useEffect** - побочные эффекты:
   - Применение фильтров при изменении dependencies
   - Отрисовка Canvas при изменении timeline данных

3. **useMemo** - мемоизация:
   - Вычисление timelineData (тяжелая операция)

4. **useRef** - прямые DOM ссылки:
   - Доступ к Canvas элементу для рендеринга


## Безопасность

### Обработка пользовательского ввода:

- **JSON.parse с try-catch** - защита от невалидного JSON
- **Regex validation** - для timestamp извлечения
- **Type checking** - проверка типов перед операциями

### XSS защита:

- React автоматически экранирует контент
- Highlight.js используется для безопасной подсветки кода
- Нет dangerouslySetInnerHTML

## Ограничения

1. **Размер файла**: Ограничен памятью браузера (~100MB)
2. **Формат файла**: Только JSON (построчно)
3. **Browser support**: Современные браузеры (ES6+)
4. **No persistence**: Нет сохранения состояния между сессиями
5. **Single file**: Одновременная работа только с одним файлом


## Дальнейшее развитие

1. **Export** - экспорт отфильтрованных логов в JSON/CSV
2. **Bookmarks** - сохранение закладок в localStorage (при доступности)
4. **Themes** - светлая/темная тема
5. **Performance profiling** - анализ производительности Terraform
6. **gRPC plugins** - подключение внешних плагинов для анализа

7. **Web Workers** - парсинг в отдельном потоке
8. **Virtual scrolling** - для больших списков событий
9. **IndexedDB** - для работы с очень большими файлами


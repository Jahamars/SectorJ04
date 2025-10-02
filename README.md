# Terraform Log Analyzer - Техническая документация

## Описание

Terraform Log Analyzer — это одностраничное приложение (SPA) для парсинга, фильтрации и визуализации JSON-логов Terraform. Приложение обеспечивает анализ логов в реальном времени с расширенными возможностями фильтрации, интерактивной временной шкалой и **плагинной системой на базе gRPC** для расширения функциональности (например, фильтрация и автоматическая агрегация ошибок).

## Стек технологий

### Основные технологии

- **React 18.x** - UI-фреймворк (production build через UMD)
- **Babel Standalone** - Транспиляция JSX в браузере
- **Tailwind CSS** - Utility-first CSS фреймворк (JIT CDN)
- **Highlight.js 11.9.0** - Подсветка синтаксиса JSON

### gRPC Плагины

- **Google Protocol Buffers (protobuf.js)** - для сериализации/десериализации сообщений (в браузере как JS-объекты для симуляции)
- **gRPC-Web (клиент)** - для подключения к внешним gRPC-серверам (в данном случае симулируется)

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
├── gRPC Plugin Controls (Панель управления плагинами)
│   ├── Log Filter Plugin (Фильтрация по уровню)
│   └── Error Aggregator Plugin (Агрегация ошибок)
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
5. **State Colocation** - Состояния плагинов (`grpcStatus`, `grpcFilterResult`, `grpcAggResult`) находятся в корневом компоненте.

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

### 6. Плагинная система на gRPC

Приложение включает симулированную систему плагинов, демонстрирующую интеграцию с внешними gRPC-сервисами.

#### Поддерживаемые плагины:

1. **LogFilterService** (фильтрация по уровню)
   - **Proto**:
     ```protobuf
     syntax = "proto3";
     package logfilter;
     service LogFilterService {
       rpc FilterLogs (FilterRequest) returns (FilterResponse) {}
     }
     message FilterRequest {
       repeated string logs = 1; // Сериализованные JSON-строки логов
       string level = 2;  // e.g., "error"
     }
     message FilterResponse {
       repeated string filtered_logs = 1; // Сериализованные JSON-строки отфильтрованных логов
       string status = 2;
     }
     ```
   - **Функция**: `callGrpcFilterPlugin(logs, level)`
   - **Описание**: Принимает список логов и уровень, возвращает только логи заданного уровня. Результат *заменяет* текущие `filteredLogs`.

2. **ErrorAggregatorService** (агрегация ошибок)
   - **Proto**:
     ```protobuf
     syntax = "proto3";
     package erroragg;
     service ErrorAggregatorService {
       rpc AggregateErrors (AggregateRequest) returns (AggregateResponse) {}
     }
     message AggregateRequest {
       repeated string logs = 1; // Сериализованные JSON-строки логов
     }
     message ErrorGroup {
       string error_message_pattern = 1; // Шаблон сообщения об ошибке
       int32 count = 2; // Количество повторений
       repeated string related_logs = 3; // Примеры логов, связанных с этой группой
     }
     message AggregateResponse {
       repeated ErrorGroup groups = 1;
       string status = 2;
     }
     ```
   - **Функция**: `callGrpcAggregatePlugin(logs)`
   - **Описание**: Принимает список логов, анализирует ошибки, группирует их по шаблону и возвращает агрегированные группы с подсчетом и примерами.

#### Механизм вызова плагинов:

- **Симуляция**: В браузере вызовы плагинов *не* отправляются на реальный gRPC-сервер. Вместо этого, они симулируются с помощью `setTimeout`, имитируя задержку и логику обработки. Для реального использования, `callGrpc...` функции должны использовать gRPC-Web клиент и подключаться к реальному серверу.
- **Состояния**:
  - `grpcStatus` - отображает текущий статус выполнения плагина.
  - `grpcFilterResult` - результат работы `LogFilterService`.
  - `grpcAggResult` - результат работы `ErrorAggregatorService`.

#### Интерактивность:

- Пользователь может выбрать уровень для фильтрации и нажать кнопку для вызова `LogFilterService`.
- Пользователь может нажать кнопку для вызова `ErrorAggregatorService`.
- Результаты отображаются в соответствующих блоках UI.

## Управление состоянием

### React Hooks использование:

1. **useState** - основное состояние:
   ```javascript
   - logs: массив всех логов
   - filteredLogs: отфильтрованный массив (изменяется как фильтрами, так и плагинами)
   - stats: объект статистики
   - fileName: имя загруженного файла
   - filter*: состояния всех фильтров
   - readLogs: Set прочитанных индексов
   - grpc*: состояния плагинов
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
- Нет `dangerouslySetInnerHTML`

## Оптимизации и улучшения

- **Удаление API**: Полностью удалены все функции, связанные с внешними API (`exportFilteredLogs`, `getCurlCommand`, `apiResult`).
- **Улучшенная плагинная система**: Добавлен симулированный `ErrorAggregatorService` и улучшена логика `LogFilterService`.
- **Улучшенный UI**: Добавлены отдельные блоки для демонстрации работы каждого плагина.
- **Улучшенная структура кода**: Удалены неиспользуемые импорты и состояния, улучшена читаемость.

## Ограничения

1. **Размер файла**: Ограничен памятью браузера (~100MB)
2. **Формат файла**: Только JSON (построчно)
3. **Browser support**: Современные браузеры (ES6+)
4. **No persistence**: Нет сохранения состояния между сессиями
5. **Single file**: Одновременная работа только с одним файлом
6. **gRPC плагины**: В текущей версии симулируются и не подключены к реальному серверу.

## Дальнейшее развитие

1. **Real gRPC Client**: Подключить реальные gRPC-Web клиенты к серверам плагинов.
2. **Virtual scrolling** - для больших списков событий
3. **Themes** - светлая/темная тема
4. **Performance profiling** - анализ производительности Terraform
5. **Web Workers** - парсинг в отдельном потоке
6. **IndexedDB** - для работы с очень большими файлами
7. **Плагины**: Разработка реальных gRPC-серверов для фильтрации и агрегации.



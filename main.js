import React, { useState } from 'react';
import { Upload, CheckCircle, AlertCircle, Info, AlertTriangle, FileText } from 'lucide-react';

const TerraformLogParser = () => {
  const [logs, setLogs] = useState([]);
  const [stats, setStats] = useState(null);
  const [fileName, setFileName] = useState('');

  const parseLog = (content) => {
    const lines = content.split('\n').filter(line => line.trim());
    const parsed = [];
    let currentSection = null;
    let sectionStartIndex = -1;

    lines.forEach((line, index) => {
      try {
        const entry = JSON.parse(line);
        
        // Определяем секцию (plan/apply)
        const message = entry['@message'] || '';
        if (message.includes('CLI args:')) {
          if (message.includes('"plan"')) {
            currentSection = 'plan';
            sectionStartIndex = index;
          } else if (message.includes('"apply"')) {
            currentSection = 'apply';
            sectionStartIndex = index;
          }
        }

        parsed.push({
          index,
          timestamp: entry['@timestamp'] || 'N/A',
          level: entry['@level'] || 'unknown',
          message: entry['@message'] || '',
          section: currentSection,
          sectionStart: sectionStartIndex === index,
          raw: entry
        });
      } catch (e) {
        // Эвристический парсинг для non-JSON строк
        const timestampMatch = line.match(/(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})/);
        const levelMatch = line.match(/\b(info|debug|trace|warn|error)\b/i);
        
        parsed.push({
          index,
          timestamp: timestampMatch ? timestampMatch[1] : 'N/A',
          level: levelMatch ? levelMatch[1].toLowerCase() : 'unknown',
          message: line,
          section: currentSection,
          sectionStart: false,
          raw: { unparsed: line }
        });
      }
    });

    return parsed;
  };

  const calculateStats = (parsedLogs) => {
    const stats = {
      total: parsedLogs.length,
      levels: {},
      sections: { plan: 0, apply: 0, other: 0 },
      timeRange: { start: null, end: null }
    };

    parsedLogs.forEach(log => {
      // Подсчет уровней
      stats.levels[log.level] = (stats.levels[log.level] || 0) + 1;

      // Подсчет секций
      if (log.section === 'plan') stats.sections.plan++;
      else if (log.section === 'apply') stats.sections.apply++;
      else stats.sections.other++;

      // Временной диапазон
      if (log.timestamp !== 'N/A') {
        if (!stats.timeRange.start || log.timestamp < stats.timeRange.start) {
          stats.timeRange.start = log.timestamp;
        }
        if (!stats.timeRange.end || log.timestamp > stats.timeRange.end) {
          stats.timeRange.end = log.timestamp;
        }
      }
    });

    return stats;
  };

  const handleFileUpload = (event) => {
    const file = event.target.files[0];
    if (!file) return;

    setFileName(file.name);
    const reader = new FileReader();
    
    reader.onload = (e) => {
      const content = e.target.result;
      const parsed = parseLog(content);
      setLogs(parsed);
      setStats(calculateStats(parsed));
    };
    
    reader.readAsText(file);
  };

  const getLevelColor = (level) => {
    const colors = {
      error: 'text-red-600 bg-red-50',
      warn: 'text-yellow-600 bg-yellow-50',
      info: 'text-blue-600 bg-blue-50',
      debug: 'text-gray-600 bg-gray-50',
      trace: 'text-purple-600 bg-purple-50',
      unknown: 'text-gray-400 bg-gray-50'
    };
    return colors[level] || colors.unknown;
  };

  const getLevelIcon = (level) => {
    const icons = {
      error: <AlertCircle className="w-4 h-4" />,
      warn: <AlertTriangle className="w-4 h-4" />,
      info: <Info className="w-4 h-4" />,
      debug: <FileText className="w-4 h-4" />,
      trace: <FileText className="w-4 h-4" />
    };
    return icons[level] || icons.debug;
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 text-white p-6">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-4xl font-bold mb-2 bg-gradient-to-r from-cyan-400 to-blue-500 bg-clip-text text-transparent">
            Terraform Log Analyzer
          </h1>
          <p className="text-slate-400">Интеллектуальный парсинг и анализ логов Terraform</p>
        </div>

        {/* Upload Section */}
        <div className="bg-slate-800 rounded-lg p-6 mb-6 border border-slate-700">
          <label className="flex flex-col items-center justify-center w-full h-32 border-2 border-dashed border-slate-600 rounded-lg cursor-pointer hover:border-cyan-500 transition-all">
            <div className="flex flex-col items-center justify-center pt-5 pb-6">
              <Upload className="w-10 h-10 mb-3 text-slate-400" />
              <p className="mb-2 text-sm text-slate-400">
                <span className="font-semibold">Загрузите JSON-лог</span> или перетащите файл
              </p>
              {fileName && <p className="text-xs text-cyan-400">Загружен: {fileName}</p>}
            </div>
            <input type="file" className="hidden" accept=".json" onChange={handleFileUpload} />
          </label>
        </div>

        {/* Statistics */}
        {stats && (
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
            <div className="bg-gradient-to-br from-cyan-600 to-cyan-700 rounded-lg p-4 shadow-lg">
              <div className="text-sm text-cyan-100 mb-1">Всего записей</div>
              <div className="text-3xl font-bold">{stats.total}</div>
            </div>
            <div className="bg-gradient-to-br from-blue-600 to-blue-700 rounded-lg p-4 shadow-lg">
              <div className="text-sm text-blue-100 mb-1">План</div>
              <div className="text-3xl font-bold">{stats.sections.plan}</div>
            </div>
            <div className="bg-gradient-to-br from-purple-600 to-purple-700 rounded-lg p-4 shadow-lg">
              <div className="text-sm text-purple-100 mb-1">Применение</div>
              <div className="text-3xl font-bold">{stats.sections.apply}</div>
            </div>
            <div className="bg-gradient-to-br from-pink-600 to-pink-700 rounded-lg p-4 shadow-lg">
              <div className="text-sm text-pink-100 mb-1">Ошибки</div>
              <div className="text-3xl font-bold">{stats.levels.error || 0}</div>
            </div>
          </div>
        )}

        {/* Level Distribution */}
        {stats && (
          <div className="bg-slate-800 rounded-lg p-6 mb-6 border border-slate-700">
            <h2 className="text-xl font-semibold mb-4">Распределение по уровням</h2>
            <div className="flex flex-wrap gap-3">
              {Object.entries(stats.levels).map(([level, count]) => (
                <div key={level} className={`px-4 py-2 rounded-full ${getLevelColor(level)} flex items-center gap-2`}>
                  {getLevelIcon(level)}
                  <span className="font-semibold">{level.toUpperCase()}</span>
                  <span className="text-sm">({count})</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Logs Display */}
        {logs.length > 0 && (
          <div className="bg-slate-800 rounded-lg border border-slate-700 overflow-hidden">
            <div className="bg-slate-750 px-6 py-4 border-b border-slate-700">
              <h2 className="text-xl font-semibold">Журнал событий</h2>
            </div>
            <div className="overflow-x-auto">
              <div className="max-h-96 overflow-y-auto">
                {logs.map((log, idx) => (
                  <div key={idx} className={`px-6 py-3 border-b border-slate-700 hover:bg-slate-750 transition-colors ${log.sectionStart ? 'border-l-4 border-l-cyan-500 bg-slate-750' : ''}`}>
                    <div className="flex items-start gap-4">
                      {/* Index */}
                      <div className="text-slate-500 text-xs font-mono w-12 flex-shrink-0 pt-1">
                        #{log.index}
                      </div>
                      
                      {/* Level Badge */}
                      <div className={`px-2 py-1 rounded text-xs font-semibold flex items-center gap-1 flex-shrink-0 ${getLevelColor(log.level)}`}>
                        {getLevelIcon(log.level)}
                        {log.level.toUpperCase()}
                      </div>
                      
                      {/* Section Badge */}
                      {log.section && (
                        <div className={`px-2 py-1 rounded text-xs font-semibold flex-shrink-0 ${
                          log.section === 'plan' ? 'bg-blue-500 text-white' : 'bg-purple-500 text-white'
                        }`}>
                          {log.sectionStart && <CheckCircle className="w-3 h-3 inline mr-1" />}
                          {log.section.toUpperCase()}
                        </div>
                      )}
                      
                      {/* Timestamp */}
                      <div className="text-slate-400 text-xs font-mono flex-shrink-0 pt-1">
                        {log.timestamp !== 'N/A' ? new Date(log.timestamp).toLocaleString('ru-RU') : 'N/A'}
                      </div>
                      
                      {/* Message */}
                      <div className="flex-1 text-sm text-slate-300 font-mono break-all">
                        {log.message}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {logs.length === 0 && !stats && (
          <div className="text-center py-12 text-slate-400">
            <FileText className="w-16 h-16 mx-auto mb-4 opacity-50" />
            <p>Загрузите файл логов для начала анализа</p>
          </div>
        )}
      </div>
    </div>
  );
};

export default TerraformLogParser;

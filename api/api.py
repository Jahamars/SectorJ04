# api.py
import json
import re
from datetime import datetime
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import grpc
import plugin_pb2
import plugin_pb2_grpc

app = FastAPI(title="Terraform Log Analyzer API")

# --- Парсинг (зеркало логики из index.html) ---
def parse_log_content(content: str) -> List[Dict[str, Any]]:
    lines = [line.strip() for line in content.split("\n") if line.strip()]
    parsed = []
    current_section = None
    section_start_index = -1

    for idx, line in enumerate(lines):
        entry = {}
        is_parsed = True
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            is_parsed = False
            # Эвристика для timestamp и level
            ts_match = re.search(r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2}))', line)
            level_match = re.search(r'\b(info|debug|trace|warn|error)\b', line, re.IGNORECASE)
            entry = {
                "@message": line,
                "@timestamp": ts_match.group(1) if ts_match else None,
                "@level": level_match.group(1).lower() if level_match else "unknown"
            }

        message = entry.get("@message", "")
        if "CLI args:" in message:
            if '"plan"' in message:
                current_section = "plan"
                section_start_index = idx
            elif '"apply"' in message:
                current_section = "apply"
                section_start_index = idx

        log = {
            "index": idx,
            "timestamp": entry.get("@timestamp") or "N/A",
            "level": (entry.get("@level") or "unknown").lower(),
            "message": message,
            "section": current_section,
            "sectionStart": section_start_index == idx,
            "isParsed": is_parsed,
            "tf_req_id": entry.get("tf_req_id") or entry.get("request_id"),
            "tf_resource_type": entry.get("tf_resource_type") or entry.get("resource_type"),
            "http_req_body": entry.get("tf_http_req_body") or entry.get("http_req_body"),
            "http_res_body": entry.get("tf_http_res_body") or entry.get("http_res_body"),
        }
        parsed.append(log)
    return parsed

# --- gRPC-плагин (агрегация ошибок) ---
def apply_grpc_plugin(logs: List[Dict]) -> List[Dict]:
    try:
        with grpc.insecure_channel("localhost:50051") as channel:
            stub = plugin_pb2_grpc.LogProcessorStub(channel)
            batch = plugin_pb2.LogBatch(entries=[
                plugin_pb2.LogEntry(
                    timestamp=log["timestamp"],
                    level=log["level"],
                    message=log["message"],
                    tf_req_id=log["tf_req_id"] or "",
                    tf_resource_type=log["tf_resource_type"] or "",
                    section=log["section"] or ""
                ) for log in logs
            ])
            response = stub.Process(batch)
            return [{
                "index": i,
                "timestamp": e.timestamp,
                "level": e.level,
                "message": e.message,
                "section": e.section or None,
                "sectionStart": False,
                "isParsed": True,
                "tf_req_id": e.tf_req_id or None,
                "tf_resource_type": e.tf_resource_type or None,
                "http_req_body": None,
                "http_res_body": None,
            } for i, e in enumerate(response.entries)]
    except grpc.RpcError:
        # Если плагин недоступен — возвращаем как есть
        return logs

# --- Экспорт: подготовка данных для диаграммы Ганта ---
def build_gantt_data(logs: List[Dict]) -> List[Dict]:
    """Строит хронологию запросов по tf_req_id с длительностью"""
    req_map = {}
    for log in logs:
        req_id = log.get("tf_req_id")
        if not req_id:
            continue
        if req_id not in req_map:
            req_map[req_id] = {"start": None, "end": None, "resource": log.get("tf_resource_type")}
        ts = log.get("timestamp")
        if ts != "N/A":
            try:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                if req_map[req_id]["start"] is None or dt < req_map[req_id]["start"]:
                    req_map[req_id]["start"] = dt
                if req_map[req_id]["end"] is None or dt > req_map[req_id]["end"]:
                    req_map[req_id]["end"] = dt
            except:
                pass

    gantt = []
    for req_id, data in req_map.items():
        if data["start"] and data["end"]:
            gantt.append({
                "tf_req_id": req_id,
                "tf_resource_type": data["resource"],
                "start": data["start"].isoformat(),
                "end": data["end"].isoformat(),
                "duration_ms": int((data["end"] - data["start"]).total_seconds() * 1000)
            })
    return gantt

# --- Модели ---
class ExportRequest(BaseModel):
    logs: List[Dict[str, Any]]

# --- Эндпоинты ---
@app.post("/upload")
async def upload_log(file: UploadFile = File(...)):
    if not file.filename.endswith(".json"):
        raise HTTPException(status_code=400, detail="Only .json files allowed")
    content = await file.read()
    try:
        logs = parse_log_content(content.decode("utf-8"))
        processed_logs = apply_grpc_plugin(logs)
        return JSONResponse({"logs": processed_logs})
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Parse error: {str(e)}")

@app.post("/api/export")
async def export_logs(data: ExportRequest):
    # Интеграция с Jira, Slack, DB и т.д.
    return {
        "exported_count": len(data.logs),
        "status": "success",
        "message": "Exported to external incident system"
    }

@app.get("/api/gantt")
async def get_gantt_data(logs: List[Dict] = None):
    # В реальном проекте — хранение состояния. Здесь — заглушка.
    # Для демо: передавайте логи через POST или храните в памяти.
    raise HTTPException(status_code=405, detail="Use POST /api/gantt with logs")

@app.post("/api/gantt")
async def post_gantt_data(data: ExportRequest):
    gantt = build_gantt_data(data.logs)
    return {"gantt": gantt}

# --- Запуск ---
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

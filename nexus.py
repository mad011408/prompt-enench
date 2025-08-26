#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
NEXUS PRIME - Hyper-Advanced Terminal AI Automation System (single-file edition)

Real-world, production-grade single-file implementation that includes:
- Configuration and environment handling
- Gemini API integration for workflow synthesis and reasoning
- Workflow compiler: NL → JSON workflow (validated)
- Task plugins: shell, http, file ops (extensible)
- Priority scheduler and parallel executor with retries, timeouts
- Anomaly detection and basic self-healing
- Knowledge logging and run history in SQLite
- CLI interface: chat, plan, run

Usage examples:
  python nexus.py chat "Analyze logs and propose remediation plan"
  python nexus.py plan "Deploy Nginx container and verify health"
  python nexus.py run plan.json --max-workers 4 --dry-run
  python nexus.py run plan.json --var env=prod --var url=https://example.com

Security notes:
- API keys can be set via env NEXUS_GEMINI_API_KEY or --api-key
- Shell task defaults to non-interactive; use with care.

"""

from __future__ import annotations

import argparse
import asyncio
import base64
import dataclasses
import functools
import json
import logging
import os
import queue
import re
import shlex
import signal
import sqlite3
import string
import subprocess
import sys
import textwrap
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple, Union, Callable

try:
    import requests
except Exception:  # pragma: no cover
    requests = None  # type: ignore

# ---------------------------
# Configuration
# ---------------------------

DEFAULT_API_KEY = "AIzaSyDxzcuwVpOy_2-Ze61AVduJHUVKTJKiaYc"  # Provided by user
DEFAULT_MODEL = "gemini-2.5-pro"
DEFAULT_BASE_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{DEFAULT_MODEL}:generateContent"
DEFAULT_MAX_TOKENS = 600000
DEFAULT_TIMEOUT = 800


@dataclass
class Config:
    api_key: str = field(default_factory=lambda: os.environ.get("NEXUS_GEMINI_API_KEY", DEFAULT_API_KEY))
    model: str = DEFAULT_MODEL
    base_url: str = DEFAULT_BASE_URL
    max_tokens: int = DEFAULT_MAX_TOKENS
    timeout_seconds: int = DEFAULT_TIMEOUT
    db_path: str = field(default_factory=lambda: os.environ.get("NEXUS_DB_PATH", str(Path.home() / ".nexus_prime.sqlite")))
    log_level: str = field(default_factory=lambda: os.environ.get("NEXUS_LOG_LEVEL", "INFO"))
    max_workers: int = field(default_factory=lambda: int(os.environ.get("NEXUS_MAX_WORKERS", "8")))

    def override(self, **kwargs: Any) -> "Config":
        for k, v in kwargs.items():
            if v is not None:
                setattr(self, k, v)
        # Keep base_url aligned with model if user changed it and left base_url default
        if kwargs.get("model") and kwargs.get("base_url") is None:
            self.base_url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        return self


# ---------------------------
# Logging Setup
# ---------------------------

def setup_logging(level: str) -> None:
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


# ---------------------------
# SQLite Knowledge and Runs
# ---------------------------

class KnowledgeBase:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    started_at INTEGER NOT NULL,
                    finished_at INTEGER,
                    status TEXT NOT NULL,
                    request TEXT,
                    plan TEXT,
                    result TEXT
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER NOT NULL,
                    ts INTEGER NOT NULL,
                    level TEXT NOT NULL,
                    message TEXT NOT NULL,
                    data TEXT,
                    FOREIGN KEY(run_id) REFERENCES runs(id)
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS knowledge (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts INTEGER NOT NULL,
                    topic TEXT NOT NULL,
                    content TEXT NOT NULL
                )
                """
            )
            conn.commit()
        finally:
            conn.close()

    def start_run(self, request: str, plan: Optional[dict]) -> int:
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO runs (started_at, status, request, plan) VALUES (?, ?, ?, ?)",
                (int(time.time()), "running", request, json.dumps(plan) if plan else None),
            )
            conn.commit()
            return int(cur.lastrowid)
        finally:
            conn.close()

    def finish_run(self, run_id: int, status: str, result: Optional[dict]) -> None:
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(
                "UPDATE runs SET finished_at=?, status=?, result=? WHERE id=?",
                (int(time.time()), status, json.dumps(result) if result else None, run_id),
            )
            conn.commit()
        finally:
            conn.close()

    def log_event(self, run_id: int, level: str, message: str, data: Optional[dict] = None) -> None:
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO events (run_id, ts, level, message, data) VALUES (?, ?, ?, ?, ?)",
                (run_id, int(time.time()), level, message, json.dumps(data) if data else None),
            )
            conn.commit()
        finally:
            conn.close()

    def upsert_knowledge(self, topic: str, content: str) -> None:
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO knowledge (ts, topic, content) VALUES (?, ?, ?)",
                (int(time.time()), topic, content),
            )
            conn.commit()
        finally:
            conn.close()


# ---------------------------
# Gemini Client
# ---------------------------

class GeminiClient:
    def __init__(self, config: Config) -> None:
        if requests is None:
            raise RuntimeError("The 'requests' library is required. Install with: pip install requests")
        self.session = requests.Session()
        self.config = config
        self.logger = logging.getLogger(self.__class__.__name__)

    def generate(self, prompt: str, system_instruction: Optional[str] = None, temperature: float = 0.2) -> str:
        headers = {
            "Content-Type": "application/json",
        }
        contents: List[Dict[str, Any]] = []
        if system_instruction:
            contents.append({"role": "user", "parts": [{"text": system_instruction}]})
        contents.append({"role": "user", "parts": [{"text": prompt}]})

        payload = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": min(self.config.max_tokens, 8192),  # service-side caps
            },
        }
        url = f"{self.config.base_url}?key={self.config.api_key}"
        self.logger.debug("POST %s", url)
        resp = self.session.post(url, headers=headers, json=payload, timeout=self.config.timeout_seconds)
        if resp.status_code != 200:
            raise RuntimeError(f"Gemini API error {resp.status_code}: {resp.text[:500]}")
        data = resp.json()
        # Expected structure for generateContent
        try:
            candidates = data["candidates"]
            content = candidates[0]["content"]["parts"][0]["text"]
            return content
        except Exception:
            # Fallback to common alt shape
            text = (
                data.get("candidates", [{}])[0]
                .get("content", {})
                .get("parts", [{}])[0]
                .get("text")
            )
            if not text:
                raise RuntimeError(f"Unexpected Gemini response: {json.dumps(data)[:600]}")
            return text


# ---------------------------
# Workflow Types
# ---------------------------

TaskSpec = Dict[str, Any]
WorkflowSpec = Dict[str, Any]


class ValidationError(Exception):
    pass


class WorkflowCompiler:
    """Turns natural language requests into validated workflow JSON using Gemini.

    Workflow JSON schema (concise):
    {
      "name": "string",
      "vars": {"key": "value", ...},
      "tasks": [
        {
          "id": "unique-id",
          "type": "shell|http|file",
          "name": "human friendly",
          "priority": 0..100 (higher runs first),
          "retries": 0..5,
          "timeout": seconds,
          "depends_on": ["task-id", ...],
          "params": { ... type-specific ... }
        }
      ]
    }
    """

    SYSTEM_PROMPT = (
        "You are Nexus Prime, an expert DevOps and automation planner."
        " Produce a STRICT JSON workflow that implements the user's request in real-world steps."
        " Use only types: shell, http, file."
        " Each task must include: id, type, name, priority (0-100), retries (0-5), timeout (5-3600), depends_on (array), params (object)."
        " Prefer idempotent commands, fail-fast flags, and non-interactive options."
        " Keep secrets out of logs."
        " Output ONLY JSON with no markdown or commentary."
    )

    def __init__(self, llm: GeminiClient) -> None:
        self.llm = llm
        self.logger = logging.getLogger(self.__class__.__name__)

    def compile(self, request: str) -> WorkflowSpec:
        prompt = (
            "Convert the following request into a real, executable workflow."
            " Include verification steps and rollback if appropriate.\n\n" + request
        )
        raw = self.llm.generate(prompt, system_instruction=self.SYSTEM_PROMPT)
        self.logger.debug("Raw workflow: %s", raw)
        workflow = self._coerce_json(raw)
        self._validate(workflow)
        return workflow

    def _coerce_json(self, text: str) -> WorkflowSpec:
        # If the model returned JSON with code fences, strip them
        text = text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```[a-zA-Z]*", "", text).strip()
            if text.endswith("```"):
                text = text[:-3].strip()
        try:
            data = json.loads(text)
            return data
        except json.JSONDecodeError as e:
            raise ValidationError(f"Invalid JSON from model: {e}\n{text[:500]}")

    def _validate(self, wf: WorkflowSpec) -> None:
        if not isinstance(wf, dict):
            raise ValidationError("Workflow must be an object")
        if "tasks" not in wf or not isinstance(wf["tasks"], list) or not wf["tasks"]:
            raise ValidationError("Workflow must include non-empty 'tasks' array")
        ids = set()
        for t in wf["tasks"]:
            self._validate_task(t)
            if t["id"] in ids:
                raise ValidationError(f"Duplicate task id: {t['id']}")
            ids.add(t["id"])

    def _validate_task(self, t: TaskSpec) -> None:
        required = ["id", "type", "name", "priority", "retries", "timeout", "depends_on", "params"]
        for k in required:
            if k not in t:
                raise ValidationError(f"Task missing '{k}'")
        if t["type"] not in {"shell", "http", "file"}:
            raise ValidationError(f"Unsupported task type {t['type']}")
        if not isinstance(t["depends_on"], list):
            raise ValidationError("depends_on must be a list")
        if not (0 <= int(t["priority"]) <= 100):
            raise ValidationError("priority must be 0..100")
        if not (0 <= int(t["retries"]) <= 5):
            raise ValidationError("retries must be 0..5")
        if not (5 <= int(t["timeout"]) <= 3600):
            raise ValidationError("timeout must be 5..3600 seconds")


# ---------------------------
# Task Plugin System
# ---------------------------

class TaskContext:
    def __init__(self, variables: Dict[str, str], workdir: Path, run_id: int, kb: KnowledgeBase, logger: logging.Logger) -> None:
        self.variables = variables
        self.workdir = workdir
        self.run_id = run_id
        self.kb = kb
        self.logger = logger

    def render(self, value: Any) -> Any:
        # simple templating using {var}
        if isinstance(value, str):
            try:
                return value.format(**self.variables)
            except KeyError as e:
                raise ValidationError(f"Missing variable: {e}")
        if isinstance(value, list):
            return [self.render(v) for v in value]
        if isinstance(value, dict):
            return {k: self.render(v) for k, v in value.items()}
        return value


class TaskResult(Dict[str, Any]):
    pass


class BaseTask:
    type_name: str = "base"

    def run(self, task: TaskSpec, ctx: TaskContext) -> TaskResult:  # pragma: no cover (to be overridden)
        raise NotImplementedError


class ShellTask(BaseTask):
    type_name = "shell"

    def run(self, task: TaskSpec, ctx: TaskContext) -> TaskResult:
        params = ctx.render(task.get("params", {}))
        command = params.get("command")
        env = params.get("env", {})
        cwd = params.get("cwd", str(ctx.workdir))
        if not command:
            raise ValidationError("shell task requires 'command'")
        # Use subprocess with shlex split and capture output
        args = command if isinstance(command, list) else shlex.split(str(command))
        proc_env = os.environ.copy()
        proc_env.update({str(k): str(v) for k, v in env.items()})
        try:
            completed = subprocess.run(
                args,
                cwd=cwd,
                env=proc_env,
                capture_output=True,
                text=True,
                timeout=int(task.get("timeout", 120)),
                check=False,
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"Command timed out: {command}")
        result: TaskResult = {
            "returncode": completed.returncode,
            "stdout": completed.stdout[-10000:],
            "stderr": completed.stderr[-10000:],
        }
        if completed.returncode != 0:
            raise RuntimeError(f"Command failed ({completed.returncode}): {command}\n{completed.stderr[-1000:]}")
        return result


class HttpTask(BaseTask):
    type_name = "http"

    def run(self, task: TaskSpec, ctx: TaskContext) -> TaskResult:
        if requests is None:
            raise RuntimeError("'requests' library required for http tasks")
        params = ctx.render(task.get("params", {}))
        method = params.get("method", "GET").upper()
        url = params.get("url")
        headers = params.get("headers", {})
        body = params.get("body")
        timeout = int(task.get("timeout", 60))
        if not url:
            raise ValidationError("http task requires 'url'")
        resp = requests.request(method, url, headers=headers, json=body, timeout=timeout)
        result: TaskResult = {
            "status_code": resp.status_code,
            "headers": dict(resp.headers),
            "text": resp.text[-10000:],
        }
        if resp.status_code >= 400:
            raise RuntimeError(f"HTTP {resp.status_code} for {method} {url}: {resp.text[:1000]}")
        return result


class FileTask(BaseTask):
    type_name = "file"

    def run(self, task: TaskSpec, ctx: TaskContext) -> TaskResult:
        params = ctx.render(task.get("params", {}))
        action = params.get("action")
        path = params.get("path")
        content = params.get("content")
        if not action or not path:
            raise ValidationError("file task requires 'action' and 'path'")
        p = Path(path)
        if action == "write":
            p.parent.mkdir(parents=True, exist_ok=True)
            data = content if isinstance(content, str) else json.dumps(content, indent=2)
            p.write_text(data)
            return {"bytes": len(data)}
        elif action == "read":
            data = p.read_text()
            return {"bytes": len(data), "content": data[-10000:]}
        elif action == "append":
            p.parent.mkdir(parents=True, exist_ok=True)
            data = content if isinstance(content, str) else json.dumps(content)
            with p.open("a") as f:
                f.write(data)
            return {"appended_bytes": len(data)}
        elif action == "delete":
            if p.exists():
                p.unlink()
                return {"deleted": True}
            return {"deleted": False}
        else:
            raise ValidationError(f"Unsupported file action: {action}")


PLUGIN_REGISTRY: Dict[str, BaseTask] = {
    ShellTask.type_name: ShellTask(),
    HttpTask.type_name: HttpTask(),
    FileTask.type_name: FileTask(),
}


# ---------------------------
# Scheduler and Executor
# ---------------------------

@dataclass(order=True)
class PrioritizedItem:
    priority: int
    task_id: str = field(compare=False)


class PriorityScheduler:
    def __init__(self, workflow: WorkflowSpec) -> None:
        self.workflow = workflow
        self.tasks: Dict[str, TaskSpec] = {t["id"]: t for t in workflow["tasks"]}
        self.dependents: Dict[str, List[str]] = {tid: [] for tid in self.tasks}
        for t in workflow["tasks"]:
            for dep in t.get("depends_on", []):
                if dep not in self.tasks:
                    raise ValidationError(f"Task {t['id']} depends on unknown {dep}")
                self.dependents[dep].append(t["id"])
        self.completed: set[str] = set()
        self.failed: set[str] = set()
        self.ready_queue: "queue.PriorityQueue[PrioritizedItem]" = queue.PriorityQueue()
        self._initialize_ready()

    def _initialize_ready(self) -> None:
        for tid, t in self.tasks.items():
            if not t.get("depends_on"):
                # Negative because PriorityQueue retrieves smallest first
                self.ready_queue.put(PrioritizedItem(-int(t["priority"]), tid))

    def mark_done(self, task_id: str, ok: bool) -> None:
        if ok:
            self.completed.add(task_id)
            # If some depended on it, check if they are now ready
            for dep in self.dependents.get(task_id, []):
                dtask = self.tasks[dep]
                if all(x in self.completed for x in dtask.get("depends_on", [])):
                    self.ready_queue.put(PrioritizedItem(-int(dtask["priority"]), dep))
        else:
            self.failed.add(task_id)
            # Cancel downstream tasks that depend on failed task
            for dep in self.dependents.get(task_id, []):
                self.failed.add(dep)

    def get_next(self) -> Optional[str]:
        try:
            item = self.ready_queue.get_nowait()
            return item.task_id
        except queue.Empty:
            return None

    def is_finished(self) -> bool:
        return len(self.completed) + len(self.failed) >= len(self.tasks)


class ParallelExecutor:
    def __init__(self, config: Config, kb: KnowledgeBase, scheduler: PriorityScheduler, variables: Dict[str, str], workdir: Path, max_workers: int) -> None:
        self.config = config
        self.kb = kb
        self.scheduler = scheduler
        self.variables = variables
        self.workdir = workdir
        self.max_workers = max_workers
        self.logger = logging.getLogger(self.__class__.__name__)
        self.pool = ThreadPoolExecutor(max_workers=max_workers)
        self._lock = threading.Lock()

    def _run_single(self, run_id: int, task_id: str) -> Tuple[str, bool, TaskResult]:
        t = self.scheduler.tasks[task_id]
        plugin = PLUGIN_REGISTRY.get(t["type"])  # type: ignore
        if not plugin:
            raise ValidationError(f"No plugin for task type {t['type']}")
        ctx = TaskContext(self.variables, self.workdir, run_id, self.kb, logging.getLogger(f"Task.{task_id}"))
        retries = int(t.get("retries", 0))
        attempts = 0
        last_err: Optional[Exception] = None
        while attempts <= retries:
            attempts += 1
            try:
                self.kb.log_event(run_id, "INFO", f"Running {task_id} attempt {attempts}")
                start = time.time()
                result = plugin.run(t, ctx)
                elapsed = time.time() - start
                self.kb.log_event(run_id, "INFO", f"Task {task_id} success in {elapsed:.2f}s", {"result": self._redact(result)})
                return task_id, True, result
            except Exception as e:  # noqa: BLE001
                last_err = e
                self.kb.log_event(run_id, "ERROR", f"Task {task_id} failed attempt {attempts}: {e}")
                time.sleep(min(2 ** attempts, 10))
        assert last_err is not None
        return task_id, False, {"error": str(last_err)}

    def _redact(self, data: Dict[str, Any]) -> Dict[str, Any]:
        redacted = {}
        for k, v in data.items():
            if isinstance(v, str) and len(v) > 500:
                redacted[k] = v[:500] + "…"
            else:
                redacted[k] = v
        return redacted

    def run(self, run_id: int) -> Dict[str, Any]:
        futures: Dict[str, asyncio.Future] = {}
        results: Dict[str, Any] = {}

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        async def schedule_more() -> None:
            while not self.scheduler.is_finished():
                with self._lock:
                    while True:
                        tid = self.scheduler.get_next()
                        if tid is None:
                            break
                        if tid in futures:
                            continue
                        future = loop.run_in_executor(self.pool, self._run_single, run_id, tid)
                        futures[tid] = asyncio.ensure_future(future)
                if not futures:
                    await asyncio.sleep(0.05)
                else:
                    done, _ = await asyncio.wait(futures.values(), timeout=0.1, return_when=asyncio.FIRST_COMPLETED)
                    for d in done:
                        task_id, ok, res = d.result()
                        results[task_id] = res
                        self.scheduler.mark_done(task_id, ok)
                        del futures[task_id]
        loop.run_until_complete(schedule_more())
        loop.close()
        self.pool.shutdown(wait=True)
        return results


# ---------------------------
# Anomaly Detection and Self-Healing
# ---------------------------

class AnomalyDetector:
    def __init__(self) -> None:
        self.logger = logging.getLogger(self.__class__.__name__)

    def analyze(self, results: Dict[str, Any]) -> List[str]:
        issues: List[str] = []
        for tid, res in results.items():
            if isinstance(res, dict) and ("error" in res or res.get("returncode", 0) != 0):
                issues.append(f"Task {tid} reported failure")
        return issues


class SelfHealer:
    def __init__(self, kb: KnowledgeBase) -> None:
        self.kb = kb
        self.logger = logging.getLogger(self.__class__.__name__)

    def attempt(self, run_id: int, issues: List[str]) -> Optional[str]:
        if not issues:
            return None
        summary = "; ".join(issues)
        self.kb.log_event(run_id, "WARN", f"Anomalies detected: {summary}")
        # Simple action: record knowledge for future improvement
        self.kb.upsert_knowledge("anomalies", summary)
        # In real system, could trigger rollback tasks or alternative paths
        return "Recorded anomalies and suggested manual review"


# ---------------------------
# High-level Orchestration
# ---------------------------

class NexusPrime:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.logger = logging.getLogger(self.__class__.__name__)
        self.kb = KnowledgeBase(config.db_path)
        self.llm = GeminiClient(config)
        self.compiler = WorkflowCompiler(self.llm)
        self.detector = AnomalyDetector()
        self.healer = SelfHealer(self.kb)

    def chat(self, message: str) -> str:
        system = (
            "You are Nexus Prime, a helpful DevOps and automation expert."
            " Provide precise, actionable guidance."
        )
        return self.llm.generate(message, system_instruction=system, temperature=0.2)

    def plan(self, request: str) -> WorkflowSpec:
        return self.compiler.compile(request)

    def run(self, workflow: WorkflowSpec, variables: Dict[str, str], workdir: Optional[str] = None, max_workers: Optional[int] = None) -> Dict[str, Any]:
        run_id = self.kb.start_run(request=json.dumps(workflow), plan=workflow)
        try:
            workdir_path = Path(workdir) if workdir else Path.cwd()
            scheduler = PriorityScheduler(workflow)
            executor = ParallelExecutor(self.config, self.kb, scheduler, variables, workdir_path, max_workers or self.config.max_workers)
            results = executor.run(run_id)
            issues = self.detector.analyze(results)
            heal = self.healer.attempt(run_id, issues)
            outcome = {
                "results": results,
                "anomalies": issues,
                "healing": heal,
                "status": "success" if not issues else "partial",
            }
            self.kb.finish_run(run_id, outcome["status"], outcome)
            return outcome
        except Exception as e:  # noqa: BLE001
            self.kb.log_event(run_id, "ERROR", f"Run failed: {e}")
            self.kb.finish_run(run_id, "failed", {"error": str(e)})
            raise


# ---------------------------
# CLI
# ---------------------------

def parse_vars(var_items: List[str]) -> Dict[str, str]:
    vars_dict: Dict[str, str] = {}
    for item in var_items:
        if "=" not in item:
            raise ValueError(f"Invalid var '{item}', expected key=value")
        k, v = item.split("=", 1)
        vars_dict[k] = v
    return vars_dict


def load_workflow(path: str) -> WorkflowSpec:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_workflow(path: str, workflow: WorkflowSpec) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(workflow, f, indent=2)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="NEXUS PRIME - Terminal AI Automation")
    parser.add_argument("command", choices=["chat", "plan", "run"], help="Mode of operation")
    parser.add_argument("input", nargs="?", help="Input text (for chat/plan) or workflow file (for run)")
    parser.add_argument("--api-key", dest="api_key", default=None, help="Gemini API key (overrides env)")
    parser.add_argument("--model", dest="model", default=None, help="Model name")
    parser.add_argument("--base-url", dest="base_url", default=None, help="Override base URL")
    parser.add_argument("--log", dest="log_level", default=None, help="Log level (DEBUG, INFO, WARNING)")

    # run options
    parser.add_argument("--var", dest="vars", action="append", default=[], help="Workflow variables key=value")
    parser.add_argument("--workdir", dest="workdir", default=None, help="Working directory for tasks")
    parser.add_argument("--max-workers", dest="max_workers", type=int, default=None, help="Parallelism for executor")
    parser.add_argument("--dry-run", dest="dry_run", action="store_true", help="For run: only validate and print plan")
    parser.add_argument("--output", dest="output", default=None, help="For plan: save plan JSON to file")

    args = parser.parse_args(argv)

    config = Config()
    config.override(api_key=args.api_key, model=args.model, base_url=args.base_url, log_level=args.log_level)
    setup_logging(config.log_level)

    nexus = NexusPrime(config)

    if args.command == "chat":
        if not args.input:
            print("Provide a message to chat with.", file=sys.stderr)
            return 2
        reply = nexus.chat(args.input)
        print(reply)
        return 0

    if args.command == "plan":
        if not args.input:
            print("Provide a request to plan.", file=sys.stderr)
            return 2
        wf = nexus.plan(args.input)
        if args.output:
            save_workflow(args.output, wf)
            logging.info("Saved plan to %s", args.output)
        print(json.dumps(wf, indent=2))
        return 0

    if args.command == "run":
        if not args.input:
            print("Provide a workflow JSON file to run.", file=sys.stderr)
            return 2
        wf = load_workflow(args.input)
        # validate via compiler's validator for consistency
        nexus.compiler._validate(wf)
        if args.dry_run:
            print(json.dumps(wf, indent=2))
            return 0
        variables = parse_vars(args.vars)
        outcome = nexus.run(wf, variables, workdir=args.workdir, max_workers=args.max_workers)
        print(json.dumps(outcome, indent=2))
        return 0

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except ValidationError as ve:
        logging.error("Validation error: %s", ve)
        sys.exit(3)
    except KeyboardInterrupt:
        print("Interrupted", file=sys.stderr)
        sys.exit(130)
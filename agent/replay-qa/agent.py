"""replay-qa: a generic tool-calling A2A agent for agent-env. Every MCP tool the env exposes is offered to the model
as a function tool over OpenAI-compatible chat completions on agent-env's model endpoint (LITELLM_BASE_URL and
LITELLM_API_KEY, which deploy_agent injects from [model] in .agentenv/config.toml). Tool results go back into the
history; the loop ends when the model answers without a tool call, or on its last turn, which it gets without tools so
it has to answer. The final assistant text is the response, and the chat history is the trajectory."""

import json
import logging
import os
import re
import time
from contextlib import AsyncExitStack
from dataclasses import dataclass
from typing import Any

import httpx
import openai
from agentenv_protocol.a2a_agent import (
    MCP_CONFIG_V1,
    TRAJECTORY_V1,
    AgentConfig,
    AgentEnvAgent,
    AgentIdentity,
    TaskRequest,
    TaskResult,
    Usage,
    a2a_agent,
)
from mcp import ClientSession, McpError
from mcp.client.streamable_http import streamable_http_client

log = logging.getLogger("replay-qa")

REQUEST_TIMEOUT = 300.0
TRAJECTORY_FORMAT = "replay-qa-chat/1"
TOOL_RESULT_CHARS = int(os.environ.get("REPLAY_QA_TOOL_RESULT_CHARS", "16000"))
DEFAULT_SYSTEM = ("You answer questions about an environment by calling its tools. Call the tools you need, read "
                  "their results, then reply with the answer and nothing else.")
LAST_TURN = "This is your last turn: answer the question now in plain text."
NO_ANSWER = "You sent neither text nor a tool call. Call a tool, or answer the question in plain text."
# chat.completions.create keyword arguments; any other [model.params] key travels in extra_body.
DIRECT_PARAMS = {"max_tokens", "max_completion_tokens", "temperature", "top_p", "seed", "stop", "presence_penalty",
                 "frequency_penalty", "reasoning_effort", "parallel_tool_calls", "logprobs", "n", "user"}


class ReplayQAConfig(AgentConfig):
    model: str = "openai/gpt-oss-120b:groq"
    system_prompt: str = ""
    max_turns: int = 6
    model_params: dict[str, Any] = {"max_tokens": 1024}


@dataclass(frozen=True)
class Tool:
    name: str  # the function name the model sees
    server: str
    mcp_name: str
    description: str
    schema: dict

    def spec(self) -> dict:
        return {"type": "function", "function": {"name": self.name, "description": self.description,
                                                 "parameters": self.schema}}


class Envs:
    """One MCP session per registered server, and the tools they list under the names the model calls them by.
    A name two servers share is prefixed with the server's alias."""

    def __init__(self):
        self.sessions: dict[str, ClientSession] = {}
        self.tools: dict[str, Tool] = {}

    async def open(self, servers: dict[str, dict], stack: AsyncExitStack) -> None:
        for alias, server in servers.items():
            http = await stack.enter_async_context(httpx.AsyncClient(headers=server.get("headers") or None,
                                                                     timeout=REQUEST_TIMEOUT))
            read, write, _ = await stack.enter_async_context(streamable_http_client(server["url"], http_client=http))
            session = await stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
            self.sessions[alias] = session
        listed = [(alias, t) for alias, session in self.sessions.items() for t in (await session.list_tools()).tools]
        shared = {t.name for i, (_, t) in enumerate(listed) if any(o.name == t.name for _, o in listed[:i])}
        for alias, t in listed:
            name = _function_name(f"{alias}__{t.name}" if t.name in shared else t.name, set(self.tools))
            self.tools[name] = Tool(name, alias, t.name, t.description or "",
                                    t.inputSchema or {"type": "object", "properties": {}})

    async def call(self, name: str, arguments: dict) -> str:
        tool = self.tools.get(name)
        if tool is None:
            return json.dumps({"error": f"no tool named {name!r}; the tools are {', '.join(sorted(self.tools))}"})
        result = await self.sessions[tool.server].call_tool(tool.mcp_name, arguments)
        text = "\n".join(c.text for c in result.content if c.type == "text")
        return json.dumps({"error": text}) if result.isError else text


def _function_name(name: str, taken: set[str]) -> str:
    """``name`` as a function name a provider accepts: [A-Za-z0-9_-], at most 64 characters, unique."""
    base = re.sub(r"[^A-Za-z0-9_-]", "_", name)[:64] or "tool"
    candidate, n = base, 2
    while candidate in taken:
        suffix = f"_{n}"
        candidate, n = base[:64 - len(suffix)] + suffix, n + 1
    return candidate


def _arguments(raw: str | None) -> tuple[dict, str | None]:
    try:
        value = json.loads(raw or "{}")
    except json.JSONDecodeError as e:
        return {}, f"arguments are not valid JSON: {e.msg}"
    return (value, None) if isinstance(value, dict) else ({}, "arguments must be a JSON object")


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else f"{text[:limit]}\n...[truncated {len(text) - limit} characters]"


def _v1(base: str) -> str:
    base = base.rstrip("/")
    return base if base.endswith("/v1") else f"{base}/v1"


def _call_params(model_params: dict) -> dict:
    direct = {k: v for k, v in model_params.items() if k in DIRECT_PARAMS}
    extra = {k: v for k, v in model_params.items() if k not in DIRECT_PARAMS}
    return {**direct, "extra_body": extra} if extra else direct


def _reasoning(message: Any) -> str:
    extra = getattr(message, "model_extra", None) or {}
    value = getattr(message, "reasoning_content", None) or extra.get("reasoning_content") or extra.get("reasoning")
    return value if isinstance(value, str) else ""


class Episode:
    """One task: the chat history sent to the model and the record of it that becomes the trajectory."""

    def __init__(self, config: ReplayQAConfig, environ: dict[str, str]):
        self.config = config
        self.base, self.key = environ.get("LITELLM_BASE_URL", ""), environ.get("LITELLM_API_KEY", "")
        headers = environ.get("LITELLM_EXTRA_HEADERS")
        self.headers = json.loads(headers) if headers else None
        self.started = time.time()
        self.history: list[dict] = []
        self.record: dict[str, Any] = {"agent": "replay-qa", "model": config.model, "messages": [], "turns": [],
                                       "tools": [], "usage": {"input_tokens": 0, "output_tokens": 0},
                                       "end_reason": None, "errors": []}
        self.answer = ""
        self.tool_calls = 0
        self.failure: tuple[str, str] | None = None
        self.error: str | None = None

    def describe(self, error: BaseException) -> str:
        text = str(error).replace(self.key, "<LITELLM_API_KEY>") if self.key else str(error)
        return f"{type(error).__name__}: {text[:800]}"

    def fail(self, code: str, message: str | None = None, error: BaseException | None = None) -> None:
        if error is not None:
            self.error = self.describe(error)
            self.record["errors"].append(self.error)
        self.failure = (code, message or self.error or code)
        self.record["end_reason"] = code

    def say(self, message: dict, **details: Any) -> None:
        """Add a message to the history the model sees, and to the record with ``details`` it doesn't."""
        self.history.append(message)
        self.record["messages"].append({**message, **details})

    async def run(self, servers: dict[str, dict], prompt: str) -> None:
        if not self.base or not self.key:
            return self.fail("model_endpoint", "no model endpoint: agent-env passes LITELLM_BASE_URL and "
                                               "LITELLM_API_KEY from [model] in .agentenv/config.toml")
        envs = Envs()
        try:
            async with AsyncExitStack() as stack:
                await envs.open(servers, stack)
                self.record["tools"] = sorted(envs.tools)
                await self.turns(envs, prompt)
        except* (McpError, httpx.HTTPError) as group:
            error = group
            while isinstance(error, BaseExceptionGroup):
                error = error.exceptions[0]
            self.fail("env_error", error=error)

    async def turns(self, envs: Envs, prompt: str) -> None:
        config, record = self.config, self.record
        self.say({"role": "system", "content": config.system_prompt or DEFAULT_SYSTEM})
        self.say({"role": "user", "content": prompt})
        specs = [t.spec() for t in envs.tools.values()]
        params = _call_params(config.model_params)
        client = openai.AsyncOpenAI(base_url=_v1(self.base), api_key=self.key, max_retries=4,
                                    timeout=REQUEST_TIMEOUT, default_headers=self.headers)
        async with client:
            for turn in range(config.max_turns):
                if time.time() - self.started > config.timeout_seconds:
                    return self.fail("wall_clock", f"turn {turn + 1} would start after {config.timeout_seconds} s")
                last = turn == config.max_turns - 1
                if last and specs:
                    self.say({"role": "user", "content": LAST_TURN})
                request = {"model": config.model, "messages": self.history, **params}
                if specs and not last:
                    request["tools"] = specs
                try:
                    reply = await client.chat.completions.create(**request)
                except openai.APIError as e:
                    return self.fail("provider_error", error=e)
                choice = reply.choices[0]
                message = choice.message
                text, calls = message.content or "", list(message.tool_calls or [])
                usage = reply.usage
                if usage is not None:
                    record["usage"]["input_tokens"] += usage.prompt_tokens or 0
                    record["usage"]["output_tokens"] += usage.completion_tokens or 0
                record["turns"].append({"turn": turn + 1, "finish_reason": choice.finish_reason,
                                        "tool_calls": len(calls),
                                        "usage": usage.model_dump(exclude_none=True) if usage else None})
                assistant: dict[str, Any] = {"role": "assistant", "content": text}
                if calls:
                    assistant["tool_calls"] = [{"id": c.id, "type": "function", "function": {
                        "name": c.function.name, "arguments": c.function.arguments or "{}"}} for c in calls]
                self.say(assistant, reasoning=_reasoning(message), finish_reason=choice.finish_reason)
                log.info("turn %d: %d tool calls, finish %s", turn + 1, len(calls), choice.finish_reason)
                if not calls:
                    if text.strip():
                        self.answer = text
                        record["end_reason"] = "answered"
                        return
                    if last:
                        break
                    self.say({"role": "user", "content": NO_ANSWER})
                    continue
                for call in calls:
                    arguments, problem = _arguments(call.function.arguments)
                    if problem:
                        out = json.dumps({"error": problem})
                    else:
                        out = await envs.call(call.function.name, arguments)
                        self.tool_calls += 1
                    self.say({"role": "tool", "tool_call_id": call.id, "name": call.function.name,
                              "content": _clip(out, TOOL_RESULT_CHARS)})
            record["end_reason"] = "no_answer"

    def result(self) -> TaskResult:
        record = self.record
        record["seconds"] = round(time.time() - self.started, 1)
        usage = record["usage"]
        summary = {"agent": "replay-qa", "model": self.config.model, "end_reason": record["end_reason"],
                   "turns": len(record["turns"]), "tool_calls": self.tool_calls,
                   "input_tokens": usage["input_tokens"], "output_tokens": usage["output_tokens"],
                   "seconds": record["seconds"], "error": self.error}
        builder = TaskResult.builder()
        builder = builder.failed(*self.failure, error_type="infra_error") if self.failure else builder.succeeded()
        return (builder.add_text(self.answer or (self.failure[1] if self.failure else ""))
                .add_structured_output(summary)
                .usage(Usage(tool_call_count=self.tool_calls, input_tokens=usage["input_tokens"],
                             output_tokens=usage["output_tokens"],
                             total_tokens=usage["input_tokens"] + usage["output_tokens"]))
                .native_trajectory(format=TRAJECTORY_FORMAT, payload=record).build())


@a2a_agent(
    identity=AgentIdentity(
        name="replay-qa",
        description="A generic tool-calling loop: the env's MCP tools as function tools over OpenAI-compatible "
                    "chat completions on agent-env's model endpoint, answering in text.",
        version="0.1.0",
    ),
    config=ReplayQAConfig,
    extensions=(MCP_CONFIG_V1, TRAJECTORY_V1),
)
class ReplayQA(AgentEnvAgent):
    async def run(self, request: TaskRequest[ReplayQAConfig]) -> TaskResult:
        prompt = "\n\n".join(part.text for part in request.parts if part.kind == "text")
        episode = Episode(request.config, dict(os.environ))
        await episode.run(dict(request.mcp_servers), prompt)
        return episode.result()


if __name__ == "__main__":
    logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    log.setLevel(logging.INFO)
    ReplayQA().serve()

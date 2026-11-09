#!/usr/bin/env python3
"""fake-gateway.py — a gateway that answers as a model would, so a live crew can run with no model.

WHAT IT GUARDS. With no gateway the engine takes its placeholder path, which checks nothing, so no
suite or probe sees a model's answer reach a crew. This answers `POST /v1/chat/completions` on a
real socket, and what it says depends on what the task asked for, by a word in the description:

  say-prose     prose, every time: a task with a shape never meets it
  say-fenced    the shape inside a code fence
  say-late      prose the first time, the shape once it is re-asked
  use-tool NAME WORD  (when the request offers tools) a call to NAME with WORD as its `target_url` and
                      its `message`, then `{"verdict":"pass"}` once a tool's result has come back
  anything else `{"verdict":"pass"}`

`GET /v1/models` lists one model and `/v1/models/catalog` is a 404, as an older gateway answers: a
crew whose agents name no model reads the list, and agnosai picks from it.

Usage: scripts/fake-gateway.py PORT
"""
import http.server
import json
import re
import sys

SHAPE = '{"verdict":"pass"}'


class Gateway(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def answer(self, prompt):
        if "say-prose" in prompt:
            return "All of it passed."
        if "say-fenced" in prompt:
            return "Here it is:\n```json\n" + SHAPE + "\n```\n"
        if "say-late" in prompt:
            return SHAPE if "failed validation" in prompt else "Not yet."
        return SHAPE

    def tool_call(self, body, prompt):
        """The call this request should answer with, or None."""
        if not body.get("tools") or any(m.get("role") == "tool" for m in body.get("messages", [])):
            return None
        asked = re.search(r"use-tool (\S+) (\S+)", prompt)
        if not asked:
            return None
        word = asked.group(2)
        arguments = json.dumps({"target_url": word, "message": word, "concurrent_users": 1, "duration_seconds": 1})
        return {"id": "call_1", "type": "function", "function": {"name": asked.group(1), "arguments": arguments}}

    def do_GET(self):
        if self.path != "/v1/models":
            self.send_error(404)
            return
        self.send(json.dumps({"object": "list", "data": [{"id": "fake-model", "owned_by": "fake"}]}).encode())

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        prompt = " ".join(str(m.get("content", "")) for m in body.get("messages", []))
        call = self.tool_call(body, prompt)
        message = {"role": "assistant", "content": "" if call else self.answer(prompt)}
        if call:
            message["tool_calls"] = [call]
        self.send(json.dumps({
            "model": body.get("model", "fake"),
            "choices": [{"message": message}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15, "provider": "fake"},
        }).encode())

    def send(self, reply):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(reply)))
        self.end_headers()
        self.wfile.write(reply)


http.server.ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1])), Gateway).serve_forever()

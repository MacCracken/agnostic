#!/usr/bin/env python3
"""fake-gateway.py — a gateway that answers as a model would, so a live crew can run with no model.

WHAT IT GUARDS. With no gateway the engine takes its placeholder path, which checks nothing, so no
suite or probe sees a model's answer reach a crew. This answers `POST /v1/chat/completions` on a
real socket, and what it says depends on what the task asked for, by a word in the description:

  say-prose     prose, every time: a task with a shape never meets it
  say-fenced    the shape inside a code fence
  say-late      prose the first time, the shape once it is re-asked
  anything else `{"verdict":"pass"}`

Usage: scripts/fake-gateway.py PORT
"""
import http.server
import json
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

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        prompt = " ".join(str(m.get("content", "")) for m in body.get("messages", []))
        reply = json.dumps({
            "model": body.get("model", "fake"),
            "choices": [{"message": {"role": "assistant", "content": self.answer(prompt)}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15, "provider": "fake"},
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(reply)))
        self.end_headers()
        self.wfile.write(reply)


http.server.ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1])), Gateway).serve_forever()

"""The builder's trace: one plain-text line per event, written to traces/<slot>.log and mirrored to stdout.

Required by the rules: start and end time, every model call (model and a one-line purpose), what was created on Freya
(workflow id, agent id, node and tool counts), every self-test with its result. Secrets are masked before writing.
"""
import os, re, sys, time


class Trace:
    def __init__(self, path, mirror=True):
        self.path = path; self.mirror = mirror
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self.f = open(path, "a", encoding="utf-8")
        self.t0 = time.time(); self.model_calls = 0; self.cost_usd = 0.0
        self.secrets = [v for v in (os.environ.get("FREYA_API_KEY"), os.environ.get("FREYA_BANK_TEAM_KEY"), os.environ.get("ANTHROPIC_API_KEY")) if v and len(v) >= 8]

    def _mask(self, s):
        s = str(s)
        for v in self.secrets: s = s.replace(v, "<redacted>")
        s = re.sub(r"fak_[A-Za-z0-9_-]{6,}", "fak_<redacted>", s)
        s = re.sub(r"sk-ant-[A-Za-z0-9_-]{6,}", "sk-ant-<redacted>", s)
        return s

    def line(self, kind, text=""):
        text = " ".join(self._mask(text).split())
        row = f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} {kind} {text}".rstrip()
        self.f.write(row + "\n"); self.f.flush()
        if self.mirror: print(row, flush=True)
        return row

    def start(self, brief, tools, slot, budget_s, model):
        self.line("START", f"brief={brief} tools={tools} slot={slot} budget_s={budget_s} builder_model={model} cwd={os.getcwd()}")
    def model_call(self, model, purpose, seconds=None, tokens_in=None, tokens_out=None, cost_usd=None):
        self.model_calls += 1
        if cost_usd: self.cost_usd += float(cost_usd)
        bits = [purpose]
        if seconds is not None: bits.append(f"{seconds:.0f}s")
        if tokens_in is not None: bits.append(f"in={tokens_in}")
        if tokens_out is not None: bits.append(f"out={tokens_out}")
        if cost_usd is not None: bits.append(f"cost_usd={float(cost_usd):.3f}")
        self.line("MODEL", f"{model} | " + " ".join(str(b) for b in bits))
    def spec(self, text): self.line("SPEC", text)
    def compile(self, nodes, tools, lint_errors, lint_warnings=0):
        self.line("COMPILE", f"nodes={nodes} tools={tools} lint={'ok' if not lint_errors else str(len(lint_errors)) + ' errors'} warnings={lint_warnings}")
    def freya(self, text): self.line("FREYA", text)
    def created(self, slot, workflow_id, agent_id, version, nodes, tools):
        self.line("FREYA", f"saved slot={slot} workflow_id={workflow_id} agent_id={agent_id} version={version} nodes={nodes} tools={tools}")
    def export(self, path, nodes, tools): self.line("EXPORT", f"{path} nodes={nodes} tools={tools}")
    def test(self, name, result, detail=""): self.line("TEST", f"{name} {result} {detail}")
    def warn(self, text): self.line("WARN", text)
    def info(self, text): self.line("INFO", text)
    def error(self, text): self.line("ERROR", text)
    def end(self, status, extra=""):
        self.line("END", f"status={status} elapsed_s={time.time() - self.t0:.0f} model_calls={self.model_calls} cost_usd={self.cost_usd:.3f} {extra}")
        self.f.close()
    def elapsed(self): return time.time() - self.t0


class Budget:
    def __init__(self, seconds, trace=None):
        self.t0 = time.time(); self.seconds = float(seconds); self.trace = trace
    def remaining(self): return self.seconds - (time.time() - self.t0)
    def allows(self, estimate_s, what=""):
        ok = self.remaining() >= estimate_s
        if not ok and self.trace: self.trace.warn(f"budget: skipping {what} (needs ~{estimate_s:.0f}s, {self.remaining():.0f}s left)")
        return ok

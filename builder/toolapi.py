"""Tool definitions generated from the bank's OpenAPI file. Nothing about a tool is hard-coded.

The seven tool names stay the same across briefs; their fields and allowed values can change, so every body field,
enum and required list comes from the file that was passed to the builder.
"""
import json


class ToolAPI:
    def __init__(self, doc, path=""):
        self.doc = doc; self.path = path
        servers = doc.get("servers") or [{}]
        self.base_url = (servers[0].get("url") or "").rstrip("/")
        self.tools = {}
        for p, methods in (doc.get("paths") or {}).items():
            op = methods.get("post") or next(iter(methods.values()), {})
            schema = (((op.get("requestBody") or {}).get("content") or {}).get("application/json") or {}).get("schema") or {}
            props = schema.get("properties") or {}
            fields = {}
            for fname, fs in props.items():
                fields[fname] = {"type": fs.get("type", "string"), "enum": fs.get("enum"), "description": fs.get("description", ""),
                                 "format": fs.get("format"), "required": fname in (schema.get("required") or [])}
            resp = ((((op.get("responses") or {}).get("200") or {}).get("content") or {}).get("application/json") or {}).get("schema") or {}
            name = p.strip("/").split("/")[-1]
            self.tools[name] = {"name": name, "path": p, "url": self.base_url + p, "summary": op.get("summary", ""),
                                "fields": fields, "required": list(schema.get("required") or []),
                                "response_fields": list((resp.get("properties") or {}).keys()), "response_schema": resp}

    def names(self): return list(self.tools)
    def tool(self, name):
        if name not in self.tools: raise KeyError(f"tool '{name}' is not in the tool API file ({self.path})")
        return self.tools[name]
    def has(self, name): return name in self.tools
    def enum(self, tool, field):
        t = self.tools.get(tool) or {}
        return ((t.get("fields") or {}).get(field) or {}).get("enum")
    def enums(self):
        out = {}
        for tn, t in self.tools.items():
            for fn, f in t["fields"].items():
                if f.get("enum"): out[f"{tn}.{fn}"] = list(f["enum"])
        return out
    def field_names(self, tool): return list(self.tool(tool)["fields"])
    def find_field(self, tool, *candidates, fmt=None, typ=None):
        """First field whose name is in candidates, else first field with the given format/type."""
        fields = self.tool(tool)["fields"]
        for c in candidates:
            if c in fields: return c
        for fn, f in fields.items():
            if fmt and f.get("format") == fmt: return fn
            if typ and f.get("type") == typ and fn != "customer_id": return fn
        return None


def load_openapi(path):
    with open(path, encoding="utf-8") as f: return ToolAPI(json.load(f), path)


def api_tool(api, name, baked, description, *, max_retries=0, timeout_ms=12000, pre_hook="", post_hook="",
             response_mapping=None, model_fields=None, connect_retries=1):
    """One api_call tool in the verified shape (docs/tools-and-code.md).

    baked:        field -> value that the workflow supplies (a literal or '{{var}}'); the model never sees these.
    model_fields: fields the dialogue model fills; they get default '{{<field>}}' so the model is shown type/enum/description.
    Other fields: dropped when optional; when required, left to the model with a note.
    """
    t = api.tool(name); model_fields = list(model_fields or [])
    props = {}; required = []
    for fname, f in t["fields"].items():
        leaf = {"type": f["type"] or "string"}
        if f.get("description"): leaf["description"] = f["description"]
        if f.get("enum"): leaf["enum"] = list(f["enum"])
        if fname in baked:
            leaf["default"] = baked[fname]
        elif fname in model_fields or f["required"]:
            leaf["default"] = "{{" + fname + "}}"
            if f.get("enum"): leaf["description"] = (leaf.get("description", "") + " One of: " + ", ".join(map(str, f["enum"]))).strip()
        else:
            continue
        props[fname] = leaf
        if f["required"] or fname in model_fields: required.append(fname)
    tool = {
        "type": "function",
        "config": {"timeoutMs": timeout_ms, "maxRetries": max_retries},
        "function": {
            "name": name, "handler": "__function__:api_call", "description": description,
            "parameters": {"type": "object", "properties": {
                "url": {"type": "string", "default": t["url"]},
                "method": {"type": "string", "default": "POST"},
                "connect_retries": {"type": "number", "default": connect_retries},
                "headers": {"type": "object", "properties": {"Content-Type": {"type": "string", "default": "application/json"}}},
                "body": {"type": "object", "required": required, "properties": props},
            }},
        },
    }
    if response_mapping: tool["response_mapping"] = list(response_mapping)
    if pre_hook: tool["pre_process_code"] = pre_hook
    if post_hook: tool["post_process_code"] = post_hook
    return tool


if __name__ == "__main__":
    import sys
    api = load_openapi(sys.argv[1] if len(sys.argv) > 1 else "tools/openapi.json")
    print("base:", api.base_url); print("tools:", api.names()); print("enums:", json.dumps(api.enums(), indent=1))

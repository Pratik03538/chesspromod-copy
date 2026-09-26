from __future__ import annotations

import ast
import json
from pathlib import Path

_NAMESPACE=None
BASE=Path(__file__).resolve().parent.parent
CONFIG=BASE/"config.py"
MODULES=BASE/"modules"
MANIFEST=MODULES/"manifest.json"
GUARD=MODULES/"main_guard.py"


def _compile_node(node, filename, source_text, namespace):
    flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT if False else 0
    tree=ast.parse(source_text, filename=filename, mode="exec")
    code=compile(tree, filename, "exec")
    exec(code, namespace, namespace)


def bootstrap_namespace(caller_name="main", caller_file=None):
    global _NAMESPACE
    if _NAMESPACE is not None:
        return _NAMESPACE

    manifest=json.loads(MANIFEST.read_text(encoding="utf-8"))
    ns={
        "__name__": caller_name,
        "__file__": str(caller_file or (BASE/"main.py")),
        "__package__": None,
        "__cached__": None,
    }

    config_text=CONFIG.read_text(encoding="utf-8")
    config_tree=ast.parse(config_text, filename=str(CONFIG))
    config_nodes=config_tree.body

    # Map every generated module's function definitions by local order.
    module_cache={}
    def get_functions(filename):
        if filename not in module_cache:
            path=MODULES/filename
            mt=path.read_text(encoding="utf-8")
            tr=ast.parse(mt, filename=str(path))
            module_cache[filename]=[n for n in tr.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))]
        return module_cache[filename]

    for item in sorted(manifest["nodes"], key=lambda x:x["index"]):
        kind=item["kind"]
        if kind=="config":
            node=config_nodes[item["position"]]
            wrapper=ast.Module(body=[node],type_ignores=[])
            ast.fix_missing_locations(wrapper)
            exec(compile(wrapper,str(CONFIG),"exec"),ns,ns)
        elif kind=="function":
            fn=item["module"]
            node=get_functions(fn)[item["position"]]
            wrapper=ast.Module(body=[node],type_ignores=[])
            ast.fix_missing_locations(wrapper)
            exec(compile(wrapper,str(MODULES/fn),"exec"),ns,ns)
        elif kind=="main_guard":
            guard_text=GUARD.read_text(encoding="utf-8")
            guard_tree=ast.parse(guard_text, filename=str(GUARD))
            # Preserve original guard semantics exactly.
            exec(compile(guard_tree,str(GUARD),"exec"),ns,ns)
        else:
            raise RuntimeError(f"Unknown manifest node kind: {kind}")

    _NAMESPACE=ns
    return ns


def get_namespace(caller_name="main", caller_file=None):
    return bootstrap_namespace(caller_name, caller_file)

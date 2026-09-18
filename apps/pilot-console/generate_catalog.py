"""Extract implemented route declarations; descriptions are module package metadata."""
import ast
import json
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
items = []
for directory in sorted((ROOT / 'modules').iterdir()):
    if not (directory / 'pyproject.toml').exists():
        continue
    meta = tomllib.loads((directory / 'pyproject.toml').read_text())['project']
    routes = []
    for path in sorted((directory / 'src').rglob('routes*.py')):
        tree = ast.parse(path.read_text())
        prefixes = {}
        for node in tree.body:
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
                for kw in node.value.keywords:
                    if kw.arg == 'prefix' and isinstance(kw.value, ast.Constant):
                        prefixes[getattr(node.targets[0], 'id', '')] = kw.value.value
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for dec in node.decorator_list:
                    if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute) and dec.func.attr in ['get','post','put','patch','delete'] and dec.args and isinstance(dec.args[0], ast.Constant):
                        routes.append({'method':dec.func.attr.upper(),'path':prefixes.get(getattr(dec.func.value,'id',''),'')+dec.args[0].value,'handler':node.name,'source':str(path.relative_to(ROOT))})
    items.append({'id': directory.name, 'name': directory.name.replace('-', ' ').title().replace('Llm','LLM').replace('Db','DB').replace('Rag','RAG').replace('Mcp','MCP').replace('A2a','A2A'), 'description':meta.get('description',''), 'routes':routes})
(Path(__file__).parent / 'static/catalog.json').write_text(json.dumps(items, indent=2)+'\n')
print(f'{len(items)} modules, {sum(len(x["routes"]) for x in items)} route declarations')

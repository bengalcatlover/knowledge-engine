import ast
from pathlib import Path

root = Path(__file__).resolve().parents[1]
files = {'evidence_miner.py': 2048, 'node_factory.py': 1024,
         'relation_engine.py': 1024, 'knowledge_amplifier.py': 2048}
backup = root / 'work/pre_cheap_worker'
backup.mkdir(exist_ok=True)
for name, limit in files.items():
    p = root / name
    if not (backup / name).exists():
        (backup / name).write_bytes(p.read_bytes())
    text = p.read_text(encoding='utf-8')
    tree = ast.parse(text)
    func = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == '_call_anthropic')
    lines = text.splitlines(keepends=True)
    lines[func.lineno-1:func.end_lineno] = [
        'def _call_anthropic(prompt: str, model: str = HAIKU_MODEL) -> str:\n'
        '    # Compatibility name; all normal work uses the pinned low-cost worker.\n'
        '    from cheap_llm import complete\n'
        f'    return complete(prompt, task="{p.stem}", max_tokens={limit})\n']
    p.write_text(''.join(lines), encoding='utf-8')
    print('Updated', name)

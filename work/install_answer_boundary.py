"""Replace old answer entry points without reading secrets into logs."""
import ast
from pathlib import Path
root=Path(__file__).resolve().parents[1]
p=root/'ask_knowledge.py'
backup=root/'work/ask_knowledge_before_boundary.py'
if not backup.exists(): backup.write_bytes(p.read_bytes())
text=p.read_text(encoding='utf-8'); lines=text.splitlines(keepends=True)
replacements={
'build_context': '''def build_context(query: str, limit: int = 6, use_vectors: bool = False) -> dict:
    from answer_service import context
    return context(query)
''',
'format_prompt': '''def format_prompt(ctx: dict) -> str:
    return json.dumps(ctx, ensure_ascii=False)
''',
'call_haiku': '''def call_haiku(prompt: str) -> str:
    # Compatibility helper; no direct high-cost provider path.
    from cheap_llm import complete
    return complete(prompt, 'answer_evidence_selection', 512)
''',
'ask': '''def ask(query: str, use_vectors: bool = False, verbose: bool = False) -> str:
    from answer_service import answer
    result = answer(query)
    if verbose:
        print(json.dumps({'status': result['status'], 'claim_ids': result['claim_ids']}, ensure_ascii=False))
    return result['answer']
'''}
for n in sorted([n for n in ast.parse(text).body if isinstance(n,ast.FunctionDef) and n.name in replacements],key=lambda n:n.lineno,reverse=True):
    lines[n.lineno-1:n.end_lineno]=[replacements[n.name]]
p.write_text(''.join(lines),encoding='utf-8')
print('Answer entry points now enforce claim validation')

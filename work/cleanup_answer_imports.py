import ast
from pathlib import Path
p=Path('ask_knowledge.py'); text=p.read_text(encoding='utf-8'); lines=text.splitlines(keepends=True)
remove=[]
for n in ast.parse(text).body:
    if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id in ('ANTHROPIC_KEY','MODEL') for t in n.targets):
        remove.append(n)
    elif isinstance(n,ast.Import) and any(a.name in ('os','urllib.request') for a in n.names):
        remove.append(n)
    elif isinstance(n,ast.ImportFrom) and n.module=='search_engine':
        remove.append(n)
for n in sorted(remove,key=lambda n:n.lineno,reverse=True): lines[n.lineno-1:n.end_lineno]=[]
p.write_text(''.join(lines),encoding='utf-8')
print('Removed obsolete answer-provider imports and configuration')

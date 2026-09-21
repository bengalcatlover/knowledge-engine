import json
import sqlite3
from pathlib import Path

db = sqlite3.connect('work/mvp.sqlite3')
before = sqlite3.connect('work/mvp_before_resume_20260914_185309.sqlite3')
old_ids = {r[0] for r in before.execute('SELECT claim_id FROM claim')}
new_claims = [dict(zip(('id', 'statement', 'status'), row)) for row in
              db.execute('SELECT claim_id, statement, epistemic_status FROM claim') if row[0] not in old_ids]
cost_db = sqlite3.connect('work/cheap_llm.sqlite3')
usage = cost_db.execute('SELECT count(*), sum(input_tokens), sum(output_tokens), sum(estimated_usd) FROM usage').fetchone()
report = {'new_claims': new_claims, 'api_calls': usage[0], 'input_tokens': usage[1],
          'output_tokens': usage[2], 'estimated_total_usd': usage[3],
          'integrity_check': db.execute('PRAGMA integrity_check').fetchone()[0]}
Path('work/cheap_worker_resume_result.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(report, ensure_ascii=False, indent=2))

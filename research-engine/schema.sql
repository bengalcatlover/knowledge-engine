PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS artifacts (
  id TEXT PRIMARY KEY,
  url TEXT,
  title TEXT NOT NULL,
  source_class TEXT NOT NULL,
  publisher TEXT,
  published_at TEXT,
  retrieved_at TEXT NOT NULL,
  original_hash TEXT NOT NULL,
  extracted_hash TEXT,
  license_note TEXT,
  retention_status TEXT NOT NULL DEFAULT 'active',
  CHECK (source_class IN ('lecture', 'primary_paper', 'standard', 'government', 'textbook', 'official_docs', 'other')),
  CHECK (retention_status IN ('active', 'removed'))
);

CREATE TABLE IF NOT EXISTS concepts (
  id TEXT PRIMARY KEY,
  label TEXT NOT NULL,
  domain TEXT NOT NULL,
  scope_note TEXT,
  lifecycle TEXT NOT NULL DEFAULT 'candidate',
  created_at TEXT NOT NULL,
  created_by TEXT NOT NULL,
  CHECK (lifecycle IN ('candidate', 'reviewed', 'adopted', 'retired'))
);

CREATE TABLE IF NOT EXISTS concept_origins (
  concept_id TEXT NOT NULL REFERENCES concepts(id),
  artifact_id TEXT NOT NULL REFERENCES artifacts(id),
  origin_type TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (concept_id, artifact_id),
  CHECK (origin_type IN ('discovery_hint', 'definition_source', 'application_source'))
);

CREATE TABLE IF NOT EXISTS claims (
  id TEXT PRIMARY KEY,
  concept_id TEXT NOT NULL REFERENCES concepts(id),
  statement TEXT NOT NULL,
  claim_type TEXT NOT NULL,
  conditions TEXT,
  limitations TEXT,
  work_state TEXT NOT NULL DEFAULT 'draft',
  evidence_state TEXT NOT NULL DEFAULT 'unassessed',
  freshness_state TEXT NOT NULL DEFAULT 'current',
  supersedes_claim_id TEXT REFERENCES claims(id),
  created_at TEXT NOT NULL,
  created_by TEXT NOT NULL,
  CHECK (work_state IN ('draft', 'format_checked', 'human_reviewed')),
  CHECK (evidence_state IN ('unassessed', 'supported_with_conditions', 'conflicting', 'insufficient')),
  CHECK (freshness_state IN ('current', 'recheck_needed', 'superseded'))
);

CREATE TABLE IF NOT EXISTS evidence_links (
  id TEXT PRIMARY KEY,
  claim_id TEXT NOT NULL REFERENCES claims(id),
  artifact_id TEXT NOT NULL REFERENCES artifacts(id),
  stance TEXT NOT NULL,
  locator TEXT NOT NULL,
  excerpt TEXT NOT NULL,
  context_note TEXT,
  assessment_reason TEXT,
  created_at TEXT NOT NULL,
  CHECK (stance IN ('supports_candidate', 'refutes_candidate', 'qualifies_candidate'))
);

CREATE TABLE IF NOT EXISTS relations (
  id TEXT PRIMARY KEY,
  from_concept_id TEXT NOT NULL REFERENCES concepts(id),
  to_concept_id TEXT NOT NULL REFERENCES concepts(id),
  relation_type TEXT NOT NULL,
  basis_claim_id TEXT REFERENCES claims(id),
  created_at TEXT NOT NULL,
  created_by TEXT NOT NULL,
  CHECK (relation_type IN ('scientific_relation', 'citation_relation', 'analogy_hint', 'user_decision'))
);

CREATE TABLE IF NOT EXISTS research_questions (
  id TEXT PRIMARY KEY,
  question TEXT NOT NULL,
  origin TEXT NOT NULL,
  priority_reason TEXT,
  status TEXT NOT NULL DEFAULT 'proposed',
  budget_reserved_usd REAL NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  CHECK (origin IN ('human', 'knowledge_gap', 'contradiction', 'staleness')),
  CHECK (status IN ('proposed', 'planned', 'running', 'reported', 'blocked', 'closed'))
);

CREATE TABLE IF NOT EXISTS research_runs (
  id TEXT PRIMARY KEY,
  question_id TEXT NOT NULL REFERENCES research_questions(id),
  plan TEXT NOT NULL,
  model_policy_version INTEGER NOT NULL,
  dry_run INTEGER NOT NULL,
  outcome TEXT NOT NULL DEFAULT 'planned',
  cost_usd REAL NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  completed_at TEXT,
  CHECK (outcome IN ('planned', 'partial', 'answered', 'dead_end', 'budget_stopped', 'failed'))
);

CREATE TABLE IF NOT EXISTS proposals (
  id TEXT PRIMARY KEY,
  proposal_type TEXT NOT NULL,
  body_json TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'unreviewed',
  created_at TEXT NOT NULL,
  created_by TEXT NOT NULL,
  CHECK (proposal_type IN ('pilot_plan', 'research_plan', 'hypothesis')),
  CHECK (status IN ('unreviewed', 'reviewed', 'rejected'))
);

CREATE TABLE IF NOT EXISTS reviews (
  id TEXT PRIMARY KEY,
  subject_type TEXT NOT NULL,
  subject_id TEXT NOT NULL,
  decision TEXT NOT NULL,
  rationale TEXT NOT NULL,
  actor TEXT NOT NULL,
  created_at TEXT NOT NULL,
  CHECK (decision IN ('approve', 'hold', 'reject', 'request_recheck'))
);

CREATE TABLE IF NOT EXISTS audit_events (
  id TEXT PRIMARY KEY,
  run_id TEXT REFERENCES research_runs(id),
  event_type TEXT NOT NULL,
  model_id TEXT,
  input_hash TEXT,
  output_hash TEXT,
  estimated_cost_usd REAL,
  created_at TEXT NOT NULL,
  detail TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_claims_concept ON claims(concept_id);
CREATE INDEX IF NOT EXISTS idx_evidence_claim ON evidence_links(claim_id);
CREATE INDEX IF NOT EXISTS idx_runs_question ON research_runs(question_id);

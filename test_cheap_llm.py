import io
import json
from unittest.mock import patch
import pytest
from cheap_llm import Worker, BudgetExceeded, WorkerError


def response(finish='stop', content='{"claims": []}'):
    return io.BytesIO(json.dumps({'choices': [{'finish_reason': finish,
        'message': {'content': content}}], 'usage': {'prompt_tokens': 100,
        'completion_tokens': 20}}).encode())


def test_cache_and_call_limit(tmp_path, monkeypatch):
    monkeypatch.setenv('LLM_API_KEY', 'test-only')
    worker = Worker(tmp_path / 'cache.db', max_calls=1)
    with patch('cheap_llm.urllib.request.urlopen', return_value=response()) as send:
        assert worker.call('JSON: extract', 'extract') == '{"claims": []}'
        assert worker.call('JSON: extract', 'extract') == '{"claims": []}'
        with pytest.raises(BudgetExceeded):
            worker.call('JSON: another input', 'extract')
        assert send.call_count == 1
    assert worker.cache_hits == 1


@pytest.mark.parametrize('finish,content', [('length', '{}'), ('stop', 'not json'), ('stop', '[]')])
def test_invalid_output_not_cached(tmp_path, monkeypatch, finish, content):
    monkeypatch.setenv('LLM_API_KEY', 'test-only')
    worker = Worker(tmp_path / 'cache.db')
    with patch('cheap_llm.urllib.request.urlopen', return_value=response(finish, content)):
        with pytest.raises(WorkerError):
            worker.call('JSON: extract', 'extract')
    with worker.db() as db:
        assert db.execute('SELECT count(*) FROM cache').fetchone()[0] == 0
    assert worker.errors == 1


def test_budget_before_network(tmp_path, monkeypatch):
    monkeypatch.setenv('LLM_API_KEY', 'test-only')
    worker = Worker(tmp_path / 'cache.db', max_reserved_usd=0)
    with patch('cheap_llm.urllib.request.urlopen') as send:
        with pytest.raises(BudgetExceeded):
            worker.call('JSON: extract', 'extract')
        send.assert_not_called()


def test_no_fallback_or_retry(tmp_path, monkeypatch):
    monkeypatch.setenv('LLM_API_KEY', 'test-only')
    worker = Worker(tmp_path / 'cache.db')
    with patch('cheap_llm.urllib.request.urlopen', side_effect=OSError('secret detail')) as send:
        with pytest.raises(WorkerError, match='no retry or fallback') as error:
            worker.call('JSON: extract', 'extract')
        assert 'secret detail' not in str(error.value)
        assert send.call_count == 1


def test_task_and_limit_are_cache_keys(tmp_path, monkeypatch):
    monkeypatch.setenv('LLM_API_KEY', 'test-only')
    worker = Worker(tmp_path / 'cache.db')
    with patch('cheap_llm.urllib.request.urlopen', side_effect=lambda *a, **k: response()) as send:
        worker.call('JSON: same', 'task1', 128)
        worker.call('JSON: same', 'task2', 128)
        worker.call('JSON: same', 'task2', 256)
        assert send.call_count == 3


def test_source_quote_and_hypothesis_gate():
    from evidence_miner import validate_extracted_claims
    source = 'We hypothesize that a memory module may improve completion.'
    claim = dict(text=source, source_quote=source, claim_type='theoretical',
                 polarity='supports', confidence='hedged', attribution='hypothesis', subjects=[])
    assert validate_extracted_claims([claim], source)[0]['confidence'] == 'speculative'
    assert validate_extracted_claims([{**claim, 'source_quote': 'Invented quote that does not exist.'}], source) == []


def test_refutation_deferred():
    from evidence_miner import validate_extracted_claims
    source = 'No statistically significant association was found.'
    claim = dict(text=source, source_quote=source, claim_type='empirical',
                 polarity='refutes', confidence='strong', attribution='own_result', subjects=[])
    assert validate_extracted_claims([claim], source)[0]['review_required']

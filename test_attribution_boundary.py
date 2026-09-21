from evidence_miner import validate_extracted_claims


def candidate(quote):
    return dict(text='The auction is 15-competitive.', source_quote=quote,
                claim_type='theoretical', polarity='supports', confidence='strong',
                attribution='own_result', subjects=[])


def test_prior_authors_hidden_by_crop_are_deferred():
    source = 'The auction was analyzed by Feige and colleagues, who have shown that it is 15-competitive in the worst case.'
    quote = 'it is 15-competitive in the worst case'
    result = validate_extracted_claims([candidate(quote)], source)[0]
    assert result['review_required']
    assert 'prior_work_attribution_requires_review' in result['review_reasons']


def test_unresolved_method_is_deferred():
    quote = 'this method obtains the stated competitive bound'
    assert validate_extracted_claims([candidate(quote)], quote)[0]['review_required']


def test_prior_sentence_does_not_contaminate_own_result():
    quote = 'We prove that our auction is 4-competitive.'
    source = 'Earlier work was analyzed by other authors. ' + quote
    assert not validate_extracted_claims([candidate(quote)], source)[0].get('review_required')

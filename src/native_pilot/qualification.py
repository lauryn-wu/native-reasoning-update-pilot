"""Join source-preserving human/agent proof reviews into a prospective audit.

A pending earlier candidate cannot be skipped to fill a domain quota. Review
artifacts contain derivations, exact computations, and independent checks;
experimental provider responses are neither accepted nor read by this module.
"""
from __future__ import annotations
import json
from pathlib import Path
from .assets import hydrate_tasks, checked_path
from .data import (ROOT, SELECTION_RULE, SourceBlocked, _read_rows, canonical_hash,
                   select_tasks, verify_sources)
from .grading import qualify_references
from .util import file_digest, utcnow

MATH_FORMAT = ('Solve the stated problem. End with an exact final answer in \\boxed{...}. '
               'Integers, exact rational arithmetic and square roots of nonnegative rational numbers are accepted. '
               'Use sqrt(...) or \\sqrt{...}; do not replace an exact value by a decimal approximation.')


def independent_review_passed(record):
    review=record.get('independent_review')
    if isinstance(review,dict):
        return review.get('status') in ('passed','approved')
    return review in ('passed','approved')


def verify_evidence_descriptors(value, cache, root):
    """Validate every recorded file binding, including proof/run evidence."""
    if isinstance(value,dict):
        if 'path' in value and 'sha256' in value:
            base=cache if str(value['path']).startswith('lcb/') else root
            checked_path(base,value)
        for child in value.values():
            verify_evidence_descriptors(child,cache,root)
    elif isinstance(value,list):
        for child in value:
            verify_evidence_descriptors(child,cache,root)


def assemble_prompts(row, domain):
    """Keep each released field byte-for-byte in an explicit composition."""
    initial, updated = row['revised_problem'], row['original_problem']
    if domain == 'coding':
        for field, variant in [('revised_starter_code','original'),('original_starter_code','updated')]:
            if row.get(field):
                addition='\n\nReleased starter code:\n'+row[field]
                if variant=='original': initial+=addition
                else: updated+=addition
        # Source update carries constraints/examples withheld from the initial
        # statement. Include its exact bytes for the complete fresh target.
        updated+='\n\nReleased correction and supplemental specifications:\n'+row['update']
    return {'original_prompt':initial,'updated_prompt':updated,'correction_prompt':row['update'],
            'released_fields':{k:row[k] for k in ('revised_problem','original_problem','update',
                              'revised_starter_code','original_starter_code') if k in row}}


def assert_ordered_prefix(inventory, reviews, selected_ids, smoke_id):
    """Every earlier candidate must have a resolved, evidence-backed review."""
    for domain in ('math','coding'):
        rows=[r for r in inventory if r['domain']==domain]
        needed=[i for i,r in enumerate(rows) if r['task_id'] in selected_ids or r['task_id']==smoke_id]
        if not needed: continue
        for row in rows[:max(needed)+1]:
            review=reviews.get(row['task_id'])
            if review is None or review.get('status') not in ('qualified','excluded'):
                raise SourceBlocked('Earlier candidate unresolved: '+row['task_id'])
            if review['status']=='excluded' and not review.get('reason'):
                raise SourceBlocked('Exclusion has no documented reason: '+row['task_id'])
            if not independent_review_passed(review):
                raise SourceBlocked('Independent review missing: '+row['task_id'])


def build_qualification_audit(cache, *, root=ROOT):
    source=verify_sources(cache,root/'provenance/source_lock.json')
    if not source['verified']:
        raise SourceBlocked('; '.join(source['blockers']))
    math_rows,code_rows=_read_rows(cache)
    raw={f"{r.get('source','livecodebench')}:{r['id']}":r for r in math_rows+code_rows}
    inventory=json.loads((root/'provenance/review_inventory.json').read_text())['candidates']
    original={r['task_id']:r for r in inventory}
    reviews={}; pool=[]; blockers=[]; counts={}
    review_hashes={}
    for domain in ('math','coding'):
        review_path=root/f'provenance/{domain}_review.json'
        review_hashes[str(review_path.relative_to(root))]=file_digest(review_path)
        document=json.loads(review_path.read_text())
        entries=document.get('candidates',document.get('reviewed_candidates',[]))
        for record in entries:
            tid=record['task_id']; reviews[tid]=dict(record)
            verify_evidence_descriptors(record,cache,root)
            if record['status'] not in ('qualified','reference_verified_pending_grader'):
                continue
            if not independent_review_passed(record):
                blockers.append(tid+': independent review incomplete'); continue
            row=raw[tid]
            if canonical_hash(row)!=original[tid]['source_row_sha256']:
                raise SourceBlocked('Source row changed: '+tid)
            task={**original[tid],**assemble_prompts(row,domain),
                  'qualified':True,'qualification_blockers':[],
                  'qualification_evidence_sha256':canonical_hash(record),
                  'review_rank':record.get('review_rank',record.get('rank_zero_based',-1)+1)}
            if domain=='math':
                task['original']={'answer':record['original_answer']}
                task['updated']={'answer':record['updated_answer']}
                task['output_instructions']=MATH_FORMAT
                validation=qualify_references([task])
                if not validation['passed']:
                    raise SourceBlocked(tid+': exact math grader qualification failed')
                task['reference_qualification']=validation['checks'][tid]
            else:
                task['original']=record['original']; task['updated']=record['updated']
                task['timeout_seconds']=record.get('timeout_seconds',60)
                task['memory_mb']=record.get('memory_mb',768)
                task['output_limit']=record.get('output_limit',4_000_000)
                mode=task['original'].get('mode','stdin')
                task['output_instructions']=('Return exactly one Python 3.12 code block implementing the released starter interface. '
                   'Do not call the method yourself; the evaluator invokes it with positional arguments.' if mode=='function' else
                   'Return exactly one complete Python 3.12 program that reads standard input and writes the requested standard output.')
                hydrate_tasks([task],cache,root=root)
            pool.append(task)
            reviews[tid]['status']='qualified'
        counts[domain]=sum(t['domain']==domain for t in pool)
    audit={'schema_version':2,'at':utcnow(),'status':'qualified','paid_execution_allowed':False,
           'source_lock_sha256':file_digest(root/'provenance/source_lock.json'),
           'selection_rule':SELECTION_RULE,'pair_semantics_verified':True,
           'qualified_counts':counts,'qualified_tasks':pool,'blockers':blockers,
           'review_hashes':review_hashes,'reviewed_candidates':list(reviews.values()),
           'paid_calls_made':0,'selection_uses_experimental_outcomes':False}
    try:
        selection=select_tasks(audit)
        assert_ordered_prefix(inventory,reviews,{r['task_id'] for r in selection['tasks']},selection['smoke_task']['task_id'])
        audit['selected_task_ids']=[r['task_id'] for r in selection['tasks']]
        audit['smoke_task_id']=selection['smoke_task']['task_id']
        audit['control_task_ids']=selection['control_task_ids']
    except SourceBlocked as exc:
        audit['status']='blocked'; audit['blockers'].append(str(exc))
    ordered_counts={}; pending=[]
    for domain in ('math','coding'):
        count=0
        for row in (r for r in inventory if r['domain']==domain):
            review=reviews.get(row['task_id'])
            if not review or review.get('status') not in ('qualified','excluded') or not independent_review_passed(review):
                if count<12:
                    pending.append({'task_id':row['task_id'],'domain':domain,
                                    'reason':(review or {}).get('reason','Not yet reviewed')})
                break
            count+=review['status']=='qualified'
            if count==12:break
        ordered_counts[domain]=count
    audit['ordered_eligible_counts']=ordered_counts
    audit['first_unresolved_by_domain']=pending
    audit['shortfall']={domain:max(0,12-ordered_counts[domain]) for domain in ('math','coding')}
    return audit

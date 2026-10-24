"""No command dispatches a model request without --allow-paid and all gates."""
import argparse
import json
import subprocess
import sys
import tarfile
from pathlib import Path
from .util import atomic_json, digest, file_digest, utcnow
from .manifest import ROOT, freeze, load_manifest, paid_preflight


def show(value):
    print(json.dumps(value, sort_keys=True, indent=2))


def read_json(path):
    return json.loads(Path(path).read_text())


def qualification(manifest, *, docker=False):
    process = subprocess.run([sys.executable,'-m','unittest','discover','-s',str(ROOT/'tests'),'-v'],
                             cwd=ROOT, capture_output=True,text=True)
    result = {'manifest_sha256':manifest['manifest_sha256'], 'at':utcnow(),
              'offline_passed': process.returncode==0, 'test_output': process.stdout+process.stderr,
              'docker_passed':False, 'source_reference_passed':False}
    if docker:
        from .sandbox import qualify_docker
        from .grading import qualify_references
        result['docker'] = qualify_docker()
        result['docker_passed'] = result['docker'].get('passed') is True
        result['source_references'] = qualify_references(manifest['tasks'] + ([manifest['smoke_task']] if manifest.get('smoke_task') else []))
        result['source_reference_passed'] = result['source_references'].get('passed') is True
    else:
        result['docker'] = {'status':'not_run','passed':False}
        result['source_references'] = {'status':'not_run','passed':False}
    return result


def dry_run(manifest):
    from .budget import reservation
    from .provider import build_request
    initials = []
    for task in manifest['tasks']:
        request=build_request(task,'initial',settings=manifest['settings'])
        initials.append({'task_id':task['task_id'],**reservation(request)})
    return {'manifest_sha256':manifest['manifest_sha256'],'status':manifest['status'],
            'blockers':manifest['blockers'],'planned_counts':manifest['planned_counts'],
            'actual_frozen_tasks':len(manifest['tasks']),'assignments':manifest['schedule'],
            'pair_difference':'Only reasoning.context: all_turns versus current_turn; same complete initial checkpoint',
            'initial_reservations':initials,
            'budget':{'hard_total_usd':40,'output_only_max_for_200_usd':65.536,
                      'output_only_max_for_3_smoke_usd':0.98304,
                      'retry_allowance':'At most one transport retry per call; separately reserved',
                      'input_bound':'UTF-8 request bytes + prior output tokens + 4096 + 64 per item',
                      'input_reservation_rate_usd_per_million':5,
                      'cache':'Explicit 30m mode without breakpoints disables caching; reserve worst supported writes anyway',
                      'completion_not_guaranteed':True}}


def report(manifest, ledger_path):
    from .analysis import analyze
    from .budget import Ledger
    from .runner import outcomes_from_ledger
    if ledger_path.exists():
        ledger=Ledger(ledger_path)
        try:
            outcomes=outcomes_from_ledger(ledger,manifest)
            accounting={'total_accounted_usd_all_campaign_versions':ledger.total()/1e6,
                        'attempts_this_manifest':len(ledger.rows(manifest['manifest_sha256'])),
                        'transport_retries_this_manifest':sum(r['attempt']==2 for r in ledger.rows(manifest['manifest_sha256']))}
        finally:
            ledger.close()
    else:
        outcomes=[]
        accounting={'total_accounted_usd_all_campaign_versions':0,'attempts_this_manifest':0,
                    'transport_retries_this_manifest':0}
    return {'manifest_sha256':manifest['manifest_sha256'],'source_blockers':manifest['blockers'],
            'accounting':accounting,'analysis':analyze(manifest,outcomes)}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest',type=Path,default=ROOT/'manifests/pilot-v1.json')
    sub=parser.add_subparsers(dest='command',required=True)
    for name in ('prepare','audit'):
        child=sub.add_parser(name)
        child.add_argument('--cache',type=Path,default=ROOT/'work/source-cache')
    child=sub.add_parser('freeze')
    child.add_argument('--version',required=True)
    child.add_argument('--out',type=Path,required=True)
    child=sub.add_parser('qualify')
    child.add_argument('--docker',action='store_true')
    sub.add_parser('dry-run')
    for name in ('smoke','run'):
        child=sub.add_parser(name)
        child.add_argument('--allow-paid',action='store_true',help='Explicit permission; does not bypass qualification')
    sub.add_parser('report')
    sub.add_parser('archive')
    args=parser.parse_args(argv)
    try:
        if args.command in ('prepare','audit'):
            from .data import prepare_sources, audit_sources
            if args.command=='prepare':
                show(prepare_sources(args.cache))
                return 0
            audit=audit_sources(args.cache)
            atomic_json(ROOT/'work/audit-current.json',audit)
            show({k:v for k,v in audit.items() if k not in ('candidates','review_inventory')})
            return 0  # Successful audit can establish that the design is blocked.
        if args.command=='freeze':
            m=freeze(args.out,args.version)
            show({'manifest':str(args.out),'sha256':m['manifest_sha256'],'status':m['status'],'blockers':m['blockers']})
            return 0
        manifest=load_manifest(args.manifest)
        run_dir=ROOT/'runs'
        qpath=run_dir/f"qualification-{manifest['manifest_sha256']}.json"
        ledger_path=run_dir/'budget.sqlite'
        if args.command=='qualify':
            result=qualification(manifest,docker=args.docker)
            atomic_json(qpath,result)
            show({k:v for k,v in result.items() if k!='test_output'})
            print(result['test_output'],file=sys.stderr)
            return (0 if result['offline_passed'] and (not args.docker or (result['docker_passed'] and result['source_reference_passed']))
                    else 2 if result['offline_passed'] and result['docker_passed'] else 1)
        if args.command=='dry-run':
            show(dry_run(manifest)); return 0
        if args.command in ('smoke','run'):
            if not args.allow_paid:
                raise ValueError('Paid execution requires explicit --allow-paid')
            q=read_json(qpath) if qpath.exists() else {}
            paid_preflight(manifest,q,smoke=args.command=='smoke')
            from .budget import Ledger
            from .runner import campaign_lock, execute, smoke_schedule, outcomes_from_ledger
            from .provider import OpenAIProvider
            with campaign_lock(run_dir/'campaign.lock'):
                ledger=Ledger(ledger_path)
                try:
                    smoke_calls=smoke_schedule(manifest['smoke_task'])
                    if args.command=='run':
                        smoke_outcomes=outcomes_from_ledger(ledger,manifest,smoke_calls)
                        if any(o.get('protocol_valid') is not True for o in smoke_outcomes):
                            raise ValueError('Run/resume the separately labeled three-call protocol smoke first')
                    provider=OpenAIProvider(allow_paid=True)
                    result=execute(manifest,ledger,provider,
                        schedule=smoke_calls if args.command=='smoke' else None,
                        tasks=[manifest['smoke_task']] if args.command=='smoke' else None)
                    atomic_json(run_dir/f"{args.command}-{manifest['manifest_sha256']}.json",result)
                    show({'kind':args.command,'stop_reason':result['stop_reason'],
                          'attempts':result['attempts'],'accounted_usd':result['accounted_usd']})
                finally:
                    ledger.close()
            return 0 if not result['stop_reason'] else 1
        result=report(manifest,ledger_path)
        target=run_dir/f"report-{manifest['manifest_sha256']}.json"
        atomic_json(target,result)
        md=(f"# Pilot analysis\n\nDecision: **{result['analysis']['decision']}**.\n\n"
            f"Frozen tasks: {len(manifest['tasks'])}; planned responses: 200.\n\n"
            f"Accounted spend: ${result['accounting']['total_accounted_usd_all_campaign_versions']:.6f}.\n\n"
            "## Source blockers\n\n" + '\n'.join('- '+b for b in manifest['blockers']) +
            "\n\n## Full results\n\n```json\n"+json.dumps(result,indent=2,sort_keys=True)+"\n```\n")
        (run_dir/'report.md').write_text(md)
        if args.command=='report':
            show(result); return 0
        archive=run_dir/f"review-{manifest['manifest_sha256']}.tar.gz"
        # Explicit allowlist: no raw responses, opaque reasoning, ledger, secrets,
        # source downloads, or paid output archives enter the shareable review.
        paths=[]
        for folder in ('src','tests','docs','provenance','manifests'):
            paths.extend(p for p in (ROOT/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts)
        paths += [ROOT/'README.md',ROOT/'pyproject.toml',ROOT/'.gitignore',target,run_dir/'report.md']
        if qpath.exists():
            paths.append(qpath)
        with tarfile.open(archive,'w:gz') as bundle:
            for path in sorted(paths):
                bundle.add(path,arcname=path.relative_to(ROOT),recursive=False)
        show({'archive':str(archive),'sha256':file_digest(archive),'contains_private_reasoning':False})
        return 0
    except (ValueError,FileNotFoundError,RuntimeError) as exc:
        print(f'Blocked: {exc}',file=sys.stderr)
        return 2

if __name__=='__main__':
    raise SystemExit(main())

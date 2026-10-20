"""Verify and consolidate two HF caches on the same /workspace filesystem. CPU only."""
import argparse,hashlib,json,os,re,shutil,time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed


def digest(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def verify_pair(source,target):
    left=digest(source);right=digest(target)
    if left!=right:raise ValueError("Cache copies differ in file content")
    return right


def active_users(paths):
    current=os.getpid();result=[]
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit() or int(proc.name)==current:continue
        try:
            cmd=(proc/'cmdline').read_bytes().replace(bytes([0]),b' ').decode(errors='replace')
            if any(n in cmd for n in ('runpod_factory_sample.py','control_pipeline.py','compare_factory_sample.py','benchmark_performance.py')):
                result.append(int(proc.name));continue
            for fd in (proc/'fd').iterdir():
                try:target=os.readlink(fd)
                except OSError:continue
                if any(target.startswith(str(p)+'/') for p in paths):result.append(int(proc.name));break
        except (OSError,PermissionError):continue
    return sorted(set(result))


def consolidate(source,target,report,apply=False):
    source=Path(source);target=Path(target);report=Path(report)
    if os.name!='posix':raise ValueError('Use the Linux Pod for cache consolidation')
    workspace=Path('/workspace').resolve()
    if source.is_symlink():
        if source.resolve()==target.resolve():return {'status':'ALREADY_CONSOLIDATED','source':str(source),'target':str(target)}
        raise ValueError('Source is already a different symlink')
    source=source.resolve(strict=True);target=target.resolve(strict=True)
    for p in (source,target):
        if not p.is_relative_to(workspace) or p==workspace:raise ValueError('Cache paths must stay inside /workspace')
    if source==target or source.is_relative_to(target) or target.is_relative_to(source):raise ValueError('Cache paths overlap')
    if source.stat().st_dev!=target.stat().st_dev:raise ValueError('Expected both caches on the same volume')
    if not (source/'hub').is_dir() or not (target/'hub').is_dir():raise ValueError('Expected HF cache roots')
    if active_users((source,target)):raise ValueError('A process is using a cache; stop it before consolidation')
    # Check every source snapshot name and target against the retained cache.
    snapshots=list((source/'hub').glob('models--*/snapshots/*'))
    if not snapshots:raise ValueError('No source snapshots')
    blobs={};snapshot_files=0
    for snapshot in snapshots:
        counterpart=target/snapshot.relative_to(source)
        if not counterpart.is_dir():raise ValueError('Retained cache lacks a snapshot')
        index=snapshot/'model.safetensors.index.json'
        if index.exists():
            for name in set(json.loads(index.read_text())['weight_map'].values()):
                if not (snapshot/name).is_file() or not (counterpart/name).is_file():raise ValueError('Missing model shard')
        for item in snapshot.rglob('*'):
            if item.is_dir():continue
            other=target/item.relative_to(source)
            if not item.is_file() or not other.is_file():raise ValueError('Broken or missing snapshot file')
            if item.stat().st_size!=other.stat().st_size:raise ValueError('Snapshot file sizes differ')
            real=other.resolve(strict=True)
            if not real.is_relative_to(target):raise ValueError('Retained snapshot points outside the retained cache')
            if re.fullmatch('[0-9a-f]{64}',real.name):blobs[real]=item.resolve(strict=True)
            elif digest(item)!=digest(other):raise ValueError('Snapshot metadata differs')
            snapshot_files+=1
    state={'status':'PLANNED','source':str(source),'target':str(target),'snapshot_files':snapshot_files,'blob_files':len(blobs),'verified_blobs':0,'apply':apply}
    report.parent.mkdir(parents=True,exist_ok=True)
    def save():
        temp=report.with_suffix('.tmp');temp.write_text(json.dumps(state,indent=2));os.replace(temp,report)
    save()
    if not apply:return state
    before=shutil.disk_usage(workspace).free
    try:
        state['status']='VERIFYING';save()
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures={pool.submit(verify_pair,source_file,target_file):target_file for target_file,source_file in blobs.items()}
            for future in as_completed(futures):
                path=futures[future]
                verified_sha=future.result()
                state.setdefault('verified_sha256',{})[str(path.relative_to(target))]=verified_sha
                state['verified_blobs']+=1;save()
        if active_users((source,target)):raise ValueError('A cache user appeared during verification')
        state['status']='MERGING';save()
        conflicts=report.parent/'metadata_conflicts';moved=duplicates=0
        # No source data is removed until the retained counterpart is present and verified.
        for item in sorted(source.rglob('*')):
            if item.is_dir() and not item.is_symlink():continue
            relative=item.relative_to(source);other=target/relative
            if item.is_symlink():
                if not other.exists():raise ValueError('Unexpected source-only symlink')
                continue
            if not other.exists():
                other.parent.mkdir(parents=True,exist_ok=True);os.replace(item,other);moved+=1;continue
            if item.stat().st_size==other.stat().st_size:
                if other.resolve() in blobs:duplicates+=1;continue
                if digest(item)==digest(other):duplicates+=1;continue
            # Preserve differing small metadata/logs; never discard an unverified large file.
            if item.stat().st_size>16*1024**2:raise ValueError('Unverified non-matching large cache file')
            backup=conflicts/relative;backup.parent.mkdir(parents=True,exist_ok=True);os.replace(item,backup)
        old=source.with_name(source.name+'.before_consolidation')
        if old.exists() or old.is_symlink():raise ValueError('Previous backup path exists')
        source.rename(old)
        try:
            source.symlink_to(target,target_is_directory=True)
            for snapshot in snapshots:
                now=source/snapshot.relative_to(source)
                for item in now.rglob('*'):
                    if item.is_symlink() and not item.exists():raise ValueError('Consolidated snapshot has a broken link')
            # Also validate the original index and all listed shards via the original path.
            for index in source.glob('hub/models--*/snapshots/*/model.safetensors.index.json'):
                for name in set(json.loads(index.read_text())['weight_map'].values()):
                    if not (index.parent/name).is_file():raise ValueError('Consolidated model shard is missing')
        except Exception:
            if source.is_symlink():source.unlink()
            old.rename(source);raise
        if old.resolve()!=old or old.parent!=source.parent:raise ValueError('Unexpected removal target')
        shutil.rmtree(old)
        state.update(status='COMPLETE',duplicate_files=duplicates,unique_files_moved=moved,
                     freed_bytes=shutil.disk_usage(workspace).free-before,
                     free_bytes=shutil.disk_usage(workspace).free,source_is_alias=source.is_symlink())
        save();return state
    except Exception as exc:
        state.update(status='FAILED',error_type=type(exc).__name__,error=str(exc));save();raise


def main():
    p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--target',required=True);p.add_argument('--report',required=True);p.add_argument('--apply',action='store_true');a=p.parse_args()
    print(json.dumps(consolidate(a.source,a.target,a.report,a.apply)))
if __name__=='__main__':main()

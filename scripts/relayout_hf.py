"""Move a dataset on the Hugging Face Hub from table-first to company-first layout.

    HF_TOKEN=... python scripts/relayout_hf.py owner/dataset [--public]

    <table>/<company>/<file>.parquet  ->  <company>/<table>/<file>.parquet
    <table>/<file>.parquet            ->  shared/<file>.parquet

Files are copied server-side (nothing is downloaded), then the old paths are deleted, in
batches of commits. The dataset card is replaced with dataset_card/README.md. With
--public, the dataset is made public at the end.
"""

import os
import sys
import time

from huggingface_hub import CommitOperationAdd, CommitOperationCopy, CommitOperationDelete, HfApi

repo = sys.argv[1]
make_public = "--public" in sys.argv
api = HfApi(token=os.environ["HF_TOKEN"])
files = api.list_repo_files(repo, repo_type="dataset")
existing = set(files)
moves = []
for path in files:
    parts = path.split("/")
    if not path.endswith(".parquet") or parts[0] == "shared":
        continue
    if len(parts) == 3:
        table, company, name = parts
        new = f"{company}/{table}/{name}"
    elif len(parts) == 2:
        new = f"shared/{parts[1]}"
    else:
        continue
    moves.append((path, new))
print(f"{len(files)} files in the repo, {len(moves)} to move")


def commit(ops, message):
    for attempt in range(6):
        try:
            api.create_commit(repo, repo_type="dataset", operations=ops, commit_message=message)
            return
        except Exception as exc:
            wait = 20 * (attempt + 1)
            print(f"commit failed ({exc}); retrying in {wait}s")
            time.sleep(wait)
    sys.exit("giving up")


batch = 400
for i in range(0, len(moves), batch):
    chunk = moves[i:i + batch]
    ops = [CommitOperationCopy(src_path_in_repo=old, path_in_repo=new) for old, new in chunk if new not in existing]
    ops += [CommitOperationDelete(path_in_repo=old) for old, _ in chunk]
    commit(ops, f"Company-first layout ({i + len(chunk)}/{len(moves)})")
    print(f"moved {i + len(chunk)}/{len(moves)}")

commit([CommitOperationAdd(path_in_repo="README.md", path_or_fileobj="dataset_card/README.md")],
       "Dataset card: company-first layout, CC BY 4.0")
print("dataset card updated")

if make_public:
    try:
        api.update_repo_settings(repo, private=False, repo_type="dataset")
    except AttributeError:
        api.update_repo_visibility(repo, private=False, repo_type="dataset")
    print("dataset is now public")

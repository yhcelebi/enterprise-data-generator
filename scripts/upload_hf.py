"""Upload a generated output folder to a Hugging Face dataset repository.

    HF_TOKEN=... python scripts/upload_hf.py OUT_DIR owner/dataset-name [--private]

Many jobs upload to the same repository in parallel; each commit only adds its own
files, and conflicting commits are retried.
"""

import os
import sys
import time

from huggingface_hub import HfApi

folder, repo = sys.argv[1], sys.argv[2]
private = "--private" in sys.argv
api = HfApi(token=os.environ["HF_TOKEN"])
api.create_repo(repo, repo_type="dataset", private=private, exist_ok=True)
for attempt in range(8):
    try:
        api.upload_folder(folder_path=folder, repo_id=repo, repo_type="dataset",
                          commit_message=f"Add {os.path.basename(os.path.normpath(folder))} "
                                         f"({os.environ.get('GITHUB_JOB', 'local')})")
        print("uploaded", folder)
        break
    except Exception as exc:  # concurrent commits occasionally conflict; back off and retry
        wait = 15 * (attempt + 1)
        print(f"upload failed ({exc}); retrying in {wait}s")
        time.sleep(wait)
else:
    sys.exit("upload failed after retries")

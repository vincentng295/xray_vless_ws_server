import os
import shutil
from git import Repo

def upload_file(token, repo, file, branch, rename = None, tempdir = "__tmp__"):
    # Create a temporary directory for the branch
    repo_dir = f'./{tempdir}/{repo}'
    branch_dir = os.path.join(repo_dir, branch)
    
    # Clone the repo into a new folder if it doesn't exist
    if not os.path.exists(repo_dir):
        os.makedirs(repo_dir)
        repo_instance = Repo.clone_from(f'https://github-actions:{token}@github.com/{repo}.git', repo_dir)
    else:
        # If it exists, use the existing directory
        print(f"Directory {repo_dir} exists, using it for the repository.")
        repo_instance = Repo(repo_dir)
    origin = repo_instance.remote(name="origin")
    origin.fetch()

    # Fetch all remote branches to make sure we have the latest refs
    repo_instance.git.fetch('--all')

    try:
        origin.pull(branch)
    except Exception:
        pass

    # Check if the branch exists locally, if not, check it out from the remote
    try:
        if branch not in [b.name for b in repo_instance.branches]:
            print(f"Branch {branch} does not exist locally. Checking it out from remote.")
            # Check out the remote branch (this will create a local tracking branch)
            repo_instance.git.checkout(f'origin/{branch}', b=branch)
            origin.pull(branch)
    except Exception:
        pass

    if branch not in repo_instance.branches:
        print(f"Branch {branch} does not exist. Creating an orphan branch.")
        repo_instance.git.checkout('--orphan', branch)
        repo_instance.git.reset('--hard')

        # Make an empty commit so that the branch is recognized by git
        repo_instance.index.commit("Initial empty commit on orphan branch")
        
        # Push the new branch to the remote repository
        origin = repo_instance.remote(name='origin')
        origin.push(branch)
        print(f"Branch {branch} created and pushed to remote repository.")

    # Checkout the target branch
    repo_instance.git.checkout(branch)

    # Copy the file directly to the root of the branch
    if rename == None:
        rename = os.path.basename(file)
        dest = os.path.join(repo_dir, rename)
    else:
        rename = rename.lstrip("/")
        dest = os.path.join(repo_dir, rename)
        dir_of_dest = os.path.dirname(dest)
        if not os.path.exists(dir_of_dest):
            os.makedirs(dir_of_dest)

    if os.path.isdir(file):
        if os.path.exists(dest):
            shutil.rmtree(dest)
        shutil.copytree(file, dest)
    else:
        shutil.copy(file, dest)

    # Stage the file for commit
    repo_instance.git.add(rename)

   # Commit the file
    repo_instance.index.commit(f"Add {file} to {branch} branch")

    # Force push the changes (to overwrite any conflicting changes in the remote branch)
    origin = repo_instance.remote(name='origin')
    origin.push(branch, force=True)  # Force push the branch to the remote repository

    full_sha = repo_instance.head.object.hexsha

    if branch.startswith("hidden/"):
        origin.push(branch, delete=True)
        print(f"Branch {branch} deleted from remote repository.")

    return full_sha
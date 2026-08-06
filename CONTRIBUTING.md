# Starting a project and collaborating

This repository contains the workflow code, documentation, tests, and small
command scripts. Keep experimental inputs and generated results outside Git:
do not commit `.ims` movies, TIFFs, ROI masks, CSVs, MP4s, scratch folders, or
external-drive paths.

## Start an independent calcium-imaging project

### Option A: fork and clone from the command line

This creates a fork under the signed-in user's GitHub account, clones it, and
adds the original workflow repository as a remote for future updates:

```bash
brew install gh                        # install GitHub CLI on macOS, once
gh auth login                          # sign in, once per computer
gh repo fork ecresp1el/organoid_calcium_imaging_workflow --clone --remote
cd organoid_calcium_imaging_workflow
conda env create --file environment.yml
conda activate organoid-calcium-workflow
```

If `brew` is also not found, install Homebrew first or download the macOS
GitHub CLI installer from <https://cli.github.com/>, then start again at
`gh auth login`. Your fork has its own GitHub history and can later receive
workflow updates through a pull request or from the original remote.

### Option B: create a separate repository from a local copy

Use this if the new project should not remain a fork. Create an empty GitHub
repository first, then run:

```bash
git clone https://github.com/ecresp1el/organoid_calcium_imaging_workflow.git my-calcium-project
cd my-calcium-project
git remote rename origin upstream
git remote add origin https://github.com/YOUR-ACCOUNT/YOUR-NEW-REPOSITORY.git
git push -u origin main
```

`origin` is now the new project's repository; `upstream` remains a read-only
reference to this workflow repository.

## Contribute a change to this repository

Work on a branch, never directly on `main`:

```bash
git checkout main
git pull --ff-only origin main
git switch -c short-description-of-change

# Edit code or documentation, then run the relevant tests.
PYTHONPATH=src conda run --no-capture-output -n organoid-calcium-workflow pytest -q

git status
git add README.md src/ tests/                 # replace with only the files you intend
git commit -m "Describe the change"
git push -u origin short-description-of-change
```

Open a pull request from that branch on GitHub. A collaborator without direct
write access should fork first, make the branch in their fork, then open a pull
request back to this repository.

Before every commit, inspect `git status` and verify that only code,
documentation, tests, and intentionally versioned small scripts are staged.
The source-only and scratch-folder workflow described in
[README_WALKTHROUGH.md](README_WALKTHROUGH.md) still applies to every project.

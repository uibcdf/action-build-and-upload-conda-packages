# action-conda-deployment-with-new-tag
[![Open Source Love](https://badges.frapsoft.com/os/v2/open-source.svg?v=103)](https://github.com/ellerbrock/open-source-badges/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

The sphinx documentation in a repository is automatically compiled as 'html' and deployed, by means
of the 'gh-pages' branch, with this GitHub Action. The user has only to be sure that the repository
accomplishes [a couple of requirements](#Requirements).

In summary, this GitHub action does the following:

- Takes the author and SHA id of the trigger action ('push' or 'pull request') to be consistent
  along the action.
- Creates a new 'gh-pages' branch if this is not already in the repository.
- Compiles the sphinx documentation in the directory and branch specified by the user.
- Pushes the output html documentation to the 'gh-pages' branch.

This GitHub Action was developed by [the Computational Biology and Drug Design Research Unit -UIBCDF- at the
Mexico City Children's Hospital Federico Gómez](https://www.uibcdf.org/). Other GitHub Actions can
be found at [the UIBCDF GitHub site](https://github.com/search?q=topic%3Agithub-actions+org%3Auibcdf&type=Repositories).

## Requirements

## How to use it

To include this GitHub Action, put a Yaml file (named 'sphinx\_docs\_to\_gh\_pages.yaml', for instance) with the following content in the
directory '.github/workflows' of your repository:

```yaml
name: Sphinx docs to gh-pages

on:
  push:
    branches: [ main ]
  pull_request:
    branches: [ main ]

  workflow_dispatch:

jobs:
  sphinx_docs_to_gh-pages:
    runs-on: ubuntu-latest
    name: Sphinx docs to gh-pages
    steps:
      - uses: actions/checkout@v2
      - name: Make conda environment
        uses: conda-incubator/setup-miniconda@v2
        with:
          environment-file: devtools/conda-envs/docs_env.yaml    # Path to the documentation conda environment
          activate-environment: docs
          auto-update-conda: false
          auto-activate-base: false
          show-channel-urls: true
      - name: Running the Sphinx to gh-pages Action
        uses: uibcdf/action-sphinx-docs-to-gh-pages@v1.0-beta.1
          with:
            branch: main
            dir_docs: docs
            sphinxopts: ''
```

Two things need to be known to run the GitHub Actions without further work: the meaning of the input parameters
and the yaml file to make a temporary conda environment where the sphinx documentation can
be compiled.

### Input parameters

These are the input parameters of the action:

| Input parameters | Description | Default value | 
| ---------------- | ------------------------------------------- | ------------------------------------------------------ |
| branch | Name of the branch where the sphinx documentation is located | 'main' |
| dir\_docs | Path where the sphinx documentation is located | 'docs' |
| sphinxopts | Compilation options for sphinx-build | '' |

They are placed in the last three lines of the above workflow example file:

```yaml
      - name: Running the Sphinx to gh-pages Action
        uses: uibcdf/action-sphinx-docs-to-gh-pages@v1.0-beta.1
          with:
            branch: main
            dir_docs: docs
            sphinxopts: ''
```

In case your sphinx documentation is placed in a directory named 'docs' in the 'main' branch to be
compiled with no further options, you can do without the section `with:`.

### Deployment conda environment

Your library will need specific libraries and packages to be deployed. They can be
specified in a conda environment file. This way, a temporary enviroment can be made and activated
to compile the conda package and upload it to your conda channel with all dependencies satisfied. Write a file in the repository with
the following content:

```yaml
name: deploy

channels:

  - conda-forge
  - defaults

dependencies:

  # Write here all dependencies to compile the conda package.
  # This list is just an example
  - python=3.7
```

And replace the value of the workflow input parameter `environment-file:` with the right path to your deployment conda enviroment file. In
the case of [the above example](#How-to-use-it) ('devtools/conda-envs/deploy\_env.yaml'):

```yaml
jobs:
  sphinx_docs_to_gh-pages:
    steps:
      - name: Make conda environment
        uses: conda-incubator/setup-miniconda@v2
        with:
          # Replace with the path to your documentation conda enviroment file
          environment-file: devtools/conda-envs/deploy_env.yaml
```

## Other tools like this one

This GitHub Action was developed to solve a need of the [UIBCDF]((https://www.uibcdf.org/)). And to be used, additionally, as example of
house-made GitHub Action for researchers and students in this lab.

Other tools you can find in the market doing these same tasks are mentioned below. We recognize and
thank the work of their developers. Many of those GitHub Actions were used by us to learn how to set up our own one.

If you think that your GitHub Action should be mentioned here, fell free to PR with a new line.

### Automatic Conda deployment
https://github.com/fdiblen/anaconda-action   
https://github.com/MichaelsJP/conda-package-publish-action    
https://github.com/Jegp/conda-package-publish-action    
https://github.com/amauryval/publish_conda_package_action    
https://github.com/elbeejay/conda-publish-action    
https://github.com/maxibor/conda-package-publish-action    
https://github.com/m0nhawk/conda-package-publish-action    
https://github.com/fcakyon/conda-publish-action    



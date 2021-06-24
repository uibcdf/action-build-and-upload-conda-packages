# build-and-upload-conda-packages
[![Open Source Love](https://badges.frapsoft.com/os/v2/open-source.svg?v=103)](https://github.com/ellerbrock/open-source-badges/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

If a repository contains a meta.yaml file to build conda packages, the process of building and
uploading packages to an Anaconda user or channel is automatized by this GitHub Action. The user has only to be sure that the repository
accomplishes [a couple of requirements](#Requirements).

In summary, this GitHub action does the following:

- Checks if the meta.yaml file exists in the directory specified by the user.
- Compiles the list of packages to the platform and Python version specified by the user, in the
  branch also specified by the user.
- Uploads all packages built to the Anaconda user or channel specified by the user, with the label
  specified by the user.

This GitHub Action was developed by [the Computational Biology and Drug Design Research Unit -UIBCDF- at the
Mexico City Children's Hospital Federico Gómez](https://www.uibcdf.org/). Other GitHub Actions can
be found at [the UIBCDF GitHub site](https://github.com/search?q=topic%3Agithub-actions+org%3Auibcdf&type=Repositories).

## Requirements

### Anaconda token as GitHub secret



## How to use it

To include this GitHub Action, put a Yaml file (named 'build\_and\_upload\_conda\_packages.yaml', for instance) with the following content in the
directory '.github/workflows' of your repository:

```yaml

name: Build and upload conda packages

on:
  release:
    types: ['released', 'prereleased']

jobs:
  conda_deployment_with_new_tag:
    name: Conda deployment of package to platform ${{ matrix.platform }} with Python ${{ matrix.python-version }}
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: [3.7, 3.8, 3.9]
    steps:
      - uses: actions/checkout@v2
      - name: Conda environment creation and activation
        uses: conda-incubator/setup-miniconda@v2
        with:
          activate-environment: deployment
          python-version: ${{ matrix.python-version }}
          channels: conda-forge, default
          auto-activate-base: false
          auto-update-conda: false
          show-channel-urls: true
      - name: Installing tools and dependencies in environment to build and upload conda packages
        shell: bash -l {0}
        run: |
          conda install -y anaconda-client conda-build
      - name: Build and upload the conda packages
        uses: uibcdf/action-build-and-upload-conda-packages@0.0.1-beta.1
        with:
          branch: main
          meta_yaml_dir: devtools/conda-build
          python-version: ${{ matrix.python-version }}
          platform_linux-64: true
          platform_osx-64: true
          platform_win-64: true
          channel: uibcdf
          label: dev
          token: ${{ secrets.ANACONDA_TOKEN}}
```


Three things need to be known to run the GitHub Actions without further work: the meaning of the input parameters, the meta.yaml file with instructions to compile the packages -and how to work with it-, and how to include an Anaconda token to upload packages to your Anaconda user, organization or channel without login username and password.

### Input parameters

These are the input parameters of the action:

| Input parameters | Description | Required | Default value | 
| ---------------- | ----------- | -------- | ------------- |
| branch | Name of the branch with the code to be built as conda packages | No | 'main' |
| meta_yaml_dir | Path to the directory where the meta.yaml file with building instructions is located  | Yes |  |
| python-version | Python version of the packages to build  | Yes |  |
| platform_all | Build packages for all supported platforms  | No | False |
| platform_linux-64 | Build a package for the platform: linux-64 | No | False |
| platform\_linux-32 | Build a package for the platform: linux-32 | No | False |
| platform\_osx-64 | Build a package for the platform: osx-64 | No | False |
| platform\_arm-64 | Build a package for the platform: arm-64 | No | False |
| platform\_linux-ppc64 | Build a package for the platform: linux-ppc64 | No | False |
| platform\_linux-ppc64le | Build a package for the platform: linux-ppc64le | No | False |
| platform\_linux-s390x | Build a package for the platform: linux-s390x | No | False |
| platform\_linux-armv6l | Build a package for the platform: linux-armv6l | No | False |
| platform\_linux-armv7l | Build a package for the platform: linux-armv7l | No | False |
| platform\_linux-aarch64 | Build a package for the platform: linux-aarch64 | No | False |
| platform\_win-32 | Build a package for the platform: linux-win-32 | No | False |
| platform\_win-64 | Build a package for the platform: linux-win-64 | No | False |
| user\_channel | User, organization or channel name where the packages will be uploaded | True |  |
| label | Name of the label to upload the package ('main', 'dev', ...). If the value is equal to 'auto', the action will automatically label releases as 'main' and prereleases as 'dev' | True | auto |
| token | Anaconda token to authorize the uploading (more info [here]()) | Yes |  |

They are placed in the `with:` subsection of the step named `Build and upload the conda packages` of the above workflow example file:

```yaml
      - name: Build and upload the conda packages
        uses: uibcdf/action-build-and-upload-conda-packages@0.0.1-beta.1
        with:
          branch: main
          meta_yaml_dir: devtools/conda-build
          python-version: ${{ matrix.python-version }}
          platform_linux-64: true
          platform_osx-64: true
          platform_win-64: true
          channel: uibcdf
          label: dev
          token: ${{ secrets.ANACONDA_TOKEN}}
```

There are two special input parameters: `token` and `python_version`.

#### `token`

#### `python_version`

    strategy:
      matrix:
        python-version: [3.7, 3.8, 3.9]

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



#!/usr/bin/env bash
set -euo pipefail

"$PYTHON" -c "import os, pathlib; pathlib.Path(os.environ['SP_DIR'], 'action_multiple_variants_fixture.py').write_text('__version__ = \\\"0.1.0\\\"')"

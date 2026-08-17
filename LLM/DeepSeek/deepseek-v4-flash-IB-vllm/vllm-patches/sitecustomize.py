# Debian images load /usr/lib/python3.12/sitecustomize.py first, so the
# copy in dist-packages is ignored. This file is also mounted over that
# stdlib path. Keep import-light.
import long_ctx_defaults  # noqa: F401

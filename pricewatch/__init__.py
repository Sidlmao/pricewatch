import warnings
warnings.filterwarnings("ignore", message="urllib3 v2 only supports OpenSSL")
from . import config  # noqa: E402,F401  (loads .env before db/fetch read the environment)
